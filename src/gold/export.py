"""Exportação: `python -m src.gold.export` (spec da fase 3, seção 6).

Lê a gold (lake/gold/metrics e lake/gold/models) e grava os JSONs do painel v4 em `paths.export` (export/painel_v4, fora
do git). Nenhuma métrica é calculada aqui: o SQL de cada arquivo (sql/gold/export/<arquivo>.sql) só renomeia as colunas
para o contrato, arredonda nas casas do painel publicado e põe na ordem do contrato (G31). Os arquivos da Metodologia
(lab_*) saem dos modelos com as mesmas expressões do exportador do painel (conversão de 0–100 para fração, G17).
Formato do contrato: números crus, frações de 0 a 1, ausente = null, UTF-8 sem escape, JSON minificado e o formato
compacto 2.0 (`dimensoes` / `colunas` / `linhas`) nos arquivos grandes; o manifest por último.

Tudo é gravado numa pasta temporária e validado (contrato, índices do formato compacto, grão sem repetição, orçamento
de bytes, manifest). A pasta de saída só é trocada se tudo passar; se algo falhar, termina com código 1 e a pasta
anterior fica intacta.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
from deltalake import DeltaTable

from src.comum import RAIZ, caminho_tabela, carregar_config, conectar_duckdb, eh_delta, registrar_delta
from src.gold import build

EXPORT_SQL = RAIZ / "sql" / "gold" / "export"
ABAS = ["categoria", "produtos", "laboratorio"]   # a aba Clientes & Lojas saiu do v4 (manifest 5.0, G36)
ATRIBUTOS = ["participacao", "crescimento", "penetracao", "frequencia", "desconto", "marca_propria"]
MODELOS = ["churn_classifier", "churn_roc", "clv_segment", "discount_test_pair", "discount_test_segment", "model_summary"]
CLASSIFICADOR = {"model": "modelo", "baseline": "regra_simples"}   # rótulos do contrato
SEM_COMPRA = "Sem compra na janela"


@dataclass(frozen=True)
class Arquivo:
    """Um JSON do contrato. `grao` e `carga` são os do painel publicado; `dimensoes` = colunas do formato compacto."""
    base: str
    grao: str
    carga: str
    por_periodo: bool = False
    dimensoes: tuple[str, ...] = ()
    atributos: str | None = None   # departamentos_ficha / _segmento: o 2º campo de cada atributo (percentil / indice)
    chave: tuple[str, ...] = ()    # grão: nenhuma linha pode repetir a combinação
    linhas: int | None = None      # número de linhas esperado, se fixo
    so_com_ano_anterior: bool = False   # por período, sem a base inteira (não há crescimento para comparar, G46)


# Na ordem do manifest (a do exportador do painel, com faturamento_tempo no lugar de cubo_faturamento).
ARQUIVOS = [
    Arquivo("departamentos", "1 linha por departamento com venda na base inteira", "abertura", chave=("departamento",)),
    Arquivo("faturamento_tempo", "1 linha por ponto (dia em 4s, semana nos demais) × grupo × departamento", "abertura", True,
            ("inicio", "grupo", "departamento"), chave=("inicio", "grupo", "departamento")),
    Arquivo("cubo_periodo", "1 linha por período × grupo × departamento", "abertura", dimensoes=("periodo", "grupo", "departamento"),
            chave=("periodo", "grupo", "departamento")),
    Arquivo("kpis_filtrados", "1 linha por período × subconjunto de segmentos × departamento", "abertura",
            dimensoes=("periodo", "subconjunto", "departamento"), chave=("periodo", "subconjunto", "departamento")),
    Arquivo("acionamento_crm", "1 linha por capacidade de contato × objetivo × método de priorização", "abertura", chave=("capacidade", "objetivo", "metodo")),
    Arquivo("departamentos_quadrante", "1 linha por subconjunto de segmentos × departamento sem amostra pequena", "abertura", True,
            chave=("subconjunto", "departamento"), so_com_ano_anterior=True),
    Arquivo("departamentos_ficha", "1 linha por departamento com faturamento no período", "categoria", True,
            atributos="percentil", chave=("departamento",)),
    Arquivo("departamentos_segmento", "1 linha por subconjunto de segmentos × departamento (ou 'todos')", "categoria", True,
            atributos="indice", chave=("subconjunto", "departamento")),
    Arquivo("subcategorias", "1 linha por departamento (ou 'todos') × subcategoria (top 10)", "categoria", True,
            chave=("departamento", "subcategoria", "departamento_origem")),
    Arquivo("departamentos_risco", "1 linha por subconjunto de segmentos × departamento (ou 'todos'), 26 semanas", "categoria",
            chave=("subconjunto", "departamento")),
    Arquivo("cesta_subcategorias",
            "1 linha por subconjunto × departamento × par de subcategorias (os 10 de maior lift, 200+ cestas)", "categoria", True,
            ("subconjunto", "departamento", "subcategoria_a", "subcategoria_b"),
            chave=("subconjunto", "departamento", "subcategoria_a", "subcategoria_b")),
    Arquivo("concentracao", "1 linha por período × subconjunto de segmentos", "produtos", chave=("periodo", "subconjunto")),
    Arquivo("marcas", "1 linha por subconjunto de segmentos × departamento com venda", "produtos", True,
            chave=("subconjunto", "departamento")),
    Arquivo("rede_nos", "1 linha por nó da rede de cestas (as maiores subcategorias)", "produtos", chave=("no",)),
    Arquivo("rede_pares", "1 linha por subconjunto de segmentos × ligação desenhada da rede", "produtos", True, ("subconjunto",),
            chave=("subconjunto", "no_a", "no_b")),
    Arquivo("rede_vizinhos", "1 linha por subconjunto de segmentos × nó × par com o nó (os 10 de maior lift)", "produtos", True,
            ("subconjunto",), chave=("subconjunto", "no", "outro")),
    Arquivo("rede_caracteristicos", "1 linha por subconjunto de segmentos × par mais característico", "produtos", True,
            chave=("subconjunto", "posicao")),
    Arquivo("lab_roc", "1 linha por classificador × ponto da curva ROC no conjunto de teste do RAG", "laboratorio",
            dimensoes=("classificador",), chave=("classificador", "ponto")),
    Arquivo("lab_modelo", "1 linha por classificador (modelo de risco e regra simples) no conjunto de teste", "laboratorio",
            chave=("classificador",), linhas=2),
    Arquivo("lab_clv", "1 linha por segmento do CLV do RAG, com o backtest de 26 semanas", "laboratorio", chave=("segmento",)),
    Arquivo("lab_desconto", "1 linha por par de segmentos do teste de desconto", "laboratorio", chave=("segmento_a", "segmento_b")),
    Arquivo("lab_desconto_segmentos", "1 linha por segmento do teste de desconto", "laboratorio", chave=("segmento",), linhas=4),
]


def periodos(cfg: dict) -> list[str]:
    return [p["periodo"] for p in cfg["gold"]["metricas"]["periodos"]]


def nomes_arquivos(cfg: dict) -> list[tuple[Arquivo, str, str | None]]:
    """(arquivo, nome do JSON, período) de todos os arquivos, na ordem do manifest."""
    saida = []
    com_ano_anterior = [p["periodo"] for p in cfg["gold"]["metricas"]["periodos"] if p["semanas"] is not None]
    for a in ARQUIVOS:
        for p in ((com_ano_anterior if a.so_com_ano_anterior else periodos(cfg)) if a.por_periodo else [None]):
            saida.append((a, f"{a.base}_{p}.json" if p else f"{a.base}.json", p))
    return saida


def schema_de(nome: str) -> str:
    """O contrato de um arquivo por período é o do nome sem o período (subcategorias_4s.json -> subcategorias)."""
    return re.sub(r"_(4s|13s|26s|base)$", "", nome.removesuffix(".json"))


# ---------------------------------------------------------------- formato

def limpo(v):
    """Tipos do DuckDB/Arrow para JSON: Decimal vira float, NaN e infinito viram null."""
    if isinstance(v, dict):
        return {k: limpo(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [limpo(x) for x in v]
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def compactar(grao: str, linhas: list[dict], dimensoes: tuple[str, ...], colunas: list[str] | None = None) -> dict:
    """Formato compacto 2.0: cada coluna de dimensão vira um índice em `dimensoes[coluna]`, na ordem da primeira
    aparição (determinística, porque as linhas já vêm na ordem do contrato). `colunas` vale para o arquivo sem linhas."""
    colunas = list(linhas[0]) if linhas else list(colunas or dimensoes)
    valores = {d: [] for d in dimensoes}
    indice = {d: {} for d in dimensoes}
    saida = []
    for l in linhas:
        linha = []
        for c in colunas:
            v = l[c]
            if c in indice:
                if v not in indice[c]:
                    indice[c][v] = len(valores[c])
                    valores[c].append(v)
                v = indice[c][v]
            linha.append(v)
        saida.append(linha)
    return {"grao": grao, "dimensoes": valores, "colunas": colunas, "linhas": saida}


def expandir(dado: dict) -> list[dict]:
    """Lista de objetos a partir de qualquer um dos dois formatos do contrato."""
    if "colunas" not in dado:
        return dado["linhas"]
    dims = dado["dimensoes"]
    return [{c: (dims[c][v] if c in dims else v) for c, v in zip(dado["colunas"], linha)} for linha in dado["linhas"]]


def texto_json(dado: dict) -> str:
    return json.dumps(dado, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


# ---------------------------------------------------------------- leitura da gold

def conectar(cfg: dict):
    """Conexão com as tabelas da gold registradas, os parâmetros das métricas e a ordem dos grupos do contrato."""
    con = conectar_duckdb(cfg)
    build.configurar_metricas(con, cfg)
    con.execute(build.MACROS_SQL.read_text(encoding="utf-8"))
    m = cfg["gold"]["metricas"]
    grupos = m["segmentos"] + [m["sem_segmento"]]
    con.register("group_order", pa.table({"segment": grupos, "position": pa.array(range(1, len(grupos) + 1), pa.int32())}))
    for nome, tipo in build.METRICAS:
        if tipo in ("tabela", "por_periodo_departamento", "layout"):
            registrar_delta(con, nome, caminho_tabela(cfg, "gold", f"metrics/{nome}"))
    for nome in MODELOS:
        registrar_delta(con, nome, caminho_tabela(cfg, "gold", f"models/{nome}"))
    return con


def consultar(con, sql: str, params=None) -> tuple[list[str], list[dict]]:
    cur = con.execute(sql, params or [])
    colunas = [d[0] for d in cur.description]
    return colunas, [dict(zip(colunas, limpo(list(l)))) for l in cur.fetchall()]


def ler_modelo(cfg: dict, nome: str) -> list[dict]:
    """Tabela pequena dos modelos (no máximo algumas centenas de linhas)."""
    return DeltaTable(str(caminho_tabela(cfg, "gold", f"models/{nome}"))).to_pyarrow_table().to_pylist()


def resumo(cfg: dict) -> dict[str, dict]:
    """models/model_summary como {modelo: {chave: valor}}."""
    saida: dict[str, dict] = {}
    for l in ler_modelo(cfg, "model_summary"):
        saida.setdefault(l["model"], {})[l["key"]] = json.loads(l["value"])
    return saida


def com_atributos(linhas: list[dict], segundo: str) -> list[dict]:
    """Junta <atributo>_valor e <atributo>_<segundo> no objeto `atributos` do contrato, antes de amostra_pequena."""
    saida = []
    for l in linhas:
        atributos = {a: {"valor": l.pop(f"{a}_valor"), segundo: l.pop(f"{a}_{segundo}")} for a in ATRIBUTOS}
        amostra = l.pop("amostra_pequena")
        saida.append({**l, "atributos": atributos, "amostra_pequena": amostra})
    return saida


# ---------------------------------------------------------------- Metodologia (lab_*), dos modelos

def _ordem_segmentos(cfg: dict) -> dict[str, int]:
    return {s: i for i, s in enumerate(cfg["gold"]["metricas"]["segmentos"] + [SEM_COMPRA])}


def lab_roc(cfg: dict) -> list[dict]:
    pontos = sorted(ler_modelo(cfg, "churn_roc"), key=lambda r: (list(CLASSIFICADOR).index(r["classifier"]), r["point"]))
    return [{"classificador": CLASSIFICADOR[r["classifier"]], "ponto": r["point"], "fpr": round(r["fpr"], 6),
             "tpr": round(r["tpr"], 6), "corte": r["cutoff"]} for r in pontos]


def lab_modelo(cfg: dict) -> list[dict]:
    linhas = sorted(ler_modelo(cfg, "churn_classifier"), key=lambda r: list(CLASSIFICADOR).index(r["classifier"]))
    return [{"classificador": CLASSIFICADOR[m["classifier"]], "descricao": m["description"],
             # o corte da regra simples é k, em semanas (inteiro)
             "corte": int(m["cutoff"]) if m["classifier"] == "baseline" else m["cutoff"],
             "auc": m["auc"], "auc_ic_inf": m["auc_ci_low"], "auc_ic_sup": m["auc_ci_high"], "auc_pr": m["auc_pr"],
             "precisao": m["precision"], "recall": m["recall"], "f1": m["f1"], "alertas": m["alerts"],
             "tn": m["tn"], "fp": m["fp"], "fn": m["fn"], "tp": m["tp"], "pausas": m["pauses"],
             "taxa_falso_alarme": round(m["false_alarm_rate"], 6)} for m in linhas]


def lab_clv(cfg: dict) -> list[dict]:
    ordem = _ordem_segmentos(cfg)
    linhas = sorted(ler_modelo(cfg, "clv_segment"), key=lambda r: ordem.get(r["segment"], len(ordem)))
    return [{"segmento": s["segment"], "households": s["households"], "clv_medio": s["clv_mean"], "clv_ic_inf": s["clv_ci_low"],
             "clv_ic_sup": s["clv_ci_high"], "clv_total": s["clv_total"], "receita_esperada": s["expected_revenue"],
             "backtest_households": s["backtest_households"], "backtest_real": s["backtest_actual"],
             "backtest_metodo": s["backtest_method"], "backtest_ingenuo": s["backtest_naive"],
             "backtest_erro_metodo_pct": s["backtest_error_method_pct"] / 100,
             "backtest_erro_ingenuo_pct": s["backtest_error_naive_pct"] / 100} for s in linhas]


def lab_desconto(cfg: dict) -> list[dict]:
    ordem = _ordem_segmentos(cfg)
    linhas = sorted(ler_modelo(cfg, "discount_test_pair"), key=lambda r: (ordem[r["segment_a"]], ordem[r["segment_b"]]))
    return [{"segmento_a": d["segment_a"], "segmento_b": d["segment_b"], "diferenca_pp": d["difference_pp"] / 100,
             "ic_inf": d["ci_low"] / 100, "ic_sup": d["ci_high"] / 100, "exclui_zero": d["excludes_zero"],
             "p_ajustado": d["p_adjusted"], "significativo": d["significant"]} for d in linhas]


def lab_desconto_segmentos(cfg: dict) -> list[dict]:
    ordem = _ordem_segmentos(cfg)
    linhas = sorted(ler_modelo(cfg, "discount_test_segment"), key=lambda r: ordem[r["segment"]])
    return [{"segmento": g["segment"], "households": g["households"], "mediana_pct": g["median_pct"] / 100,
             "q25_pct": g["q25_pct"] / 100, "q75_pct": g["q75_pct"] / 100, "bigode_inf_pct": g["whisker_low_pct"] / 100,
             "bigode_sup_pct": g["whisker_high_pct"] / 100, "taxa_ponderada_pct": g["weighted_rate_pct"] / 100,
             "desconto_total": g["discount_total"], "valor_bruto": g["gross_value"]} for g in linhas]


LAB = {"lab_roc": lab_roc, "lab_modelo": lab_modelo, "lab_clv": lab_clv, "lab_desconto": lab_desconto,
       "lab_desconto_segmentos": lab_desconto_segmentos}


def linhas_do_arquivo(con, cfg: dict, a: Arquivo, periodo: str | None) -> tuple[list[str], list[dict]]:
    """(colunas, linhas) do arquivo; as colunas servem ao arquivo de um período sem nenhuma linha."""
    if a.base in LAB:
        linhas = limpo(LAB[a.base](cfg))
        return list(linhas[0]) if linhas else [], linhas
    if periodo:
        con.execute("SET VARIABLE periodo = ?::VARCHAR", [periodo])
    colunas, linhas = consultar(con, (EXPORT_SQL / f"{a.base}.sql").read_text(encoding="utf-8"))
    return colunas, com_atributos(linhas, a.atributos) if a.atributos else linhas


# ---------------------------------------------------------------- manifest

def silver_versoes(cfg: dict) -> dict[str, int]:
    return {t: DeltaTable(str(caminho_tabela(cfg, "silver", t))).version() for t in build.SILVER.values()}


def versao_da_ultima_gold(cfg: dict) -> int | None:
    """Versão da fact_sales que o último build da gold com sucesso leu (controle da gold)."""
    caminho = caminho_tabela(cfg, "gold", build.CONTROLE)
    if not eh_delta(caminho):
        return None
    linhas = [l for l in DeltaTable(str(caminho)).to_pyarrow_table().to_pylist() if l["status"] == "sucesso"]
    return max(linhas, key=lambda l: l["processado_em"])["versao_fact_sales"] if linhas else None


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.strip()


def parametros_laboratorio(s: dict) -> dict:
    """Os números de uma linha da Metodologia e as conclusões, de models/model_summary (expressões do painel)."""
    ch, clv, de = s["churn"], s["clv"], s["teste_desconto"]
    kw, bt = de["kruskal_wallis"], clv["backtest"]
    return {
        "risco": {"definicao": ch["definicao_churn"], "horizonte_semanas": ch["horizonte_semanas"],
                  "periodo_teste": ch["periodo_teste"], "linhas_teste": ch["linhas"]["teste"],
                  "prevalencia_teste_pct": ch["prevalencia_pct"]["teste"] / 100, "diferenca_auc": ch["diferenca_auc"],
                  "diferenca_auc_ic": ch["diferenca_auc_ic"], "conclusao": ch["e_dai"]["conclusao"]},
        "clv": {"households": clv["total"]["households"], "clv_total": clv["total"]["clv_total_usd"],
                "clv_total_ic": clv["total"]["ic_95"], "receita_esperada_total": clv["total"]["receita_esperada_total_usd"],
                "margem": clv["premissas"]["margem"], "horizonte_semanas": clv["premissas"]["horizonte_semanas"],
                "metodo": clv["premissas"]["metodo"], "backtest_horizonte_semanas": bt["horizonte_semanas"],
                "backtest_erro_metodo_pct": bt["total"]["erro_metodo_pct"] / 100,
                "backtest_erro_ingenuo_pct": bt["total"]["erro_ingenuo_pct"] / 100,
                "backtest_grupos_em_que_ganha": bt["segmentos_em_que_o_metodo_ganha"], "backtest_grupos": bt["segmentos_avaliados"],
                "conclusao": clv["e_dai"]["conclusao"]},
        "desconto": {"households": de["households"], "kruskal_h": kw["estatistica_H"], "p_valor": kw["p_valor"],
                     "significativo": kw["significativo_5pct"], "eta_quadrado": kw["eta_quadrado_aprox"],
                     "eta_quadrado_relevante": de["parametros"]["eta2_relevante"], "alfa": de["parametros"]["alfa"],
                     "diferenca_relevante_pp": de["parametros"]["diferenca_relevante_pp"] / 100, "veredito": de["veredito"],
                     "desconto_total": de["impacto"]["desconto_total_usd"], "taxa_geral_pct": de["impacto"]["taxa_geral_pct"] / 100,
                     "economia_se_igualar": de["impacto"]["desconto_a_menos_se_igualar_usd"],
                     "conclusao": de["e_dai"]["conclusao"], "evidencia": de["e_dai"]["evidencia"],
                     "acao_recomendada": de["e_dai"]["acao_recomendada"]},
    }


def montar_manifest(con, cfg: dict, pasta: Path, arquivos: list[tuple[Arquivo, str, str | None]], versoes: dict) -> dict:
    fuso = ZoneInfo(cfg["bronze"]["fuso"])
    m = cfg["gold"]["metricas"]
    s = resumo(cfg)
    ch = s["churn"]
    janelas = {p: {"semana_ini": ini, "semana_fim": fim, "data_ini": str(d_ini), "data_fim": str(d_fim)}
               for p, ini, fim, d_ini, d_fim in con.execute(
                   "SELECT period, week_start, week_end, date_start, date_end FROM dim_period ORDER BY position").fetchall()}
    # Cobertura do dicionário de datas da silver (periodo_base) e o que a rede cobre do faturamento da janela.
    registrar_delta(con, "dim_date", caminho_tabela(cfg, "silver", build.SILVER["dim_date"]))
    inicio, fim = con.execute("SELECT min(date), max(date) FROM dim_date").fetchall()[0]
    cobertura, ligacoes = con.execute("""
        SELECT share((SELECT sum(revenue) FROM network_node),
                     (SELECT sum(revenue) FROM cube_period WHERE period = getvariable('periodo_segmento'))),
               (SELECT count(*) FROM network_link WHERE period = getvariable('periodo_segmento') AND subset = 'todos')
    """).fetchall()[0]
    lista = []
    for a, nome, periodo in arquivos:
        conteudo = (pasta / nome).read_bytes()
        item = {"nome": nome, "carga": a.carga, "linhas": len(json.loads(conteudo)["linhas"]), "bytes": len(conteudo),
                "sha256": hashlib.sha256(conteudo).hexdigest()}
        if periodo:
            item["periodo"] = periodo
        lista.append(item)
    ps = periodos(cfg)
    janela_cesta = janelas[con.execute("SELECT getvariable('periodo_segmento')").fetchall()[0][0]]
    return {
        "versao_contrato": cfg["gold"]["exportacao"]["versao_contrato"],
        "gerado_em": datetime.now(fuso).isoformat(timespec="seconds"),
        "base_hash": hashlib.sha256(json.dumps(versoes, sort_keys=True).encode()).hexdigest()[:12],
        "periodo_base": {"inicio": str(inicio), "fim": str(fim)},
        "janelas": janelas,
        "lakehouse_commit": git("rev-parse", "HEAD"),
        "lakehouse_sujo": bool(git("status", "--porcelain")),
        "silver_versoes": versoes,
        "modelo": {
            "limiar_alerta": ch["limiar"], "corte_medio": round(ch["limiar"] / 2, 4),
            "auc_modelo": ch["auc_modelo"], "auc_regra_simples": ch["auc_baseline"],
            "pausas_esperadas": round(sum(r["pausas_esperadas"] for r in ch["risco_por_segmento"]), 4),
            "clientes_ativos": sum(r["households"] for r in ch["risco_por_segmento"]),
            "alertas": sum(r["alertas"] for r in ch["risco_por_segmento"]),
            "risco_por_segmento": [{"segmento": r["nome"], "clientes": r["households"], "pausas_esperadas": r["pausas_esperadas"],
                                    "alertas": r["alertas"]} for r in ch["risco_por_segmento"]],
        },
        "parametros_cesta": {"semana_ini": janela_cesta["semana_ini"], "semana_fim": janela_cesta["semana_fim"],
                             "minimo_cestas_par": m["limites"]["par_cestas"]},
        "parametros_rede": {"rede_subcategorias": m["cesta"]["rede_nos"], "rede_ligacoes_por_no": m["cesta"]["rede_ligacoes_por_no"],
                            "rede_caracteristicos": m["cesta"]["caracteristicos"],
                            "cobertura_faturamento_pct": round(float(cobertura), 4), "ligacoes_desenhadas": int(ligacoes),
                            "posicoes": "layout.posicoes_em_dois_niveis(compacto=True): departamentos como grupos, "
                                        "o maior no centro, Jaccard das cestas"},
        "parametros_laboratorio": parametros_laboratorio(s),
        # o que o navegador baixa ao abrir o painel (o manifest fica fora: é lido antes de tudo) e em cada aba × período
        "bytes_abertura": sum(i["bytes"] for i in lista if i["carga"] == "abertura"),
        "bytes_por_aba": {aba: {p: sum(i["bytes"] for i in lista if i["carga"] == aba and i.get("periodo") in (None, p))
                                for p in ps} for aba in ABAS},
        "arquivos": lista,
    }


# ---------------------------------------------------------------- validação

def validar(pasta: Path, cfg: dict) -> list[str]:
    """Contrato de cada arquivo, índices do formato compacto, grão sem repetição, linhas esperadas, orçamento de bytes e
    manifest (lista completa, bytes, sha256 e linhas de cada arquivo). Devolve a lista de erros."""
    from jsonschema import Draft202012Validator

    erros = []
    esperados = {nome: a for a, nome, _ in nomes_arquivos(cfg)}
    for nome in [*esperados, "manifest.json"]:
        caminho = pasta / nome
        if not caminho.exists():
            erros.append(f"{nome}: arquivo não existe")
            continue
        dado = json.loads(caminho.read_text(encoding="utf-8"))
        schema = json.loads((cfg["paths"]["contratos"] / f"{schema_de(nome)}.schema.json").read_text(encoding="utf-8"))
        for e in Draft202012Validator(schema).iter_errors(dado):
            onde = "/".join(str(p) for p in e.absolute_path)
            erros.append(f"{nome}: {onde or '(raiz)'}: {e.message[:200]}")
        if nome == "manifest.json":
            continue
        if "colunas" in dado:
            for coluna, valores in dado["dimensoes"].items():
                usados = {l[dado["colunas"].index(coluna)] for l in dado["linhas"]}
                if usados - set(range(len(valores))):
                    erros.append(f"{nome}: índice fora de dimensoes.{coluna}")
        a = esperados[nome]
        vistos = [tuple(l[c] for c in a.chave) for l in expandir(dado)]
        if len(vistos) != len(set(vistos)):
            erros.append(f"{nome}: linhas repetidas no grão {a.chave}")
        if a.linhas is not None and len(vistos) != a.linhas:
            erros.append(f"{nome}: {len(vistos)} linhas, esperado {a.linhas}")
    manifest = pasta / "manifest.json"
    if manifest.exists():
        m = json.loads(manifest.read_text(encoding="utf-8"))
        listados = {i["nome"] for i in m["arquivos"]}
        erros += [f"{n}: fora do manifest" for n in esperados if n not in listados]
        for i in m["arquivos"]:
            caminho = pasta / i["nome"]
            if not caminho.exists():
                erros.append(f"{i['nome']}: está no manifest, mas não existe")
                continue
            conteudo = caminho.read_bytes()
            if (len(conteudo), hashlib.sha256(conteudo).hexdigest(), len(json.loads(conteudo)["linhas"])) != \
                    (i["bytes"], i["sha256"], i["linhas"]):
                erros.append(f"{i['nome']}: diferente do manifest (bytes, sha256 ou linhas)")
        limite = cfg["gold"]["exportacao"]["limite_bytes"]
        totais = [("abertura", m["bytes_abertura"])] + [(f"{aba} {p}", v) for aba, porp in m["bytes_por_aba"].items()
                                                        for p, v in porp.items()]
        erros += [f"orçamento: {carga} com {total:,} bytes, acima de {limite:,}" for carga, total in totais if total > limite]
    sobrando = {p.name for p in pasta.glob("*.json")} - set(esperados) - {"manifest.json"}
    erros += [f"{n}: arquivo fora do contrato" for n in sorted(sobrando)]
    return erros


# ---------------------------------------------------------------- execução

def exportar(cfg: dict) -> int:
    """Grava todos os JSONs numa pasta temporária, valida e só então troca a pasta de saída. 0 = sucesso, 1 = erro."""
    destino: Path = cfg["paths"]["export"]
    faltando = [f"metrics/{n}" for n, t in build.METRICAS if t in ("tabela", "por_periodo_departamento", "layout")
                and not eh_delta(caminho_tabela(cfg, "gold", f"metrics/{n}"))]
    faltando += [f"models/{n}" for n in MODELOS if not eh_delta(caminho_tabela(cfg, "gold", f"models/{n}"))]
    if faltando:
        print(f"A gold não está pronta (faltam: {', '.join(faltando)}): rode `python -m src.gold.build` antes.")
        return 1
    versoes = silver_versoes(cfg)
    lida = versao_da_ultima_gold(cfg)
    fact = versoes[build.SILVER["fact_sales"]]
    if lida != fact:
        print(f"A gold foi construída com a fact_sales versão {lida}, mas a silver está na {fact}: rode `python -m src.gold.build`.")
        return 1

    temporaria = destino.with_name(destino.name + ".tmp")
    shutil.rmtree(temporaria, ignore_errors=True)
    temporaria.mkdir(parents=True)
    arquivos = nomes_arquivos(cfg)
    con = conectar(cfg)
    try:
        for a, nome, periodo in arquivos:
            colunas, linhas = linhas_do_arquivo(con, cfg, a, periodo)
            grao = f"{a.grao}; período {periodo}" if periodo else a.grao
            dado = compactar(grao, linhas, a.dimensoes, colunas) if a.dimensoes else {"grao": grao, "linhas": linhas}
            (temporaria / nome).write_text(texto_json(dado), encoding="utf-8", newline="\n")
            print(f"  {nome:<36} {len(linhas):>6,} linhas {(temporaria / nome).stat().st_size:>10,} bytes")
        manifest = montar_manifest(con, cfg, temporaria, arquivos, versoes)
    finally:
        con.close()
    (temporaria / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")

    erros = validar(temporaria, cfg)
    if erros:
        for e in erros:
            print("ERRO", e)
        shutil.rmtree(temporaria)
        print(f"\nExportação cancelada: {len(erros)} erro(s). A pasta {destino} ficou como estava.")
        return 1
    antiga = destino.with_name(destino.name + ".old")
    shutil.rmtree(antiga, ignore_errors=True)
    if destino.exists():
        destino.rename(antiga)
    temporaria.rename(destino)
    shutil.rmtree(antiga, ignore_errors=True)
    print(f"\n{len(arquivos)} arquivos + manifest validados contra o contrato {manifest['versao_contrato']} em {destino}")
    print(f"abertura {manifest['bytes_abertura']:,} bytes; maior aba × período: "
          + ", ".join(f"{aba} {max(v.values()):,}" for aba, v in manifest["bytes_por_aba"].items()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta os JSONs do painel v4 a partir da gold.")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    args = parser.parse_args(argv)
    return exportar(carregar_config(args.config))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
