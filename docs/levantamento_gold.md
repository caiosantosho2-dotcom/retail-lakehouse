# Levantamento para a gold (29/10/2026)

> Só levantamento, sem construir nada. Fontes lidas sem alterar (somente leitura): `C:\retail-bi-dashboard` (painel atual, commit `dc69cc1`) e `C:\RAG_Varejo` (commit `fffb207`, o mesmo `rag_commit` do `manifest.json` do painel).
> Base para a spec da fase 3. As perguntas que só o Caio decide estão na seção 4.

## Resumo
- **A silver já reproduz todos os números de gabarito**, conferidos aqui por SQL próprio sobre `fact_sales` com `is_merchandise` (seção 2.3). A gold pode partir da silver como está. Falta só uma informação que o RAG usa e a silver não guarda: quantos dias tem cada semana, porque a janela termina na última semana completa (a 101).
- **O painel não calcula quase nada:** ele herda as definições das views do RAG (`vw_vendas_item`, `vw_janela`, `vw_metricas_cliente`, `vw_lojas_like_for_like`...) e acrescenta as suas em `scripts/sql/views_painel.sql`. Na gold, essas duas camadas viram uma só.
- **Três métricas têm mais de uma definição** (seção 2.2): "base inteira" (101 ou 102 semanas), "dinheiro/valor em risco" (3 fórmulas) e "ticket médio" por segmento (média de médias no RFM do RAG).
- **Os modelos estatísticos dependem uns dos outros:** RFM → CLV, risco de pausa e teste de desconto. O risco de pausa **não devolve a probabilidade por cliente**, e o painel teve de reproduzir o treino por fora (`rag_modelos._reproduzir`) para obtê-la e para desenhar a curva ROC.
- **O venv do lakehouse não tem** scikit-learn, scipy nem statsmodels, e o numpy e o pandas estão em versões diferentes das do RAG.

---

## 1. Painel v4: o que cada elemento precisa

### 1.0 Convenções que valem para todas as abas
| Item | Hoje no painel | Origem |
|---|---|---|
| **Universo de venda** | só mercadoria: o RAG lê `fato_transacoes`, que já exclui não mercadoria e quantidade 0 (= silver `fact_sales WHERE is_merchandise`) | `RAG src/etl.py`, `vw_vendas_item` |
| **Fim dos dados** | semana **101**, a última com 7 dias (a 102 tem 6) | `vw_janela` (`dim_data.semana_completa`) |
| **Períodos do filtro** | `4s` = semanas 98–101 · `13s` = 89–101 · `26s` = 76–101 · `base` = **1–101** | `painel_periodos.sql`, `manifest.janelas` |
| **Ano anterior** | as mesmas semanas − 52 (`26s` → 24–49); a base inteira não tem | `vw_janela.offset_semanas` |
| **Lojas comparáveis** | por período: pelo menos 1 cesta no período e no mesmo período − 52. São 123 lojas em 4s, 160 em 13s e 214 em 26s | `painel.lojas_comparaveis` (regra de `vw_lojas_like_for_like` levada a cada janela) |
| **Segmento** | atributo **fixo** do cliente: RFM das 26 semanas (76–101), aplicado a todo o histórico. Quem não comprou nas 26 semanas fica em **"Sem segmento"** (um grupo, não um chip) | `painel.grupo_cliente` |
| **Filtro de segmento** | 4 chips: nenhum ligado = os 4 segmentos + "Sem segmento"; ligar chips forma 15 **subconjuntos** (máscara de bits, ex.: `Fiéis+Regulares`) | `painel.subconjuntos` |
| **Filtro de departamento** | lista na ordem do faturamento de 26 s; ⚠ quando o departamento tem menos de 0,1% do faturamento de 26 s | `departamentos.json` |
| **Somas no navegador** | só do que soma (faturamento, desconto, valor bruto); o que não soma vem pronto por subconjunto | `agregados.js` |

### 1.1 Visão Geral
| Elemento | v4 | Grão | Colunas | Período / segmento / departamento |
|---|---|---|---|---|
| **KPI Faturamento** | fica | período × grupo × departamento (soma no navegador) | `faturamento` (todas as lojas), `faturamento_comparavel`, `faturamento_ano_anterior` | os 4 períodos; filtra segmento e departamento (aceita vários); variação = comparável ÷ ano anterior − 1 |
| **KPI % de desconto** | fica | o mesmo cubo | `desconto`, `valor_bruto` nos 3 recortes | idem; % = desconto ÷ valor bruto |
| **KPI Cestas, Ticket médio, Itens por cesta** | fica | período × **subconjunto** × departamento (`'todos'` ou **um** só) | valor, comparável, ano anterior, variação, `lojas_comparaveis`, `amostra_pequena` (menos de 100 cestas) | com 2 ou mais departamentos o card mostra "selecione um departamento" |
| **KPI Clientes ativos** | fica | idem | valor e ano anterior (comparável = valor, **sem filtro de loja**) | o mesmo número em 4, 13 e 26 s (todos terminam na 101) |
| **Faturamento semanal** | **muda**: só o período selecionado, com o ano anterior tracejado. Proposta ainda a confirmar: **diário** em 4 s, **semanal** em 13 s, 26 s e base | hoje: semana (as 52 últimas) × grupo × departamento | `semana_inicio`, `faturamento`, `faturamento_ano_anterior` (só nas semanas ≥ 76) | hoje usa as **lojas comparáveis de 26 s em todas as semanas**. O v4 precisa de: semanas 1–101 com o ano anterior onde ele existir; e, se o diário for aprovado, dia × grupo × departamento das semanas 98–101 mais o mesmo dia − 364 |
| **Faturamento por segmento** | fica | período × grupo (do cubo) | `faturamento` por grupo, % do total | todas as lojas; filtra departamento; o segmento destaca, não filtra; "Sem segmento" aparece e não é clicável |
| **Faturamento por departamento + traço do ano anterior** | fica | período × departamento (do cubo) | com ano anterior: barras = **comparável**, traço = ano anterior; base: todas as lojas | top 10 + "Outros"; filtra segmento; departamento destaca |
| ~~O que puxou a variação~~ | **sai** | — | — | — |

### 1.2 Categorias (fica como está)
| Elemento | Grão | Colunas | Observação |
|---|---|---|---|
| **Lista de departamentos** (busca; ordem por faturamento, crescimento ou % de desconto; ⇄ = tem par confiável) | período × subconjunto × departamento | faturamento, crescimento, desconto; `amostra_pequena`; a marca ⇄ vem dos pares de 1.2 | arquivos por período |
| **Cabeçalho** (faturamento, participação, vs ano anterior, clientes) | idem | `faturamento`, `participacao`, `crescimento` (lojas comparáveis), `compradores` | ⚠ abaixo de 30 compradores no subconjunto |
| **Quem compra** (barra por segmento) | período × grupo × departamento | faturamento | soma do cubo da Visão Geral |
| **Faturamento semanal, 52 semanas** | semana × grupo × departamento | faturamento (sem ano anterior) | usa o mesmo cubo semanal da Visão Geral: ver a pergunta 3 |
| **Compra junto com** (pares de subcategorias em frases) | período × subconjunto × departamento × par | `cestas_par`, `cestas_a`, `cestas_b`, `cestas_total`, `suporte`, `confianca_a_b`, `confianca_b_a`, `lift` | top 10 por lift entre pares com **200 ou mais cestas** |
| **Perfil (radar de 6 atributos) + comparação** | período × departamento (percentil entre departamentos) e período × subconjunto × departamento (índice contra todos) | participação, crescimento, penetração, frequência, desconto, marca própria; percentil 0–100; índice 100 = igual | penetração e crescimento ficam nulos na base inteira |
| **Top 10 subcategorias** | período × departamento (ou `'todos'`) × subcategoria | `faturamento`, `participacao`, `posicao`; em `'todos'`, também `departamento_origem` | todas as lojas; não filtra segmento |
| **Dinheiro em risco** | subconjunto × departamento, **fixo em 26 s** | `dinheiro_em_risco` (faturamento de 26 s vindo de clientes na **faixa alta**, prob ≥ limiar do modelo) e % do departamento | precisa da **probabilidade de pausa por cliente** (seção 3.3) |

### 1.3 Cestas & Marcas (fica como está)
| Elemento | Grão | Colunas | Observação |
|---|---|---|---|
| **Concentração** ("N subcategorias fazem 80% do faturamento") | período × subconjunto | `subcategorias_80`, `subcategorias` | subcategoria = departamento × `commodity_desc`; a que cruza 80% conta |
| **Rede de cestas: nós** | nó (as **80** maiores subcategorias em 26 s) | `no`, `departamento`, `subcategoria`, `faturamento`, `x`, `y` | nós e posições **fixos** em qualquer período; `x`/`y` vêm de `scripts/layout.py` (MDS) |
| **Rede: ligações desenhadas** | par desenhado | as **3** de maior lift de cada nó (todos os clientes, 26 s, 200 ou mais cestas) | fixas |
| **Rede: números por período** | período × subconjunto × ligação | `cestas_par`, `lift`, `indice` (lift do subconjunto ÷ lift de todos), `amostra_pequena` | — |
| **Pares do nó selecionado** | período × subconjunto × nó × outro | `confianca`, `lift`, `indice`, `cestas_par` | top 10 por lift, 200 ou mais cestas |
| **Pares característicos do segmento** | período × subconjunto (sem `'todos'`) × par | `confianca_a_b`, `confianca_b_a`, `lift`, `lift_todos`, `indice`, `posicao` | top **15** por índice |
| **Marca própria e fornecedores** | período × subconjunto × departamento | faturamento, participação, % de marca própria, crescimento da marca própria e da nacional (lojas comparáveis), fabricantes nacionais, quantos fazem 80%, parte do maior | ⚠ abaixo de 0,1% do faturamento do subconjunto |

### 1.4 Página de Metodologia (fica como está; nenhum filtro se aplica)
| Elemento | Grão | Colunas |
|---|---|---|
| **Curva ROC** (modelo × regra simples) | classificador × ponto | `fpr`, `tpr`, `corte` (roc_curve com `drop_intermediate`) |
| **Matriz de confusão e métricas** | classificador | `descricao`, `corte`, `auc` + IC 95%, `auc_pr`, `precisao`, `recall`, `f1`, `alertas`, `tn/fp/fn/tp`, `pausas`, `taxa_falso_alarme` |
| **CLV por segmento + backtest** | segmento (os 4 + "Sem compra na janela") | `households`, `clv_medio` + IC 95%, `clv_total`, `receita_esperada`, backtest (households, real, método, ingênuo, erros) |
| **Teste de desconto: pares** | par de segmentos | `diferenca_pp`, IC 95%, `exclui_zero`, `p_ajustado` (Holm), `significativo` |
| **Teste de desconto: segmentos** | segmento | households, mediana, q25, q75, bigodes, taxa ponderada, desconto total, valor bruto |
| **Números de uma linha e textos** | — | definição do risco, período de teste, prevalência, diferença de AUC com IC; totais do CLV, margem, horizonte, erro do backtest; H, p, eta², veredito, impacto; **as conclusões ("e daí?") escritas pelo RAG** |

### 1.5 O que sai com a aba Clientes & Lojas
Somem: regiões (Jaccard das clientelas + layout), perfil, ranking e ficha de loja, matriz de migração (que exigia o RFM refeito no semestre anterior), lista de ação e o CSV, valor em risco por loja e o arquivo `segmentos.json`.
**Continuam necessários:** o segmento por cliente (todos os filtros) e a probabilidade de pausa por cliente com o limiar (dinheiro em risco em Categorias).

---

## 2. Métricas: onde e como são calculadas hoje

### 2.1 Definições
Convenções do RAG: desconto positivo, `desconto_total = −(RETAIL_DISC + COUPON_DISC + COUPON_MATCH_DISC)`, `valor_bruto = faturamento + desconto_total`, percentuais de 0 a 100. **No painel os percentuais são frações (0 a 1).** O universo é só mercadoria e quantidade > 0.

| Métrica | RAG (onde · fórmula · filtros) | Painel (onde · fórmula · filtros) | Gabarito |
|---|---|---|---|
| **Faturamento** | `vw_vendas_item` · `SUM(SALES_VALUE)` | `cubo_periodo` · a mesma soma; KPI = todas as lojas; a variação usa as lojas comparáveis | 26 s: US$ 2.151.812,00 (todas as lojas) |
| **Cestas** | `vw_metricas_cesta` · `COUNT(DISTINCT BASKET_ID)` | `kpis_filtrados` · idem; **com 1 departamento = cestas que têm o departamento** | 26 s: 68.947 |
| **Ticket médio** | `views.METRICAS` · `SUM(faturamento) / COUNT(DISTINCT BASKET_ID)`; o relatório de qualidade calcula sobre **todas as 102 semanas** | `kpis_filtrados` · idem, nas semanas do período; **com 1 departamento = faturamento do departamento ÷ cestas com ele** | **US$ 29,39** (102 semanas) · painel `base` (1–101): **29,38** · 26 s: 31,21 |
| **Itens por cesta** | `SUM(QUANTITY) / cestas` (102 semanas no relatório) | idem por período (com 1 departamento: itens do departamento ÷ cestas com ele) | **13,3** (13,3218 em 102 semanas; 13,3227 em 1–101) |
| **% de desconto** | `100 × SUM(desconto_total) / SUM(valor_bruto)` | `desconto ÷ valor_bruto` (fração), somados do cubo | **16,1%** (16,1179 em 102 semanas; 16,1294 em 1–101) |
| **Clientes ativos** | `vw_metricas_cliente.cliente_ativo`: ≥ 1 compra nas últimas 8 semanas do período (94–101) | idem; ano anterior = o mesmo estoque um ano antes, **sem filtro de loja**; **com 1 departamento = comprou o departamento nessas 8 semanas** | 2.205 (ano anterior 2.138) |
| **Lojas comparáveis** | `vw_lojas_like_for_like`: ≥ 1 cesta em 76–101 **e** em 24–49 (só 26 s) | a mesma regra em cada período | **214** em 26 s · 123 em 4 s · 160 em 13 s |
| **Variação contra o ano anterior** | `vw_yoy_resumo`: `100 × (atual ÷ base − 1)`, lojas comparáveis | `comparável ÷ ano anterior − 1` por período | **+3,4%** em 26 s (US$ 2.068.074,67 × 1.999.776,43) · 4 s +4,79% · 13 s +4,73% |
| **Penetração** | `vw_yoy_categoria`: clientes que compraram a categoria ÷ clientes com qualquer compra no período, os dois nas lojas comparáveis (26 s) | a mesma, em cada período | — |
| Participação, crescimento, frequência, marca própria (radar) | — | `departamento_subconjunto`: participação = faturamento do departamento ÷ faturamento do subconjunto; crescimento = lojas comparáveis; frequência = cestas com o departamento ÷ compradores; marca própria = `BRAND = 'Private'` ÷ faturamento | — |
| **Segmentos** | RFM (seção 3.1) | importados do RAG | Fiéis = **35%** dos clientes e **71%** do faturamento |
| **Risco de pausa** | `churn` (seção 3.3) | importado e reproduzido | AUC **0,85** × **0,74** (regra simples) · limiar **0,17** · **243** alertas · **135,95** (~136) pausas esperadas |
| **Amostra pequena** | loja com menos de 100 cestas | departamento com menos de 0,1% do faturamento de 26 s · par com menos de 200 cestas · grupo com menos de 30 compradores · KPI com menos de 100 cestas | — |

### 2.2 Uma métrica com duas definições (pontos de conflito)
1. **"Base inteira"**
   - **Relatório de qualidade do RAG:** **semanas 1–102**. Dá ticket 29,39 e faturamento US$ 7.376.322,37. É o gabarito citado na F2 do documento de decisões.
   - **Painel:** **semanas 1–101** (decisão 4 da fase 2 do painel). Dá ticket 29,38 e faturamento US$ 7.310.849,82.
   - O mesmo nome serve a duas janelas. Itens por cesta e % de desconto só coincidem por causa do arredondamento.
2. **"Dinheiro / valor em risco": três fórmulas**
   - **RAG, `churn.risco_por_segmento.valor_em_risco_usd`:** `Σ prob × (gasto de 26 s ÷ 26) × 8`, o gasto esperado que se perde nas 8 semanas.
   - **Painel, Categorias (`dinheiro_em_risco`, fica):** faturamento de 26 s **dos clientes com prob ≥ limiar** (faixa alta), sem ponderar.
   - **Painel, lista de ação (`faturamento_em_risco`, sai com Clientes & Lojas):** `prob × faturamento de 26 s`.
3. **"Ticket médio" por segmento:** o perfil do RFM do RAG (`ticket_medio_usd`) é a **média dos tickets dos clientes** (média de médias), não `faturamento ÷ cestas` do segmento. O painel exporta esse número em `rag_segmentos` (era usado em `segmentos.json`, que sai no v4).
4. *(Extensões, não conflitos, mas a gold precisa nomeá-las):* cestas, ticket, itens por cesta e clientes ativos **com um departamento** têm definição própria no painel. O teste de desconto usa a **mediana do % por cliente**, uma estatística diferente da taxa ponderada do KPI.

### 2.3 Conferência por outro caminho: a silver reproduz os gabaritos? (SQL próprio, só leitura)
| Recorte (silver `fact_sales WHERE is_merchandise`) | Faturamento | Cestas | Ticket | Itens/cesta | % desconto |
|---|---:|---:|---:|---:|---:|
| semanas 1–102 (relatório do RAG) | 7.376.322,37 | 250.975 | 29,3907 | 13,3218 | 16,1179% |
| semanas 1–101 (painel, `base`) | 7.310.849,82 | 248.827 | 29,3813 | 13,3227 | 16,1294% |
| semanas 76–101 (26 s) | 2.151.812,00 | 68.947 | 31,2097 | 13,8036 | 15,6716% |

Lojas comparáveis de 26 s: **214**; faturamento US$ 2.068.074,67 × 1.999.776,43 = **+3,42%**. Clientes ativos (semanas 94–101): **2.205**. Households com mercadoria: 2.500. **Tudo bate** com o RAG e com o painel publicado. Dias por semana na `dim_date`: semana 1 = 5, 101 = 7, 102 = 6.

---

## 3. Código estatístico do RAG

**Pontos comuns aos cinco:**
- Parâmetros em `RAG config.yaml` (`semente: 42`, seção `analises`).
- Conexão somente leitura ao DuckDB do RAG (`src/nucleo/banco.py`) e cache em memória (`cache.py`).
- As funções públicas têm o decorador `registrar_chamada`, **que grava em `logs/chamadas.jsonl`**. O painel só chama as funções internas (`_calcular`, `_resultado`) para não escrever no RAG.
- Todas leem das views do RAG, nunca das tabelas cruas.

**Bibliotecas:**

| Biblioteca | RAG | venv do lakehouse |
|---|---|---|
| numpy | 2.5.3 | 2.5.4 |
| pandas | 3.0.6 | 3.1.0 |
| scikit-learn | 1.9.1 | não instalado |
| scipy | 1.18.1 | não instalado |
| statsmodels | 0.15.0 | não instalado |

**Ordem de dependência:**
```
vw_janela, vw_metricas_cliente, vw_cliente_semana, dim_household, dim_data
   └─ RFM (segmento por cliente, K)
        ├─ CLV (refaz o RFM na janela base com o mesmo K)
        ├─ Risco de pausa (usa o segmento só para o resumo por segmento)
        └─ Teste de desconto
```

### 3.1 Segmentação RFM: `src/nucleo/rfm.py`
- **Entrada:** `_calcular(cur, n_clusters=None)` / `_resultado` (com cache); `segmentos_por_household(cur)` para os outros módulos.
- **Entradas:**
  - `vw_metricas_cliente` com `periodo = 'atual'`: `recencia_dias`, `frequencia`, `valor`, `ticket_medio`, `pct_desconto`, `desconto_total`, `valor_bruto`, `tem_demografia`;
  - `COUNT(*)` de `dim_household` (2.500);
  - `base_rfm(cur, ini, fim)` monta o mesmo para qualquer janela, a partir de `vw_cliente_semana` e `dim_data`.
  - **Exclusões:** sem compra na janela; valor ≤ 0.
- **Método:**
  - matriz: R em dias, F e V em `log1p`, padronizados com `StandardScaler`;
  - K-Means com `n_init` 10 e semente 42;
  - **regra do K:** testa K de 2 a 8, com K ≥ 3; ARI mínimo de 0,90 entre 10 sementes e entre 10 subamostras de 80%; menor segmento ≥ 5%; silhueta ≥ 0,25; entre os que passam, vence a maior silhueta;
  - **nomes:** recência média ≥ 56 dias (8 × 7) → "Em pausa"; os demais, por valor médio (`LADO`; com 3 ativos: Fiéis, Regulares, Esporádicos).
- **Saídas:**
  - **atribuição `household_key → segmento`**;
  - perfil por segmento: households, % de households, recência, frequência, valor médio, valor total, ticket médio (média de médias), % do faturamento, desconto %;
  - tabela de avaliação dos K, estabilidade, `k_usado`, silhueta, excluídos e textos "e daí?".
- **Bibliotecas:** numpy, pandas, scikit-learn (`KMeans`, `silhouette_score`, `adjusted_rand_score`, `StandardScaler`).
- **O painel v4 usa:** o **segmento de cada cliente**, que é a base de todos os filtros, do faturamento por segmento, do "quem compra", do índice dos pares e das marcas; e os nomes, que o contrato exige que sejam os 4 de sempre.

### 3.2 CLV: `src/nucleo/clv.py`
- **Entrada:** `_calcular(cur)`.
- **Entradas:**
  - o RFM atual (K e atribuição);
  - `rfm.carregar_base(cur, 'base')`, que **refaz o K-Means na janela base** (24–49) com o mesmo K e exige os mesmos nomes (`_segmentar`; se os nomes mudarem, para);
  - gasto por janela vindo de `vw_cliente_semana` (`gasto_no_periodo`);
  - todos os households de `dim_household`.
- **Método:**
  - `CLV por cliente = margem 0,25 × gasto médio de 26 s × razão`, em que razão = gasto nas 52 semanas seguintes ÷ gasto nas 26 anteriores, do **mesmo segmento um ano antes**;
  - grupo "Sem compra na janela" = gasto médio futuro dos análogos do ano anterior;
  - IC 95% por bootstrap de households (2.000, semente 42);
  - horizonte de 52 semanas, que tem de ser igual ao deslocamento do ano anterior;
  - **backtest** de 26 semanas: calibra 24–49 → 50–75, segmenta 50–75, prevê 76–101 e compara com o real e com a regra ingênua "repetir".
- **Saídas:**
  - por segmento: `n`, valor médio, razão + IC, receita esperada, `clv_medio` + IC, `clv_total`, calibração;
  - total + IC, premissas, backtest (por segmento e total, MAE por cliente, em quantos grupos ganha), avisos e "e daí?".
- **Bibliotecas:** numpy, pandas (e o RFM).
- **O painel v4 usa:** o CLV por segmento com IC e o backtest (`lab_clv`), mais os totais, a margem, o horizonte e a conclusão (`parametros_laboratorio.clv`).

### 3.3 Risco de pausa (churn): `src/nucleo/churn.py`
- **Entrada:** `_calcular(cur)`.
- **Entradas:**
  - `vw_cliente_semana` até a semana 101 (cestas e faturamento por cliente × semana), virando uma matriz em memória (`carregar_painel`);
  - os ids de `dim_household`;
  - o fim da janela vindo de `vw_janela`;
  - o segmento, só para o resumo.
- **Método:**
  - **população** da foto T: comprou nas últimas 8 semanas e tem ≥ 16 semanas de histórico;
  - **5 variáveis:** recência em semanas, `log1p` das compras de 8 s, `log1p` do valor de 26 s, semanas com compra em 26 s, maior pausa em 26 s;
  - **rótulo:** nenhuma compra em T+1..T+8;
  - **fotos:** treino T = 30..68 de 4 em 4; validação 77; teste 85 e 93;
  - `StandardScaler` + `LogisticRegression(C=1, L2, max_iter=2000, semente 42)`;
  - **limiar** = maior F1 na validação, na grade 0,01..0,795 com passo 0,005 (deu 0,17);
  - **regra simples:** recência ≥ k, com o k de maior F1 no treino (1..7);
  - IC da AUC por bootstrap de households (500).
- **Saídas:**
  - modelo e regra simples: AUC, AUC-PR, precisão, recall, F1, `tn/fp/fn/tp`, alertas; IC da AUC, diferença de AUC + IC; `limiar`, `k_baseline`;
  - curva de limiares, calibração por decil, fatores (coeficientes), taxa de retorno em 18 semanas;
  - **resumo por segmento na foto final T = 101:** households, risco médio, pausas esperadas, alertas, `valor_em_risco_usd`;
  - "e daí?".
  - **Não devolve:** a probabilidade **por cliente** nem as notas do conjunto de teste.
- **Bibliotecas:** numpy, pandas, scikit-learn (`LogisticRegression`, `StandardScaler`, `roc_auc_score`, `average_precision_score`, `confusion_matrix`, `precision_recall_fscore_support`).
- **O painel v4 usa:**
  - a **probabilidade por cliente + o limiar** (dinheiro em risco de Categorias);
  - as métricas e as duas matrizes de confusão (Metodologia);
  - as **notas do teste**, para a curva ROC.
  - **Como o painel obtém o que falta:** `rag_modelos._reproduzir` repete os passos de `_calcular` (fotos, treino, limiar, foto final) com as funções do RAG. `curvas_roc` **para a exportação** se a AUC (4 casas), o k ou as matrizes não forem iguais aos do RAG.

### 3.4 Curva ROC (não existe como saída no RAG)
- **Onde:** `retail-bi-dashboard/scripts/rag_modelos.py::curvas_roc`.
- **Entrada:** as notas reproduzidas do teste (modelo = probabilidade; regra simples = recência), o `y` do teste, o limiar e o k.
- **Método:** `sklearn.metrics.roc_curve(drop_intermediate=True)`; matriz de confusão em cada ponto de operação; conferência contra o RAG.
- **Saída:** pontos `classificador × ponto (fpr, tpr, corte)`.
- **O painel v4 usa:** o gráfico ROC da Metodologia.

### 3.5 Teste de desconto: `src/nucleo/teste_desconto.py` (+ `src/teste_hipotese.py`)
- **Entrada:** `_calcular(cur)`.
- **Entradas:** `rfm.carregar_base(cur)` (`pct_desconto`, `frequencia` e `valor` por cliente, janela de 26 s) + o segmento de cada cliente. Para se a junção perder algum cliente.
- **Método:**
  - hipótese escrita antes de rodar ("desconto parecido");
  - Shapiro por grupo (só reportado);
  - **Kruskal-Wallis** (`scipy.stats`, com eta² aproximado);
  - post-hoc de **Mann-Whitney com Holm** (`statsmodels.multipletests`), só se o teste geral for significativo;
  - IC bootstrap da diferença de medianas por par (2.000, 95%, semente 42);
  - **veredito** exige efeito: eta² ≥ 0,01 ou algum par com diferença ≥ 1 pp e IC que exclui zero;
  - **sensibilidade:** repete só com clientes de ≥ 5 compras.
- **Saídas:**
  - por segmento: households, mediana, q25, q75, bigodes, taxa ponderada, desconto total, valor bruto;
  - Kruskal-Wallis (H, p, eta²), post-hoc, IC das diferenças, veredito, sensibilidade;
  - impacto (desconto total, taxa geral, economia se igualar) e "e daí?".
- **Bibliotecas:** numpy, pandas, scipy, statsmodels.
- **O painel v4 usa:** `lab_desconto` (pares), `lab_desconto_segmentos` (caixas) e `parametros_laboratorio.desconto` (estatísticas, veredito e textos).

### 3.6 O que o código precisa para ler da silver
- Views equivalentes a `vw_janela`, `vw_metricas_cliente`, `vw_cliente_semana`, `dim_household` e `dim_data`.
- **`vw_janela` precisa de `semana_completa`:** dias por semana = 7. A silver tem os dias; falta derivar a coluna (silver ou gold).
- A conta do faturamento e dos clientes já fecha (2.3).
- **Fora do RAG, mas usado pelo v4:** o layout da rede de cestas (`retail-bi-dashboard/scripts/layout.py`, MDS do scikit-learn + `scipy.shortest_path`, semente fixa). É código do **painel**, não do RAG (ver a pergunta 9).

---

## 4. Perguntas que só o Caio pode decidir
1. **"Base inteira" = semanas 1–101 ou 1–102?**
   - Com 1–101 (painel), o ticket é **29,38** e a gold bate com o painel publicado.
   - Com 1–102 (relatório do RAG), o ticket é **29,39** e bate com o gabarito escrito na F2 do documento de decisões.
   - Seja qual for a escolha, a outra diferença precisa ficar registrada (regra 3).
2. **Faturamento semanal do v4:**
   - (a) A proposta "diário em 4 s, semanal no resto" está aprovada? O diário exige um ano anterior **por dia** (dia − 364), que nem o RAG nem o painel definem hoje.
   - (b) **Quais lojas?** Hoje são as comparáveis de 26 s em todas as semanas. Com só o período selecionado, faria sentido usar as comparáveis **do próprio período**, como nos KPIs.
   - (c) Na base inteira, a linha fica sem o ano anterior?
3. **Categorias "fica como está", mas o gráfico semanal dela usa o mesmo cubo do da Visão Geral.** Ele continua com 52 semanas e o sombreado, diferente do novo gráfico da Visão Geral, ou acompanha a mudança?
4. **Dinheiro em risco: qual é a definição única?** Há três fórmulas (2.2, item 2). A que fica no v4 é a do painel: faturamento de 26 s dos clientes na faixa alta. A do RAG pondera pela probabilidade e olha 8 semanas. A gold só pode ter uma (regra 4).
5. **Escopo do código estatístico:**
   - a gold leva os 4 modelos, a curva ROC e os **textos "e daí?"** que a Metodologia mostra?
   - Proposta: adaptar a cópia do `churn` para **devolver a probabilidade por cliente e as notas do teste**, em vez de reproduzir o treino por fora como o painel faz.
6. **Quanto os modelos precisam bater:** exigir igualdade exata com o RAG? Os números a conferir são AUC de 0,85 e 0,74 em 4 casas, matrizes de confusão, limiar 0,17, k, 243 alertas, 135,95 pausas esperadas, Fiéis 35% / 71%, CLV e IC, Kruskal-Wallis. Ou admitir uma tolerância? Para igualar, a proposta é **instalar exatamente as versões do RAG** (scikit-learn 1.9.1, scipy 1.18.1, statsmodels 0.15.0) e decidir se numpy e pandas descem para as versões do RAG (2.5.3 e 3.0.6).
7. **Segmento fixo:** confirmar que o segmento é o das 26 semanas (76–101), aplicado a todo o histórico e em todos os períodos, e que "Sem segmento" continua sendo um grupo.
8. **Formato da gold e como o painel v4 a lê:**
   - (a) **cubos prontos** como hoje (período × subconjunto de segmentos × departamento, 15 subconjuntos), com o navegador só somando; ou
   - (b) tabelas mais granulares, com a agregação feita na exportação.
   - E o painel v4 continua lendo **JSONs exportados** (mantendo os contratos em `contracts/`) ou passa a ler outra coisa?
9. **Layout da rede de cestas:** a R1 só autoriza reaproveitar código do **RAG**. O layout (MDS) é código do **painel**. Copiar `layout.py` é permitido, ou as posições são recalculadas de outro jeito?
10. **Métricas com um departamento:** a gold mantém as definições do painel (cestas com o departamento, ticket do departamento, clientes ativos do departamento) e o "selecione um departamento" quando há 2 ou mais?
11. **`semana_completa` / dias por semana:** entra na `dim_date` da silver (mudança na silver) ou é calculada só na gold?
