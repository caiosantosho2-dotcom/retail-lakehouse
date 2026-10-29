"""Inspeciona qualquer tabela Delta do lake pelo terminal. Só lê: nunca grava, apaga nem altera o lake.

Uso:
  python scripts/espiar.py <camada>/<tabela> [modo] [N] [--carga AAAA-MM-DD] [--versao N] [--csv arquivo.csv]

Modos: topo N (padrão) | amostra N | colunas | resumo | contagem | cargas | versoes
Exemplos:
  python scripts/espiar.py bronze/product topo 10
  python scripts/espiar.py bronze/transaction_data resumo
  python scripts/espiar.py bronze/_controle_cargas
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pyarrow as pa  # noqa: E402
from deltalake import DeltaTable  # noqa: E402

from src.comum import caminho_tabela, carregar_config, conectar_duckdb, eh_delta, ler_delta  # noqa: E402

CAMADAS = ("bronze", "silver", "gold")
MODOS = ("topo", "amostra", "colunas", "resumo", "contagem", "cargas", "versoes")
CONTROLE = "_controle_cargas"


class ErroAmigavel(Exception):
    """Erro de uso: mostra a mensagem (com as opções disponíveis) e sai com código 2."""


def tabelas_da_camada(lake: Path, camada: str) -> list[str]:
    pasta = lake / camada
    if not pasta.is_dir():
        return []
    return sorted(p.parent.relative_to(pasta).as_posix() for p in pasta.rglob("_delta_log") if p.is_dir())


def escolher_versao(dt: DeltaTable, versao: int | None) -> int | None:
    if versao is None:
        return None
    disponiveis = sorted(h["version"] for h in dt.history())
    if versao not in disponiveis:
        raise ErroAmigavel(f"Versão {versao} não existe. Versões disponíveis: {disponiveis}")
    return versao


def escolher_carga(dt: DeltaTable, carga: str | None) -> str | None:
    """Bronze: partição pedida em --carga ou, por padrão, a mais recente."""
    if "_data_carga" not in dt.metadata().partition_columns:
        if carga:
            raise ErroAmigavel("Esta tabela não é particionada por _data_carga; --carga não se aplica.")
        return None
    datas = sorted({p["_data_carga"] for p in dt.partitions()})
    if not datas:
        raise ErroAmigavel("A tabela não tem nenhuma carga.")
    if carga is None:
        return datas[-1]
    if carga not in datas:
        raise ErroAmigavel(f"Carga {carga} não existe. Cargas disponíveis: {', '.join(datas)}")
    return carga


def historico(dt: DeltaTable) -> pa.Table:
    linhas = []
    for h in sorted(dt.history(), key=lambda h: h["version"]):
        params = h.get("operationParameters") or {}
        linhas.append({
            "versao": h["version"],
            "gravada_em": datetime.fromtimestamp(h["timestamp"] / 1000, tz=timezone.utc),
            "operacao": h.get("operation"),
            "modo": params.get("mode"),
            "predicado": params.get("predicate"),
        })
    return pa.Table.from_pylist(linhas)


def espiar(cfg: dict, alvo: str, modo: str, n: int, carga: str | None, versao: int | None):
    """Monta a consulta pedida e devolve (descrição, relação DuckDB)."""
    camada, _, tabela = alvo.strip("/").partition("/")
    if camada not in CAMADAS or not tabela:
        raise ErroAmigavel(f"Use <camada>/<tabela>, com camada em {CAMADAS}. Recebido: {alvo!r}")
    lake = cfg["paths"]["lake"]
    caminho = caminho_tabela(cfg, camada, tabela)
    if not eh_delta(caminho):
        disponiveis = tabelas_da_camada(lake, camada)
        raise ErroAmigavel(
            f"Tabela {alvo} não encontrada. Tabelas em {camada}: {', '.join(disponiveis) or '(nenhuma)'}"
        )

    con = conectar_duckdb(cfg)
    dt = DeltaTable(str(caminho))
    versao = escolher_versao(dt, versao)

    if modo == "versoes":
        return f"{alvo} | histórico de versões", con.from_arrow(historico(dt))

    if modo == "cargas":
        if camada != "bronze":
            raise ErroAmigavel("O modo cargas vale só para a bronze.")
        controle = caminho_tabela(cfg, "bronze", CONTROLE)
        if not eh_delta(controle):
            raise ErroAmigavel("O controle de cargas ainda não existe: rode a ingestão primeiro.")
        rel = ler_delta(con, controle)
        if tabela != CONTROLE:
            rel = rel.filter(f"tabela = '{tabela}'")
        return f"{alvo} | cargas registradas no controle", rel.order("carregado_em DESC")

    if versao is not None:
        dt = DeltaTable(str(caminho), version=versao)
    carga = escolher_carga(dt, carga)
    rel = ler_delta(con, caminho, carga=carga, versao=versao)
    rel.create_view("t")
    descricao = f"{alvo} | versão {versao if versao is not None else dt.version()}"
    if carga:
        descricao += f" | carga {carga}"

    if modo == "topo":
        # Tabelas de controle: execução mais recente primeiro.
        coluna_tempo = next((c for c in ("carregado_em", "processado_em") if c in rel.columns), None)
        ordem = f" ORDER BY {coluna_tempo} DESC" if tabela.startswith("_controle") and coluna_tempo else ""
        return descricao, con.sql(f"SELECT * FROM t{ordem} LIMIT {n}")
    if modo == "amostra":
        return descricao, con.sql(f"SELECT * FROM t USING SAMPLE reservoir({n} ROWS)")
    if modo == "colunas":
        return descricao, con.sql("DESCRIBE t")
    if modo == "resumo":
        return descricao, con.sql("SUMMARIZE t")
    if modo == "contagem":
        return descricao, con.sql("SELECT count(*) AS linhas FROM t")
    raise ErroAmigavel(f"Modo desconhecido: {modo}. Modos: {', '.join(MODOS)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspeciona uma tabela Delta do lake (só leitura).")
    parser.add_argument("alvo", help="camada/tabela, ex.: bronze/product")
    parser.add_argument("modo", nargs="?", default="topo", choices=MODOS)
    parser.add_argument("n", nargs="?", type=int, default=20, help="número de linhas (topo, amostra)")
    parser.add_argument("--carga", help="AAAA-MM-DD (bronze); padrão: a mais recente")
    parser.add_argument("--versao", type=int, help="versão Delta da tabela")
    parser.add_argument("--csv", help="salva o resultado neste arquivo CSV")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    args = parser.parse_args(argv)

    cfg = carregar_config(args.config)
    try:
        descricao, rel = espiar(cfg, args.alvo, args.modo, args.n, args.carga, args.versao)
    except ErroAmigavel as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 2

    print(descricao)
    rel.show(max_rows=max(args.n, 100), max_width=250)
    if args.csv:
        destino = Path(args.csv).resolve()
        if destino.is_relative_to(cfg["paths"]["lake"]):
            print("Erro: --csv não pode gravar dentro do lake.", file=sys.stderr)
            return 2
        rel.write_csv(str(destino))
        print(f"Resultado salvo em {destino}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
