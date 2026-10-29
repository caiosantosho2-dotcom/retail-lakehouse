# Spec — Fase 2: Silver (`clean` + `context`)

> Regras gerais: `docs/decisoes_arquitetura_lakehouse.md` (L1, R1, F2, F3, S1–S9, P1–P8, A1–A3) e `CLAUDE.md`. Esta spec diz **o que construir agora**. Em conflito, vale o documento de decisões.
> **Execução sem supervisão:** o Caio aprovou esta spec e não vai estar olhando. Não espere aprovação de plano. Quando surgir uma dúvida, escolha a opção mais conservadora (a que não perde nem esconde dado), registre a escolha no documento de decisões (seção "Decisões tomadas na construção da fase 2") e siga. **Não faça commit**: o Caio revisa primeiro.

## Objetivo
Construir a silver a partir da **carga mais recente** da bronze, em Delta, reconstruída por inteiro a cada execução (P8):
- `silver/clean/`: `transaction_data`, `product`, `hh_demographic`, com tipos, nomes em snake_case e regras de qualidade; rejeitados em `silver/_rejected/`;
- `silver/context/`: o star schema (`sales/fact_sales`, `sales/dim_store`, `customer/dim_household`, `product/dim_product`, `shared/dim_date`).

## Fora do escopo
Gold, marketing (S7: `campaign_*` e `coupon*` ficam só na bronze), skills, `vacuum`, mudanças no RAG ou no painel atual.

---

## 1. Configuração declarativa (S8)
No `config.yaml` **e** no `config.example.yaml`, uma seção `silver` que declara cada tabela da `clean`:
- tabela de origem na bronze;
- para cada coluna: nome original → nome novo (snake_case, S1) e tipo;
- chave (não nula e única, quando for dimensão);
- regras específicas de rejeição, **em ordem**, cada uma com um `motivo` e uma condição SQL;
- regras de marcação (colunas booleanas novas).

Também no config: a lista de **não mercadoria** (departamentos e commodity, S9.2), as faixas válidas (`day` 1–711, `week_no` 1–102), o limite de rejeição (`0.01`) e a data-base `2016-01-01`.

O código lê a declaração e aplica **regras globais + específicas**. Acrescentar uma tabela nova = declarar no config (+ uma consulta, se for da `context`).

## 2. Tipos (S4, P5, A2)
| Coluna | Tipo |
|---|---|
| `household_key`, `basket_id`, `product_id`, `store_id`, `manufacturer` | `BIGINT` |
| `day`, `week_no`, `quantity`, `trans_hour`, `trans_minute` | `INTEGER` |
| `sales_value`, `retail_disc`, `coupon_disc`, `coupon_match_disc` | `DECIMAL(18,4)` |
| textos | `VARCHAR` com `TRIM`; vazio → `NULL` |

Conversão com `TRY_CAST`: se falhar, a linha é rejeitada com motivo `invalid_number` (nunca vira nulo em silêncio).

## 3. `silver/clean/` (uma tabela por arquivo, grão igual ao da origem)

### 3.1 `transaction_data`
Rejeição, nesta ordem (S9; primeiro motivo que falhar):
1. `invalid_number` — alguma coluna numérica não converte;
2. `null_key` — `basket_id`, `household_key`, `product_id`, `store_id` ou `day` nulos;
3. `out_of_range` — `day` fora de 1–711, `week_no` fora de 1–102, `trans_time` com hora > 23 ou minuto > 59;
4. `negative_sales_value` — `sales_value < 0`;
5. `positive_coupon_discount` — `coupon_disc > 0` ou `coupon_match_disc > 0`;
6. `quantity_zero` — `quantity = 0` (S9.1; esperado **14.466**).

Colunas novas: `trans_hour`, `trans_minute` (no lugar de `trans_time`), `is_free_item` (`sales_value = 0 AND quantity > 0`), `is_refund_discount` (`retail_disc > 0`).

### 3.2 `product`
Chave `product_id` não nula e única. Textos com `TRIM`, vazio → `NULL` (S9.7). Nenhuma rejeição esperada.

### 3.3 `hh_demographic`
Chave `household_key` não nula e única. Valores mantidos como vieram (S9.9), só com `TRIM`. Nenhuma rejeição esperada.

### 3.4 Regras globais (todas as tabelas da `clean`)
- Colunas de rastreio: `_data_carga` (herdada da bronze) e `_processado_em` (timestamp com fuso, como na bronze).
- Rejeitados em `silver/_rejected/<tabela>`: as **colunas originais da bronze (texto)** + `_motivo` + `_data_carga` + `_processado_em`. Sobrescrito a cada execução, como o resto da silver.
- **Limite:** rejeitados > 1% das linhas de uma tabela → a execução **para com erro** antes de montar a `context` (P6). O que foi rejeitado fica gravado para investigar.
- Conferência: linhas da bronze (carga lida) = linhas da `clean` + rejeitadas. Se não bater → erro.

## 4. `silver/context/` (star schema)
Membro **desconhecido** `-1` em cada dimensão (P2); vendas órfãs apontam para `-1` e são contadas (esperado: 0).

| Tabela | Grão | Colunas |
|---|---|---|
| `product/dim_product` | um produto | `product_id`, `manufacturer`, `department`, `brand`, `commodity_desc`, `sub_commodity_desc`, `curr_size_of_product`, `is_merchandise`. `department` e `commodity_desc` nulos → `'UNKNOWN'` (S9.7). `is_merchandise = false` pela lista do config (S9.2). |
| `sales/dim_store` | uma loja | `store_id` (lojas distintas da venda) |
| `customer/dim_household` | um cliente | `household_key` (todos da venda ∪ demografia), `has_demographics`, as 7 colunas de demografia (nulas para quem não tem, P3/S9.10), `age_band_order` (19-24 = 1 … 65+ = 6), `income_band_order` (Under 15K = 1 … 250K+ = 12) |
| `shared/dim_date` | um dia | `day`, `date` (= 2016-01-01 + `day` − 1), `week_no` **do arquivo** (nunca calculado a partir do dia), `month`, `year`, `day_of_cycle` (1–7, a semana começa no `day` 6: `((day - 6) % 7 + 7) % 7 + 1`; sem nome de dia) |
| `sales/fact_sales` | um item de uma cesta | `basket_id`, `household_key`, `product_id`, `store_id`, `day`, `week_no`, `quantity`, `sales_value`, `retail_disc`, `coupon_disc`, `coupon_match_disc`, `trans_hour`, `trans_minute`, `is_merchandise` (da `dim_product`), `is_free_item`, `is_refund_discount`, `_data_carga`, `_processado_em` |

Se algum `day` aparecer com mais de um `week_no` na venda, isso é erro (e não escolha arbitrária).

## 5. Controle: `lake/silver/_controle_silver` (Delta, append)
Uma linha por tabela por execução: `tabela`, `camada` (`clean`/`context`), `data_carga_bronze`, `processado_em`, `linhas_entrada`, `linhas_saida`, `linhas_rejeitadas`, `pct_rejeitado`, `status`, `mensagem`.

## 6. Execução e código
- Comando: `python -m src.silver.build`, que roda `clean` e depois `context`. Termina com **código 1** em qualquer erro.
- Leitura sempre com `src.comum.ler_delta` (F3), filtrando a carga mais recente. Escrita em Delta com `mode="overwrite"` (gera versão nova, L1/P8).
- **Pouca memória:** nada de carregar a `transaction_data` inteira no pandas; passar do DuckDB ao Delta em lotes (como a bronze faz). `memory_limit` e `threads` do config.
- `espiar.py` deve funcionar na silver: `silver/clean/transaction_data`, `silver/context/sales/fact_sales`, `silver/_rejected/transaction_data` (ajustar a resolução de caminho se precisar).

## 7. Testes (`tests/`, pytest, com dados pequenos em pasta temporária)
- cada regra de rejeição pega a linha certa com o motivo certo; ordem dos motivos respeitada;
- marcações (`is_free_item`, `is_refund_discount`, `is_merchandise` por departamento **e** por commodity);
- bronze = `clean` + rejeitados;
- limite de 1% para a execução e nada da `context` é gravado;
- órfão vai para `-1`; dimensões com chave única e sem nulos;
- `dim_date` usa o `week_no` do arquivo (caso de teste em que `ceil(day/7)` daria outra semana) e a data-base;
- idempotência: rodar duas vezes → mesmas contagens;
- os 28 testes da bronze continuam passando.

## 8. Notebook de tour: seção Silver (`notebooks/explorando_lakehouse.ipynb`)
Acrescentar a seção Silver **depois** da Bronze, no mesmo estilo (uma verificação por célula, ✅/❌ com esperado e encontrado), e atualizar o quadro-resumo. **Desligar a barra de progresso do DuckDB** no notebook (`SET enable_progress_bar = false`): ela trava o notebook no VS Code. Rodar com `jupyter nbconvert --execute --inplace` e salvar com as saídas.

| Verificação | Esperado |
|---|---|
| `transaction_data`: bronze = clean + rejeitadas | 2.595.732 = 2.581.266 + 14.466 |
| rejeitadas por motivo | só `quantity_zero` (14.466); 0,56% |
| `product` e `hh_demographic` | 92.353 e 801, 0 rejeitadas |
| `fact_sales` linhas / soma `sales_value` | 2.581.266 / US$ 8.057.443,80 |
| mercadoria (`is_merchandise = true`) | 2.548.662 linhas, US$ 7.376.322,37 |
| não mercadoria | 32.604 linhas, US$ 681.121,43 |
| `is_free_item` em mercadoria / total | 3.994 / 4.451 |
| `is_refund_discount` em mercadoria / total | 2 / 10 |
| soma semanal de `sales_value`: `fact_sales` × bronze (SQL próprio direto da bronze, sem reaproveitar o código da silver; S6) | 102 semanas, diferença ≤ US$ 0,01 |
| vendas apontando para `-1` (produto, loja, cliente) | 0 |
| chaves das `dim_` sem nulo e sem repetição | 0 e 0 |
| `dim_product` / `dim_store` / `dim_household` (sem o `-1`) | 92.353 / 582 / 2.500 |
| `dim_household` com `has_demographics = true` | 801 |
| `dim_date` | 711 dias, semanas 1 a 102, `day` 6 com `day_of_cycle` = 1 |

**Se um número não bater:** não ajuste a regra para forçar. Investigue, explique a causa no relatório e deixe o ❌ visível.

## 9. Documentação
- `CLAUDE.md`: comandos da silver.
- `docs/decisoes_arquitetura_lakehouse.md`: seção "Decisões tomadas na construção da fase 2" com o que você decidiu sozinho.
- `docs/validacao/fase2_silver.md`: relatório para o Caio ler de manhã — o que foi feito, resultado dos testes, quadro do notebook (✅/❌), contagens por tabela, rejeitados por motivo, decisões tomadas sozinho e o que ficou pendente. **Primeira linha: "tudo verde" ou a lista do que precisa de atenção.**

## Critérios de aceite
- [ ] `python -m src.silver.build` roda do zero até o fim com código 0.
- [ ] Rodar de novo não muda nenhuma contagem.
- [ ] Todas as verificações da seção 8 ✅ (ou ❌ explicado no relatório).
- [ ] Todos os testes passam (bronze + silver).
- [ ] `espiar.py` funciona nas tabelas da silver.
- [ ] Nada de `lake/`, `data/`, `venv/` ou `config.yaml` no git; **nenhum commit** feito.
