"""Curva ROC do risco de pausa (G5): escrita aqui, não copiada do painel.

Entrada: as notas do conjunto de teste devolvidas pela cópia do churn (nota do modelo = probabilidade; nota da regra
simples = semanas desde a última compra) e o rótulo y. Saída: os pontos (fpr, tpr, corte) de cada classificador, com
`roc_curve(drop_intermediate=True)`, e a AUC recalculada pelas mesmas notas, para conferir com a do churn.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve

CLASSIFICADORES = {"model": "nota_modelo", "baseline": "nota_regra"}


def curvas(notas_teste: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    y = notas_teste["y"].to_numpy()
    linhas, aucs = [], {}
    for nome, coluna in CLASSIFICADORES.items():
        nota = notas_teste[coluna].to_numpy(dtype=float)
        fpr, tpr, corte = roc_curve(y, nota, drop_intermediate=True)
        aucs[nome] = float(roc_auc_score(y, nota))
        for i, (f, t, c) in enumerate(zip(fpr, tpr, corte)):
            # o primeiro corte do scikit-learn é +infinito (nenhum alerta): fica nulo na tabela
            linhas.append({"classifier": nome, "point": i, "fpr": float(f), "tpr": float(t),
                           "cutoff": None if np.isinf(c) else float(c)})
    return pd.DataFrame(linhas), aucs
