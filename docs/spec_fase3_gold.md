# Spec — Fase 3: Gold (métricas + modelos + exportação para o painel v4)

> Regras gerais: `docs/decisoes_arquitetura_lakehouse.md` (L1, R1 com a emenda G9, Painel v4, F2, F3, S9, **G1–G12**) e `CLAUDE.md`. Levantamento que originou esta spec: `docs/levantamento_gold.md`. Em conflito, vale o documento de decisões.
> Fluxo normal: plano → aprovação do Caio → construção → parada para revisão. **Não fazer commit** sem o Caio pedir.
> Fontes de regra (somente leitura, nunca alteradas): `C:\RAG_Varejo` (commit `fffb207`) e `C:\retail-bi-dashboard` (commit `dc69cc1`).

## Objetivo
Construir a gold a partir da silver, em Delta, reconstruída por inteiro a cada execução, em **três áreas (G12)**:
- `gold/features/`: as variáveis que entram nos modelos, calculadas do jeito do RAG e gravadas como foram usadas;
- `gold/models/`: as tabelas dos modelos estatísticos (segmento RFM, risco de pausa, CLV, teste de desconto, curva ROC e textos "e daí?"), com o código do RAG copiado para cá e adaptado para ler da silver (R1, G5);
- `gold/metrics/`: as métricas do painel v4 no grão dos cubos que ele usa (G8), cada métrica definida **uma vez**;
- uma **exportação** que grava os JSONs do painel v4 com os contratos atuais;
- uma **conferência** que compara o exportado com o painel publicado, valor a valor (G6: igualdade, não tolerância).

## Fora do escopo
- Construir o painel v4 (HTML/JS).
- Tudo da aba Clientes & Lojas: regiões, perfil, ranking e ficha de loja, migração, lista de ação, valor em risco por loja.
- Marketing (S7), `vacuum`, skills.
- Mudanças no RAG ou no painel publicado.

---

## 0. Ambiente (G6)
- `requirements.txt`: travar as versões do RAG:
  - `numpy==2.5.3` (desce de 2.5.4);
  - `pandas==3.0.6` (desce de 3.1.0);
  - `scikit-learn==1.9.1`, `scipy==1.18.1`, `statsmodels==0.15.0`;
  - as dependências que vierem junto: `joblib`, `threadpoolctl`, `patsy`.
- Antes de qualquer código da gold, provar que a troca de numpy/pandas não quebrou nada:
  - `python -m pytest -q` (74 testes);
  - o notebook com 23 de 23.
- Se alguma versão não instalar no Python 3.14.7, **parar e perguntar**. Nunca trocar de versão por conta própria.

## 1. Ajuste na silver: semana completa (G11)
- `sql/silver/dim_date.sql` ganha duas colunas:
  - `days_in_week` (INTEGER): `count(*) OVER (PARTITION BY week_no)`;
  - `is_complete_week` (BOOLEAN): `days_in_week = 7`.
- No membro `-1`, as duas ficam nulas (S12).
- Esperado: semana 1 = 5 dias, semana 102 = 6 dias, as outras 100 semanas = 7 dias.
- Teste novo em `tests/test_silver.py`, com uma semana curta nos dados mínimos.
- Verificação nova no notebook (seção Silver).
- Rodar `python -m src.silver.build` de novo e confirmar que as contagens da silver não mudaram.

## 2. Configuração (`config.yaml` e `config.example.yaml`, seção `gold`)
Nenhum número de regra fica escrito no código. A seção `gold` declara:
- **Períodos** (`4s` = 4 semanas, `13s` = 13, `26s` = 26, `base` = desde a semana 1):
  - todos terminam na **última semana completa** (lida da `dim_date`, G11; hoje a 101);
  - deslocamento do ano anterior: **52 semanas**; no diário (G2): **364 dias**;
  - grão do gráfico de tempo por período: `4s: day`, demais: `week`.
- **Janela do segmento:** `26s` (G7).
- **Clientes ativos:** comprou nas últimas **8** semanas do período.
- **Limites de amostra:**
  - KPI: 100 cestas;
  - departamento: 0,1% do faturamento de 26 s;
  - par: 200 cestas;
  - grupo: 30 compradores.
- **Rede de cestas:**
  - 80 nós da janela `26s`;
  - 3 ligações por nó;
  - top 10 pares por nó;
  - top 15 pares característicos;
  - concentração em 80%.
- **Top N:** 10 subcategorias e 10 departamentos no gráfico (o resto vira "Outros", no painel).
- **Modelos:** os parâmetros da seção `analises` do `config.yaml` do RAG, copiados com os mesmos valores, mais `semente: 42`. Inclui:
  - RFM: K 2..8 com K ≥ 3, ARI 0,90, menor segmento 5%, silhueta 0,25, pausa = 56 dias;
  - risco de pausa: fotos, horizonte de 8 semanas, grade do limiar, k da regra simples 1..7, bootstrap 500;
  - CLV: margem 0,25, horizonte 52, bootstrap 2.000;
  - teste de desconto: bootstrap 2.000, efeito mínimo eta² 0,01 ou 1 pp, sensibilidade com ≥ 5 compras.
- **Ordem e nomes dos segmentos:** Fiéis, Regulares, Esporádicos, Em pausa, depois "Sem segmento". Os textos ficam em português, porque o contrato exige.
- **Exportação:**
  - pasta de saída: `export/painel_v4/`, fora do git;
  - pasta dos contratos: `contracts/`;
  - pasta do painel publicado, usada só pela conferência e só para leitura: `C:\retail-bi-dashboard\site\data`. Esse caminho fica só no `config.yaml`; o `config.example.yaml` leva um caminho genérico.
- **Gabaritos fixos** (seção 8) com o valor esperado de cada um.

## 3. Base comum da gold (uma definição por métrica, regra 4)
- **`sql/gold/base/*.sql`:** as views de partida, registradas na conexão a cada execução e lidas da silver via `registrar_delta`:
  - `sales_item`: `fact_sales` só com mercadoria (`is_merchandise`) e semanas até o fim dos dados, com `discount = −(retail_disc + coupon_disc + coupon_match_disc)` e `gross_value = sales_value + discount`;
  - `customer_week`: cestas e faturamento por cliente × semana;
  - `customer_metrics`: as métricas de cliente na janela, equivalentes a `vw_metricas_cliente` do RAG;
  - `period`: os 4 períodos com semanas e dias, do atual e do ano anterior.
- **`sql/gold/metricas.sql`:** **macros do DuckDB**, uma por métrica. Todo cubo usa a macro e nunca reescreve a conta:
  - `avg_ticket(revenue, baskets)`;
  - `items_per_basket(items, baskets)`;
  - `discount_rate(discount, gross_value)`;
  - `growth(current, prior)`;
  - `penetration`, `frequency`, `share`, `private_label_share`;
  - `lift`, `confidence`, `support`, `index_vs_all`.
- **Percentuais em fração (0–1)**, como nos contratos. A conversão para 0–100 fica no painel.
- Gravadas como tabelas em `gold/metrics/`, porque outras tabelas e o painel dependem delas:

| Tabela | Grão | Conteúdo |
|---|---|---|
| `dim_period` | período | `period`, `week_start`, `week_end`, `day_start`, `day_end`, `prior_week_start`/`end` (nulos na base), `date_start`, `date_end` |
| `period_comparable_store` | período × loja | lojas com ≥ 1 cesta no período **e** no mesmo período − 52; esperado 123 / 160 / 214; a base não tem |
| `customer_group` | cliente (2.500) | `household_key`, `segment` (os 4 ou "Sem segmento"), vindo de `models/customer_segment` (G7) |
| `segment_subset` | subconjunto × segmento | os 15 subconjuntos (máscara de bits, rótulo `Fiéis+Regulares` etc.) e mais `todos` |

## 4. Modelos: `src/gold/modelos/` → `gold/features/` + `gold/models/` (G5, G6, G12)
- **Copiar do RAG (commit `fffb207`):**
  - `src/nucleo/rfm.py`, `clv.py`, `churn.py`, `teste_desconto.py`;
  - `src/teste_hipotese.py`.
- **Cada arquivo começa com um cabeçalho:** origem (arquivo + commit) e a lista de adaptações.
- **Adaptações permitidas, só estas:**
  1. **Entrada:** ler das views da seção 3 em vez das views do RAG. Mesmas colunas, nomes em inglês.
  2. **Remover o que escreve fora daqui:** o decorador `registrar_chamada` (que grava em `logs/chamadas.jsonl`) e o cache.
  3. **`churn`:** devolver também `prob_por_cliente`, a foto final T = 101, e `notas_teste`, as fotos 85 e 93 com `y`, a nota do modelo e a nota da regra simples (G5). O treino não muda.
  3b. **`churn` e `clv` (G12):** devolver também as variáveis que já calculam (as 5 variáveis e o rótulo de cada foto; o gasto por cliente por janela). Nenhuma conta é refeita fora do modelo.
  4. **Parâmetros:** vêm da seção `gold` do config.
- **Nenhuma adaptação pode mudar o método, a semente ou a ordem das operações.** Se for preciso mudar algo além disso, parar e perguntar.
- **ROC:**
  - código novo, `src/gold/modelos/roc.py`, com `roc_curve(drop_intermediate=True)` sobre `notas_teste`;
  - matriz de confusão no ponto de operação de cada classificador: limiar 0,17 no modelo e recência ≥ k na regra simples.
- **Pandas só com dados já agregados no DuckDB** (2.500 clientes × 101 semanas no máximo). Nunca a `fact_sales` inteira.

| Tabela (`gold/features/`, G12) | Grão | Colunas principais |
|---|---|---|
| `customer_rfm_features` | cliente com compra em 26 s (a entrada do K-Means) | `household_key`, `week_start`, `week_end`, `recency_days`, `frequency`, `monetary` (valores originais: o `log1p` e a padronização são do modelo, G21) (+ ticket, desconto, demografia) |
| `churn_features` | cliente × foto (treino, validação, teste, final) | `household_key`, `snapshot_week`, `role`, as 5 variáveis (`recency_weeks`, `log_purchases_8w`, `log_value_26w`, `weeks_with_purchase_26w`, `longest_gap_26w`), `label` (nulo na foto final) |
| `clv_features` | cliente × janela usada pelo CLV | `household_key`, `spend_window`, `week_start`, `week_end`, `spend`, `segment` |

| Tabela (`gold/models/`) | Grão | Colunas principais |
|---|---|---|
| `customer_segment` | cliente com compra em 26 s | `household_key`, `segment`, `recency_days`, `frequency`, `monetary`, `avg_ticket`, `discount_rate` |
| `rfm_k_evaluation` | K testado | `k`, `silhouette`, `ari_seeds_*`, `ari_subsamples_*`, `min_segment_pct`, `sizes`, `chosen` (sem `passed`: G16) |
| `rfm_segment_profile` | segmento (G16) | `households`, `households_pct`, `revenue_pct`, médias de R, F e V, ticket (média dos clientes), desconto |
| `churn_score` | cliente na foto T = 101 | `household_key`, `probability`, `is_high_risk` (prob ≥ limiar), `segment` |
| `churn_test_score` | cliente × foto de teste (85, 93) | `household_key`, `snapshot_week`, `label`, `model_score`, `baseline_score` |
| `churn_classifier` | classificador (modelo, regra simples) | `description`, `cutoff`, `auc` + IC 95%, `auc_pr`, `precision`, `recall`, `f1`, `alerts`, `tn`, `fp`, `fn`, `tp`, `pauses`, `false_alarm_rate` |
| `churn_roc` | classificador × ponto | `fpr`, `tpr`, `cutoff` |
| `clv_segment` | segmento (os 4 + "Sem compra na janela") | `households`, `clv_mean` + IC 95%, `clv_total`, `expected_revenue`, `ratio` + IC, colunas do backtest |
| `discount_test_pair` | par de segmentos | `difference_pp` + IC 95%, `excludes_zero`, `p_adjusted` (Holm), `significant` |
| `discount_test_segment` | segmento | `households`, `median`, `q25`, `q75`, `whisker_low`, `whisker_high`, `weighted_rate`, `discount_total`, `gross_value` |
| `model_summary` | modelo × chave | `model`, `key`, `value` (texto JSON): números de uma linha (limiar, k, prevalência, diferença de AUC + IC, totais do CLV, H, p, eta², veredito, impacto) e os **textos "e daí?"** do RAG |

## 5. Métricas: `sql/gold/metrics/*.sql` → `gold/metrics/` (G1–G4, G7, G10)
- **Uma tabela por cubo do painel**, com nomes em inglês. As regras vêm dos SQL do painel publicado (`scripts/sql/views_painel.sql` e os SQL de cada JSON), **lidos e reescritos aqui**, nunca copiados (G9).
- **Universo:** `sales_item` (mercadoria, semanas 1–101).
- **Lojas:**
  - o "atual" soma todas as lojas;
  - o "comparável" e o "ano anterior" usam `period_comparable_store` do próprio período.

| Tabela | Grão | Vira o JSON | Observação |
|---|---|---|---|
| `department` | departamento | `departamentos.json` | ordem: faturamento de 26 s, base, nome; `small_sample` < 0,1% |
| `revenue_over_time` | período × ponto (dia ou semana) × grupo × departamento | **novo**: `faturamento_tempo_<periodo>.json` | **G2/G3:** `point_start`, `revenue` e `revenue_prior_year`, os dois só das lojas comparáveis do período; diário em 4 s (dia − 364); base com todas as lojas e ano anterior nulo. Substitui `cubo_faturamento.json` |
| `cube_period` | período × grupo × departamento | `cubo_periodo.json` | só o que soma: faturamento, comparável, ano anterior, desconto, valor bruto |
| `kpi_filtered` | período × subconjunto × departamento (`todos` ou um) | `kpis_filtrados.json` | cestas, ticket, itens por cesta, clientes ativos: valor, comparável, ano anterior, variação, lojas comparáveis, `small_sample`; com um departamento, G10 |
| `department_profile` | período × departamento | `departamentos_ficha_<p>.json` | 6 atributos do radar + percentil; penetração e crescimento nulos na base |
| `department_segment` | período × subconjunto × departamento | `departamentos_segmento_<p>.json` | 6 atributos + índice contra todos; ⚠ < 30 compradores |
| `subcategory_top` | período × departamento (ou `todos`) × subcategoria | `subcategorias_<p>.json` | top 10, todas as lojas |
| `department_risk` | subconjunto × departamento (ou `todos`), 26 s | `departamentos_risco.json` | **G4:** faturamento de 26 s de clientes com `churn_score.is_high_risk` |
| `basket_pair` | período × subconjunto × departamento × par | `cesta_subcategorias_<p>.json` | top 10 por lift, ≥ 200 cestas |
| `concentration` | período × subconjunto | `concentracao.json` | subcategorias que fazem 80% |
| `network_node` | nó (80) | `rede_nos.json` | x/y de `src/gold/layout.py`, copiado do painel (G9) com cabeçalho de origem |
| `network_link` | período × subconjunto × ligação desenhada | `rede_pares_<p>.json` | ligações fixas (3 por nó, 26 s, todos os clientes) |
| `network_neighbor` | período × subconjunto × nó × par | `rede_vizinhos_<p>.json` | top 10 por lift, ≥ 200 cestas |
| `network_characteristic` | período × subconjunto (sem `todos`) × par | `rede_caracteristicos_<p>.json` | top 15 por índice |
| `brand` | período × subconjunto × departamento | `marcas_<p>.json` | marca própria e fornecedores |

**Os JSONs da Metodologia** vêm de `gold/models/`:
- `lab_modelo` ← `churn_classifier`;
- `lab_roc` ← `churn_roc`;
- `lab_clv` ← `clv_segment`;
- `lab_desconto` ← `discount_test_pair`;
- `lab_desconto_segmentos` ← `discount_test_segment`.

## 6. Exportação: `python -m src.gold.export`
- Lê **só a gold**: nenhuma conta nova acontece aqui. Apenas renomeia colunas para o contrato, arredonda como o painel publicado e compacta (formato compacto 2.0, `dimensoes` / `colunas` / `linhas`).
- Grava em `export/painel_v4/`, que fica fora do git: acrescentar `export/` ao `.gitignore`, onde hoje não está.
- **Contratos:** copiar para `contracts/` deste projeto os `.schema.json` dos arquivos que ficam, sem alterar.
  - Novo: `faturamento_tempo.schema.json` (G2/G3).
  - Ajustado: `manifest.schema.json`. Saem `parametros_regioes`, `parametros_migracao` e `minimo_cestas_loja`. `rag_commit` vira `lakehouse_commit` mais as versões da silver lidas.
- **Validação:**
  - todo JSON gravado é validado contra o seu contrato;
  - se um arquivo falhar, a exportação para com código 1, e a pasta só é trocada se todos passarem.
- **Arquivos que saem** (não exportados): `segmentos`, `lista_acao`, `migracao`, `migracao_segmentos`, `lojas`, `regioes`, `regioes_segmento`, `regioes_clientes`, `perfis`, `lojas_risco`, `lojas_ranking_<p>`, `lojas_ficha_<p>`, `cubo_faturamento`.

## 7. Execução e código
```
python -m src.silver.build        # 1x, para ganhar days_in_week / is_complete_week
python -m src.gold.build          # modelos e depois métricas; --etapa modelos|metricas para rodar uma parte
python -m src.gold.export         # gold → JSONs validados em export/painel_v4/
python -m src.gold.reconcile      # conferência com o painel publicado + gabaritos fixos
```
- **Ordem do `build`:**
  1. base;
  2. `customer_segment` (com `customer_rfm_features`);
  3. os outros modelos, cada um gravando as suas features junto;
  4. `customer_group`, `segment_subset`, `period_comparable_store`;
  5. cubos.
  Para na primeira tabela que falhar, e as tabelas anteriores da gold continuam na versão de antes (S13).
- **Uma tabela por vez**, DuckDB com `memory_limit` e poucas threads. Pares e rede, que são as contas mais pesadas, rodam período por período.
- **Controle:** `lake/gold/_controle_gold` (Delta, append) com tabela, linhas, status, mensagem, `processado_em` e a versão da `fact_sales` lida.
- **`espiar.py`:** passa a aceitar `gold/models/<t>`, `gold/metrics/<t>` e `gold/_controle_gold`.
- **Ao final, mostrar o pico de memória medido** (o maior até agora foi ~810 MB, na silver).

## 8. Conferência (regra 3, G6): `python -m src.gold.reconcile`
- **Caminho 1, painel publicado:** para cada JSON que fica, comparar `export/painel_v4/<arquivo>` com `C:\retail-bi-dashboard\site\data\<arquivo>`, linha a linha e valor a valor, depois de expandir o formato compacto. A comparação é **exata** na precisão publicada.
  - Exceções esperadas, cada uma explicada no relatório:
    - `faturamento_tempo` não existe no publicado. Ele é conferido pelo caminho 2: a soma por semana em 26 s de `revenue_over_time` = um SQL próprio sobre a silver.
    - o `manifest`.
  - Os números de 4 s, 13 s e 26 s que dependem só de período e lojas devem bater. O painel publicado já usa a base 1–101 (G1).
- **Caminho 2, gabaritos fixos do config,** recalculados por SQL próprio direto da silver, sem usar as macros nem as views da gold:
  - ticket 1–101 = 29,3813; 26 s = 31,2097;
  - itens por cesta 1–101 = 13,3227; desconto 1–101 = 16,1294%;
  - 214 lojas comparáveis em 26 s e +3,42%; 123 em 4 s e 160 em 13 s;
  - clientes ativos 2.205 (ano anterior 2.138);
  - Fiéis = 35% dos clientes e 71% do faturamento;
  - AUC 0,8531 × 0,7378;
  - limiar 0,17; 243 alertas; 135,952 pausas esperadas.
- **Saída:** um quadro no terminal (arquivo, linhas, iguais, diferentes, primeira diferença) e código 1 se houver diferença sem explicação registrada no config.

## 9. Testes (`tests/test_gold.py`, dados mínimos em pasta temporária)
- **Macros:** cada uma com um caso feito à mão, incluindo divisão por zero → nulo.
- **Períodos e lojas:**
  - os períodos terminam na última semana completa;
  - semana incompleta no fim → o período recua;
  - lojas comparáveis: uma loja sem venda no ano anterior fica fora.
- **Gráfico de tempo:**
  - diário em 4 s com dia − 364;
  - semanal no resto;
  - base com ano anterior nulo e todas as lojas.
- **Uma definição por métrica:** nenhum SQL em `sql/gold/metrics/` contém `/ count(DISTINCT basket_id)` nem outra conta que já tenha macro (teste de texto).
- **Grupos e filtros:**
  - "Sem segmento" para quem não comprou em 26 s;
  - 15 subconjuntos mais `todos`;
  - métricas com um departamento (G10);
  - dinheiro em risco só com `is_high_risk` (G4).
- **Features (G12):** a entrada do RFM é a padronizada (média 0); cada foto do churn tem o papel certo e o rótulo só fica nulo na final; as variáveis do teste geram as notas da regra simples; o gasto do CLV soma o faturamento da janela.
- **Modelos:** em dados sintéticos pequenos, só a parte mecânica: colunas, grão, semente (rodar 2 vezes dá o mesmo), `churn` devolve as probabilidades e as notas. **A igualdade com o RAG é provada pela conferência sobre os dados reais, não pelos testes.**
- **Exportação:**
  - JSON inválido contra o contrato → código 1 e pasta antiga intacta;
  - o formato compacto ida e volta dá as mesmas linhas.
- **Execução:** idempotência (rodar 2 vezes = mesmas tabelas); `espiar.py` nas tabelas da gold.

## 10. Notebook de tour: seção Gold
Uma célula por verificação, com ✅/❌ e o esperado × encontrado:
- períodos e lojas comparáveis (123 / 160 / 214);
- os 6 KPIs de 26 s e da base;
- dinheiro em risco total de 26 s;
- segmentos (35% / 71%);
- AUC, limiar, alertas e pausas;
- CLV total;
- veredito do teste de desconto;
- resultado da conferência (arquivos iguais / total).

Mais o quadro-resumo por camada atualizado (bronze, silver e gold).

## 11. Documentação
- `CLAUDE.md`: os comandos da gold.
- Documento de decisões: as decisões pequenas desta fase (G12 em diante) e qualquer diferença com o gabarito, explicada.
- `docs/validacao/fase3_gold.md`:
  - a primeira linha diz "tudo verde" ou o que precisa de atenção;
  - contagens por tabela, quadro da conferência, testes, notebook e pico de memória.

## Critérios de aceite
1. As versões das 5 bibliotecas são iguais às do RAG, e os 74 testes antigos + o notebook continuam verdes depois da troca.
2. A `dim_date` tem `days_in_week` e `is_complete_week`, e as contagens da silver são as mesmas de antes.
3. `python -m src.gold.build`, `export` e `reconcile` terminam com código 0. Rodar 2 vezes dá o mesmo resultado.
4. **Conferência:** todos os JSONs que ficam são iguais aos publicados, e os gabaritos fixos batem. Qualquer exceção está explicada no relatório e no documento de decisões.
5. Todo JSON exportado passa no seu contrato.
6. `python -m pytest -q` passa por inteiro; o notebook roda com todas as verificações ✅.
7. `git status`: nada de `lake/`, `export/`, `data/`, `venv/` nem `config.yaml`.
8. Nada foi alterado em `C:\RAG_Varejo` nem em `C:\retail-bi-dashboard` (`git status` limpo nos dois).

## Pontos para a revisão do Caio (escolhas desta spec, não decididas por ele)
1. **Nome e formato do JSON novo do gráfico de tempo:**
   - proposta: `faturamento_tempo_<periodo>.json`, um por período como os outros da v3;
   - colunas `inicio`, `grupo`, `departamento`, `faturamento`, `faturamento_ano_anterior`;
   - contrato novo, com o `cubo_faturamento.json` deixando de existir.
2. **Copiar os contratos do painel para `contracts/` deste projeto.** A G9 só citou o `layout.py`. Os contratos são a interface combinada (regra já decidida), mas estão no repositório do painel.
3. **Mudanças no `manifest`:** saem os campos de regiões e migração, e `rag_commit` vira `lakehouse_commit`. Isso muda o contrato do manifest e a `versao_contrato`: proposta 5.0.
4. **Fatiar a fase em 3 paradas, cada uma com revisão e commit próprios:**
   - **3a:** ambiente, silver e modelos;
   - **3b:** métricas;
   - **3c:** exportação e conferência.
   A fase é grande, e os modelos são onde a igualdade com o RAG é mais difícil.
5. **Nomes das tabelas da gold em inglês** (regra 6) e os textos dos segmentos em português (contrato). Na exportação, as colunas voltam aos nomes em português dos contratos.
