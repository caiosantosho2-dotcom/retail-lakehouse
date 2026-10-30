"""Gold: `python -m src.gold.build` (spec da fase 3).

Base comum (sql/gold/base, views sobre a silver), modelos estatísticos copiados do RAG (src/gold/modelos) e métricas
do painel (sql/gold/metrics, com as macros de sql/gold/metricas.sql). Três áreas (G12): lake/gold/features/ (as
variáveis que entraram nos modelos, como o RAG as calcula), lake/gold/models/ (resultados) e lake/gold/metrics/
(métricas do painel no grão dos cubos, uma definição cada). A exportação para os JSONs entra na 3c.
Cada execução reconstrói as tabelas (nova versão Delta). Uma falha para a execução e as tabelas já gravadas
continuam na versão anterior; o controle (lake/gold/_controle_gold) registra o que aconteceu.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ETAPAS = ["modelos", "metricas"]


# ---------------------------------------------------------------- linha de comando (parte leve, G33)
# Vem antes dos imports pesados: com `tudo`, este processo só abre um processo por etapa e espera; sai pelo
# `if __name__` abaixo sem carregar pandas, DuckDB nem os modelos, para não somar memória à da etapa em andamento.

def executar_em_processos(config: str | None) -> int:
    """`tudo` pela linha de comando: cada etapa num processo Python novo, em sequência, para a memória da etapa
    anterior ser devolvida ao sistema antes da próxima. Uma etapa com erro interrompe as seguintes."""
    for etapa in ETAPAS:
        comando = [sys.executable, "-m", "src.gold.build", "--etapa", etapa]
        if config:
            comando += ["--config", str(Path(config).resolve())]
        print(f"\n=== gold: etapa {etapa} (processo próprio) ===", flush=True)
        if subprocess.run(comando, cwd=Path(__file__).resolve().parents[2]).returncode != 0:
            print(f"A etapa {etapa} terminou com erro: as etapas seguintes não rodaram.")
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstrói a gold a partir da silver.")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    parser.add_argument("--etapa", choices=["tudo", *ETAPAS], default="tudo",
                        help="parte da gold a rodar: modelos, metricas (lê os modelos já gravados) ou tudo "
                             "(padrão: as duas, cada uma num processo próprio)")
    args = parser.parse_args(argv)
    if args.etapa == "tudo":
        return executar_em_processos(args.config)
    from src.gold import build  # o módulo completo (com os imports pesados), só quando uma etapa roda aqui
    return build.executar(build.carregar_config(args.config), args.etapa)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())


# ---------------------------------------------------------------- construção da gold
import json  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
from deltalake import DeltaTable, write_deltalake  # noqa: E402

from src.comum import RAIZ, caminho_tabela, carregar_config, conectar_duckdb, eh_delta, registrar_delta  # noqa: E402
from src.gold import layout  # noqa: E402

CONTROLE = "_controle_gold"
BASE_SQL = RAIZ / "sql" / "gold" / "base"
METRICS_SQL = RAIZ / "sql" / "gold" / "metrics"
MACROS_SQL = RAIZ / "sql" / "gold" / "metricas.sql"
SILVER = {"fact_sales": "context/sales/fact_sales", "dim_date": "context/shared/dim_date",
          "dim_household": "context/customer/dim_household", "dim_product": "context/product/dim_product"}
# Views da base que os modelos consultam muitas vezes: viram tabela temporária (como as views materializadas do RAG).
MATERIALIZAR = {"customer_week", "customer_metrics", "basket_department", "basket"}


def esquema_controle(fuso: str) -> pa.Schema:
    return pa.schema([
        ("tabela", pa.string()),
        ("etapa", pa.string()),
        ("processado_em", pa.timestamp("us", tz=fuso)),
        ("versao_fact_sales", pa.int64()),
        ("linhas", pa.int64()),
        ("segundos", pa.float64()),
        ("status", pa.string()),
        ("mensagem", pa.string()),
    ])


def preparar_conexao(cfg: dict) -> duckdb.DuckDBPyConnection:
    """Conexão com a silver registrada e as views da base comum criadas, em ordem (o prefixo numérico do arquivo)."""
    j = cfg["gold"]["janela"]
    con = conectar_duckdb(cfg)
    for nome, valor in {"janela_semanas": j["semanas"], "offset_semanas": j["offset_ano_anterior"],
                        "cliente_ativo_semanas": j["cliente_ativo_semanas"]}.items():
        con.execute(f"SET VARIABLE {nome} = ?::INTEGER", [valor])
    for nome, tabela in SILVER.items():
        registrar_delta(con, nome, caminho_tabela(cfg, "silver", tabela))
    for arquivo in sorted(BASE_SQL.glob("*.sql")):
        nome = arquivo.stem.split("_", 1)[1]
        sql = arquivo.read_text(encoding="utf-8")
        tipo = "TEMP TABLE" if nome in MATERIALIZAR else "VIEW"
        con.execute(f"CREATE OR REPLACE {tipo} {nome} AS {sql}")
    con.execute(MACROS_SQL.read_text(encoding="utf-8"))
    return con


def gravar_duckdb(cfg: dict, con, tabela: str, nome: str) -> int:
    """Grava a tabela `nome` da conexão em lake/gold/<tabela>, em lotes (HUGEINT das somas de contagem vira BIGINT)."""
    colunas = [f'"{c}"::BIGINT AS "{c}"' if tipo == "HUGEINT" else f'"{c}"'
               for c, tipo, *_ in con.execute(f"DESCRIBE {nome}").fetchall()]
    leitor = con.sql(f"SELECT {', '.join(colunas)} FROM {nome}").to_arrow_reader(int(cfg["silver"]["batch_rows"]))
    write_deltalake(str(caminho_tabela(cfg, "gold", tabela)), leitor, mode="overwrite", schema_mode="overwrite")
    return con.execute(f"SELECT count(*) FROM {nome}").fetchall()[0][0]


def gravar(cfg: dict, tabela: str, df: pd.DataFrame) -> int:
    destino = caminho_tabela(cfg, "gold", tabela)
    write_deltalake(str(destino), pa.Table.from_pandas(df, preserve_index=False), mode="overwrite", schema_mode="overwrite")
    return len(df)


def _json(v) -> str:
    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return str(o)
    return json.dumps(v, ensure_ascii=False, default=conv)


def resumo(modelo: str, retorno: dict) -> list[dict]:
    """model_summary: cada chave do retorno do modelo (números de uma linha, premissas e textos "e daí?") como JSON."""
    return [{"model": modelo, "key": k, "value": _json(v)} for k, v in retorno.items()]


# ---------------------------------------------------------------- modelos

def tabelas_rfm(con) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    from src.gold.modelos import rfm
    r, atrib = rfm._resultado(con, None)
    base, _ = rfm.carregar_base(con)
    seg = base.merge(atrib, on="household_key", how="inner")
    if len(seg) != len(base):
        raise RuntimeError(f"atribuição do RFM perdeu clientes: {len(base)} -> {len(seg)}")
    customer_segment = pd.DataFrame({
        "household_key": seg["household_key"].astype("int64"), "segment": seg["segmento"],
        "recency_days": seg["recencia_dias"], "frequency": seg["frequencia"], "monetary": seg["valor"],
        "avg_ticket": seg["ticket_medio"], "discount_pct": seg["pct_desconto"]})
    avaliacao = pd.DataFrame(r["avaliacao_k"]).rename(columns={
        "silhueta": "silhouette", "inercia": "inertia", "ari_sementes_min": "ari_seeds_min",
        "ari_sementes_mediana": "ari_seeds_median", "ari_subamostras_min": "ari_subsamples_min",
        "ari_subamostras_mediana": "ari_subsamples_median", "menor_segmento_pct": "min_segment_pct", "tamanhos": "sizes"})
    avaliacao["chosen"] = avaliacao["k"] == r["k_usado"]
    perfil = pd.DataFrame(r["segmentos"]).rename(columns={
        "nome": "segment", "pct_households": "households_pct", "recencia_media_dias": "recency_days_mean",
        "frequencia_media": "frequency_mean", "valor_medio_usd": "monetary_mean", "valor_total_usd": "monetary_total",
        "ticket_medio_usd": "avg_ticket_mean_of_customers", "pct_faturamento": "revenue_pct",
        "desconto_medio_pct": "discount_pct"})
    perfil.insert(0, "position", range(1, len(perfil) + 1))
    # G12/G21: a base que o K-Means recebe (janela de 26 s, só valor > 0), com os valores originais; o log1p e a
    # padronização são etapas do modelo (rfm.matriz) e não são gravados
    w = con.execute("SELECT week_start_current, week_end_current FROM analysis_window").fetchall()[0]
    features = pd.DataFrame({
        "household_key": base["household_key"].astype("int64"), "week_start": w[0], "week_end": w[1],
        "recency_days": base["recencia_dias"], "frequency": base["frequencia"], "monetary": base["valor"],
        "avg_ticket": base["ticket_medio"], "discount_pct": base["pct_desconto"], "discount": base["desconto_total"],
        "gross_value": base["valor_bruto"], "has_demographics": base["tem_demografia"].astype(bool)})
    sumario = {k: v for k, v in r.items() if k not in ("segmentos", "avaliacao_k")}
    return {"features/customer_rfm_features": features, "models/customer_segment": customer_segment,
            "models/rfm_k_evaluation": avaliacao, "models/rfm_segment_profile": perfil}, resumo("rfm", sumario)


def tabelas_churn(con) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    from src.gold.modelos import churn, roc
    r, detalhe = churn._calcular(con)
    p = detalhe["prob_por_cliente"]
    churn_score = pd.DataFrame({"household_key": p["household_key"].astype("int64"), "probability": p["probabilidade"],
                                "is_high_risk": p["alerta"].astype(bool), "segment": p["segmento"]})
    n = detalhe["notas_teste"]
    churn_test_score = pd.DataFrame({"household_key": n["household_key"].astype("int64"), "snapshot_week": n["foto"].astype("int32"),
                                     "label": n["y"].astype("int32"), "model_score": n["nota_modelo"],
                                     "baseline_score": n["nota_regra"].astype(float)})
    pontos, aucs = roc.curvas(n)
    classificadores = []
    for nome, m, ic, corte, desc in (
            ("model", r["modelo"], r["auc_modelo_ic"], r["limiar"],
             f"Regressão logística: alerta com risco de {str(r['limiar']).replace('.', ',')} ou mais (limiar de maior F1 na validação)"),
            ("baseline", r["baseline"], r["auc_baseline_ic"], r["k_baseline"], r["baseline_descricao"])):
        classificadores.append({
            "classifier": nome, "description": desc, "cutoff": float(corte), "auc": m["auc"], "auc_ci_low": ic[0],
            "auc_ci_high": ic[1], "auc_pr": m["auc_pr"], "precision": m["precisao"], "recall": m["recall"], "f1": m["f1"],
            "alerts": m["alertas"], "tn": m["tn"], "fp": m["fp"], "fn": m["fn"], "tp": m["tp"], "pauses": m["tp"] + m["fn"],
            "false_alarm_rate": m["fp"] / (m["fp"] + m["tn"]), "auc_from_roc_scores": aucs[nome]})
    v = detalhe["variaveis"]
    features = pd.DataFrame({
        "household_key": v["household_key"].astype("int64"), "snapshot_week": v["foto"].astype("int32"), "role": v["papel"],
        "recency_weeks": v["recencia_semanas"], "log_purchases_8w": v["log_compras_8s"], "log_value_26w": v["log_valor_26s"],
        "weeks_with_purchase_26w": v["semanas_com_compra_26s"], "longest_gap_26w": v["maior_pausa_26s"],
        "label": pd.array(v["rotulo"], dtype="Int32")})
    sumario = {k: v for k, v in r.items() if k not in ("modelo", "baseline")}
    return {"features/churn_features": features, "models/churn_score": churn_score, "models/churn_test_score": churn_test_score,
            "models/churn_classifier": pd.DataFrame(classificadores), "models/churn_roc": pontos}, resumo("churn", sumario)


def tabelas_clv(con) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    from src.gold.modelos import clv
    r, gasto = clv._calcular(con)
    bt = {s["nome"]: s for s in (r["backtest"] or {}).get("segmentos", [])}
    linhas = []
    for s in r["segmentos"]:
        b = bt.get(s["nome"], {})
        linhas.append({
            "segment": s["nome"], "households": s["n"], "window_mean_value": s["valor_medio_janela_usd"],
            "ratio": s["razao_futuro_passado"], "ratio_ci_low": (s["razao_ic_95"] or [None, None])[0],
            "ratio_ci_high": (s["razao_ic_95"] or [None, None])[1], "expected_revenue": s["receita_esperada_usd"],
            "clv_mean": s["clv_medio"], "clv_ci_low": s["ic_95"][0], "clv_ci_high": s["ic_95"][1], "clv_total": s["clv_total_usd"],
            "calibration_households": s["calibracao"]["households"], "calibration_past": s["calibracao"]["gasto_passado_usd"],
            "calibration_future": s["calibracao"]["gasto_futuro_usd"],
            "backtest_households": b.get("households"), "backtest_actual": b.get("real_usd"),
            "backtest_method": b.get("previsto_metodo_usd"), "backtest_naive": b.get("previsto_ingenuo_usd"),
            "backtest_error_method_pct": b.get("erro_metodo_pct"), "backtest_error_naive_pct": b.get("erro_ingenuo_pct")})
    sumario = {k: v for k, v in r.items() if k != "segmentos"}
    features = pd.DataFrame({
        "household_key": gasto["household_key"].astype("int64"), "spend_window": gasto["janela"],
        "week_start": gasto["semana_ini"].astype("int32"), "week_end": gasto["semana_fim"].astype("int32"),
        "spend": gasto["gasto"].astype(float), "segment": gasto["segmento"]})
    return {"features/clv_features": features, "models/clv_segment": pd.DataFrame(linhas)}, resumo("clv", sumario)


def tabelas_desconto(con) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    from src.gold.modelos import teste_desconto
    r = teste_desconto._calcular(con)
    ph = {frozenset((p["grupo_1"], p["grupo_2"])): p for p in (r["post_hoc"] or [])}
    pares = []
    for i in r["ic_diferencas"]:
        p = ph.get(frozenset((i["grupo_1"], i["grupo_2"])), {})
        pares.append({"segment_a": i["grupo_1"], "segment_b": i["grupo_2"], "difference_pp": i["diferenca_mediana_pp"],
                      "ci_low": i["ic_inferior"], "ci_high": i["ic_superior"], "excludes_zero": i["exclui_zero"],
                      "p_raw": p.get("p_valor_bruto"), "p_adjusted": p.get("p_valor_ajustado"),
                      "significant": p.get("significativo_5pct")})
    segmentos = pd.DataFrame(r["grupos"]).rename(columns={
        "segmento": "segment", "mediana_pct": "median_pct", "media_pct": "mean_pct", "desvio_padrao_pp": "std_pp",
        "q25_pct": "q25_pct", "q75_pct": "q75_pct", "bigode_inf_pct": "whisker_low_pct", "bigode_sup_pct": "whisker_high_pct",
        "fora_do_bigode": "outside_whiskers", "taxa_ponderada_pct": "weighted_rate_pct",
        "desconto_total_usd": "discount_total", "valor_bruto_usd": "gross_value"})
    sumario = {k: v for k, v in r.items() if k not in ("grupos", "ic_diferencas", "post_hoc")}
    return {"models/discount_test_pair": pd.DataFrame(pares), "models/discount_test_segment": segmentos}, resumo("teste_desconto", sumario)


MODELOS = [("rfm", tabelas_rfm), ("churn", tabelas_churn), ("clv", tabelas_clv), ("teste_desconto", tabelas_desconto)]


# ---------------------------------------------------------------- métricas (seção 5 da spec)

# Ordem de execução. Cada nome é um arquivo de sql/gold/metrics/. Tipos:
#   tabela      -> tabela temporária na conexão e gravada em lake/gold/metrics/<nome>
#   view        -> view auxiliar (nome com "_"), não gravada
#   auxiliar    -> tabela temporária auxiliar, não gravada
#   por_periodo / por_periodo_departamento -> a consulta roda um período (e departamento) por vez e as partes se juntam
#   layout      -> network_node ganha as posições x/y (src/gold/layout.py) e é gravada
METRICAS = [
    ("_item", "auxiliar"), ("dim_period", "tabela"), ("period_comparable_store", "tabela"), ("customer_group", "tabela"),
    ("segment_subset", "tabela"),
    ("_cut_basket_department", "view"), ("_cut_basket", "view"),
    ("cube_period", "tabela"), ("department", "tabela"), ("revenue_over_time", "tabela"), ("kpi_filtered", "tabela"),
    ("_department_group", "auxiliar"), ("department_segment", "tabela"), ("department_profile", "tabela"),
    ("department_risk", "tabela"), ("subcategory_top", "tabela"), ("concentration", "tabela"),
    ("_brand_cut", "auxiliar"), ("brand", "tabela"),
    ("_basket_subcategory", "auxiliar"), ("basket_pair", "por_periodo_departamento"),
    ("network_node", "auxiliar"), ("_network_pair", "por_periodo"), ("network_node", "layout"),
    ("network_link", "tabela"), ("network_neighbor", "tabela"), ("network_characteristic", "tabela"),
]
# Auxiliares que saem da memória depois do último passo que as usa (notebook com pouca RAM).
LIBERAR = {"department_segment": ["_department_group"], "brand": ["_brand_cut"], "basket_pair": ["_basket_subcategory"],
           "network_characteristic": ["_item", "_network_pair"]}
# Tabelas dos modelos que as métricas leem (da gold gravada, para a etapa de métricas rodar sozinha).
MODELOS_LIDOS = {"customer_segment": "models/customer_segment", "churn_score": "models/churn_score"}


def configurar_metricas(con, cfg: dict) -> None:
    """Parâmetros da seção gold.metricas como variáveis e tabelas pequenas na conexão (nenhum número fica no SQL)."""
    m, j = cfg["gold"]["metricas"], cfg["gold"]["janela"]
    periodos = m["periodos"]
    base = [p["periodo"] for p in periodos if p["semanas"] is None]
    segmento = [p["periodo"] for p in periodos if p["semanas"] == j["semanas"]]
    if len(base) != 1 or len(segmento) != 1:
        raise ValueError("gold.metricas.periodos precisa de um período sem semanas (base) e um com as semanas da janela")
    con.register("config_period", pa.table({
        "period": [p["periodo"] for p in periodos], "position": pa.array(range(1, len(periodos) + 1), pa.int32()),
        "weeks": pa.array([p["semanas"] for p in periodos], pa.int32()), "point_grain": [p["ponto"] for p in periodos]}))
    con.register("config_segment", pa.table({"segment": m["segmentos"],
                                             "bit": pa.array(range(len(m["segmentos"])), pa.int32())}))
    variaveis = {"offset_dias": (m["offset_dias_ano_anterior"], "INTEGER"), "sem_segmento": (m["sem_segmento"], "VARCHAR"),
                 "periodo_base": (base[0], "VARCHAR"), "periodo_segmento": (segmento[0], "VARCHAR")}
    for chave, valor in {**m["limites"], **m["cesta"]}.items():
        variaveis[chave] = (valor, "DOUBLE" if isinstance(valor, float) else "INTEGER")
    for nome, (valor, tipo) in variaveis.items():
        con.execute(f"SET VARIABLE {nome} = ?::{tipo}", [valor])


def _sql_metrica(nome: str) -> str:
    return (METRICS_SQL / f"{nome}.sql").read_text(encoding="utf-8")


def _acumular(con, nome: str, sql: str, valores: list[dict]) -> None:
    """Roda `sql` para cada conjunto de variáveis e junta as partes na tabela temporária `nome`."""
    for i, v in enumerate(valores):
        for k, x in v.items():
            con.execute(f"SET VARIABLE {k} = ?::VARCHAR", [x])
        con.execute(f"CREATE OR REPLACE TEMP TABLE {nome} AS {sql}" if i == 0 else f"INSERT INTO {nome} {sql}")


def posicionar_rede(con) -> None:
    """network_node ganha x/y: semelhança entre nós = Jaccard das cestas (todos os clientes, janela do segmento); grupos =
    departamentos; posições normalizadas para 0–1 na maior dimensão (o mesmo passo do painel publicado)."""
    nos = con.execute("SELECT node, department FROM network_node ORDER BY node").df()
    pares = con.execute("""SELECT node_a, node_b, jaccard(baskets_pair, baskets_a, baskets_b) AS j FROM _network_pair
                           WHERE period = getvariable('periodo_segmento') AND subset = 'todos'""").df()
    semelhanca = np.eye(len(nos))
    for a, b, j in pares.itertuples(index=False):
        semelhanca[a, b] = semelhanca[b, a] = j
    xy = layout.posicoes_em_dois_niveis(semelhanca, nos["department"].to_numpy(), compacto=True)
    xy = (xy - xy.min(axis=0)) / (xy.max(axis=0) - xy.min(axis=0)).max()
    con.register("_posicao", pd.DataFrame({"node": nos["node"].astype("int32"), "x": xy[:, 0], "y": xy[:, 1]}))
    con.execute("""CREATE OR REPLACE TEMP TABLE network_node AS
                   SELECT n.*, p.x, p.y FROM network_node n JOIN _posicao p USING (node)""")
    con.unregister("_posicao")


def construir_metricas(cfg: dict, registros: list[dict]) -> bool:
    """Roda METRICAS em ordem. Para na primeira falha: as tabelas já gravadas ficam, as seguintes na versão anterior."""
    etapa = "metricas"
    con = preparar_conexao(cfg)
    try:
        configurar_metricas(con, cfg)
        for nome, tabela in MODELOS_LIDOS.items():
            registrar_delta(con, nome, caminho_tabela(cfg, "gold", tabela))
        for nome, tipo in METRICAS:
            t0 = time.time()
            print(f"métrica {nome} ...", flush=True)
            try:
                if tipo == "view":
                    con.execute(f"CREATE OR REPLACE TEMP VIEW {nome} AS {_sql_metrica(nome)}")
                    continue
                if tipo == "layout":
                    posicionar_rede(con)
                elif tipo == "por_periodo":
                    periodos = [p for (p,) in con.execute("SELECT period FROM dim_period ORDER BY position").fetchall()]
                    _acumular(con, nome, _sql_metrica(nome), [{"periodo": p} for p in periodos])
                elif tipo == "por_periodo_departamento":
                    pares = con.execute("""SELECT p.period, b.department FROM dim_period p
                                           JOIN basket_department b ON b.week_no BETWEEN p.week_start AND p.week_end
                                           GROUP BY p.period, p.position, b.department
                                           ORDER BY p.position, b.department""").fetchall()
                    _acumular(con, nome, _sql_metrica(nome), [{"periodo": p, "departamento": d} for p, d in pares])
                else:
                    con.execute(f"CREATE OR REPLACE TEMP TABLE {nome} AS {_sql_metrica(nome)}")
                if tipo in ("tabela", "layout", "por_periodo_departamento"):
                    linhas = gravar_duckdb(cfg, con, f"metrics/{nome}", nome)
                    registros.append({"tabela": f"metrics/{nome}", "etapa": etapa, "linhas": linhas,
                                      "segundos": time.time() - t0, "status": "sucesso"})
                for auxiliar in LIBERAR.get(nome, []):
                    con.execute(f"DROP TABLE {auxiliar}")
            except Exception as e:
                registros.append({"tabela": f"metrics/{nome}", "etapa": etapa, "status": "erro",
                                  "segundos": time.time() - t0, "mensagem": f"{type(e).__name__}: {e}"})
                return False
    finally:
        con.close()
    return True


# ---------------------------------------------------------------- execução

def registrar_controle(cfg: dict, registros: list[dict], processado_em: datetime, versao: int | None) -> None:
    esquema = esquema_controle(cfg["bronze"]["fuso"])
    linhas = [{**{c.name: r.get(c.name) for c in esquema}, "processado_em": processado_em, "versao_fact_sales": versao}
              for r in registros]
    write_deltalake(str(caminho_tabela(cfg, "gold", CONTROLE)), pa.Table.from_pylist(linhas, schema=esquema), mode="append")


def executar(cfg: dict, etapa: str = "tudo", agora: datetime | None = None) -> int:
    """Reconstrói a gold neste processo: modelos e depois métricas, ou só uma etapa. Devolve 0 se tudo deu certo, 1 em
    qualquer erro. A linha de comando com `tudo` não passa por aqui: usa executar_em_processos (G33)."""
    fuso = ZoneInfo(cfg["bronze"]["fuso"])
    processado_em = (agora or datetime.now(fuso)).astimezone(fuso)
    faltando = [t for t in SILVER.values() if not eh_delta(caminho_tabela(cfg, "silver", t))]
    if faltando:
        print(f"A silver não está pronta (faltam: {', '.join(faltando)}): rode `python -m src.silver.build` antes.")
        return 1
    etapas = ETAPAS if etapa == "tudo" else [etapa]
    if "modelos" not in etapas:
        faltando = [t for t in MODELOS_LIDOS.values() if not eh_delta(caminho_tabela(cfg, "gold", t))]
        if faltando:
            print(f"Os modelos não estão prontos (faltam: {', '.join(faltando)}): rode com --etapa modelos antes.")
            return 1
    versao = DeltaTable(str(caminho_tabela(cfg, "silver", SILVER["fact_sales"]))).version()
    registros: list[dict] = []
    ok = construir_modelos(cfg, registros) if "modelos" in etapas else True
    if ok and "metricas" in etapas:
        ok = construir_metricas(cfg, registros)
    registrar_controle(cfg, registros, processado_em, versao)

    print(f"\nResumo da gold ({processado_em:%Y-%m-%d %H:%M %Z}; fact_sales versão {versao})")
    for r in registros:
        linhas = f"{r['linhas']:,}" if r.get("linhas") is not None else "-"
        print(f"{r['tabela']:<34} {linhas:>8}  {r['status']}")
        if r.get("mensagem"):
            print(f"    -> {r['mensagem']}")
    ok = ok and bool(registros) and all(r["status"] == "sucesso" for r in registros)
    return 0 if ok else 1


def construir_modelos(cfg: dict, registros: list[dict]) -> bool:
    """Os 4 modelos, cada um gravando as suas features e resultados, e o model_summary no fim."""
    # Os modelos (scikit-learn e cia.) são importados só aqui: o processo que só orquestra o `tudo` fica leve (G33).
    from src.gold.modelos import parametros
    etapa = "modelos"
    con = preparar_conexao(cfg)
    parametros.configurar(cfg)
    sumario: list[dict] = []
    try:
        for nome, funcao in MODELOS:
            print(f"modelo {nome} ...", flush=True)
            t0 = time.time()
            try:
                tabelas, linhas_resumo = funcao(con)
            except Exception as e:
                registros.append({"tabela": f"models ({nome})", "etapa": etapa, "status": "erro",
                                  "segundos": time.time() - t0, "mensagem": f"{type(e).__name__}: {e}"})
                break
            sumario += linhas_resumo
            for tabela, df in tabelas.items():
                registros.append({"tabela": tabela, "etapa": etapa, "linhas": gravar(cfg, tabela, df),
                                  "segundos": time.time() - t0, "status": "sucesso"})
        else:
            registros.append({"tabela": "models/model_summary", "etapa": etapa, "status": "sucesso",
                              "linhas": gravar(cfg, "models/model_summary", pd.DataFrame(sumario))})
    finally:
        con.close()
    return bool(sumario) and all(r["status"] == "sucesso" for r in registros)
