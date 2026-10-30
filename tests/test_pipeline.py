"""Testes do comando único `python -m src.pipeline` (a ordem, a parada no erro e o resumo). Os processos são simulados:
cada etapa já tem os seus testes, e o pipeline completo sobre os dados reais está em docs/validacao/fase3c_gold.md."""
from __future__ import annotations

import sys

from src import pipeline


def simular(monkeypatch, codigos: dict[str, int]) -> list[list[str]]:
    chamadas = []

    def falso(comando, cwd):
        chamadas.append(comando)
        return type("R", (), {"returncode": codigos.get(comando[2], 0)})()

    monkeypatch.setattr(pipeline.subprocess, "run", falso)
    return chamadas


def test_roda_as_cinco_etapas_em_ordem_cada_uma_num_processo(monkeypatch, capsys):
    chamadas = simular(monkeypatch, {})
    assert pipeline.main([]) == 0
    assert chamadas == [[sys.executable, "-m", m] for m in
                        ("src.bronze.ingest", "src.silver.build", "src.gold.build", "src.gold.export", "src.gold.reconcile")]
    saida = capsys.readouterr().out
    assert "Resumo do pipeline" in saida and saida.count("sucesso") == 6   # 5 etapas + o total


def test_para_no_primeiro_erro_com_codigo_1(monkeypatch, capsys):
    chamadas = simular(monkeypatch, {"src.gold.build": 1})
    assert pipeline.main([]) == 1
    assert [c[2] for c in chamadas] == ["src.bronze.ingest", "src.silver.build", "src.gold.build"]
    saida = capsys.readouterr().out
    assert "gold build" in saida and "erro (código 1)" in saida
    assert saida.count("não rodou") == 2 and "parou no primeiro erro" in saida


def test_config_vai_para_todas_as_etapas(monkeypatch, tmp_path):
    chamadas = simular(monkeypatch, {})
    config = tmp_path / "config.yaml"
    assert pipeline.main(["--config", str(config)]) == 0
    assert all(c[-2:] == ["--config", str(config.resolve())] for c in chamadas)
