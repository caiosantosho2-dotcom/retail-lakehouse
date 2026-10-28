"""CSVs mínimos e um lake temporário para os testes (nunca a base real)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.comum import carregar_config

# Duas tabelas pequenas no formato da Dunnhumby. Valores escolhidos para mostrar que nada é convertido:
# zeros à esquerda, notação científica e texto com vírgula entre aspas.
CSVS = {
    "vendas.csv": (
        "household_key,BASKET_ID,SALES_VALUE,TRANS_TIME\n"
        "2375,26984851472,1.39,0001\n"
        "2375,26984851472,5.55E-17,1631\n"
        "1364,26984896261,2.99,0000\n"
    ),
    "produto.csv": (
        "PRODUCT_ID,DEPARTMENT,BRAND\n"
        "25671,GROCERY,National\n"
        "26081,\"MISC, SALES TRAN\",Private\n"
    ),
}
COLUNAS = {
    "vendas": ["household_key", "BASKET_ID", "SALES_VALUE", "TRANS_TIME"],
    "produto": ["PRODUCT_ID", "DEPARTMENT", "BRAND"],
}


@pytest.fixture
def ambiente(tmp_path: Path) -> Path:
    """Cria raw/ com os CSVs, um lake vazio e o config.yaml. Devolve o caminho do config."""
    raw = tmp_path / "raw"
    raw.mkdir()
    for nome, conteudo in CSVS.items():
        (raw / nome).write_text(conteudo, encoding="utf-8", newline="")
    cfg = {
        "paths": {"raw": "raw", "lake": "lake"},
        "duckdb": {"memory_limit": "256MB", "threads": 1},
        "bronze": {
            "batch_rows": 2,  # lotes menores que o arquivo: exercita a gravação em vários lotes
            "fuso": "America/Sao_Paulo",
            "tabelas": [
                {"tabela": "vendas", "arquivo": "vendas.csv", "colunas": COLUNAS["vendas"]},
                {"tabela": "produto", "arquivo": "produto.csv", "colunas": COLUNAS["produto"]},
            ],
        },
    }
    caminho = tmp_path / "config.yaml"
    caminho.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return caminho


@pytest.fixture
def cfg(ambiente: Path) -> dict:
    return carregar_config(ambiente)
