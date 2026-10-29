"""Parâmetros dos modelos no formato que o código copiado do RAG espera (CFG["analises"][...], CFG["semente"],
CFG["metricas"]["cliente_ativo_semanas"]), preenchidos a partir da seção `gold` do config.yaml.

`configurar(cfg)` é chamado uma vez antes de rodar os modelos. O dicionário é o mesmo objeto em todos os módulos
(`from src.gold.modelos.parametros import CFG`), então a atualização vale para todos.
"""
from __future__ import annotations

CFG: dict = {}

# Resultados já calculados nesta execução (substitui o cache em memória do RAG): o RFM é usado por CLV, risco de
# pausa e teste de desconto, e refazer a escolha de K a cada chamada custaria minutos sem mudar nada.
MEMO: dict = {}


def configurar(cfg: dict) -> None:
    g = cfg["gold"]
    CFG.clear()
    MEMO.clear()
    CFG.update({
        "semente": g["semente"],
        "analises": g["modelos"],
        "metricas": {"cliente_ativo_semanas": g["janela"]["cliente_ativo_semanas"]},
    })
