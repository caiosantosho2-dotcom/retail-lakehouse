"""Conferência: `python -m src.gold.reconcile` (spec da fase 3, seção 8; regra 3 e G6: igualdade, não tolerância).

Caminho 1, painel publicado, congelado na tag v3-rag (`paths.painel_publicado`, G44: nunca o site/data vivo do painel,
que desde o v4 é cópia desta exportação): cada JSON exportado que existe lá é comparado com o publicado linha a linha,
na ordem, valor a valor, depois de expandir o formato compacto (grão e colunas também).
Diferença só passa se estiver em `gold.conferencia.excecoes` (com o motivo registrado no documento de decisões).
- faturamento_tempo_<p>.json não existe no publicado: o de 26 s é comparado com as semanas do cubo_faturamento.json
  publicado que ele cobre, e os quatro são refeitos pelo caminho 2.
- manifest.json: comparam-se as seções de conteúdo (períodos, modelo, cesta, rede, Metodologia); os campos da geração
  (data, commit, versões, bytes, lista de arquivos) mudam por definição.

Caminho 2, gabaritos fixos do config, recalculados por SQL próprio direto da silver (sem as macros e sem as views da
gold; os períodos também são refeitos aqui) e comparados com o valor esperado e com o que a gold gravou.
Blocos de decisão (contrato 5.1, G45, G46 e G48): acionamento_crm e departamentos_quadrante não existem no publicado.
São refeitos pelo caminho 2: o faturamento de 26 s até cada foto sai da silver (não das features), a ordenação e as
contas são escritas aqui, nos dois objetivos, e os quadrantes são remontados a partir da venda. As pausas esperadas com
N = população inteira rodam o próprio SQL de crm_capacity e têm de dar o gabarito `pausas_esperadas` nos dois objetivos.
Termina com código 1 se houver diferença sem explicação ou gabarito que não bate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import median

import pyarrow as pa

from src.comum import caminho_tabela, carregar_config, conectar_duckdb, registrar_delta
from src.gold import build
from src.gold.export import ARQUIVOS, expandir, nomes_arquivos, schema_de

SECOES_MANIFEST = ["periodo_base", "janelas", "modelo", "parametros_cesta", "parametros_rede", "parametros_laboratorio"]
NOVOS_V41 = ("acionamento_crm", "departamentos_quadrante")   # contrato 5.1: não existem no gabarito congelado; caminho 2


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
        if schema_de(nome) in ("faturamento_tempo", *NOVOS_V41):
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
        for t in ["kpi_filtered", "cube_period", "period_comparable_store", "revenue_over_time", "department_risk",
                  "department_segment", "department_quadrant"]:
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

    # ------------------------------------------------------------ blocos de decisão (G45, G46)

    def crm(self, exportadas: list[dict]) -> list[dict]:
        """acionamento_crm exportado × SQL próprio, nos dois objetivos: as contas da semana e, por capacidade, a precisão,
        o recall e o valor das pausas reais entre os N (US$ e fração)."""
        idx = {(l["capacidade"], l["objetivo"], l["metodo"]): l for l in exportadas}
        capacidades = self.cfg["gold"]["crm"]["capacidades"]
        semana = self.con.execute(f"""
            WITH r AS (SELECT household_key, sum(fat) AS rev FROM v
                       WHERE week_no BETWEEN {self.fim} - {self.cfg['gold']['janela']['semanas']} + 1 AND {self.fim} GROUP BY 1)
            SELECT c.probability, r.rev, c.segment, c.household_key FROM churn_score c JOIN r USING (household_key)""").fetchall()
        teste = self.con.execute(f"""
            WITH r AS (SELECT t.household_key, t.snapshot_week, sum(v.fat) AS rev
                       FROM churn_test_score t JOIN v ON v.household_key = t.household_key
                        AND v.week_no BETWEEN t.snapshot_week - {self.cfg['gold']['janela']['semanas']} + 1 AND t.snapshot_week
                       GROUP BY 1, 2)
            SELECT t.snapshot_week, t.label, t.household_key, t.model_score, t.baseline_score, r.rev
            FROM churn_test_score t JOIN r USING (household_key, snapshot_week)""").fetchall()
        fotos = sorted({l[0] for l in teste})
        ordens_semana = {"pausas": lambda l: (-l[0], l[3]), "valor": lambda l: (-(l[0] * l[1]), l[3])}
        ordens_teste = {("pausas", "modelo"): lambda l: (-l[3], l[2]),
                        ("valor", "modelo"): lambda l: (-(l[3] * l[5]), l[2]),
                        ("pausas", "regra_simples"): lambda l: (-l[4], -l[5], l[2]),
                        ("valor", "regra_simples"): lambda l: (-l[4], -l[5], l[2])}
        checks = []
        for n in capacidades:
            for objetivo, ordem in ordens_semana.items():
                topo = sorted(semana, key=ordem)[:n]
                modelo = idx.get((n, objetivo, "modelo"), {})
                mix: dict[str, int] = {}
                for l in topo:
                    mix[l[2]] = mix.get(l[2], 0) + 1
                achado = {k: v for k, v in (modelo.get("mix_segmentos") or {}).items() if v}
                checks += [
                    {"nome": f"pausas_esperadas {objetivo} N={n}", "proprio": round(sum(l[0] for l in topo), 4), "exportado": modelo.get("pausas_esperadas"), "tol": 1e-4},
                    {"nome": f"faturamento_26s {objetivo} N={n}", "proprio": round(sum(l[1] for l in topo), 2), "exportado": modelo.get("faturamento_26s_em_jogo"), "tol": 0.01},
                    {"nome": f"mix_segmentos {objetivo} N={n}", "proprio": sorted(mix.items()), "exportado": sorted(achado.items()), "tol": None},
                ]
            for (objetivo, metodo), ordem in ordens_teste.items():
                precisoes, recalls, valores, fracoes = [], [], [], []
                for f in fotos:
                    da_foto = sorted((l for l in teste if l[0] == f), key=ordem)
                    acertos = sum(l[1] for l in da_foto[:n])
                    valor = sum(l[5] for l in da_foto[:n] if l[1] == 1)
                    precisoes.append(acertos / len(da_foto[:n]))
                    recalls.append(acertos / sum(l[1] for l in da_foto))
                    valores.append(valor)
                    fracoes.append(valor / sum(l[5] for l in da_foto if l[1] == 1))
                linha = idx.get((n, objetivo, metodo), {})
                prefixo = f"{objetivo} {metodo} N={n}"
                checks += [
                    {"nome": f"precisao {prefixo}", "proprio": round(sum(precisoes) / len(fotos), 4), "exportado": linha.get("precisao_historica"), "tol": 1e-4},
                    {"nome": f"recall {prefixo}", "proprio": round(sum(recalls) / len(fotos), 4), "exportado": linha.get("pausas_capturadas_historica"), "tol": 1e-4},
                    {"nome": f"valor {prefixo}", "proprio": round(sum(valores) / len(fotos), 2), "exportado": linha.get("valor_capturado_historico"), "tol": 0.01},
                    {"nome": f"fracao_valor {prefixo}", "proprio": round(sum(fracoes) / len(fotos), 4), "exportado": linha.get("fracao_valor_capturado_historica"), "tol": 1e-4},
                ]
        for c in checks:
            c["ok"] = c["exportado"] is not None and (
                c["proprio"] == c["exportado"] if c["tol"] is None else abs(c["proprio"] - c["exportado"]) <= c["tol"] + 1e-9)
        return checks

    def quadrante(self, periodo: str, exportadas: list[dict]) -> dict:
        """departamentos_quadrante exportado × montado aqui a partir da venda (todos os subconjuntos do período)."""
        ini = self.periodos[periodo][0]
        m = self.cfg["gold"]["metricas"]
        linhas = self.con.execute(f"""
            WITH vg AS (SELECT v.*, coalesce(s.segment, '{self.sem_segmento}') AS grupo
                        FROM v LEFT JOIN customer_segment s USING (household_key)),
                 l AS {self.lojas(ini)}
            SELECT grupo, department,
                   coalesce(sum(fat) FILTER (WHERE week_no BETWEEN {ini} AND {self.fim}), 0),
                   coalesce(sum(fat) FILTER (WHERE week_no BETWEEN {ini} AND {self.fim} AND store_id IN (SELECT * FROM l)), 0),
                   coalesce(sum(fat) FILTER (WHERE week_no BETWEEN {ini - self.ano} AND {self.fim - self.ano} AND store_id IN (SELECT * FROM l)), 0),
                   count(DISTINCT household_key) FILTER (WHERE week_no BETWEEN {ini} AND {self.fim})
            FROM vg GROUP BY 1, 2""").fetchall()
        segmentos = m["segmentos"]
        subconjuntos = {"todos": set(segmentos) | {self.sem_segmento}}
        for mascara in range(1, 1 << len(segmentos)):
            nomes = [s for b, s in enumerate(segmentos) if mascara >> b & 1]
            subconjuntos["+".join(nomes)] = set(nomes)

        def soma(grupos: set) -> dict[str, list]:
            saida: dict[str, list] = {}
            for grupo, dep, fat, comp, ant, compradores in linhas:
                if grupo in grupos:
                    t = saida.setdefault(dep, [0.0, 0.0, 0.0, 0])
                    t[0] += fat; t[1] += comp; t[2] += ant; t[3] += compradores
            return saida

        todos_fat = {d: t[0] for d, t in soma(subconjuntos["todos"]).items()}
        total_todos = sum(todos_fat.values())
        proprio = {}
        for subset, grupos in subconjuntos.items():
            t = soma(grupos)
            fat = sum(x[0] for x in t.values())
            comp, ant = sum(x[1] for x in t.values()), sum(x[2] for x in t.values())
            if not fat or not ant:
                continue
            corte_g = comp / ant - 1
            validos = {d: x for d, x in t.items() if x[0] > 0 and x[2] > 0 and x[3] >= m["limites"]["grupo_compradores"]
                       and todos_fat[d] / total_todos >= m["limites"]["departamento_participacao"]}
            if not validos:
                continue
            corte_s = median(x[0] / fat for x in validos.values())
            q = {}
            for d, x in validos.items():
                share, g = x[0] / fat, x[1] / x[2] - 1
                nome = ({True: "manter", False: "investir"} if g >= corte_g else {True: "defender", False: "rever"})[share >= corte_s]
                q[d] = {"participacao": share, "crescimento": g, "corte_participacao": corte_s, "corte_crescimento": corte_g,
                        "quadrante": nome, "valor_gap": x[2] * (g - corte_g), "destaque": None}
            defender = sorted((d for d in q if q[d]["quadrante"] == "defender"), key=lambda d: (q[d]["valor_gap"], d))
            for i, d in enumerate(defender[:3], 1):
                q[d]["destaque"] = i
            for d, v in q.items():
                proprio[(subset, d)] = v
        exp = {(l["subconjunto"], l["departamento"]): l for l in exportadas}
        tolerancia = {"participacao": 1e-4, "crescimento": 1e-4, "corte_participacao": 1e-4, "corte_crescimento": 1e-4, "valor_gap": 0.01}
        iguais, primeira = 0, ""
        for k in sorted(set(proprio) | set(exp), key=str):
            a, b = proprio.get(k), exp.get(k)
            ok = a is not None and b is not None and all(
                a[c] == b[c] if c not in tolerancia else abs(a[c] - b[c]) <= tolerancia[c] for c in a)
            iguais += ok
            if not ok and not primeira:
                primeira = f"{k}: SQL próprio {a}, exportado {b}"
        # Na gold gravada: soma de share = 1 entre os válidos (em department_quadrant) e os fora dela (amostra pequena), e
        # cada válido em exatamente um dos 4 quadrantes.
        fora = [s for s, v in self.con.execute(f"""
            SELECT s.subset, coalesce(sum(s.share) FILTER (WHERE q.department IS NOT NULL), 0)
                             + coalesce(sum(s.share) FILTER (WHERE q.department IS NULL), 0)
            FROM department_segment s
            LEFT JOIN department_quadrant q USING (period, subset, department)
            WHERE s.period = '{periodo}' AND s.department <> 'todos' GROUP BY 1""").fetchall() if abs(v - 1) > 1e-9]
        repetidos = self.um(f"""SELECT count(*) FROM (SELECT subset, department FROM department_quadrant WHERE period = '{periodo}'
                                GROUP BY 1, 2 HAVING count(*) <> 1 OR any_value(quadrant) NOT IN ('invest', 'keep', 'defend', 'review'))""")
        if repetidos:
            fora.append(f"{repetidos} departamento(s) fora de exatamente um quadrante")
        return {"periodo": periodo, "proprio": len(proprio), "exportado": len(exp), "linhas_arquivo": len(exportadas), "iguais": iguais,
                "primeira": primeira or (f"soma de share != 1 em {fora}" if fora else ""), "soma_share_ok": not fora}


def pausas_populacao_inteira(cfg: dict) -> tuple[int, dict[str, float]]:
    """O próprio SQL de crm_capacity com N = população inteira: a soma das probabilidades tem de dar o gabarito nos dois
    objetivos, porque a ordem não muda quem entra quando todos entram."""
    con = conectar_duckdb(cfg)
    try:
        build.configurar_metricas(con, cfg)
        con.execute(build.MACROS_SQL.read_text(encoding="utf-8"))
        for nome in ("churn_score", "churn_test_score", "churn_features"):
            registrar_delta(con, nome, caminho_tabela(cfg, "gold", build.MODELOS_LIDOS[nome]))
        n = con.execute("SELECT count(*) FROM churn_score").fetchall()[0][0]
        con.unregister("config_crm_capacity")
        con.register("config_crm_capacity", pa.table({"capacity": pa.array([n], pa.int32())}))
        sql = f"SELECT objective, pauses_expected FROM ({build._sql_metrica('crm_capacity')}) WHERE method = 'model'"
        return n, dict(con.execute(sql).fetchall())
    finally:
        con.close()


METRICA_DO_OBJETIVO = {"pausas": "precisao_historica", "valor": "valor_capturado_historico"}   # G48


def curva_modelo_regra(exportadas: list[dict]) -> list[tuple]:
    """(objetivo, capacidade, modelo, regra simples) na métrica do objetivo: registra quem fica acima, sem forçar (G48)."""
    idx = {(l["objetivo"], l["capacidade"], l["metodo"]): l[METRICA_DO_OBJETIVO[l["objetivo"]]] for l in exportadas}
    return [(o, n, idx[(o, n, "modelo")], idx[(o, n, "regra_simples")])
            for o in METRICA_DO_OBJETIVO for n in sorted({c for _, c, _ in idx})]


def caminho_2(cfg: dict) -> tuple[list[tuple], list[dict], dict]:
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
    crm = expandir(json.loads((cfg["paths"]["export"] / "acionamento_crm.json").read_text(encoding="utf-8")))
    populacao, pausas = pausas_populacao_inteira(cfg)
    gabarito = next(g for g in cfg["gold"]["conferencia"]["gabaritos"] if g["nome"] == "pausas_esperadas")
    blocos = {"crm": c.crm(crm), "curva": curva_modelo_regra(crm),
              "populacao": {"n": populacao, "pausas": pausas, "gabarito": gabarito["valor"],
                            "ok": len(pausas) == 2 and all(round(v, gabarito["casas"]) == gabarito["valor"] for v in pausas.values())},
              "quadrante": [c.quadrante(p, expandir(json.loads((cfg["paths"]["export"] / f"departamentos_quadrante_{p}.json").read_text(encoding="utf-8"))))
                            for p, (_, _, tem_ano) in c.periodos.items() if tem_ano]}
    c.con.close()
    return linhas, tempo, blocos


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
    gabaritos, tempo, blocos = caminho_2(cfg)
    print(f"{'gabarito':<32} {'esperado':>14} {'SQL próprio':>14} {'gold':>14}")
    for nome, e, p, g, ok in gabaritos:
        print(f"{nome:<32} {e!s:>14} {p!s:>14} {g!s:>14}  {'✅' if ok else '❌'}")
    print(f"\nGabaritos: {sum(1 for l in gabaritos if l[4])} de {len(gabaritos)}")
    print("\nfaturamento_tempo exportado × SQL próprio (ponto × grupo × departamento, 2 casas):")
    for t in tempo:
        ok = t["iguais"] == t["proprio"] == t["exportado"]
        print(f"  {t['periodo']:<5} grão {t['ponto']:<4}  linhas: SQL próprio {t['proprio']:,}, exportado {t['exportado']:,}, "
              f"iguais {t['iguais']:,}  {'✅' if ok else '❌ ' + t['primeira']}")

    print("\nBloco 1, acionamento_crm × SQL próprio (faturamento de 26 s direto da silver):")
    pop = blocos["populacao"]
    pausas_pop = "; ".join(f"{o} {v:.4f}" for o, v in sorted(pop["pausas"].items()))
    print(f"  pausas esperadas com N = população inteira ({pop['n']:,}): {pausas_pop}; gabarito {pop['gabarito']}  {'✅' if pop['ok'] else '❌'}")
    errados = [c for c in blocos["crm"] if not c["ok"]]
    print(f"  conferências: {len(blocos['crm']) - len(errados)} de {len(blocos['crm'])} iguais")
    for c in errados:
        print(f"    ❌ {c['nome']}: SQL próprio {c['proprio']}, exportado {c['exportado']}")
    for c in blocos["crm"]:
        if c["nome"] in ("precisao pausas modelo N=100", "precisao pausas regra_simples N=100",
                         "valor valor modelo N=100", "valor valor regra_simples N=100",
                         "fracao_valor valor modelo N=100", "fracao_valor valor regra_simples N=100"):
            print(f"  {c['nome']}: SQL próprio {c['proprio']}, exportado {c['exportado']}  {'✅' if c['ok'] else '❌'}")
    for objetivo, metrica in METRICA_DO_OBJETIVO.items():
        curva = [l for l in blocos["curva"] if l[0] == objetivo]
        print(f"  objetivo {objetivo}, {metrica} no teste (modelo × regra simples; informativo, não reprova):")
        for _, n, modelo, regra in curva:
            print(f"    N={n:<4} {modelo:,.4f} × {regra:,.4f}  {'modelo acima' if modelo > regra else 'empate' if modelo == regra else 'regra acima'}")
        print(f"    modelo acima em {sum(1 for _, _, a, b in curva if a > b)} de {len(curva)} capacidades")
    print("\nBloco 2, departamentos_quadrante × montado a partir da venda:")
    for q in blocos["quadrante"]:
        ok = q["iguais"] == q["proprio"] == q["exportado"] == q["linhas_arquivo"] and q["soma_share_ok"]
        print(f"  {q['periodo']:<4} linhas: SQL próprio {q['proprio']:,}, exportado {q['exportado']:,}, iguais {q['iguais']:,}; "
              f"soma de share = 1 em todos os recortes: {'sim' if q['soma_share_ok'] else 'não'}  {'✅' if ok else '❌ ' + q['primeira']}")

    falhas = (sum(len(r["sem_explicacao"]) for r in c1) + sum(1 for l in gabaritos if not l[4])
              + sum(1 for t in tempo if not t["iguais"] == t["proprio"] == t["exportado"])
              + len(errados) + (not pop["ok"])
              + sum(1 for q in blocos["quadrante"] if not (q["iguais"] == q["proprio"] == q["exportado"] == q["linhas_arquivo"] and q["soma_share_ok"])))
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
