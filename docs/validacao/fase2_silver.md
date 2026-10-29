**tudo verde** (atualizado em 29/10/2026, depois da revisão do Caio): 74 testes passando e **23 de 23** verificações do notebook ✅. As duas pendências foram decididas: esperado de `is_refund_discount` corrigido para 2 / 2; commodity `COUPON` mantida como mercadoria (limitação conhecida).

> Relatório original da noite de 28/10/2026, primeira linha: Precisa de atenção (2 itens, nenhum bloqueia): (1) a verificação `is_refund_discount` dá ❌ (2 / 2, esperado 2 / 10): a silver está certa e a expectativa da S9.4 contou antes da regra da quantidade zero, ver "Achados"; (2) decidir se a commodity `COUPON` (68 vendas, US$ 459,66) deve virar não mercadoria. Todo o resto está verde: 74 testes passando e 22 de 23 verificações do notebook ✅.

# Validação — Fase 2: Silver (`clean` + `context`) (28/10/2026)

Spec: `docs/spec_fase2_silver.md`. Decisões tomadas sozinho nesta fase: **S10–S19** em `docs/decisoes_arquitetura_lakehouse.md` ("Decisões tomadas na construção da fase 2").
Ambiente: Python 3.14.7 · duckdb 2.0.0 · deltalake 1.6.6 · pyarrow 26.0.0 · pytest 9.2.0. Context7 não conectou de novo (timeout); a API foi conferida na versão instalada, como na fase 1.
**Nenhum commit foi feito.**

## O que foi feito
| Arquivo | O quê |
|---|---|
| `config.example.yaml` / `config.yaml` | seção `silver`: parâmetros (limite 1%, faixas, data-base, não mercadoria, ordem das faixas), declaração das 3 tabelas da `clean` (colunas, tipos, chaves, rejeições em ordem, marcações) e das 5 da `context` (SQL, chave, pré-condições, contagens de órfãos) |
| `src/silver/build.py` | `python -m src.silver.build`: monta a `clean` (regras globais + específicas lidas do config), confere bronze = clean + rejeitadas e o limite de 1%, depois monta a `context` e grava o controle. Termina com 1 em qualquer erro |
| `sql/silver/*.sql` | uma consulta por tabela da `context` (`dim_product`, `dim_store`, `dim_household`, `dim_date`, `fact_sales`) |
| `src/comum.py` | `registrar_delta` (view nomeada pelo `_delta_log`) e barra de progresso do DuckDB desligada em toda conexão |
| `scripts/espiar.py` | `topo` de qualquer `_controle*` ordenado pela execução mais recente (antes só o controle da bronze) |
| `tests/test_silver.py` | 46 testes com uma bronze mínima e a **declaração real** do `config.example.yaml` |
| `notebooks/explorando_lakehouse.ipynb` | seção Silver (15 verificações) + quadro-resumo por camada, executado e salvo com as saídas |
| `CLAUDE.md` | comandos da silver |

## Execução real
| Execução | Resultado |
|---|---|
| `python -m src.silver.build` (1ª) | código 0, 8 de 8 tabelas com sucesso, 57 s |
| mesma coisa (2ª, idempotência) | código 0, **mesmas contagens** em todas as tabelas; o controle ficou com 16 linhas (2 × 8) |
| do zero (lake só com a bronze, cópia no scratchpad) | código 0, mesmos números, 29 s, pico de memória **811 MB** |

### Contagens por tabela
| Tabela | Entrada | Saída | Rejeitadas | % |
|---|---:|---:|---:|---:|
| clean/transaction_data | 2.595.732 | 2.581.266 | 14.466 | 0,56% |
| clean/product | 92.353 | 92.353 | 0 | 0% |
| clean/hh_demographic | 801 | 801 | 0 | 0% |
| context/product/dim_product | – | 92.354 (92.353 + `-1`) | – | – |
| context/sales/dim_store | – | 583 (582 + `-1`) | – | – |
| context/customer/dim_household | – | 2.501 (2.500 + `-1`) | – | – |
| context/shared/dim_date | – | 712 (711 + `-1`) | – | – |
| context/sales/fact_sales | 2.581.266 | 2.581.266 | – | – |

### Rejeitados por motivo
| Tabela | Motivo | Linhas |
|---|---|---:|
| transaction_data | `quantity_zero` | 14.466 |
| (todas) | `invalid_number`, `null_key`, `out_of_range`, `negative_sales_value`, `positive_coupon_discount`, `duplicate_key` | 0 |

Órfãos na `fact_sales` (apontando para `-1`): produto 0, loja 0, cliente 0.

## Testes (`python -m pytest -q`)
**74 passed** em 43 s (28 da bronze + 46 da silver), rodado com `-W error::DeprecationWarning`.

O que a silver cobre:
- **Regras e motivos:** cada regra de rejeição pega a linha certa com o motivo certo, e a ordem dos motivos é respeitada (`quantity = 0` com valor negativo cai em `negative_sales_value`; número inválido com chave nula cai em `invalid_number`).
- **Rejeitados e conferência:** os rejeitados guardam o texto original da bronze. A conta bronze = clean + rejeitadas fecha.
- **Tipos e limpeza:** tipos e nomes em snake_case; `TRIM` com vazio virando nulo; ruído `5.55E-17` vira `0.0000`; chave repetida vai para `duplicate_key`.
- **Limite de 1%:** a execução para, os rejeitados ficam gravados e nada da `context` é gravado.
- **Marcações:** `is_free_item`, `is_refund_discount` e `is_merchandise`, tanto pelo departamento quanto pela commodity.
- **Órfão:** vai para `-1` e é contado.
- **Dimensões:**
  - as 4 têm chave única, sem nulos, e membro `-1`;
  - `dim_product` com `'UNKNOWN'`;
  - `dim_household` com venda ∪ demografia e a ordem das faixas;
  - `dim_date` usa o `week_no` do arquivo (o `day` 6 é a semana 2, onde `ceil(6/7)` daria 1) e a data-base;
  - um `day` com dois `week_no` é erro, e a `dim_date` não é gravada.
- **Execução:** idempotência; a silver lê a carga mais recente da bronze; sem bronze, termina em erro.
- **`espiar.py`:** os 6 modos funcionam em `silver/clean/...`, `silver/context/sales/fact_sales`, `silver/_rejected/...` e `silver/_controle_silver`, e uma tabela inexistente lista as tabelas da silver.

## Notebook — quadro das verificações (seção Silver)
| # | Verificação | Esperado | Encontrado | |
|---|---|---|---|---|
| 8 | transaction_data: bronze = clean + rejeitadas | 2.595.732 = 2.581.266 + 14.466 | 2.595.732 = 2.581.266 + 14.466 | ✅ |
| 9 | rejeitadas por motivo | quantity_zero: 14.466 (0,56%) | quantity_zero: 14.466 (0,56%) | ✅ |
| 10 | product e hh_demographic | 92.353 e 801, 0 rejeitadas | 92.353 e 801, 0 rejeitadas | ✅ |
| 11 | fact_sales: linhas / soma | 2.581.266 / US$ 8.057.443,80 | 2.581.266 / US$ 8.057.443,80 | ✅ |
| 12 | mercadoria | 2.548.662, US$ 7.376.322,37 | 2.548.662, US$ 7.376.322,37 | ✅ |
| 12 | não mercadoria | 32.604, US$ 681.121,43 | 32.604, US$ 681.121,43 | ✅ |
| 13 | is_free_item mercadoria / total | 3.994 / 4.451 | 3.994 / 4.451 | ✅ |
| 13 | is_refund_discount mercadoria / total | ~~2 / 10~~ **2 / 2** (corrigido em 29/10) | 2 / 2 | ✅ |
| 13 | estornos: fact_sales + rejeitadas (quantity_zero) = bronze | 2 + 8 = 10 | 2 + 8 = 10 | ✅ |
| 14 | soma semanal fact_sales × bronze (SQL próprio da bronze) | 102 semanas, dif. ≤ US$ 0,01 | 102 semanas, dif. máx. US$ 0,00 | ✅ |
| 15 | vendas com produto / loja / cliente = -1 | 0 / 0 / 0 | 0 / 0 / 0 | ✅ |
| 16 | chaves das dim_: nulas e repetidas | 0 e 0 | 0 e 0 | ✅ |
| 17 | dim_product / dim_store / dim_household | 92.353 / 582 / 2.500 | 92.353 / 582 / 2.500 | ✅ |
| 17 | has_demographics = true | 801 | 801 | ✅ |
| 18 | dim_date | 711 dias, semanas 1–102, day 6 → ciclo 1, day 1 = 2016-01-01 | igual | ✅ |

Bronze: 8 de 8 ✅ · Silver: 15 de 15 ✅ · **Total: 23 de 23** (em 28/10 eram 22 de 23, antes da correção do esperado). A conciliação dos estornos não estava na spec: foi acrescentada para explicar o ❌.

## Achados
1. **`is_refund_discount` (o ❌):**
   - A bronze tem 10 linhas com `retail_disc > 0` depois da conversão para `DECIMAL(18,4)`. Outras 26 "positivas" eram ruído de ponto flutuante (ex.: `1.110223E-16`), que vira `0.0000`.
   - As 10 são **todas de mercadoria**, e **8 têm `quantity = 0`**: são rejeitadas por `quantity_zero` antes de chegar à `fact_sales`. Sobram 2.
   - O "10 (2 em mercadoria)" da S9.4 contava antes da regra da quantidade zero. O "2" bate com o RAG ("retail_disc positivo: 2 linhas").
   - **A regra não foi mudada.** Sugestão: corrigir o esperado da S9.4 e do notebook para "2 / 2".
2. **Commodity `COUPON` fora da lista de não mercadoria:**
   - 3 produtos (AUTOMOTIVE, MEAT-WHSE, ELECT &PLUMBING), 68 vendas, US$ 459,66, hoje contados como mercadoria.
   - `COUPONS/STORE & MFG` já sai pelo departamento COUP/STR & MFG.
   - Mantive a lista da S9.2 porque é ela que bate com o gabarito do RAG. Se `COUPON` entrar na lista, a mercadoria cai para US$ 7.375.862,71 e se afasta do RAG. **Decisão sua.**
3. **Memória:** pico de ~810 MB no processo da silver, contra 367 MB na bronze. Ficou dentro do que o notebook aguentou, mas é o maior consumo até agora. Os candidatos são as junções da `fact_sales` com as três dimensões e o buffer do gravador Delta. Se ficar apertado, dá para baixar `silver.batch_rows` ou o `memory_limit`.

## Decisões tomadas sozinho (detalhes em S10–S19)
- **Rejeições e marcações:**
  - chave repetida em dimensão → todas as cópias vão para `duplicate_key`;
  - condição de rejeição nula não rejeita; marcação nula fica nula.
- **Membro `-1` e colunas de rastreio:**
  - `is_merchandise` nulo no produto `-1`;
  - dimensões sem `_data_carga`/`_processado_em` (a spec lista essas colunas só no fato).
- **Quando algo falha:**
  - erro na `clean` → `context` não montada e sem linha no controle;
  - erro na `context` → para na primeira tabela que falhar;
  - dimensão só é gravada depois de conferir a chave.
- **Implementação:**
  - parâmetros do config como variáveis SQL (`getvariable`);
  - pré-condições e contagens declaradas no config;
  - `registrar_delta` para views que continuam válidas entre funções;
  - gravação com `schema_mode="overwrite"` (reconstrução completa).
- **Dados:**
  - `trans_time` → `INTEGER` → hora e minuto;
  - `dim_date` a partir dos dias com venda.
- **Ferramentas:** barra de progresso do DuckDB desligada em toda conexão.

## Pendências
- ~~As duas decisões do topo~~ → decididas pelo Caio em 29/10/2026 (S9.4 corrigida; `COUPON` como limitação conhecida).
- Significado de `A`/`B` no estado civil (S9.9, já pendente antes).
- `vacuum` com retenção de 30 dias (L1): ainda fora, como na fase 1.
- O script que monta o notebook ficou fora do repositório (o notebook salvo é o entregável). Mudanças futuras podem ser feitas direto no notebook.
- Commit da fase 2, depois da sua revisão. Proposta: `feat: silver (clean + context) com regras declaradas no config`.
