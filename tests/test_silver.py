"""Testes da silver (src/silver/build.py), com a declaração REAL do config.example.yaml sobre uma bronze mínima."""
from __future__ import annotations

import importlib.util
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pytest
import yaml

from src.bronze import ingest
from src.comum import RAIZ, caminho_tabela, carregar_config, conectar_duckdb, ler_delta
from src.silver import build

SP = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 10, 28, 10, 0, tzinfo=SP)

TRANSACOES = [
    "household_key,BASKET_ID,DAY,PRODUCT_ID,QUANTITY,SALES_VALUE,STORE_ID,RETAIL_DISC,TRANS_TIME,WEEK_NO,COUPON_DISC,COUPON_MATCH_DISC",
    # válidas
    "1,100,1,10,1,2.50,500,0,0930,1,0,0",          # mercadoria comum
    "1,100,1,11,1,0,500,0,0930,1,0,0",             # item grátis
    "2,101,6,12,1,30.00,501,0,1200,2,0,0",         # não mercadoria pelo departamento; day 6 = semana 2 (ceil(6/7) daria 1)
    "2,101,6,13,1,1.00,501,0.50,1200,2,0,0",       # não mercadoria pela commodity; estorno de desconto
    "3,102,7,99,1,5.55E-17,502,0,2359,2,0,0",      # produto sem cadastro (órfão -> -1); valor com ruído
    # rejeitadas: uma regra por linha (BASKET_ID identifica)
    "1,200,1,10,abc,1.00,500,0,0930,1,0,0",        # invalid_number
    ",201,1,10,1,1.00,500,0,0930,1,0,0",           # null_key
    "1,202,712,10,1,1.00,500,0,0930,1,0,0",        # out_of_range (day)
    "1,203,1,10,1,1.00,500,0,0960,1,0,0",          # out_of_range (minuto 60)
    "1,204,1,10,1,-1.00,500,0,0930,1,0,0",         # negative_sales_value
    "1,205,1,10,1,1.00,500,0,0930,1,0.50,0",       # positive_coupon_discount
    "1,206,1,10,0,0,500,0,0930,1,0,0",             # quantity_zero
    # ordem dos motivos: a linha cai na primeira regra que falhar
    "1,207,1,10,0,-1.00,500,0,0930,1,0,0",         # negative_sales_value (antes de quantity_zero)
    ",208,1,10,x,1.00,500,0,0930,1,0,0",           # invalid_number (antes de null_key)
]
MOTIVOS = {
    "200": "invalid_number", "201": "null_key", "202": "out_of_range", "203": "out_of_range",
    "204": "negative_sales_value", "205": "positive_coupon_discount", "206": "quantity_zero",
    "207": "negative_sales_value", "208": "invalid_number",
}
PRODUTOS = [
    "PRODUCT_ID,MANUFACTURER,DEPARTMENT,BRAND,COMMODITY_DESC,SUB_COMMODITY_DESC,CURR_SIZE_OF_PRODUCT",
    "10,69,GROCERY,Private,SOUP,CONDENSED SOUP,12 OZ",
    "11,69, GROCERY ,National,BREAD,WHITE,",
    "12,5,KIOSK-GAS,National,GASOLINE,REGULAR,",
    "13,5,GROCERY,National,COUPON/MISC ITEMS,GIFT CARDS,",
    "14,5, ,National, , ,",
]
DEMOGRAFIA = [
    "AGE_DESC,MARITAL_STATUS_CODE,INCOME_DESC,HOMEOWNER_DESC,HH_COMP_DESC,HOUSEHOLD_SIZE_DESC,KID_CATEGORY_DESC,household_key",
    "45-54,A,50-74K,Homeowner,2 Adults No Kids,2,None/Unknown,1",
    "65+,U,Under 15K,Unknown,Unknown,1,None/Unknown,4",     # cliente só na demografia
]


def escrever(raw: Path, nome: str, linhas: list[str]) -> None:
    (raw / nome).write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="")


def montar_config(pasta: Path) -> Path:
    """Config com a declaração real da silver (config.example.yaml), lake e CSVs em `pasta`."""
    real = yaml.safe_load((RAIZ / "config.example.yaml").read_text(encoding="utf-8"))
    real["paths"] = {"raw": "raw", "lake": "lake"}
    real["duckdb"] = {"memory_limit": "256MB", "threads": 1}
    real["bronze"]["tabelas"] = [t for t in real["bronze"]["tabelas"]
                                 if t["tabela"] in ("transaction_data", "product", "hh_demographic")]
    real["silver"]["batch_rows"] = 3
    real["silver"]["limite_rejeicao"] = 1.0  # dados mínimos: quase tudo é caso de rejeição
    raw = pasta / "raw"
    raw.mkdir()
    escrever(raw, "transaction_data.csv", TRANSACOES)
    escrever(raw, "product.csv", PRODUTOS)
    escrever(raw, "hh_demographic.csv", DEMOGRAFIA)
    caminho = pasta / "config.yaml"
    caminho.write_text(yaml.safe_dump(real, allow_unicode=True), encoding="utf-8")
    return caminho


@pytest.fixture
def config(tmp_path: Path) -> Path:
    """Config novo por teste: para os testes que mudam CSVs ou rodam a silver de novo."""
    return montar_config(tmp_path)


def preparar(config: Path, **ajustes) -> dict:
    """Carrega a bronze e devolve o cfg (com ajustes no bloco silver)."""
    cfg = carregar_config(config)
    cfg["silver"].update(ajustes)
    assert ingest.executar(cfg, agora=AGORA) == 0
    return cfg


@pytest.fixture(scope="module")
def config_pronto(tmp_path_factory) -> Path:
    """Bronze + silver construídas UMA vez para os testes que só leem (mais rápido)."""
    config = montar_config(tmp_path_factory.mktemp("silver"))
    assert build.executar(preparar(config), agora=AGORA) == 0
    return config


@pytest.fixture
def cfg(config_pronto: Path) -> dict:
    return carregar_config(config_pronto)


def ler(cfg: dict, tabela: str) -> pa.Table:
    return ler_delta(conectar_duckdb(cfg), caminho_tabela(cfg, "silver", tabela)).to_arrow_table()


def linhas(cfg: dict, tabela: str) -> list[dict]:
    return ler(cfg, tabela).to_pylist()


def controle(cfg: dict) -> list[dict]:
    return linhas(cfg, build.CONTROLE)


# ---------------------------------------------------------------- clean

def test_cada_regra_pega_a_linha_certa_na_ordem(cfg):
    rejeitadas = {r["BASKET_ID"]: r["_motivo"] for r in linhas(cfg, "_rejected/transaction_data")}
    assert rejeitadas == MOTIVOS


def test_rejeitadas_guardam_o_texto_original(cfg):
    r = next(r for r in linhas(cfg, "_rejected/transaction_data") if r["BASKET_ID"] == "200")
    assert r["QUANTITY"] == "abc" and r["TRANS_TIME"] == "0930"
    assert r["_data_carga"] == "2026-10-28" and r["_processado_em"] == AGORA
    tipos = ler(cfg, "_rejected/transaction_data").schema
    assert all(pa.types.is_string(tipos.field(c).type) for c in TRANSACOES[0].split(","))


def test_bronze_igual_clean_mais_rejeitadas(cfg):
    reg = {r["tabela"]: r for r in controle(cfg)}["clean/transaction_data"]
    assert reg["linhas_entrada"] == len(TRANSACOES) - 1 == 14
    assert reg["linhas_saida"] == 5 and reg["linhas_rejeitadas"] == 9
    assert reg["status"] == "sucesso"
    assert len(linhas(cfg, "clean/transaction_data")) == 5


def test_tipos_e_nomes_da_clean(cfg):
    esquema = ler(cfg, "clean/transaction_data").schema
    assert esquema.field("basket_id").type == pa.int64()
    assert esquema.field("day").type == pa.int32()
    assert esquema.field("sales_value").type == pa.decimal128(18, 4)
    assert "trans_time" not in esquema.names and "TRANS_TIME" not in esquema.names
    assert {"trans_hour", "trans_minute", "is_free_item", "is_refund_discount", "_data_carga", "_processado_em"} <= set(esquema.names)
    assert esquema.field("_processado_em").type.tz == "America/Sao_Paulo"
    hora = {r["basket_id"]: (r["trans_hour"], r["trans_minute"]) for r in linhas(cfg, "clean/transaction_data")}
    assert hora[100] == (9, 30) and hora[102] == (23, 59)


def test_texto_com_trim_e_vazio_vira_nulo(cfg):
    produtos = {r["product_id"]: r for r in linhas(cfg, "clean/product")}
    assert produtos[11]["department"] == "GROCERY"
    assert produtos[11]["curr_size_of_product"] is None
    assert produtos[14]["department"] is None and produtos[14]["commodity_desc"] is None


def test_valor_com_ruido_de_ponto_flutuante(cfg):
    vendas = {r["basket_id"]: r for r in linhas(cfg, "clean/transaction_data")}
    assert vendas[102]["sales_value"] == Decimal("0.0000")


def test_chave_duplicada_vai_para_rejeitados(config):
    linhas_produto = PRODUTOS + ["10,70,GROCERY,Outra,SOUP,X,"]
    escrever(Path(config).parent / "raw", "product.csv", linhas_produto)
    cfg = preparar(config)
    assert build.executar(cfg, agora=AGORA) == 0
    rej = linhas(cfg, "_rejected/product")
    assert sorted((r["PRODUCT_ID"], r["_motivo"]) for r in rej) == [("10", "duplicate_key")] * 2
    assert 10 not in {r["product_id"] for r in linhas(cfg, "clean/product")}


# ---------------------------------------------------------------- limite de rejeição

def test_limite_de_rejeicao_para_antes_da_context(config):
    cfg = preparar(config, limite_rejeicao=0.01)
    assert build.executar(cfg, agora=AGORA) == 1
    reg = {r["tabela"]: r for r in controle(cfg)}
    assert reg["clean/transaction_data"]["status"] == "erro"
    assert "acima do limite" in reg["clean/transaction_data"]["mensagem"]
    assert len(linhas(cfg, "_rejected/transaction_data")) == 9   # fica gravado para investigar
    assert not (cfg["paths"]["lake"] / "silver" / "context").exists()
    assert not any(t.startswith("context/") for t in reg)


# ---------------------------------------------------------------- context

def test_marcacoes_na_fact_sales(cfg):
    fato = {r["basket_id"] * 1000 + max(r["product_id"], 0): r for r in linhas(cfg, "context/sales/fact_sales")}
    assert fato[100010]["is_merchandise"] is True and fato[100010]["is_free_item"] is False
    assert fato[100011]["is_free_item"] is True
    assert fato[101012]["is_merchandise"] is False      # pelo departamento KIOSK-GAS
    assert fato[101013]["is_merchandise"] is False      # pela commodity COUPON/MISC ITEMS
    assert fato[101013]["is_refund_discount"] is True
    assert fato[100010]["is_refund_discount"] is False


def test_orfao_aponta_para_desconhecido_e_e_contado(cfg):
    fato = linhas(cfg, "context/sales/fact_sales")
    orfa = next(r for r in fato if r["basket_id"] == 102)
    assert orfa["product_id"] == -1 and orfa["is_merchandise"] is None
    assert len(fato) == 5
    reg = {r["tabela"]: r for r in controle(cfg)}["context/sales/fact_sales"]
    assert "orfaos_produto=1" in reg["mensagem"] and "orfaos_loja=0" in reg["mensagem"]


def test_faturamento_por_is_merchandise_fecha_com_o_total(config):
    """true + false + nulo = total (S12): a venda órfã (produto -1) não é mercadoria nem não mercadoria, cai no nulo."""
    escrever(Path(config).parent / "raw", "transaction_data.csv",
             TRANSACOES + ["4,103,8,98,1,10.00,503,0,1000,2,0,0"])   # órfã de US$ 10 (produto 98 sem cadastro)
    cfg = preparar(config)
    assert build.executar(cfg, agora=AGORA) == 0
    con = conectar_duckdb(cfg)
    con.register("fato", ler(cfg, "context/sales/fact_sales"))
    verdadeiro, falso, nulo, total = con.execute("""
        SELECT sum(sales_value) FILTER (WHERE is_merchandise = true),
               sum(sales_value) FILTER (WHERE is_merchandise = false),
               sum(sales_value) FILTER (WHERE is_merchandise IS NULL),
               sum(sales_value)
        FROM fato""").fetchall()[0]
    orfa = con.execute("SELECT product_id, is_merchandise FROM fato WHERE basket_id = 103").fetchall()
    assert orfa == [(-1, None)]
    assert nulo == Decimal("10.0000")                        # a órfã de 10 + a de ruído (0) da base mínima
    assert (verdadeiro, falso) == (Decimal("2.5000"), Decimal("31.0000"))
    assert verdadeiro + falso + nulo == total == Decimal("43.5000")


def test_grao_da_fact_sales_e_produto_na_cesta(cfg):
    """Grão da fact_sales: um produto numa cesta, chave basket_id + product_id (achado de 11/11/2026, S9).

    Exclui product_id = -1: duas vendas órfãs na mesma cesta (dois produtos sem cadastro) virariam o mesmo par
    (cesta, -1) por causa do membro desconhecido, sem que o dado de origem tenha repetição. Os órfãos são vigiados à
    parte pela contagem de órfãos da silver (orfaos_produto no controle, esperado 0 nos dados reais, P2).
    """
    con = conectar_duckdb(cfg)
    con.register("fato", ler(cfg, "context/sales/fact_sales"))
    linhas_, pares, nulos = con.execute("""
        SELECT count(*), count(DISTINCT (basket_id, product_id)),
               count(*) FILTER (WHERE basket_id IS NULL OR product_id IS NULL)
        FROM fato WHERE product_id <> -1""").fetchall()[0]
    assert linhas_ == pares == 4 and nulos == 0


@pytest.mark.parametrize("limite,codigo", [(0.10, 1), (0.25, 0)])
def test_orfaos_acima_do_limite_param_a_silver(config, limite, codigo):
    """Órfãos (P2) acima do limite da P6 são erro e a fact_sales não é gravada (S13); abaixo, o membro -1 absorve."""
    escrever(Path(config).parent / "raw", "transaction_data.csv", TRANSACOES[:6])   # as 5 válidas, 1 órfã = 20%
    cfg = preparar(config, limite_rejeicao=limite)
    assert build.executar(cfg, agora=AGORA) == codigo
    reg = {r["tabela"]: r for r in controle(cfg)}
    assert reg["clean/transaction_data"]["linhas_rejeitadas"] == 0
    fato = reg["context/sales/fact_sales"]
    assert "orfaos_produto=1" in fato["mensagem"] and "orfaos_loja=0" in fato["mensagem"]   # contagem continua
    if codigo:
        assert fato["status"] == "erro"
        assert f"órfãos acima do limite de {limite:.0%}: orfaos_produto 20.00%; tabela não gravada" in fato["mensagem"]
        assert not caminho_tabela(cfg, "silver", "context/sales/fact_sales").exists()
    else:
        assert fato["status"] == "sucesso" and "acima do limite" not in fato["mensagem"]
        assert len(linhas(cfg, "context/sales/fact_sales")) == 5


@pytest.mark.parametrize("tabela,chave", [
    ("product/dim_product", "product_id"), ("sales/dim_store", "store_id"),
    ("customer/dim_household", "household_key"), ("shared/dim_date", "day"),
])
def test_dimensoes_com_chave_unica_sem_nulos_e_desconhecido(cfg, tabela, chave):
    chaves = [r[chave] for r in linhas(cfg, f"context/{tabela}")]
    assert None not in chaves
    assert len(chaves) == len(set(chaves))
    assert -1 in chaves


def test_dim_product(cfg):
    p = {r["product_id"]: r for r in linhas(cfg, "context/product/dim_product")}
    assert p[14]["department"] == "UNKNOWN" and p[14]["commodity_desc"] == "UNKNOWN"
    assert p[14]["is_merchandise"] is True
    assert p[12]["is_merchandise"] is False and p[13]["is_merchandise"] is False
    assert p[-1]["is_merchandise"] is None


def test_dim_household(cfg):
    h = {r["household_key"]: r for r in linhas(cfg, "context/customer/dim_household")}
    assert set(h) == {1, 2, 3, 4, -1}                       # venda ∪ demografia (+ desconhecido)
    assert h[1]["has_demographics"] and h[4]["has_demographics"]
    assert not h[2]["has_demographics"] and h[2]["age_desc"] is None
    assert (h[1]["age_band_order"], h[1]["income_band_order"]) == (4, 5)
    assert (h[4]["age_band_order"], h[4]["income_band_order"]) == (6, 1)
    assert h[4]["homeowner_desc"] == "Unknown"               # mantido como veio (S9.9)


def test_dim_date_usa_week_no_do_arquivo_e_data_base(cfg):
    d = {r["day"]: r for r in linhas(cfg, "context/shared/dim_date")}
    assert set(d) == {1, 6, 7, -1}
    assert d[1]["date"] == date(2016, 1, 1)
    assert d[6]["week_no"] == 2                              # ceil(6/7) = 1: o código não calcula a semana
    assert d[6]["day_of_cycle"] == 1 and d[7]["day_of_cycle"] == 2 and d[1]["day_of_cycle"] == 3
    assert (d[7]["date"], d[7]["month"], d[7]["year"]) == (date(2016, 1, 7), 1, 2016)
    assert (d[1]["days_in_week"], d[6]["days_in_week"], d[7]["days_in_week"]) == (1, 2, 2)
    assert not any(d[k]["is_complete_week"] for k in (1, 6, 7))
    assert d[-1]["days_in_week"] is None and d[-1]["is_complete_week"] is None


def test_dim_date_marca_semana_completa(config):
    # semana 2 com os 7 dias (day 6 a 12); semana 1 só com o day 1
    extras = [f"5,{400 + d},{d},10,1,1.00,500,0,1000,2,0,0" for d in range(8, 13)]
    escrever(Path(config).parent / "raw", "transaction_data.csv", TRANSACOES + extras)
    cfg = preparar(config)
    assert build.executar(cfg, agora=AGORA) == 0
    d = {r["day"]: r for r in linhas(cfg, "context/shared/dim_date")}
    assert all(d[k]["days_in_week"] == 7 and d[k]["is_complete_week"] for k in range(6, 13))
    assert d[1]["days_in_week"] == 1 and d[1]["is_complete_week"] is False


def test_dia_com_duas_semanas_e_erro(config):
    escrever(Path(config).parent / "raw", "transaction_data.csv", TRANSACOES + ["1,300,1,10,1,1.00,500,0,0930,2,0,0"])
    cfg = preparar(config)
    assert build.executar(cfg, agora=AGORA) == 1
    reg = {r["tabela"]: r for r in controle(cfg)}
    assert "day com mais de um week_no" in reg["context/shared/dim_date"]["mensagem"]
    assert not (cfg["paths"]["lake"] / "silver" / "context" / "shared" / "dim_date").exists()
    assert "context/sales/fact_sales" not in reg             # parou na tabela que falhou


# ---------------------------------------------------------------- execução

def test_idempotencia(config):
    cfg = preparar(config)
    assert build.executar(cfg, agora=AGORA) == 0
    antes = {r["tabela"]: (r["linhas_entrada"], r["linhas_saida"], r["linhas_rejeitadas"]) for r in controle(cfg)}
    assert build.executar(cfg, agora=AGORA.replace(hour=11)) == 0
    regs = controle(cfg)
    assert len(regs) == 2 * len(antes)
    depois = {r["tabela"]: (r["linhas_entrada"], r["linhas_saida"], r["linhas_rejeitadas"])
              for r in regs if r["processado_em"].hour == 11}
    assert depois == antes
    assert len(linhas(cfg, "context/sales/fact_sales")) == 5


def test_le_a_carga_mais_recente_da_bronze(config):
    cfg = preparar(config)
    escrever(cfg["paths"]["raw"], "transaction_data.csv", TRANSACOES[:2])   # dia seguinte: 1 linha só
    ingest.executar(cfg, agora=AGORA.replace(day=29))
    assert build.executar(cfg, agora=AGORA) == 0
    assert len(linhas(cfg, "clean/transaction_data")) == 1
    assert {r["_data_carga"] for r in linhas(cfg, "clean/transaction_data")} == {"2026-10-29"}


def test_sem_bronze_e_erro(config):
    cfg = carregar_config(config)
    assert build.executar(cfg, agora=AGORA) == 1
    assert all(r["status"] == "erro" for r in controle(cfg))


# ---------------------------------------------------------------- espiar.py na silver

_spec = importlib.util.spec_from_file_location("espiar", RAIZ / "scripts" / "espiar.py")
espiar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(espiar)


@pytest.mark.parametrize("alvo", ["silver/clean/transaction_data", "silver/context/sales/fact_sales",
                                  "silver/_rejected/transaction_data", "silver/_controle_silver"])
@pytest.mark.parametrize("modo", ["topo", "amostra", "colunas", "resumo", "contagem", "versoes"])
def test_espiar_na_silver(config_pronto, alvo, modo, capsys):
    assert espiar.main([alvo, modo, "3", "--config", str(config_pronto)]) == 0
    assert alvo in capsys.readouterr().out


def test_espiar_lista_tabelas_da_silver(config_pronto, capsys):
    assert espiar.main(["silver/nao_existe", "--config", str(config_pronto)]) == 2
    erro = capsys.readouterr().err
    assert "context/sales/fact_sales" in erro and "_rejected/transaction_data" in erro
