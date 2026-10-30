"""Pipeline inteiro: `python -m src.pipeline` (G42).

Roda, em ordem, bronze → silver → gold (build) → exportação → conferência, cada etapa num processo Python novo (a
memória de uma volta ao sistema antes da próxima, como na G33). Para na primeira etapa que terminar com erro e sai
com código 1; no fim mostra o tempo e o status de cada etapa. Este processo só orquestra: não importa nada pesado.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# (nome no resumo, módulo)
ETAPAS = [
    ("bronze", "src.bronze.ingest"),
    ("silver", "src.silver.build"),
    ("gold build", "src.gold.build"),
    ("gold export", "src.gold.export"),
    ("gold reconcile", "src.gold.reconcile"),
]


def executar(config: str | None = None) -> int:
    resultados: list[tuple[str, float | None, str]] = []
    erro = False
    for nome, modulo in ETAPAS:
        if erro:
            resultados.append((nome, None, "não rodou"))
            continue
        comando = [sys.executable, "-m", modulo]
        if config:
            comando += ["--config", str(Path(config).resolve())]
        print(f"\n=== pipeline: {nome} ({' '.join(comando[1:])}) ===", flush=True)
        t0 = time.time()
        codigo = subprocess.run(comando, cwd=RAIZ).returncode
        segundos = time.time() - t0
        erro = codigo != 0
        resultados.append((nome, segundos, "sucesso" if not erro else f"erro (código {codigo})"))

    print("\nResumo do pipeline")
    for nome, segundos, status in resultados:
        tempo = "-" if segundos is None else f"{segundos:,.0f} s"
        print(f"  {nome:<16} {tempo:>8}  {status}")
    total = sum(s for _, s, _ in resultados if s is not None)
    print(f"  {'total':<16} {total:>6,.0f} s  {'sucesso' if not erro else 'parou no primeiro erro'}")
    return 1 if erro else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roda bronze, silver, gold, exportação e conferência, em ordem.")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    args = parser.parse_args(argv)
    return executar(args.config)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
