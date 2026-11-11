"""Silver: reconstrói clean e context a partir da carga mais recente da bronze (P8).

Uso: python -m src.silver.build [--config config.yaml]

- clean: uma tabela por arquivo, tipada, snake_case, regras globais + específicas declaradas no config (S8);
  o que falhar vai para silver/_rejected/<tabela> com o motivo (S3).
- context: star schema a partir das consultas em sql/silver/ (S2), com membro desconhecido -1 (P2).
Decisões: S1–S9, P1–P8, A1–A3 em docs/decisoes_arquitetura_lakehouse.md.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from src.comum import RAIZ, caminho_tabela, carregar_config, conectar_duckdb, eh_delta, ler_delta, registrar_delta

CONTROLE = "_controle_silver"
REJEITADOS = "_rejected"


def q(nome: str) -> str:
    """Identificador SQL entre aspas."""
    return '"' + nome.replace('"', '""') + '"'


def esquema_controle(fuso: str) -> pa.Schema:
    return pa.schema([
        ("tabela", pa.string()),
        ("camada", pa.string()),
        ("data_carga_bronze", pa.string()),
        ("processado_em", pa.timestamp("us", tz=fuso)),
        ("linhas_entrada", pa.int64()),
        ("linhas_saida", pa.int64()),
        ("linhas_rejeitadas", pa.int64()),
        ("pct_rejeitado", pa.float64()),
        ("status", pa.string()),
        ("mensagem", pa.string()),
    ])


def preparar_conexao(cfg: dict, processado_em: datetime) -> duckdb.DuckDBPyConnection:
    """Conexão com os limites do config e os parâmetros da silver como variáveis SQL (getvariable)."""
    s = cfg["silver"]
    con = conectar_duckdb(cfg)
    con.execute(f"SET TimeZone = '{cfg['bronze']['fuso']}'")
    variaveis = {
        "day_min": (s["faixas"]["day"][0], "INTEGER"), "day_max": (s["faixas"]["day"][1], "INTEGER"),
        "week_no_min": (s["faixas"]["week_no"][0], "INTEGER"), "week_no_max": (s["faixas"]["week_no"][1], "INTEGER"),
        "data_base": (str(s["data_base"]), "DATE"),
        "departamentos_nao_mercadoria": (s["nao_mercadoria"]["departamentos"], "VARCHAR[]"),
        "commodities_nao_mercadoria": (s["nao_mercadoria"]["commodities"], "VARCHAR[]"),
        "ordem_idade": (s["ordem_faixas"]["idade"], "VARCHAR[]"),
        "ordem_renda": (s["ordem_faixas"]["renda"], "VARCHAR[]"),
        "processado_em": (processado_em.isoformat(), "TIMESTAMPTZ"),
    }
    for nome, (valor, tipo) in variaveis.items():
        con.execute(f"SET VARIABLE {nome} = ?::{tipo}", [valor])
    return con


def contar(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return con.sql(sql).fetchall()[0][0]


def carga_mais_recente(cfg: dict, tabela_bronze: str) -> str:
    caminho = caminho_tabela(cfg, "bronze", tabela_bronze)
    if not eh_delta(caminho):
        raise FileNotFoundError(f"bronze/{tabela_bronze} não existe: rode a ingestão da bronze primeiro")
    datas = {p["_data_carga"] for p in DeltaTable(str(caminho)).partitions()}
    if not datas:
        raise ValueError(f"bronze/{tabela_bronze} não tem nenhuma carga")
    return max(datas)


def gravar(con: duckdb.DuckDBPyConnection, cfg: dict, sql: str, destino: Path) -> None:
    """Grava o resultado da consulta em Delta, em lotes, substituindo a tabela (nova versão; L1/P8)."""
    leitor = con.sql(sql).to_arrow_reader(int(cfg["silver"]["batch_rows"]))
    write_deltalake(str(destino), leitor, mode="overwrite", schema_mode="overwrite")


# ---------------------------------------------------------------- clean

def sql_clean(item: dict, origem: str) -> str:
    """Consulta com as colunas originais (__o_*), as tipadas, as derivadas, as marcações e o _motivo de rejeição.

    O _motivo é o da primeira regra que falhar, nesta ordem: invalid_number, null_key,
    rejeições do config (em ordem), duplicate_key. Nulo = linha aceita.
    """
    colunas = item["colunas"]
    originais = [f"{q(c['origem'])} AS {q('__o_' + c['origem'])}" for c in colunas]
    tipadas = []
    invalidas = []
    for c in colunas:
        texto = f"NULLIF(TRIM({q(c['origem'])}), '')"
        if c["tipo"].upper() == "VARCHAR":
            tipadas.append(f"{texto} AS {q(c['nome'])}")
        else:
            tipadas.append(f"TRY_CAST({texto} AS {c['tipo']}) AS {q(c['nome'])}")
            # Texto preenchido que não converteu: nunca vira nulo em silêncio.
            invalidas.append(f"(NULLIF(TRIM({q('__o_' + c['origem'])}), '') IS NOT NULL AND {q(c['nome'])} IS NULL)")
    derivadas = [f"{d['expressao']} AS {q(d['nome'])}" for d in item.get("derivadas", [])]
    chave = item.get("chave", [])
    if chave:
        derivadas.append(f"count(*) OVER (PARTITION BY {', '.join(q(k) for k in chave)}) AS __n_chave")

    casos = []
    if invalidas:
        casos.append(("invalid_number", " OR ".join(invalidas)))
    obrigatorias = list(dict.fromkeys(item.get("obrigatorias", []) + chave))
    if obrigatorias:
        casos.append(("null_key", " OR ".join(f"{q(k)} IS NULL" for k in obrigatorias)))
    casos += [(r["motivo"], r["condicao"]) for r in item.get("rejeicoes", [])]
    if chave:
        casos.append(("duplicate_key", "__n_chave > 1"))
    motivo = "CASE " + " ".join(f"WHEN COALESCE(({cond}), false) THEN '{m}'" for m, cond in casos) + " END" \
        if casos else "NULL::VARCHAR"

    return f"""
        WITH t AS (SELECT {', '.join(originais + tipadas)}, _data_carga FROM {origem}),
             d AS (SELECT *{''.join(', ' + x for x in derivadas)} FROM t)
        SELECT *, {motivo} AS _motivo FROM d
    """


def construir_clean(con: duckdb.DuckDBPyConnection, cfg: dict, item: dict) -> dict:
    tabela = item["tabela"]
    registro = {"tabela": f"clean/{tabela}", "camada": "clean", "status": "erro"}
    carga = carga_mais_recente(cfg, item["origem"])
    registro["data_carga_bronze"] = carga

    origem = f"bronze_{tabela}"
    registrar_delta(con, origem, caminho_tabela(cfg, "bronze", item["origem"]), carga=carga)
    base = sql_clean(item, origem)

    finais = [q(c["nome"]) for c in item["colunas"] if not c.get("descartar")]
    finais += [q(d["nome"]) for d in item.get("derivadas", [])]
    finais += [f"({m['condicao']}) AS {q(m['nome'])}" for m in item.get("marcacoes", [])]
    sql_aceitas = f"""SELECT {', '.join(finais)}, _data_carga, getvariable('processado_em') AS _processado_em
                      FROM ({base}) WHERE _motivo IS NULL"""
    originais = [f"{q('__o_' + c['origem'])} AS {q(c['origem'])}" for c in item["colunas"]]
    sql_rejeitadas = f"""SELECT {', '.join(originais)}, _motivo, _data_carga, getvariable('processado_em') AS _processado_em
                         FROM ({base}) WHERE _motivo IS NOT NULL"""

    destino = caminho_tabela(cfg, "silver", f"clean/{tabela}")
    destino_rej = caminho_tabela(cfg, "silver", f"{REJEITADOS}/{tabela}")
    gravar(con, cfg, sql_aceitas, destino)
    gravar(con, cfg, sql_rejeitadas, destino_rej)

    # Conferência (S6): bronze = clean + rejeitadas, contando pelas tabelas Delta gravadas (F3).
    entrada = contar(con, f"SELECT count(*) FROM {origem}")
    saida = ler_delta(con, destino).aggregate("count(*)").fetchall()[0][0]
    rejeitadas = ler_delta(con, destino_rej)
    n_rej = rejeitadas.aggregate("count(*)").fetchall()[0][0]
    por_motivo = rejeitadas.aggregate("_motivo, count(*) AS n").order("n DESC").fetchall()
    pct = n_rej / entrada if entrada else 0.0
    registro.update(linhas_entrada=entrada, linhas_saida=saida, linhas_rejeitadas=n_rej, pct_rejeitado=pct)

    detalhe = ", ".join(f"{m}={n:,}" for m, n in por_motivo) or "nenhuma rejeitada"
    limite = float(cfg["silver"]["limite_rejeicao"])
    if entrada != saida + n_rej:
        registro["mensagem"] = f"bronze ({entrada:,}) != clean ({saida:,}) + rejeitadas ({n_rej:,})"
    elif pct > limite:
        registro["mensagem"] = f"rejeição {pct:.2%} acima do limite de {limite:.0%} ({detalhe})"
    else:
        registro["status"] = "sucesso"
        registro["mensagem"] = detalhe
    return registro


# ---------------------------------------------------------------- context

def nome_curto(tabela: str) -> str:
    return tabela.rsplit("/", 1)[-1]


def construir_context(con: duckdb.DuckDBPyConnection, cfg: dict, item: dict, carga: str) -> dict:
    tabela = item["tabela"]
    registro = {"tabela": f"context/{tabela}", "camada": "context", "data_carga_bronze": carga,
                "linhas_rejeitadas": 0, "pct_rejeitado": 0.0, "status": "erro"}
    sql = (RAIZ / item["sql"]).read_text(encoding="utf-8")

    for pre in item.get("pre_condicoes", []):
        n = contar(con, pre["sql"])
        if n:
            registro["mensagem"] = f"pré-condição falhou: {pre['nome']} ({n:,}); tabela não gravada"
            return registro

    chave = item.get("chave", [])
    if chave:
        # Chave não nula e única (regra global das dimensões), conferida antes de gravar.
        ks = ", ".join(q(k) for k in chave)
        nulas = contar(con, f"SELECT count(*) FROM ({sql}) WHERE " + " OR ".join(f"{q(k)} IS NULL" for k in chave))
        repetidas = contar(con, f"SELECT count(*) FROM (SELECT {ks} FROM ({sql}) GROUP BY ALL HAVING count(*) > 1)")
        if nulas or repetidas:
            registro["mensagem"] = f"chave {chave}: {nulas:,} nulas, {repetidas:,} repetidas; tabela não gravada"
            return registro

    # Contagens (ex.: órfãos, P2) ANTES de gravar, sobre a consulta como view temporária com o nome da tabela: se os
    # órfãos passarem do limite da P6, nada é gravado e a versão anterior fica no lake (S13).
    nome = nome_curto(tabela)
    con.execute(f"CREATE OR REPLACE TEMP VIEW {nome} AS {sql}")
    try:
        contagens = [(c, contar(con, c["sql"])) for c in item.get("contagens", [])]
        total = contar(con, f"SELECT count(*) FROM {nome}") if any(c.get("orfaos") for c, _ in contagens) else 0
    finally:
        con.execute(f"DROP VIEW IF EXISTS {nome}")
    mensagens = [f"{c['nome']}={n:,}" for c, n in contagens]
    limite = float(cfg["silver"]["limite_rejeicao"])
    acima = [f"{c['nome']} {n / total:.2%}" for c, n in contagens if c.get("orfaos") and total and n / total > limite]
    if acima:
        registro["mensagem"] = (f"órfãos acima do limite de {limite:.0%}: {', '.join(acima)}; tabela não gravada; "
                                + ", ".join(mensagens))
        return registro

    destino = caminho_tabela(cfg, "silver", f"context/{tabela}")
    gravar(con, cfg, sql, destino)
    registrar_delta(con, nome, destino)  # as próximas consultas leem o que foi gravado
    saida = contar(con, f"SELECT count(*) FROM {nome}")
    registro["linhas_saida"] = saida

    if nome.startswith("fact_"):
        # O fato tem o grão da clean de origem: nenhuma linha pode sumir nem duplicar nas junções.
        entrada = contar(con, "SELECT count(*) FROM clean_transaction_data")
        registro["linhas_entrada"] = entrada
        if entrada != saida:
            registro["mensagem"] = f"clean ({entrada:,}) != {nome_curto(tabela)} ({saida:,}); " + ", ".join(mensagens)
            return registro
    registro["status"] = "sucesso"
    registro["mensagem"] = ", ".join(mensagens) or None
    return registro


# ---------------------------------------------------------------- execução

def registrar_controle(cfg: dict, registro: dict, processado_em: datetime) -> None:
    linha = {campo.name: registro.get(campo.name) for campo in esquema_controle(cfg["bronze"]["fuso"])}
    linha["processado_em"] = processado_em
    tabela = pa.Table.from_pylist([linha], schema=esquema_controle(cfg["bronze"]["fuso"]))
    write_deltalake(str(caminho_tabela(cfg, "silver", CONTROLE)), tabela, mode="append")


def _tentar(funcao, registro_base: dict, *args) -> dict:
    """Roda uma etapa; exceção vira registro de erro com a mensagem (o processo segue para o controle)."""
    try:
        return funcao(*args)
    except Exception as e:
        return {**registro_base, "status": "erro", "mensagem": f"{type(e).__name__}: {e}"}


def executar(cfg: dict, agora: datetime | None = None) -> int:
    """Reconstrói a silver. Devolve 0 se tudo deu certo, 1 em qualquer erro."""
    fuso = ZoneInfo(cfg["bronze"]["fuso"])
    processado_em = (agora or datetime.now(fuso)).astimezone(fuso)
    con = preparar_conexao(cfg, processado_em)
    registros = []

    for item in cfg["silver"]["clean"]:
        print(f"clean/{item['tabela']} ...", flush=True)
        reg = _tentar(construir_clean, {"tabela": f"clean/{item['tabela']}", "camada": "clean"}, con, cfg, item)
        registrar_controle(cfg, reg, processado_em)
        registros.append(reg)

    if all(r["status"] == "sucesso" for r in registros):
        for item in cfg["silver"]["clean"]:
            registrar_delta(con, f"clean_{item['tabela']}", caminho_tabela(cfg, "silver", f"clean/{item['tabela']}"))
        carga = ", ".join(sorted({r["data_carga_bronze"] for r in registros}))
        for item in cfg["silver"]["context"]:
            print(f"context/{item['tabela']} ...", flush=True)
            base = {"tabela": f"context/{item['tabela']}", "camada": "context", "data_carga_bronze": carga}
            reg = _tentar(construir_context, base, con, cfg, item, carga)
            registrar_controle(cfg, reg, processado_em)
            registros.append(reg)
            if reg["status"] != "sucesso":
                break  # as próximas tabelas dependem desta
    else:
        print("\nA clean teve erro: a context NÃO foi montada (P6).")
    con.close()

    print(f"\nResumo da silver ({processado_em:%Y-%m-%d %H:%M %Z})")
    print(f"{'tabela':<32} {'entrada':>11} {'saída':>11} {'rejeit.':>8} {'%':>6}  status")
    for r in registros:
        def fmt(v):
            return f"{v:,}" if isinstance(v, int) else "-"
        pct = f"{r['pct_rejeitado']:.2%}" if r.get("pct_rejeitado") is not None else "-"
        print(f"{r['tabela']:<32} {fmt(r.get('linhas_entrada')):>11} {fmt(r.get('linhas_saida')):>11} "
              f"{fmt(r.get('linhas_rejeitadas')):>8} {pct:>6}  {r['status']}")
        if r.get("mensagem"):
            print(f"    -> {r['mensagem']}")
    esperadas = len(cfg["silver"]["clean"]) + len(cfg["silver"]["context"])
    ok = len(registros) == esperadas and all(r["status"] == "sucesso" for r in registros)
    print(f"\n{sum(r['status'] == 'sucesso' for r in registros)} de {esperadas} tabelas com sucesso.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstrói a silver (clean + context) a partir da bronze.")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    args = parser.parse_args(argv)
    return executar(carregar_config(args.config))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
