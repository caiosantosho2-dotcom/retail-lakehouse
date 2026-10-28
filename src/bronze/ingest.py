"""Bronze: carrega os CSVs do config em tabelas Delta, tudo como texto, uma partição por dia de carga.

Uso: python -m src.bronze.ingest [--config config.yaml] [--data-carga AAAA-MM-DD]

Decisões: B1–B11, L1 e F3 em docs/decisoes_arquitetura_lakehouse.md.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from src.comum import caminho_tabela, carregar_config, conectar_duckdb, eh_delta, ler_delta

CONTROLE = "_controle_cargas"


def esquema_controle(fuso: str) -> pa.Schema:
    return pa.schema([
        ("tabela", pa.string()),
        ("arquivo", pa.string()),
        ("data_carga", pa.string()),
        ("carregado_em", pa.timestamp("us", tz=fuso)),
        ("linhas_lidas", pa.int64()),
        ("linhas_gravadas", pa.int64()),
        ("colunas_esperadas_ok", pa.bool_()),
        ("status", pa.string()),
        ("mensagem", pa.string()),
    ])


def validar_arquivo(caminho: Path, esperadas: list[str]) -> tuple[bool, str | None]:
    """Confere existência, tamanho, cabeçalho e ao menos uma linha de dado.

    Devolve (colunas_ok, mensagem_de_erro). Mensagem None = arquivo pronto para carregar.
    """
    if not caminho.is_file():
        return False, f"arquivo não encontrado: {caminho}"
    if caminho.stat().st_size == 0:
        return False, "arquivo vazio (0 bytes)"
    with caminho.open(encoding="utf-8", newline="") as f:
        leitor = csv.reader(f)
        cabecalho = next(leitor, [])
        primeira_linha = next(leitor, None)
    if cabecalho != esperadas:
        faltando = [c for c in esperadas if c not in cabecalho]
        sobrando = [c for c in cabecalho if c not in esperadas]
        detalhe = f"faltando={faltando} sobrando={sobrando}" if faltando or sobrando else "mesmas colunas em outra ordem"
        return False, f"colunas diferentes das esperadas ({detalhe}); cabeçalho lido: {cabecalho}"
    if primeira_linha is None:
        return True, "arquivo só com cabeçalho (0 linhas de dado)"
    return True, None


def contar_particao(con: duckdb.DuckDBPyConnection, destino: Path, data_carga: str) -> int:
    """Linhas da partição do dia, lidas pela tabela Delta (F3), nunca pelos arquivos."""
    return ler_delta(con, destino, carga=data_carga).aggregate("count(*)").fetchall()[0][0]


def _fluxo_com_rastreio(leitor: pa.RecordBatchReader, arquivo: str, data_carga: str,
                        carregado_em: datetime, contador: dict) -> pa.RecordBatchReader:
    """Acrescenta as colunas de rastreio a cada lote e conta as linhas lidas, sem juntar os lotes na memória."""
    tipo_ts = pa.timestamp("us", tz=str(carregado_em.tzinfo))
    esquema = leitor.schema.append(pa.field("_arquivo_origem", pa.string())) \
                           .append(pa.field("_data_carga", pa.string())) \
                           .append(pa.field("_carregado_em", tipo_ts))

    def lotes():
        for lote in leitor:
            n = lote.num_rows
            contador["linhas"] += n
            yield pa.RecordBatch.from_arrays(
                lote.columns + [
                    pa.array([arquivo] * n, pa.string()),
                    pa.array([data_carga] * n, pa.string()),
                    pa.array([carregado_em] * n, tipo_ts),
                ],
                schema=esquema,
            )

    return pa.RecordBatchReader.from_batches(esquema, lotes())


def carregar_tabela(con: duckdb.DuckDBPyConnection, cfg: dict, item: dict,
                    data_carga: str, carregado_em: datetime) -> dict:
    """Carrega um CSV na partição `data_carga` da tabela bronze. Devolve a linha do controle."""
    registro = {
        "tabela": item["tabela"], "arquivo": item["arquivo"], "data_carga": data_carga,
        "carregado_em": carregado_em, "linhas_lidas": None, "linhas_gravadas": None,
        "colunas_esperadas_ok": False, "status": "erro", "mensagem": None,
    }
    origem = cfg["paths"]["raw"] / item["arquivo"]
    destino = caminho_tabela(cfg, "bronze", item["tabela"])

    colunas_ok, erro = validar_arquivo(origem, item["colunas"])
    registro["colunas_esperadas_ok"] = colunas_ok
    if erro:
        registro["mensagem"] = erro
        return registro

    versao_antes = DeltaTable(str(destino)).version() if eh_delta(destino) else None
    predicado = f"_data_carga = '{data_carga}'"
    gravou = False
    try:
        caminho_sql = str(origem).replace("'", "''")
        leitor = con.sql(
            f"SELECT * FROM read_csv('{caminho_sql}', header = true, delim = ',', quote = '\"', all_varchar = true)"
        ).to_arrow_reader(int(cfg["bronze"]["batch_rows"]))
        contador = {"linhas": 0}
        fluxo = _fluxo_com_rastreio(leitor, item["arquivo"], data_carga, carregado_em, contador)

        if versao_antes is None:
            write_deltalake(str(destino), fluxo, mode="overwrite", partition_by=["_data_carga"])
        else:
            write_deltalake(str(destino), fluxo, mode="overwrite", predicate=predicado)
        gravou = True

        registro["linhas_lidas"] = contador["linhas"]
        registro["linhas_gravadas"] = contar_particao(con, destino, data_carga)
        if registro["linhas_lidas"] != registro["linhas_gravadas"]:
            raise RuntimeError(
                f"linhas lidas ({registro['linhas_lidas']:,}) != gravadas ({registro['linhas_gravadas']:,})"
            )
        registro["status"] = "sucesso"
    except Exception as e:  # registra e segue para a próxima tabela (B11)
        registro["mensagem"] = f"{type(e).__name__}: {e}"
        if gravou:
            registro["mensagem"] += f" | {_desfazer(destino, versao_antes, predicado)}"
    return registro


def _desfazer(destino: Path, versao_antes: int | None, predicado: str) -> str:
    """Volta a tabela ao estado de antes da gravação desta execução."""
    dt = DeltaTable(str(destino))
    if versao_antes is not None:
        dt.restore(versao_antes)
        return f"tabela restaurada para a versão {versao_antes}"
    # Tabela criada nesta execução: não há versão anterior para restaurar.
    dt.delete(predicado)
    return "tabela criada nesta execução; partição do dia apagada"


def registrar_controle(cfg: dict, registro: dict) -> None:
    destino = caminho_tabela(cfg, "bronze", CONTROLE)
    linha = pa.Table.from_pylist([registro], schema=esquema_controle(cfg["bronze"]["fuso"]))
    write_deltalake(str(destino), linha, mode="append")


def executar(cfg: dict, data_carga: str | None = None, agora: datetime | None = None) -> int:
    """Carrega todas as tabelas do config. Devolve 0 se todas deram sucesso, 1 se alguma deu erro."""
    fuso = ZoneInfo(cfg["bronze"]["fuso"])
    relogio = (lambda: agora.astimezone(fuso)) if agora else (lambda: datetime.now(fuso))
    # Data LOCAL da carga: às 22h em São Paulo ainda é o mesmo dia (em UTC já seria o seguinte).
    data_carga = date.fromisoformat(data_carga).isoformat() if data_carga else relogio().date().isoformat()

    con = conectar_duckdb(cfg)
    registros = []
    for item in cfg["bronze"]["tabelas"]:
        print(f"Carregando {item['tabela']} ...", flush=True)
        registro = carregar_tabela(con, cfg, item, data_carga, relogio())
        registrar_controle(cfg, registro)
        registros.append(registro)
    con.close()

    print(f"\nResumo da carga {data_carga}")
    print(f"{'tabela':<18} {'lidas':>12} {'gravadas':>12}  status")
    for r in registros:
        lidas = f"{r['linhas_lidas']:,}" if r["linhas_lidas"] is not None else "-"
        gravadas = f"{r['linhas_gravadas']:,}" if r["linhas_gravadas"] is not None else "-"
        print(f"{r['tabela']:<18} {lidas:>12} {gravadas:>12}  {r['status']}")
        if r["mensagem"]:
            print(f"    -> {r['mensagem']}")
    erros = sum(r["status"] != "sucesso" for r in registros)
    print(f"\n{len(registros) - erros} de {len(registros)} tabelas com sucesso.")
    return 1 if erros else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga da bronze (CSV -> Delta).")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    parser.add_argument("--data-carga", help="AAAA-MM-DD; padrão: hoje no fuso do config")
    args = parser.parse_args(argv)
    return executar(carregar_config(args.config), data_carga=args.data_carga)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
