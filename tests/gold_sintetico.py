"""Silver sintética para os testes da gold: só as colunas que a gold lê, gravadas direto em Delta numa pasta temporária.

Quatro perfis de cliente, com padrão que se repete em todo bloco de 26 semanas (assim a segmentação dá os mesmos nomes
na janela atual, na do ano anterior e na do backtest, que o CLV exige):
- fiel: compra quase toda semana, cesta grande;
- regular: compra cerca de 1 semana em 2, cesta média;
- esporádico: compra cerca de 1 semana em 5, cesta pequena;
- em pausa: compra só nas 6 primeiras semanas de cada bloco de 26 (recência alta no fim de cada janela).
Mais clientes que só compram nas semanas 1–20 (sem compra nas janelas) e um produto de não mercadoria.
Semanas de 7 dias (day = 7 * (week - 1) + 1..7); a semana 102 tem só 3 dias e fica fora da janela.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
from deltalake import write_deltalake

PERFIS = {"fiel": (60, 0.9, 60.0), "regular": (70, 0.5, 30.0), "esporadico": (50, 0.2, 12.0), "pausa": (30, 0.8, 25.0),
          "antigo": (10, 0.6, 20.0)}
ULTIMA_SEMANA = 102
DIAS_ULTIMA_SEMANA = 3


def compra(perfil: str, semana: int, rng: np.random.Generator, prob: float) -> bool:
    if perfil == "pausa":
        return (semana - 24) % 26 < 6 and rng.random() < prob
    if perfil == "antigo":
        return semana <= 20 and rng.random() < prob
    return rng.random() < prob


def gerar(lake: Path, semente: int = 7) -> dict:
    rng = np.random.default_rng(semente)
    linhas = {c: [] for c in ("household_key", "basket_id", "store_id", "product_id", "day", "week_no", "quantity",
                              "sales_value", "retail_disc", "coupon_disc", "coupon_match_disc", "is_merchandise")}
    hh, cesta, perfil_de = 0, 0, {}
    for perfil, (n, prob, ticket) in PERFIS.items():
        for _ in range(n):
            hh += 1
            perfil_de[hh] = perfil
            for semana in range(1, ULTIMA_SEMANA + 1):
                if not compra(perfil, semana, rng, prob):
                    continue
                dias = DIAS_ULTIMA_SEMANA if semana == ULTIMA_SEMANA else 7
                dia = 7 * (semana - 1) + int(rng.integers(1, dias + 1))
                cesta += 1
                for produto, merc in ((1, True), (2, True), (9, False)):
                    if produto == 9 and rng.random() > 0.1:
                        continue
                    valor = round(float(ticket * rng.uniform(0.3, 0.7)), 2)
                    desc = round(-valor * float(rng.uniform(0, 0.3)), 2)
                    for c, v in (("household_key", hh), ("basket_id", cesta), ("store_id", 1 + hh % 3),
                                 ("product_id", produto), ("day", dia), ("week_no", semana), ("quantity", 1),
                                 ("sales_value", valor), ("retail_disc", desc), ("coupon_disc", 0.0),
                                 ("coupon_match_disc", 0.0), ("is_merchandise", merc)):
                        linhas[c].append(v)
    dec = pa.decimal128(18, 4)
    fact = pa.table({
        **{c: pa.array(linhas[c], pa.int64()) for c in ("household_key", "basket_id", "store_id", "product_id")},
        **{c: pa.array(linhas[c], pa.int32()) for c in ("day", "week_no", "quantity")},
        **{c: pa.array([round(v, 4) for v in linhas[c]], pa.float64()).cast(dec) for c in
           ("sales_value", "retail_disc", "coupon_disc", "coupon_match_disc")},
        "is_merchandise": pa.array(linhas["is_merchandise"], pa.bool_()),
    })
    dias = [(d, (d - 1) // 7 + 1) for d in range(1, 7 * (ULTIMA_SEMANA - 1) + DIAS_ULTIMA_SEMANA + 1)]
    n_semana = {w: sum(1 for _, s in dias if s == w) for w in range(1, ULTIMA_SEMANA + 1)}
    dim_date = pa.table({
        "day": pa.array([d for d, _ in dias] + [-1], pa.int32()),
        "date": pa.array([date(2016, 1, 1) + timedelta(days=d - 1) for d, _ in dias] + [None], pa.date32()),
        "week_no": pa.array([w for _, w in dias] + [None], pa.int32()),
        "days_in_week": pa.array([n_semana[w] for _, w in dias] + [None], pa.int32()),
        "is_complete_week": pa.array([n_semana[w] == 7 for _, w in dias] + [None], pa.bool_()),
    })
    dim_household = pa.table({"household_key": pa.array(list(range(1, hh + 1)) + [-1], pa.int64()),
                              "has_demographics": pa.array([k % 3 == 0 for k in range(1, hh + 1)] + [False], pa.bool_())})
    for tabela, dado in (("context/sales/fact_sales", fact), ("context/shared/dim_date", dim_date),
                         ("context/customer/dim_household", dim_household)):
        write_deltalake(str(lake / "silver" / tabela), dado, mode="overwrite")
    return perfil_de
