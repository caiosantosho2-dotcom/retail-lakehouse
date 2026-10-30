"""Conferência: `python -m src.gold.reconcile` (spec da fase 3, seção 8; regra 3 e G6: igualdade, não tolerância).

Caminho 1, painel publicado (`paths.painel_publicado`, só leitura): cada JSON exportado que existe no painel é comparado
com o publicado linha a linha, na ordem, valor a valor, depois de expandir o formato compacto (grão e colunas também).
Diferença só passa se estiver em `gold.conferencia.excecoes` (com o motivo registrado no documento de decisões).
- faturamento_tempo_<p>.json não existe no publicado: o de 26 s é comparado com as semanas do cubo_faturamento.json
  publicado que ele cobre, e os quatro são refeitos pelo caminho 2.
- manifest.json: comparam-se as seções de conteúdo (períodos, modelo, cesta, rede, Metodologia); os campos da geração
  (data, commit, versões, bytes, lista de arquivos) mudam por definição.

Caminho 2, gabaritos fixos do config, recalculados por SQL próprio direto da silver (sem as macros e sem as views da
gold; os períodos também são refeitos aqui) e comparados com o valor esperado e com o que a gold gravou.
Termina com código 1 se houver diferença sem explicação ou gabarito que não bate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.comum import caminho_tabela, carregar_config, conectar_duckdb, registrar_delta
from src.gold import build
from src.gold.export import ARQUIVOS, expandir, nomes_arquivos, schema_de

SECOES_MANIFEST = ["periodo_base", "janelas", "modelo", "parametros_cesta", "parametros_rede", "parametros_laboratorio"]


# ---------------------------------------------------------------- caminho 1

def igual(a, b) -> bool:
    """Igualdade exata de valores JSON. Número inteiro e decimal de mesmo valor são iguais (7 = 7.0); booleano só
    é igual a booleano (no Python, True == 1)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(igual(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(igual(x, y) for x, y in zip(a, b))
    return a == b


def achatar(valor, prefixo: str = "") -> dict:
    """{'atributos': {'participacao': {'valor': 1}}} -> {'atributos.participacao.valor': 1} (para apontar a diferença)."""
    if isinstance(valor, dict):
        saida = {}
        for k, v in valor.items():
            saida.update(achatar(v, f"{prefixo}{k}."))
        return saida
    return {prefixo.rstrip("."): valor}


def comparar_linhas(exportadas: list[dict], publicadas: list[dict], chave: tuple[str, ...]) -> dict:
    """Linha i com linha i (a ordem faz parte do contrato). Devolve as diferenças célula a célula e, para diagnóstico,
    quantas linhas batem pela chave do grão independentemente da posição."""
    diferencas = []   # (linha, coluna, publicado, exportado)
    iguais = 0
    for i in range(max(len(exportadas), len(publicadas))):
        e = achatar(exportadas[i]) if i < len(exportadas) else None
        p = achatar(publicadas[i]) if i < len(publicadas) else None
        if e is None or p is None:
            diferencas.append((i, "(linha)", "ausente" if p is None else "presente", "ausente" if e is None else "presente"))
            continue
        cols = [c for c in dict.fromkeys([*p, *e]) if c not in e or c not in p or not igual(e[c], p[c])]
        if list(e) != list(p) and not cols:
            cols = ["(ordem das colunas)"]
        diferencas += [(i, c, p.get(c, "ausente"), e.get(c, "ausente")) for c in cols]
        iguais += not cols
    por_chave = None
    if chave:
        idx = {tuple(json.dumps(l.get(c), ensure_ascii=False) for c in chave): l for l in publicadas}
        por_chave = sum(1 for l in exportadas
                        if igual(idx.get(tuple(json.dumps(l.get(c), ensure_ascii=False) for c in chave)), l))
    return {"iguais": iguais, "diferencas": diferencas, "iguais_pela_chave": por_chave}


def explicada(arquivo: str, coluna: str, excecoes: list[dict]) -> str | None:
    for x in excecoes:
        if x["arquivo"] == arquivo and (coluna == x["coluna"] or coluna.startswith(x["coluna"] + ".")):
            return x["motivo"]
    return None


def resultado(arquivo: str, exportadas: list[dict], publicadas: list[dict], chave, excecoes, extras=()) -> dict:
    r = comparar_linhas(exportadas, publicadas, chave)
    difs = [(i, f"(cabeçalho) {c}", p, e) for c, p, e in extras] + r["diferencas"]
    sem_explicacao = [d for d in difs if not explicada(arquivo, d[1], excecoes)]
    return {"arquivo": arquivo, "publicado": len(publicadas), "exportado": len(exportadas), "iguais": r["iguais"],
            "iguais_pela_chave": r["iguais_pela_chave"], "diferencas": difs, "sem_explicacao": sem_explicacao,
            "motivos": sorted({explicada(arquivo, d[1], excecoes) for d in difs} - {None})}


def caminho_1(cfg: dict) -> list[dict]:
    exp, pub = cfg["paths"]["export"], cfg["paths"]["painel_publicado"]
    excecoes = cfg["gold"]["conferencia"].get("excecoes") or []
    chaves = {a.base: a.chave for a in ARQUIVOS}
    saida = []
    for _, nome, _ in nomes_arquivos(cfg):
        if schema_de(nome) == "faturamento_tempo":
            continue
        e = json.loads((exp / nome).read_text(encoding="utf-8"))
        p = json.loads((pub / nome).read_text(encoding="utf-8"))
        extras = [(c, p.get(c), e.get(c)) for c in ("grao", "colunas") if not igual(e.get(c), p.get(c))]
        r = resultado(nome, expandir(e), expandir(p), chaves[schema_de(nome)], excecoes, extras)
        r["bytes_iguais"] = (exp / nome).read_bytes() == (pub / nome).read_bytes()
        saida.append(r)

    # faturamento_tempo de 26 s × as semanas do cubo_faturamento publicado que ele cobre (mesmas colunas, outro nome).
    nome = "faturamento_tempo_26s.json"
    e = expandir(json.loads((exp / nome).read_text(encoding="utf-8")))
    cubo = [{("inicio" if k == "semana_inicio" else k): v for k, v in l.items()}
            for l in expandir(json.loads((pub / "cubo_faturamento.json").read_text(encoding="utf-8")))]
    datas = {l["inicio"] for l in e}
    r = resultado(f"{nome} × cubo_faturamento.json", e, [l for l in cubo if l["inicio"] in datas],
                  ("inicio", "grupo", "departamento"), excecoes)
    r["bytes_iguais"] = None
    saida.append(r)

    # manifest: só as seções de conteúdo.
    me = json.loads((exp / "manifest.json").read_text(encoding="utf-8"))
    mp = json.loads((pub / "manifest.json").read_text(encoding="utf-8"))
    r = resultado("manifest.json", [{s: me.get(s) for s in SECOES_MANIFEST}], [{s: mp.get(s) for s in SECOES_MANIFEST}],
                  (), excecoes)
    r["bytes_iguais"] = None
    saida.append(r)
    return saida


# ---------------------------------------------------------------- caminho 2

class Caminho2:
    """Os números do gabarito por SQL próprio sobre a silver. Cada método devolve (SQL próprio, gold)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.con = con = conectar_duckdb(cfg)
        registrar_delta(con, "f", caminho_tabela(cfg, "silver", build.SILVER["fact_sales"]))
        registrar_delta(con, "d", caminho_tabela(cfg, "silver", build.SILVER["dim_date"]))
        registrar_delta(con, "pr", caminho_tabela(cfg, "silver", build.SILVER["dim_product"]))
        for t in ["kpi_filtered", "cube_period", "period_comparable_store", "revenue_over_time", "department_risk"]:
            registrar_delta(con, t, caminho_tabela(cfg, "gold", f"metrics/{t}"))
        for t in ["customer_segment", "churn_score", "churn_test_score", "churn_classifier", "model_summary"]:
            registrar_delta(con, t, caminho_tabela(cfg, "gold", f"models/{t}"))
        # Períodos refeitos aqui: o fim é a última semana com 7 dias no calendário da silver.
        self.fim = self.um("SELECT max(week_no) FROM (SELECT week_no FROM d WHERE week_no IS NOT NULL GROUP BY 1 HAVING count(*) = 7)")
        g, m = cfg["gold"], cfg["gold"]["metricas"]
        self.ano = g["janela"]["offset_ano_anterior"]
        self.ativo = g["janela"]["cliente_ativo_semanas"]
        self.dias = m["offset_dias_ano_anterior"]
        self.periodos = {p["periodo"]: (self.fim - p["semanas"] + 1 if p["semanas"] else 1, p["ponto"], p["semanas"] is not None)
                         for p in m["periodos"]}
        self.janela = next(p["periodo"] for p in m["periodos"] if p["semanas"] == g["janela"]["semanas"])
        self.sem_segmento = m["sem_segmento"]
        con.execute(f"""CREATE TEMP TABLE v AS
            SELECT f.household_key, f.basket_id, f.store_id, f.week_no, f.day, f.quantity, pr.department,
                   f.sales_value::DOUBLE AS fat, -(f.retail_disc + f.coupon_disc + f.coupon_match_disc)::DOUBLE AS desc_
            FROM f LEFT JOIN pr USING (product_id)
            WHERE f.is_merchandise AND f.week_no <= {self.fim}""")

    def um(self, sql):
        return self.con.execute(sql).fetchall()[0][0]

    def linha(self, sql):
        return self.con.execute(sql).fetchall()[0]

    def lojas(self, ini: int) -> str:
        return (f"(SELECT store_id FROM v WHERE week_no BETWEEN {ini} AND {self.fim} INTERSECT "
                f"SELECT store_id FROM v WHERE week_no BETWEEN {ini - self.ano} AND {self.fim - self.ano})")

    def gabaritos(self) -> dict[str, tuple]:
        fim, ini26 = self.fim, self.periodos[self.janela][0]
        r = {}
        fat, ces, itens, desc_ = self.linha(f"SELECT sum(fat), count(DISTINCT basket_id), sum(quantity), sum(desc_) FROM v")
        tb, ib = self.linha("SELECT avg_ticket, items_per_basket FROM kpi_filtered WHERE period = 'base' AND subset = 'todos' AND department = 'todos'")
        r["ticket_medio_base"] = (fat / ces, tb)
        r["itens_por_cesta_base"] = (itens / ces, ib)
        r["desconto_base"] = (desc_ / (fat + desc_), self.um("SELECT sum(discount) / sum(gross_value) FROM cube_period WHERE period = 'base'"))
        f26, c26 = self.linha(f"SELECT sum(fat), count(DISTINCT basket_id) FROM v WHERE week_no BETWEEN {ini26} AND {fim}")
        r["ticket_medio_26s"] = (f26 / c26, self.um(f"SELECT avg_ticket FROM kpi_filtered WHERE period = '{self.janela}' AND subset = 'todos' AND department = 'todos'"))
        for p, (ini, _, tem_ano) in self.periodos.items():
            if tem_ano:
                r[f"lojas_comparaveis_{p}"] = (self.um(f"SELECT count(*) FROM {self.lojas(ini)}"),
                                               self.um(f"SELECT count(*) FROM period_comparable_store WHERE period = '{p}'"))
        atual, anterior = self.linha(f"""SELECT sum(fat) FILTER (WHERE week_no BETWEEN {ini26} AND {fim}),
                                                sum(fat) FILTER (WHERE week_no BETWEEN {ini26 - self.ano} AND {fim - self.ano})
                                         FROM v WHERE store_id IN {self.lojas(ini26)}""")
        ga, gp = self.linha(f"SELECT sum(revenue_comparable), sum(revenue_prior_year) FROM cube_period WHERE period = '{self.janela}'")
        r["faturamento_comparavel_26s"] = (atual, ga)
        r["faturamento_ano_anterior_26s"] = (anterior, gp)
        r["variacao_26s"] = (atual / anterior - 1, float(ga) / float(gp) - 1)
        a0 = fim - self.ativo + 1
        pa_, pp = self.linha(f"""SELECT count(DISTINCT household_key) FILTER (WHERE week_no BETWEEN {a0} AND {fim}),
                                        count(DISTINCT household_key) FILTER (WHERE week_no BETWEEN {a0 - self.ano} AND {fim - self.ano}) FROM v""")
        ga, gp = self.linha(f"SELECT active_customers, active_customers_prior_year FROM kpi_filtered WHERE period = '{self.janela}' AND subset = 'todos' AND department = 'todos'")
        r["clientes_ativos"] = (pa_, ga)
        r["clientes_ativos_ano_anterior"] = (pp, gp)
        fc, fr = self.linha(f"""WITH c AS (SELECT household_key, sum(fat) AS fat FROM v WHERE week_no BETWEEN {ini26} AND {fim} GROUP BY 1)
                                SELECT count(*) FILTER (WHERE s.segment = 'Fiéis') / count(*),
                                       sum(c.fat) FILTER (WHERE s.segment = 'Fiéis') / sum(c.fat)
                                FROM customer_segment s JOIN c USING (household_key)""")
        gc, gr = self.linha("""SELECT count(*) FILTER (WHERE segment = 'Fiéis') / count(*),
                                      sum(monetary) FILTER (WHERE segment = 'Fiéis') / sum(monetary) FROM customer_segment""")
        r["fieis_clientes_pct"] = (fc, gc)
        r["fieis_faturamento_pct"] = (fr, float(gr))
        # AUC por outro caminho: Mann-Whitney sobre as notas do teste, em SQL.
        for nome, classificador, coluna in (("auc_modelo", "model", "model_score"), ("auc_regra_simples", "baseline", "baseline_score")):
            proprio = self.um(f"""
                WITH r AS (SELECT label, rank() OVER (ORDER BY {coluna}) AS rk, count(*) OVER (PARTITION BY {coluna}) AS empates
                           FROM churn_test_score),
                     a AS (SELECT label, rk + (empates - 1) / 2.0 AS rm FROM r)
                SELECT (sum(rm) FILTER (WHERE label = 1) - count(*) FILTER (WHERE label = 1) * (count(*) FILTER (WHERE label = 1) + 1) / 2.0)
                       / (count(*) FILTER (WHERE label = 1) * count(*) FILTER (WHERE label = 0)) FROM a""")
            r[nome] = (proprio, self.um(f"SELECT auc FROM churn_classifier WHERE classifier = '{classificador}'"))
        limiar = self.um("SELECT value::DOUBLE FROM model_summary WHERE model = 'churn' AND key = 'limiar'")
        r["limiar"] = (limiar, self.um("SELECT cutoff FROM churn_classifier WHERE classifier = 'model'"))
        r["alertas"] = (self.um(f"SELECT count(*) FILTER (WHERE probability >= {limiar}) FROM churn_score"),
                        self.um("SELECT count(*) FILTER (WHERE is_high_risk) FROM churn_score"))
        por_segmento = json.loads(self.um("SELECT value FROM model_summary WHERE model = 'churn' AND key = 'risco_por_segmento'"))
        r["pausas_esperadas"] = (self.um("SELECT sum(probability) FROM churn_score"), sum(s["pausas_esperadas"] for s in por_segmento))
        r["dinheiro_em_risco_26s"] = (
            self.um(f"""SELECT sum(v.fat) FROM v JOIN churn_score c USING (household_key)
                        WHERE c.probability >= {limiar} AND v.week_no BETWEEN {ini26} AND {fim}"""),
            self.um("SELECT money_at_risk FROM department_risk WHERE subset = 'todos' AND department = 'todos'"))
        return r

    def faturamento_tempo(self, periodo: str, exportadas: list[dict]) -> dict:
        """O arquivo exportado do período × SQL próprio no grão inteiro (ponto × grupo × departamento), em 2 casas."""
        ini, ponto, tem_ano = self.periodos[periodo]
        col = "day" if ponto == "day" else "week_no"
        desloc = self.dias if ponto == "day" else self.ano
        lojas = f"AND store_id IN {self.lojas(ini)}" if tem_ano else ""
        anterior = f"""SELECT {col} + {desloc} AS p, grupo, department, sum(fat) AS fat FROM vg
                       WHERE week_no BETWEEN {ini - self.ano} AND {self.fim - self.ano} {lojas} GROUP BY ALL""" if tem_ano else \
                   "SELECT NULL::INTEGER AS p, NULL AS grupo, NULL AS department, NULL::DOUBLE AS fat WHERE false"
        linhas = self.con.execute(f"""
            WITH vg AS (SELECT v.*, coalesce(s.segment, '{self.sem_segmento}') AS grupo
                        FROM v LEFT JOIN customer_segment s USING (household_key)),
                 a AS (SELECT {col} AS p, grupo, department, sum(fat) AS fat FROM vg
                       WHERE week_no BETWEEN {ini} AND {self.fim} {lojas} GROUP BY ALL),
                 b AS ({anterior}),
                 pt AS (SELECT {col} AS p, min(date) AS inicio FROM d WHERE week_no BETWEEN {ini} AND {self.fim} GROUP BY 1)
            SELECT strftime(pt.inicio, '%Y-%m-%d'), grupo, department,
                   round(coalesce(a.fat, 0), 2), {'round(coalesce(b.fat, 0), 2)' if tem_ano else 'NULL'}
            FROM a FULL JOIN b USING (p, grupo, department) JOIN pt USING (p)""").fetchall()
        proprio = {(i, g, dep): (fa, fb) for i, g, dep, fa, fb in linhas}
        exp = {(l["inicio"], l["grupo"], l["departamento"]): (l["faturamento"], l["faturamento_ano_anterior"]) for l in exportadas}
        iguais = sum(1 for k, v in exp.items() if k in proprio and igual(list(proprio[k]), list(v)))
        primeira = next((f"{k}: SQL próprio {proprio.get(k)}, exportado {exp.get(k)}"
                         for k in sorted(set(proprio) | set(exp), key=str) if not (k in proprio and k in exp and igual(list(proprio[k]), list(exp[k])))), "")
        return {"periodo": periodo, "ponto": ponto, "proprio": len(proprio), "exportado": len(exp), "iguais": iguais, "primeira": primeira}


def caminho_2(cfg: dict) -> tuple[list[tuple], list[dict]]:
    c = Caminho2(cfg)
    calculados = c.gabaritos()
    linhas = []
    for g in cfg["gold"]["conferencia"]["gabaritos"]:
        proprio, gold = calculados.get(g["nome"], (None, None))
        arred = (lambda x, n=g["casas"]: None if x is None else round(float(x), n) if n else round(float(x)))
        ok = proprio is not None and arred(g["valor"]) == arred(proprio) == arred(gold)
        linhas.append((g["nome"], arred(g["valor"]), arred(proprio), arred(gold), ok))
    tempo = []
    for p in c.periodos:
        nome = f"faturamento_tempo_{p}.json"
        exportadas = expandir(json.loads((cfg["paths"]["export"] / nome).read_text(encoding="utf-8")))
        tempo.append(c.faturamento_tempo(p, exportadas))
    c.con.close()
    return linhas, tempo


# ---------------------------------------------------------------- execução

def conferir(cfg: dict) -> int:
    if not (cfg["paths"]["export"] / "manifest.json").exists():
        print(f"Não há exportação em {cfg['paths']['export']}: rode `python -m src.gold.export` antes.")
        return 1
    print("Caminho 1: exportado × painel publicado (linha a linha, na ordem, valor a valor)\n")
    print(f"{'arquivo':<52} {'public.':>7} {'export.':>7} {'iguais':>7} {'pela chave':>10} {'difer.':>6} {'bytes':>5}  primeira diferença")
    c1 = caminho_1(cfg)
    for r in c1:
        primeira = ""
        if r["diferencas"]:
            i, col, p, e = r["diferencas"][0]
            primeira = f"linha {i}, {col}: publicado {p!r}, exportado {e!r}"
            if not r["sem_explicacao"]:
                primeira = f"explicada ({'; '.join(r['motivos'])}). " + primeira
        bytes_ = {True: "sim", False: "não", None: "-"}[r["bytes_iguais"]]
        chave = "-" if r["iguais_pela_chave"] is None else f"{r['iguais_pela_chave']:,}"
        print(f"{r['arquivo']:<52} {r['publicado']:>7,} {r['exportado']:>7,} {r['iguais']:>7,} {chave:>10} "
              f"{len(r['diferencas']):>6} {bytes_:>5}  {primeira[:160]}")
    arquivos = [r for r in c1 if r["bytes_iguais"] is not None]
    linhas_pub = sum(r["publicado"] for r in arquivos)
    print(f"\nArquivos iguais: {sum(1 for r in arquivos if not r['diferencas'])} de {len(arquivos)} "
          f"({sum(1 for r in arquivos if r['bytes_iguais'])} idênticos byte a byte); "
          f"linhas iguais: {sum(r['iguais'] for r in arquivos):,} de {linhas_pub:,} publicadas; "
          f"diferenças sem explicação: {sum(len(r['sem_explicacao']) for r in c1)}")

    print("\nCaminho 2: gabaritos fixos por SQL próprio sobre a silver\n")
    gabaritos, tempo = caminho_2(cfg)
    print(f"{'gabarito':<32} {'esperado':>14} {'SQL próprio':>14} {'gold':>14}")
    for nome, e, p, g, ok in gabaritos:
        print(f"{nome:<32} {e!s:>14} {p!s:>14} {g!s:>14}  {'✅' if ok else '❌'}")
    print(f"\nGabaritos: {sum(1 for l in gabaritos if l[4])} de {len(gabaritos)}")
    print("\nfaturamento_tempo exportado × SQL próprio (ponto × grupo × departamento, 2 casas):")
    for t in tempo:
        ok = t["iguais"] == t["proprio"] == t["exportado"]
        print(f"  {t['periodo']:<5} grão {t['ponto']:<4}  linhas: SQL próprio {t['proprio']:,}, exportado {t['exportado']:,}, "
              f"iguais {t['iguais']:,}  {'✅' if ok else '❌ ' + t['primeira']}")

    falhas = (sum(len(r["sem_explicacao"]) for r in c1) + sum(1 for l in gabaritos if not l[4])
              + sum(1 for t in tempo if not t["iguais"] == t["proprio"] == t["exportado"]))
    print(f"\n{'Conferência OK' if not falhas else f'Conferência com {falhas} problema(s) sem explicação'}")
    return 1 if falhas else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confere a exportação com o painel publicado e os gabaritos fixos.")
    parser.add_argument("--config", help="caminho do config.yaml (padrão: config.yaml da raiz)")
    args = parser.parse_args(argv)
    return conferir(carregar_config(args.config))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
