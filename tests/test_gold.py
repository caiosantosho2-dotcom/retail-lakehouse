"""Testes da gold (base comum, features, modelos e métricas) sobre uma silver sintética (tests/gold_sintetico.py).

A igualdade com o RAG e com o painel publicado é provada pelas conferências sobre os dados reais
(docs/validacao/fase3a_gold.md e fase3b_gold.md), não aqui: estes testes cobrem a parte mecânica (janela, definições,
macros, grão e colunas, semente, controle).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pyarrow as pa
import pytest
import yaml
from deltalake import DeltaTable, write_deltalake

from src.comum import RAIZ, caminho_tabela, carregar_config, registrar_delta
from src.gold import build
from src.gold.modelos import parametros
from tests.gold_sintetico import gerar

_spec = importlib.util.spec_from_file_location("espiar", RAIZ / "scripts" / "espiar.py")
espiar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(espiar)

MODELOS = ["customer_segment", "rfm_k_evaluation", "rfm_segment_profile", "churn_score", "churn_test_score",
           "churn_classifier", "churn_roc", "clv_segment", "discount_test_pair", "discount_test_segment", "model_summary"]
FEATURES = ["customer_rfm_features", "churn_features", "clv_features"]
METRICAS = [n for n, tipo in build.METRICAS if tipo in ("tabela", "por_periodo_departamento", "layout")]
TABELAS = [f"features/{t}" for t in FEATURES] + [f"models/{t}" for t in MODELOS]
TODAS = TABELAS + [f"metrics/{t}" for t in METRICAS]
SEGMENTOS = {"Fiéis", "Regulares", "Esporádicos", "Em pausa"}


def montar_config(pasta: Path) -> Path:
    """Config com a seção gold real (config.example.yaml) e o lake em `pasta`."""
    real = yaml.safe_load((RAIZ / "config.example.yaml").read_text(encoding="utf-8"))
    real["paths"] = {"raw": "raw", "lake": "lake"}
    real["duckdb"] = {"memory_limit": "256MB", "threads": 1}
    caminho = pasta / "config.yaml"
    caminho.write_text(yaml.safe_dump(real, allow_unicode=True), encoding="utf-8")
    return caminho


@pytest.fixture(scope="module")
def pronto(tmp_path_factory) -> tuple[Path, dict]:
    """Silver sintética + gold construída DUAS vezes: num processo só e pela linha de comando (um processo por etapa,
    G33). As duas versões iguais provam a idempotência e que separar os processos não muda o resultado."""
    pasta = tmp_path_factory.mktemp("gold")
    config = montar_config(pasta)
    perfil = gerar(pasta / "lake")
    cfg = carregar_config(config)
    assert build.executar(cfg) == 0
    assert build.main(["--config", str(config)]) == 0
    return config, perfil


@pytest.fixture
def cfg(pronto) -> dict:
    return carregar_config(pronto[0])


@pytest.fixture
def con(cfg):
    c = build.preparar_conexao(cfg)
    build.configurar_metricas(c, cfg)
    for t in TODAS:
        registrar_delta(c, t.split("/")[1], caminho_tabela(cfg, "gold", t))
    yield c
    c.close()


def um(con, sql):
    return con.sql(sql).fetchall()[0]


def resumo(con, modelo: str, chave: str):
    return json.loads(um(con, f"SELECT value FROM model_summary WHERE model = '{modelo}' AND key = '{chave}'")[0])


# ---------------------------------------------------------------- base comum

def test_janela_termina_na_ultima_semana_completa(con):
    # a semana 102 tem 3 dias: a janela vai até a 101; ano anterior = mesmas semanas - 52
    assert um(con, "SELECT week_start_current, week_end_current, week_start_prior, week_end_prior FROM analysis_window") \
        == (76, 101, 24, 49)


def test_semana_incompleta_no_fim_recua_a_janela(tmp_path):
    lake = tmp_path / "lake"
    gerar(lake)
    # a semana 101 perde um dia: a última completa passa a ser a 100
    dt = DeltaTable(str(lake / "silver/context/shared/dim_date")).to_pyarrow_table().to_pylist()
    for r in dt:
        if r["week_no"] == 101:
            r["days_in_week"], r["is_complete_week"] = 6, False
    write_deltalake(str(lake / "silver/context/shared/dim_date"), pa.Table.from_pylist(dt), mode="overwrite")
    cfg = carregar_config(montar_config(tmp_path))
    c = build.preparar_conexao(cfg)
    assert um(c, "SELECT week_end_current, week_start_current, week_end_prior FROM analysis_window") == (100, 75, 48)
    # os períodos do painel recuam junto
    build.configurar_metricas(c, cfg)
    c.execute(f"CREATE TEMP TABLE dim_period AS {build._sql_metrica('dim_period')}")
    assert {r for r in c.execute("SELECT period, week_start, week_end FROM dim_period").fetchall()} == \
        {("4s", 97, 100), ("13s", 88, 100), ("26s", 75, 100), ("base", 1, 100)}


def test_sales_item_so_mercadoria_ate_o_fim_e_desconto_positivo(con):
    esperado = um(con, """SELECT count(*), sum(sales_value), -sum(retail_disc + coupon_disc + coupon_match_disc)
                          FROM fact_sales WHERE is_merchandise AND week_no <= 101""")
    assert um(con, "SELECT count(*), sum(revenue), sum(discount) FROM sales_item") == esperado
    assert um(con, "SELECT count(*) FROM sales_item WHERE gross_value <> revenue + discount OR discount < 0") == (0,)
    assert um(con, "SELECT max(week_no) FROM sales_item") == (101,)


def test_customer_metrics_por_outro_caminho(con):
    # frequência = cestas distintas de mercadoria na janela; recência = dias da última compra até o fim da janela
    h = um(con, "SELECT household_key FROM customer_metrics WHERE period = 'current' ORDER BY household_key LIMIT 1")[0]
    cestas, ultima, fat = um(con, f"""SELECT count(DISTINCT f.basket_id), max(d.date), sum(f.sales_value)
        FROM fact_sales f JOIN dim_date d USING (day)
        WHERE f.household_key = {h} AND f.is_merchandise AND f.week_no BETWEEN 76 AND 101""")
    fim = um(con, "SELECT max(date) FROM dim_date WHERE week_no = 101")[0]
    m = um(con, f"SELECT frequency, recency_days, revenue FROM customer_metrics WHERE household_key = {h} AND period = 'current'")
    assert m == (cestas, (fim - ultima).days, fat)


def test_household_sem_membro_desconhecido(con, pronto):
    assert um(con, "SELECT count(*), min(household_key) FROM household") == (len(pronto[1]), 1)


def test_parametros_vem_da_secao_gold(cfg):
    parametros.configurar(cfg)
    assert parametros.CFG["semente"] == cfg["gold"]["semente"]
    assert parametros.CFG["analises"]["churn"] == cfg["gold"]["modelos"]["churn"]
    assert parametros.CFG["metricas"]["cliente_ativo_semanas"] == 8
    assert parametros.MEMO == {}


# ---------------------------------------------------------------- modelos

def test_todas_as_tabelas_dos_modelos_gravadas(cfg):
    for t in TABELAS:
        assert DeltaTable(str(caminho_tabela(cfg, "gold", t))).to_pyarrow_table().num_rows > 0, t


# ---------------------------------------------------------------- features (G12)

def test_features_do_rfm_sao_a_entrada_do_kmeans(con):
    n, segmentados = um(con, "SELECT count(*), (SELECT count(*) FROM customer_segment) FROM customer_rfm_features")
    assert n == segmentados
    assert um(con, "SELECT count(*) FROM customer_rfm_features WHERE monetary <= 0 OR week_start <> 76 OR week_end <> 101")[0] == 0
    # G21: variável = valor original; o log1p e a padronização são do modelo e não são gravados
    colunas = {c[0] for c in con.execute("DESCRIBE customer_rfm_features").fetchall()}
    assert not {c for c in colunas if c.startswith(("z_", "log1p_"))}
    seg = um(con, """SELECT count(*) FROM customer_rfm_features f JOIN customer_segment s USING (household_key)
                     WHERE f.monetary = s.monetary AND f.frequency = s.frequency AND f.recency_days = s.recency_days""")[0]
    assert seg == n


def test_features_do_churn_por_foto(con):
    papeis = dict(con.sql("SELECT role, count(DISTINCT snapshot_week) FROM churn_features GROUP BY 1").fetchall())
    assert papeis == {"treino": 10, "validacao": 1, "teste": 2, "final": 1}
    # rótulo em todas as fotos, menos na final (é o futuro)
    assert um(con, "SELECT count(*) FILTER (WHERE (label IS NULL) <> (role = 'final')) FROM churn_features")[0] == 0
    assert um(con, "SELECT count(*) FROM churn_features WHERE role = 'final'")[0] == um(con, "SELECT count(*) FROM churn_score")[0]
    # as variáveis do teste são as que geraram as notas: recência = nota da regra simples, rótulo igual
    n, iguais = um(con, """SELECT count(*), count(*) FILTER (WHERE f.recency_weeks = t.baseline_score AND f.label = t.label)
                           FROM churn_features f JOIN churn_test_score t USING (household_key, snapshot_week)
                           WHERE f.role = 'teste'""")
    assert n == iguais == um(con, "SELECT count(*) FROM churn_test_score")[0]


def test_features_do_clv_gasto_por_janela(con, pronto):
    janelas = dict(con.sql("SELECT spend_window, count(*) FROM clv_features GROUP BY 1").fetchall())
    assert janelas["atual"] == um(con, "SELECT count(*) FROM customer_segment")[0]
    assert janelas["calibracao"] + janelas["analogos_futuro"] == len(pronto[1])
    gasto = um(con, "SELECT sum(spend) FROM clv_features WHERE spend_window IN ('calibracao_futuro', 'analogos_futuro')")[0]
    assert abs(gasto - float(um(con, "SELECT sum(revenue) FROM sales_item WHERE week_no BETWEEN 50 AND 101")[0])) < 0.01


def test_segmento_um_por_cliente_com_os_nomes_do_contrato(con, pronto):
    perfil = pronto[1]
    n, distintos = um(con, "SELECT count(*), count(DISTINCT household_key) FROM customer_segment")
    assert n == distintos
    assert {r[0] for r in con.sql("SELECT DISTINCT segment FROM customer_segment").fetchall()} == SEGMENTOS
    # quem não comprou na janela fica fora (vira "Sem segmento" na 3b)
    fora = {h for h, p in perfil.items() if p == "antigo"}
    assert not fora & {r[0] for r in con.sql("SELECT household_key FROM customer_segment").fetchall()}
    assert n == um(con, "SELECT count(DISTINCT household_key) FROM customer_metrics WHERE period = 'current' AND revenue > 0")[0]
    assert um(con, "SELECT count(*) FROM rfm_k_evaluation WHERE chosen")[0] == 1


def test_perfil_do_rfm_soma_100(con):
    clientes, fat = um(con, "SELECT sum(households_pct), sum(revenue_pct) FROM rfm_segment_profile")
    assert abs(clientes - 100) < 0.5 and abs(fat - 100) < 0.5


def test_churn_devolve_probabilidade_por_cliente(con):
    limiar = resumo(con, "churn", "limiar")
    assert um(con, "SELECT count(*) FROM churn_score WHERE probability < 0 OR probability > 1")[0] == 0
    assert um(con, f"SELECT count(*) FROM churn_score WHERE is_high_risk <> (probability >= {limiar})")[0] == 0
    assert um(con, "SELECT count(*), count(DISTINCT household_key) FROM churn_score")[0] == \
        resumo(con, "churn", "populacao_prevista")
    # alertas e pausas esperadas do resumo do RAG = soma pelas probabilidades por cliente
    seg = resumo(con, "churn", "risco_por_segmento")
    alertas, pausas = um(con, "SELECT count(*) FILTER (WHERE is_high_risk), sum(probability) FROM churn_score")
    assert alertas == sum(s["alertas"] for s in seg)
    assert abs(pausas - sum(s["pausas_esperadas"] for s in seg)) < 0.01


def test_notas_do_teste_batem_com_a_matriz_e_a_auc(con):
    linhas = um(con, "SELECT count(*) FROM churn_test_score")[0]
    for nome in ("model", "baseline"):
        tn, fp, fn, tp, auc, auc_roc = um(con, f"""SELECT tn, fp, fn, tp, auc, auc_from_roc_scores
                                                  FROM churn_classifier WHERE classifier = '{nome}'""")
        assert tn + fp + fn + tp == linhas
        assert round(auc_roc, 4) == auc
    limiar = resumo(con, "churn", "limiar")
    assert um(con, f"SELECT count(*) FILTER (WHERE model_score >= {limiar} AND label = 1) FROM churn_test_score")[0] == \
        um(con, "SELECT tp FROM churn_classifier WHERE classifier = 'model'")[0]
    assert {r[0] for r in con.sql("SELECT DISTINCT snapshot_week FROM churn_test_score").fetchall()} == {85, 93}


def test_roc_vai_de_0_a_1(con):
    for nome in ("model", "baseline"):
        ini, fim, nulos = um(con, f"""SELECT arg_min(fpr, point) + arg_min(tpr, point), arg_max(fpr, point) + arg_max(tpr, point),
                                      count(*) FILTER (WHERE cutoff IS NULL) FROM churn_roc WHERE classifier = '{nome}'""")
        assert (ini, fim, nulos) == (0, 2, 1)


def test_clv_tem_os_segmentos_e_o_grupo_sem_compra(con, pronto):
    segs = {r[0] for r in con.sql("SELECT segment FROM clv_segment").fetchall()}
    assert segs == SEGMENTOS | {"Sem compra na janela"}
    total = resumo(con, "clv", "total")
    assert total["households"] == len(pronto[1])
    assert abs(um(con, "SELECT sum(clv_total) FROM clv_segment")[0] - total["clv_total_usd"]) < 0.01


def test_teste_de_desconto_pares_e_veredito(con):
    assert um(con, "SELECT count(*) FROM discount_test_pair")[0] == 6
    assert resumo(con, "teste_desconto", "veredito") in {"sem_diferenca_detectavel", "diferenca_desprezivel", "diferenca_relevante"}
    assert {r[0] for r in con.sql("SELECT model FROM model_summary").fetchall()} == {"rfm", "churn", "clv", "teste_desconto"}
    assert "conclusao" in resumo(con, "teste_desconto", "e_dai")


# ---------------------------------------------------------------- métricas: macros e uma definição por métrica

def test_macros_casos_feitos_a_mao(con):
    casos = {
        "avg_ticket(10, 4)": 2.5, "avg_ticket(10, 0)": None,
        "items_per_basket(30, 4)": 7.5, "items_per_basket(3, 0)": None,
        "discount_rate(15, 100)": 0.15, "discount_rate(1, 0)": None,
        "growth(110, 100)": 110 / 100 - 1, "growth(5, 0)": None,
        "share(1, 4)": 0.25, "share(1, 0)": None,
        "private_label_share(3, 12)": 0.25, "private_label_share(3, 0)": None,
        "penetration(20, 80)": 0.25, "penetration(2, 0)": None,
        "frequency(9, 3)": 3.0, "frequency(9, 0)": None,
        "support(2, 10)": 0.2, "confidence(2, 4)": 0.5,
        "lift(2, 4, 5, 10)": 1.0, "lift(4, 4, 5, 10)": 2.0,
        "jaccard(2, 4, 5)": 2 / 7,
        "index_vs_all(0.2, 0.1)": 200.0, "index_vs_all(1, 0)": None,
        "lift_index(3, 1.5)": 2.0,
    }
    for expressao, esperado in casos.items():
        valor = um(con, f"SELECT {expressao}")[0]
        assert (valor is None) if esperado is None else abs(valor - esperado) < 1e-12, expressao


def test_uma_definicao_por_metrica_nenhuma_conta_fora_das_macros():
    # Toda razão das métricas passa por uma macro de sql/gold/metricas.sql: nenhuma divisão escrita nos SQL dos cubos.
    for arquivo in sorted(build.METRICS_SQL.glob("*.sql")):
        codigo = "\n".join(l.split("--")[0] for l in arquivo.read_text(encoding="utf-8").splitlines())
        assert "/" not in codigo, arquivo.name


# ---------------------------------------------------------------- métricas: períodos, lojas e tempo

def test_periodos_terminam_na_ultima_semana_completa(con):
    linhas = con.execute("""SELECT period, week_start, week_end, prior_week_start, prior_week_end, point_grain
                            FROM dim_period ORDER BY position""").fetchall()
    assert linhas == [("4s", 98, 101, 46, 49, "day"), ("13s", 89, 101, 37, 49, "week"),
                      ("26s", 76, 101, 24, 49, "week"), ("base", 1, 101, None, None, "week")]


def test_loja_sem_venda_no_ano_anterior_nao_e_comparavel(con):
    lojas = dict(con.execute("SELECT period, list(store_id ORDER BY store_id) FROM period_comparable_store GROUP BY 1").fetchall())
    assert lojas == {"4s": [1, 2, 3], "13s": [1, 2, 3], "26s": [1, 2, 3]}
    # a loja 4 vende no período (fica no faturamento de todas as lojas), mas não no comparável
    total, comparavel = um(con, """SELECT sum(revenue), sum(revenue_comparable) FROM cube_period WHERE period = '4s'""")
    loja4 = um(con, "SELECT sum(revenue) FROM sales_item WHERE store_id = 4")[0]
    assert loja4 > 0 and total - comparavel == loja4


def test_faturamento_no_tempo_diario_em_4s_com_dia_menos_364(con):
    pontos = con.execute("""SELECT point, sum(revenue), sum(revenue_prior_year), any_value(point_grain)
                            FROM revenue_over_time WHERE period = '4s' GROUP BY point""").fetchall()
    dias = {d for (d,) in con.execute("SELECT day FROM calendar WHERE week_no BETWEEN 98 AND 101").fetchall()}
    assert {p[0] for p in pontos} <= dias and len(pontos) > 20
    for dia, fat, ant, grao in pontos:
        assert grao == "day"
        esperado = um(con, f"""SELECT coalesce(sum(revenue) FILTER (WHERE day = {dia}), 0),
                                      coalesce(sum(revenue) FILTER (WHERE day = {dia} - 364), 0)
                               FROM sales_item WHERE store_id IN (1, 2, 3)""")
        assert (fat, ant) == esperado, dia


def test_faturamento_no_tempo_semanal_e_base_sem_ano_anterior(con):
    assert {r[0] for r in con.execute("SELECT DISTINCT point_grain FROM revenue_over_time WHERE period <> '4s'").fetchall()} == {"week"}
    semana = um(con, """SELECT sum(revenue), sum(revenue_prior_year) FROM revenue_over_time
                        WHERE period = '26s' AND point = 100""")
    assert semana == um(con, """SELECT sum(revenue) FILTER (WHERE week_no = 100), sum(revenue) FILTER (WHERE week_no = 48)
                                FROM sales_item WHERE store_id IN (1, 2, 3)""")
    # base: todas as lojas (com a loja 4) e ano anterior nulo
    base = um(con, "SELECT sum(revenue), count(revenue_prior_year) FROM revenue_over_time WHERE period = 'base' AND point = 100")
    assert base == (um(con, "SELECT sum(revenue) FROM sales_item WHERE week_no = 100")[0], 0)
    assert um(con, "SELECT min(point), max(point) FROM revenue_over_time WHERE period = 'base'") == (1, 101)


# ---------------------------------------------------------------- métricas: grupos, filtros e departamento

def test_sem_segmento_e_os_15_subconjuntos(con, pronto):
    antigos = {h for h, p in pronto[1].items() if p == "antigo"}
    grupos = dict(con.execute("SELECT household_key, segment FROM customer_group").fetchall())
    assert len(grupos) == len(pronto[1])
    assert {grupos[h] for h in antigos} == {"Sem segmento"}
    assert um(con, "SELECT count(*) FROM customer_group WHERE segment = 'Sem segmento'")[0] == \
        len(pronto[1]) - um(con, "SELECT count(*) FROM customer_segment")[0]
    subconjuntos = dict(con.execute("SELECT subset, list(segment ORDER BY segment) FROM segment_subset GROUP BY 1").fetchall())
    assert len(subconjuntos) == 16
    assert sorted(subconjuntos["todos"]) == sorted(SEGMENTOS | {"Sem segmento"})
    assert um(con, "SELECT DISTINCT subset_mask FROM segment_subset WHERE subset = 'Fiéis+Regulares'")[0] == 3
    assert "Sem segmento" not in {s for k, v in subconjuntos.items() if k != "todos" for s in v}


def test_kpi_com_um_departamento_usa_as_definicoes_do_painel(con):
    # G10: cestas com o departamento; ticket = faturamento do departamento ÷ essas cestas; clientes ativos = compraram o
    # departamento nas 8 semanas finais (94–101)
    k = um(con, """SELECT baskets, avg_ticket, active_customers FROM kpi_filtered
                   WHERE period = '26s' AND subset = 'todos' AND department = 'PRODUCE'""")
    cestas, fat = um(con, """SELECT count(DISTINCT basket_id), sum(revenue) FROM sales_item
                            WHERE department = 'PRODUCE' AND week_no BETWEEN 76 AND 101""")
    ativos = um(con, "SELECT count(DISTINCT household_key) FROM sales_item WHERE department = 'PRODUCE' AND week_no BETWEEN 94 AND 101")[0]
    assert k == (cestas, float(fat) / cestas, ativos)
    # sem departamento, clientes ativos é a regra de customer_metrics
    assert um(con, "SELECT active_customers FROM kpi_filtered WHERE period = '26s' AND subset = 'todos' AND department = 'todos'")[0] == \
        um(con, "SELECT count(*) FROM customer_metrics WHERE period = 'current' AND is_active")[0]


def test_dinheiro_em_risco_so_de_quem_tem_alerta(con):
    risco = um(con, "SELECT money_at_risk FROM department_risk WHERE subset = 'todos' AND department = 'todos'")[0]
    esperado = um(con, """SELECT coalesce(sum(i.revenue), 0) FROM sales_item i JOIN churn_score c USING (household_key)
                          WHERE c.is_high_risk AND i.week_no BETWEEN 76 AND 101""")[0]
    assert risco == esperado
    assert um(con, "SELECT count(*) FROM department_risk WHERE money_at_risk > revenue")[0] == 0


def test_cubo_soma_todo_o_faturamento_do_periodo(con):
    for periodo, ini in (("4s", 98), ("26s", 76), ("base", 1)):
        assert um(con, f"SELECT sum(revenue) FROM cube_period WHERE period = '{periodo}'")[0] == \
            um(con, f"SELECT sum(revenue) FROM sales_item WHERE week_no BETWEEN {ini} AND 101")[0], periodo


def test_pares_de_cesta_e_rede(con):
    pares = con.execute("SELECT DISTINCT department, subcategory_a, subcategory_b FROM basket_pair").fetchall()
    assert pares == [("GROCERY", "BREAD", "SOUP")]
    assert um(con, "SELECT min(baskets_pair) FROM basket_pair")[0] >= 200
    nos, fora = um(con, "SELECT count(*), count(*) FILTER (WHERE x NOT BETWEEN 0 AND 1 OR y NOT BETWEEN 0 AND 1) FROM network_node")
    assert nos == 3 and fora == 0   # as 3 subcategorias de mercadoria
    assert um(con, "SELECT count(*) FROM network_link WHERE period = '26s' AND subset = 'todos'")[0] > 0


# ---------------------------------------------------------------- execução

def ordenada(caminho: str, versao: int) -> pa.Table:
    """A leitura de uma tabela Delta não garante a ordem das linhas: compara-se o conteúdo ordenado."""
    tabela = DeltaTable(caminho, version=versao).to_pyarrow_table()
    ordenaveis = [c for c in tabela.column_names if not pa.types.is_list(tabela.schema.field(c).type)]
    return tabela.sort_by([(c, "ascending") for c in ordenaveis])


def test_idempotencia_duas_execucoes_iguais(cfg):
    for t in TODAS:
        caminho = str(caminho_tabela(cfg, "gold", t))
        assert DeltaTable(caminho).version() == 1, t
        assert ordenada(caminho, 1).equals(ordenada(caminho, 0)), t


def test_controle_registra_as_execucoes(cfg):
    linhas = DeltaTable(str(caminho_tabela(cfg, "gold", build.CONTROLE))).to_pyarrow_table().to_pylist()
    assert len(linhas) == 2 * len(TODAS)
    assert {l["etapa"] for l in linhas} == {"modelos", "metricas"}
    assert all(l["status"] == "sucesso" and l["versao_fact_sales"] == 0 for l in linhas)


def test_tudo_roda_cada_etapa_num_processo_e_para_no_erro(monkeypatch, capsys):
    chamadas = []

    def falso(comando, cwd):
        chamadas.append(comando)
        return type("R", (), {"returncode": 1})()

    monkeypatch.setattr(build.subprocess, "run", falso)
    monkeypatch.setattr(build, "executar", lambda *a, **k: pytest.fail("tudo não roda no mesmo processo"))
    assert build.main([]) == 1
    assert chamadas == [[build.sys.executable, "-m", "src.gold.build", "--etapa", "modelos"]]
    assert "etapas seguintes não rodaram" in capsys.readouterr().out


def test_etapa_escolhida_roda_no_mesmo_processo(monkeypatch):
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: pytest.fail("não deveria abrir processo"))
    monkeypatch.setattr(build, "carregar_config", lambda c: {})
    monkeypatch.setattr(build, "executar", lambda cfg, etapa: 0 if etapa == "metricas" else 1)
    assert build.main(["--etapa", "metricas"]) == 0


def test_sem_silver_termina_com_1(tmp_path, capsys):
    cfg = carregar_config(montar_config(tmp_path))
    assert build.executar(cfg) == 1
    assert "silver não está pronta" in capsys.readouterr().out
    assert not (tmp_path / "lake" / "gold").exists()


def test_espiar_le_as_tabelas_da_gold(pronto):
    config = pronto[0]
    assert espiar.main(["gold/models/churn_score", "contagem", "--config", str(config)]) == 0
    assert espiar.main(["gold/features/churn_features", "contagem", "--config", str(config)]) == 0
    assert espiar.main(["gold/metrics/kpi_filtered", "contagem", "--config", str(config)]) == 0
    assert espiar.main(["gold/_controle_gold", "--config", str(config)]) == 0
    assert espiar.main(["gold/models/nao_existe", "--config", str(config)]) == 2
