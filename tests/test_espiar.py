"""Testes do scripts/espiar.py: todos os modos rodam e o lake nunca é alterado."""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.bronze import ingest
from src.comum import RAIZ

_spec = importlib.util.spec_from_file_location("espiar", RAIZ / "scripts" / "espiar.py")
espiar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(espiar)

SP = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def lake_pronto(ambiente: Path, cfg: dict) -> Path:
    """Duas cargas (dias 27 e 28) para haver partições e versões a escolher."""
    ingest.executar(cfg, agora=datetime(2026, 10, 27, 10, tzinfo=SP))
    ingest.executar(cfg, agora=datetime(2026, 10, 28, 10, tzinfo=SP))
    return ambiente


def rodar(config: Path, *args: str) -> int:
    return espiar.main([*args, "--config", str(config)])


def foto_do_lake(lake: Path) -> dict:
    return {p.relative_to(lake).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in lake.rglob("*") if p.is_file()}


@pytest.mark.parametrize("modo", ["topo", "amostra", "colunas", "resumo", "contagem", "cargas", "versoes"])
def test_cada_modo_roda(lake_pronto, modo, capsys):
    assert rodar(lake_pronto, "bronze/vendas", modo, "2") == 0
    assert "bronze/vendas" in capsys.readouterr().out


def test_padrao_e_carga_mais_recente(lake_pronto, capsys):
    assert rodar(lake_pronto, "bronze/vendas", "contagem") == 0
    saida = capsys.readouterr().out
    assert "carga 2026-10-28" in saida and "3" in saida


def test_controle_sem_modo(lake_pronto, capsys):
    assert rodar(lake_pronto, "bronze/_controle_cargas") == 0
    assert "sucesso" in capsys.readouterr().out


def test_carga_e_versao_validas(lake_pronto, capsys):
    assert rodar(lake_pronto, "bronze/vendas", "contagem", "--carga", "2026-10-27") == 0
    assert "carga 2026-10-27" in capsys.readouterr().out
    assert rodar(lake_pronto, "bronze/vendas", "contagem", "--versao", "0") == 0
    assert "versão 0" in capsys.readouterr().out


def test_carga_inexistente_lista_disponiveis(lake_pronto, capsys):
    assert rodar(lake_pronto, "bronze/vendas", "topo", "--carga", "2020-01-01") == 2
    erro = capsys.readouterr().err
    assert "2026-10-27" in erro and "2026-10-28" in erro


def test_versao_inexistente_lista_disponiveis(lake_pronto, capsys):
    assert rodar(lake_pronto, "bronze/vendas", "topo", "--versao", "99") == 2
    assert "[0, 1]" in capsys.readouterr().err


def test_tabela_inexistente_lista_tabelas(lake_pronto, capsys):
    assert rodar(lake_pronto, "bronze/nao_existe") == 2
    erro = capsys.readouterr().err
    assert "vendas" in erro and "produto" in erro and "_controle_cargas" in erro


def test_csv(lake_pronto, tmp_path):
    saida = tmp_path / "resultado.csv"
    assert rodar(lake_pronto, "bronze/vendas", "topo", "5", "--csv", str(saida)) == 0
    linhas = saida.read_text(encoding="utf-8").splitlines()
    assert linhas[0].startswith("household_key") and len(linhas) == 4


def test_csv_dentro_do_lake_e_recusado(lake_pronto, cfg):
    assert rodar(lake_pronto, "bronze/vendas", "--csv", str(cfg["paths"]["lake"] / "x.csv")) == 2
    assert not (cfg["paths"]["lake"] / "x.csv").exists()


def test_nunca_altera_o_lake(lake_pronto, cfg, tmp_path):
    lake = cfg["paths"]["lake"]
    antes = foto_do_lake(lake)
    for tabela in ("bronze/vendas", "bronze/produto", "bronze/_controle_cargas"):
        for modo in espiar.MODOS:
            rodar(lake_pronto, tabela, modo, "3")
        rodar(lake_pronto, tabela, "topo", "--versao", "0", "--csv", str(tmp_path / "x.csv"))
    rodar(lake_pronto, "bronze/vendas", "topo", "--carga", "2026-10-27")
    assert foto_do_lake(lake) == antes
