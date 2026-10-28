"""Peças compartilhadas pelas camadas, pelo espiar.py, pelo notebook e pelos testes.

Regra F3: tabela Delta se lê pelo _delta_log (DeltaTable), nunca pelos .parquet da pasta.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import yaml
from deltalake import DeltaTable

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_PADRAO = RAIZ / "config.yaml"


def carregar_config(caminho: str | Path | None = None) -> dict:
    """Lê o config.yaml e resolve os caminhos relativos a partir da pasta do próprio config."""
    caminho = Path(caminho) if caminho else CONFIG_PADRAO
    if not caminho.exists():
        raise FileNotFoundError(f"Config não encontrado: {caminho}. Copie config.example.yaml para config.yaml.")
    cfg = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    base = caminho.resolve().parent
    cfg["paths"] = {nome: (base / valor).resolve() for nome, valor in cfg["paths"].items()}
    return cfg


def conectar_duckdb(cfg: dict) -> duckdb.DuckDBPyConnection:
    """Conexão em memória com os limites do config (notebook com pouca RAM)."""
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{cfg['duckdb']['memory_limit']}'")
    con.execute(f"SET threads = {int(cfg['duckdb']['threads'])}")
    # Texto como string comum do Arrow (o deltalake não precisa lidar com string_view).
    con.execute("SET produce_arrow_string_view = false")
    return con


def caminho_tabela(cfg: dict, camada: str, tabela: str) -> Path:
    return cfg["paths"]["lake"] / camada / tabela


def eh_delta(caminho: Path) -> bool:
    return (caminho / "_delta_log").is_dir()


def ler_delta(con: duckdb.DuckDBPyConnection, caminho: str | Path,
              carga: str | None = None, versao: int | None = None) -> duckdb.DuckDBPyRelation:
    """Relação DuckDB sobre a versão atual (ou `versao`) da tabela Delta, opcionalmente só a partição `carga`.

    O dataset Arrow é lido sob demanda: o DuckDB só puxa as colunas e partições que a consulta usa.
    """
    dt = DeltaTable(str(caminho), version=versao)
    filtro = [("_data_carga", "=", carga)] if carga else None
    return con.from_arrow(dt.to_pyarrow_dataset(file_pruning_predicate=filtro))
