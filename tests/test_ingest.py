"""Testes da ingestão da bronze (src/bronze/ingest.py)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pyarrow as pa
from deltalake import DeltaTable

from src.bronze import ingest
from src.comum import caminho_tabela, conectar_duckdb, ler_delta

SP = ZoneInfo("America/Sao_Paulo")
D1 = datetime(2026, 10, 27, 10, 0, tzinfo=SP)
D2 = datetime(2026, 10, 28, 10, 0, tzinfo=SP)
RASTREIO = ["_arquivo_origem", "_data_carga", "_carregado_em"]


def ler(cfg, tabela, carga=None) -> pa.Table:
    con = conectar_duckdb(cfg)
    return ler_delta(con, caminho_tabela(cfg, "bronze", tabela), carga=carga).to_arrow_table()


def controle(cfg) -> list[dict]:
    return ler(cfg, ingest.CONTROLE).to_pylist()


def particoes(cfg, tabela) -> list[str]:
    dt = DeltaTable(str(caminho_tabela(cfg, "bronze", tabela)))
    return sorted(p["_data_carga"] for p in dt.partitions())


def test_carga_feliz(cfg):
    assert ingest.executar(cfg, agora=D1) == 0

    vendas = ler(cfg, "vendas", "2026-10-27")
    assert vendas.num_rows == 3
    for col in RASTREIO:
        assert vendas.column(col).null_count == 0
    dados = [f for f in vendas.schema if f.name not in RASTREIO]
    assert all(pa.types.is_string(f.type) or pa.types.is_large_string(f.type) for f in dados)
    assert set(vendas.column("_arquivo_origem").to_pylist()) == {"vendas.csv"}

    regs = {r["tabela"]: r for r in controle(cfg)}
    assert regs["vendas"]["status"] == "sucesso"
    assert regs["vendas"]["linhas_lidas"] == regs["vendas"]["linhas_gravadas"] == 3
    assert regs["produto"]["linhas_gravadas"] == 2
    assert regs["vendas"]["colunas_esperadas_ok"] is True
    assert regs["vendas"]["mensagem"] is None


def test_texto_preservado_exatamente(cfg):
    ingest.executar(cfg, agora=D1)
    vendas = ler(cfg, "vendas").to_pylist()
    assert {r["TRANS_TIME"] for r in vendas} == {"0001", "1631", "0000"}
    assert "5.55E-17" in {r["SALES_VALUE"] for r in vendas}
    assert "26984851472" in {r["BASKET_ID"] for r in vendas}
    assert "MISC, SALES TRAN" in {r["DEPARTMENT"] for r in ler(cfg, "produto").to_pylist()}


def test_data_carga_usa_dia_local_de_sao_paulo(cfg):
    # 22h em São Paulo = 01h UTC do dia seguinte. A partição tem que ser o dia local.
    noite_sp = datetime(2026, 10, 28, 22, 0, tzinfo=SP)
    assert noite_sp.astimezone(timezone.utc).date().isoformat() == "2026-10-29"

    ingest.executar(cfg, agora=noite_sp.astimezone(timezone.utc))  # mesmo instante, informado em UTC
    assert particoes(cfg, "vendas") == ["2026-10-28"]

    vendas = ler(cfg, "vendas")
    tipo = vendas.schema.field("_carregado_em").type
    assert tipo.tz == "America/Sao_Paulo"
    assert vendas.column("_carregado_em")[0].as_py() == noite_sp
    assert controle(cfg)[0]["data_carga"] == "2026-10-28"


def test_idempotencia_mesmo_dia(cfg):
    ingest.executar(cfg, agora=D1)
    ingest.executar(cfg, agora=D1)
    assert ler(cfg, "vendas", "2026-10-27").num_rows == 3
    assert particoes(cfg, "vendas") == ["2026-10-27"]
    regs = controle(cfg)
    assert len(regs) == 4  # 2 execuções x 2 tabelas
    assert all(r["status"] == "sucesso" for r in regs)


def test_historico_dois_dias(cfg):
    ingest.executar(cfg, agora=D1)
    antes_d1 = ler(cfg, "vendas", "2026-10-27")
    ingest.executar(cfg, agora=D2)

    assert particoes(cfg, "vendas") == ["2026-10-27", "2026-10-28"]
    depois_d1 = ler(cfg, "vendas", "2026-10-27")
    assert depois_d1.equals(antes_d1)  # carga do dia 1 intacta, inclusive _carregado_em
    assert ler(cfg, "vendas", "2026-10-28").num_rows == 3
    assert ler(cfg, "vendas").num_rows == 6


def test_data_carga_explicita(cfg):
    ingest.executar(cfg, data_carga="2026-01-15", agora=D1)
    assert particoes(cfg, "vendas") == ["2026-01-15"]


def _status(cfg) -> dict:
    return {r["tabela"]: r for r in controle(cfg)}


def test_arquivo_faltando(cfg):
    (cfg["paths"]["raw"] / "vendas.csv").unlink()
    assert ingest.executar(cfg, agora=D1) == 1
    regs = _status(cfg)
    assert regs["vendas"]["status"] == "erro"
    assert "não encontrado" in regs["vendas"]["mensagem"]
    assert regs["produto"]["status"] == "sucesso"
    assert ler(cfg, "produto").num_rows == 2


def test_coluna_errada(cfg):
    (cfg["paths"]["raw"] / "vendas.csv").write_text("household_key,BASKET_ID,VALOR,TRANS_TIME\n1,2,3,4\n")
    assert ingest.executar(cfg, agora=D1) == 1
    regs = _status(cfg)
    assert regs["vendas"]["status"] == "erro"
    assert regs["vendas"]["colunas_esperadas_ok"] is False
    assert "SALES_VALUE" in regs["vendas"]["mensagem"]
    assert regs["produto"]["status"] == "sucesso"
    assert not (caminho_tabela(cfg, "bronze", "vendas") / "_delta_log").exists()


def test_colunas_fora_de_ordem(cfg):
    (cfg["paths"]["raw"] / "produto.csv").write_text("DEPARTMENT,PRODUCT_ID,BRAND\nA,1,B\n")
    assert ingest.executar(cfg, agora=D1) == 1
    assert "outra ordem" in _status(cfg)["produto"]["mensagem"]


def test_arquivo_vazio_e_so_cabecalho(cfg):
    (cfg["paths"]["raw"] / "vendas.csv").write_text("")
    (cfg["paths"]["raw"] / "produto.csv").write_text("PRODUCT_ID,DEPARTMENT,BRAND\n")
    assert ingest.executar(cfg, agora=D1) == 1
    regs = _status(cfg)
    assert regs["vendas"]["status"] == "erro" and "vazio" in regs["vendas"]["mensagem"]
    assert regs["produto"]["status"] == "erro" and "só com cabeçalho" in regs["produto"]["mensagem"]
    assert regs["produto"]["colunas_esperadas_ok"] is True


def test_contagem_divergente_restaura_versao_anterior(cfg, monkeypatch):
    ingest.executar(cfg, agora=D1)
    destino = caminho_tabela(cfg, "bronze", "vendas")
    antes = ler(cfg, "vendas", "2026-10-27")
    versao_antes = DeltaTable(str(destino)).version()

    # Arquivo novo com 1 linha a mais; a conferência finge que a gravação perdeu linhas.
    with (cfg["paths"]["raw"] / "vendas.csv").open("a", newline="") as f:
        f.write("9999,1,1.00,1200\n")
    monkeypatch.setattr(ingest, "contar_particao", lambda con, destino, dia: 0)
    segunda = D1.replace(hour=11)  # mesmo dia, uma hora depois
    assert ingest.executar(cfg, agora=segunda) == 1

    reg = next(r for r in controle(cfg) if r["tabela"] == "vendas" and r["carregado_em"] == segunda)
    assert reg["status"] == "erro"
    assert "restaurada para a versão" in reg["mensagem"]
    assert ler(cfg, "vendas", "2026-10-27").equals(antes)
    assert DeltaTable(str(destino)).history(1)[0]["operation"] == "RESTORE"
    assert DeltaTable(str(destino)).version() > versao_antes


def test_contagem_divergente_em_tabela_nova_apaga_particao(cfg, monkeypatch):
    monkeypatch.setattr(ingest, "contar_particao", lambda con, destino, dia: -1)
    assert ingest.executar(cfg, agora=D1) == 1
    assert ler(cfg, "vendas").num_rows == 0
    assert "partição do dia apagada" in _status(cfg)["vendas"]["mensagem"]
