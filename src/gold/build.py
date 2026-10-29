"""Gold: `python -m src.gold.build` (spec da fase 3).

Parada 3a: base comum (sql/gold/base, views sobre a silver) e modelos estatísticos copiados do RAG
(src/gold/modelos). Três áreas (G12): lake/gold/features/ (as variáveis que entraram nos modelos, como o RAG as
calcula), lake/gold/models/ (resultados) e lake/gold/metrics/ (métricas do painel, na 3b). A exportação entra na 3c.
Cada execução reconstrói as tabelas (nova versão Delta). Uma falha para a execução e as tabelas já gravadas
continuam na versão anterior; o controle (lake/gold/_controle_gold) registra o que aconteceu.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from src.comum import RAIZ, caminho_tabela, carregar_config, conectar_duckdb, eh_delta, registrar_delta
from src.gold.modelos import churn, clv, parametros, rfm, roc, teste_desconto

CONTROLE = "_controle_gold"
BASE_SQL = RAIZ / "sql" / "gold" / "base"
SILVER = {"fact_sales": "context/sales/fact_sales", "dim_date": "context/shared/dim_date",
          "dim_household": "context/customer/dim_household"}
# Views da base que os modelos consultam muitas vezes: viram tabela temporária (como as views materializadas do RAG).
MATERIALIZAR = {"customer_week", "customer_metrics"}


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
    return con


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


# ---------------------------------------------------------------- execução

def registrar_controle(cfg: dict, registros: list[dict], processado_em: datetime, versao: int | None) -> None:
    esquema = esquema_controle(cfg["bronze"]["fuso"])
    linhas = [{**{c.name: r.get(c.name) for c in esquema}, "processado_em": processado_em, "versao_fact_sales": versao}
              for r in registros]
    write_deltalake(str(caminho_tabela(cfg, "gold", CONTROLE)), pa.Table.from_pylist(linhas, schema=esquema), mode="append")


def executar(cfg: dict, etapa: str = "modelos", agora: datetime | None = None) -> int:
    """Reconstrói a gold. Devolve 0 se tudo deu certo, 1 em qualquer erro."""
    fuso = ZoneInfo(cfg["bronze"]["fuso"])
    processado_em = (agora or datetime.now(fuso)).astimezone(fuso)
    faltando = [t for t in SILVER.values() if not eh_delta(caminho_tabela(cfg, "silver", t))]
    if faltando:
        print(f"A silver não está pronta (faltam: {', '.join(faltando)}): rode `python -m src.silver.build` antes.")
        return 1
    versao = DeltaTable(str(caminho_tabela(cfg, "silver", SILVER["fact_sales"]))).version()
    registros: list[dict] = []
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
    registrar_controle(cfg, registros, processado_em, versao)

    print(f"\nResumo da gold ({processado_em:%Y-%m-%d %H:%M %Z}; fact_sales versão {versao})")
    for r in registros:
        linhas = f"{r['linhas']:,}" if r.get("linhas") is not None else "-"
        print(f"{r['tabela']:<34} {linhas:>8}  {r['status']}")
        if r.get("mensagem"):
            print(f"    -> {r['mensagem']}")
    ok = bool(registros) and all(r["status"] == "sucesso" for r in registros) and len(sumario) > 0
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstrói a gold a partir da silver.")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    parser.add_argument("--etapa", choices=["modelos"], default="modelos",
                        help="parte da gold a rodar (parada 3a: só os modelos; métricas entram na 3b)")
    args = parser.parse_args(argv)
    return executar(carregar_config(args.config), args.etapa)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
