# Spec — Fase 1: Bronze + `espiar.py`

> Regras gerais: `docs/decisoes_arquitetura_lakehouse.md` (seções B1–B11, L1, F1, F2, F3) e `CLAUDE.md`. Esta spec diz **o que construir agora**. Em conflito, vale o documento de decisões. Se algo não estiver claro, pergunte antes de decidir.

## Objetivo
Carregar os 7 CSVs da Dunnhumby (`data/raw/`) na camada bronze, em Delta Lake, sem tipos e sem limpeza, com rastreabilidade e controle de cargas. Construir a ferramenta de inspeção `scripts/espiar.py` e a seção bronze do notebook de tour.

## Fora do escopo
Silver, gold, perfil da bronze (feito pelo Caio depois), `causal_data`, skills.

---

## 1. `config.yaml` (e `config.example.yaml`)
- Completar com a lista das 7 tabelas: nome da tabela, arquivo CSV e **colunas esperadas**.
- As colunas esperadas vêm do **cabeçalho real de cada CSV**, conferido contra a lista abaixo (documentação da base). Se o cabeçalho divergir da lista, **pare e me mostre a diferença** antes de seguir.

| Tabela | Arquivo | Colunas documentadas |
|---|---|---|
| transaction_data | transaction_data.csv | household_key, BASKET_ID, DAY, PRODUCT_ID, QUANTITY, SALES_VALUE, STORE_ID, RETAIL_DISC, TRANS_TIME, WEEK_NO, COUPON_DISC, COUPON_MATCH_DISC |
| product | product.csv | PRODUCT_ID, MANUFACTURER, DEPARTMENT, BRAND, COMMODITY_DESC, SUB_COMMODITY_DESC, CURR_SIZE_OF_PRODUCT |
| hh_demographic | hh_demographic.csv | AGE_DESC, MARITAL_STATUS_CODE, INCOME_DESC, HOMEOWNER_DESC, HH_COMP_DESC, HOUSEHOLD_SIZE_DESC, KID_CATEGORY_DESC, household_key |
| campaign_table | campaign_table.csv | DESCRIPTION, household_key, CAMPAIGN |
| campaign_desc | campaign_desc.csv | DESCRIPTION, CAMPAIGN, START_DAY, END_DAY |
| coupon | coupon.csv | COUPON_UPC, PRODUCT_ID, CAMPAIGN |
| coupon_redempt | coupon_redempt.csv | household_key, DAY, COUPON_UPC, CAMPAIGN |

- Também no config: `duckdb.memory_limit: "1GB"` e `duckdb.threads: 2` (notebook com pouca memória).
- Nomes das colunas na bronze: **iguais ao CSV** (a padronização para snake_case é da silver).

## 2. Ingestão: `src/bronze/ingest.py` (rodar com `python -m src.bronze.ingest`)
Para cada tabela do config, nesta ordem:
1. Montar o caminho do CSV; conferir que **existe**, que **não está vazio** e que as **colunas = esperadas**.
2. Ler com DuckDB, **tudo como texto** (`all_varchar = true`), sem carregar a tabela inteira na memória: passar os dados ao `deltalake` em lotes (*record batches*).
3. Acrescentar as colunas de rastreio:
   - `_arquivo_origem` — nome do CSV;
   - `_data_carga` — data da carga (`AAAA-MM-DD`), **coluna de partição**;
   - `_carregado_em` — data e hora exatas da carga.
4. Gravar em Delta em `lake/bronze/<tabela>`, **particionado por `_data_carga`**:
   - tabela ainda não existe → cria;
   - já existe → **substitui só a partição do dia** (overwrite com predicado `_data_carga = '<hoje>'`). Cargas de outros dias ficam intocadas (B10) e rodar de novo no mesmo dia não duplica (B7).
5. Conferir **linhas lidas do CSV = linhas gravadas na partição do dia** (lendo pela tabela Delta, nunca pelos arquivos — F3). Se não bater: **restaurar a tabela para a versão anterior** (`restore` do Delta) e registrar erro.
6. Registrar uma linha na tabela de controle (seção 3).

**Erros (B11):** arquivo faltando, vazio ou com coluna errada → registra erro daquela tabela e **segue para as outras**. No fim, mostra um resumo (tabela, linhas, status) e termina com **código de saída 1** se alguma tabela deu erro.

## 3. Controle de cargas: `lake/bronze/_controle_cargas` (Delta, modo append)
Uma linha por tabela por execução:

| Coluna | Conteúdo |
|---|---|
| tabela, arquivo | nome da tabela e do CSV |
| data_carga, carregado_em | data da partição e data/hora |
| linhas_lidas, linhas_gravadas | contagens (iguais no sucesso) |
| colunas_esperadas_ok | verdadeiro/falso |
| status | `sucesso` ou `erro` |
| mensagem | detalhe do erro, vazio no sucesso |

## 4. `scripts/espiar.py`
Uso: `python scripts/espiar.py <camada>/<tabela> <modo> [N] [--carga AAAA-MM-DD] [--versao N] [--csv arquivo.csv]`

| Modo | Mostra |
|---|---|
| `topo N` | primeiras N linhas |
| `amostra N` | N linhas aleatórias |
| `colunas` | nome e tipo de cada coluna |
| `resumo` | `SUMMARIZE` na tabela inteira (mín., máx., nulos, distintos) |
| `contagem` | número de linhas |
| `cargas` | cargas existentes da tabela (bronze), a partir do controle |
| `versoes` | versões da tabela Delta (histórico) |

- Lê **sempre como tabela Delta** (F3): `DeltaTable` (com `version` quando houver `--versao`) entregando ao DuckDB, ou `delta_scan`.
- Bronze: por padrão a **carga mais recente** (`_data_carga` máxima); `--carga` escolhe outra.
- Erros amigáveis: tabela inexistente → lista as tabelas da camada; carga ou versão inexistente → lista as disponíveis.
- **Só lê.** Nunca grava, apaga nem altera o lake.
- Respeita `memory_limit` e `threads` do config.

## 5. Testes (`tests/`, pytest)
Com **CSVs pequenos de teste** criados em pasta temporária (nunca a base real):
- carga feliz: linhas lidas = gravadas, colunas de rastreio preenchidas, tudo como texto;
- **idempotência:** rodar duas vezes no mesmo dia → mesma contagem na partição;
- **histórico:** cargas em dois dias diferentes → duas partições, nenhuma sobrescrita;
- arquivo faltando e coluna errada → status `erro` no controle, outras tabelas carregam, código de saída 1;
- `espiar.py`: cada modo roda numa tabela de teste e nunca altera o lake.

## 6. Notebook de tour — seção Bronze (`notebooks/explorando_lakehouse.ipynb`)
Começar o notebook só com a parte da bronze (F2), uma verificação por célula, mostrando ✅/❌ com esperado e encontrado:
- contagem de cada tabela = `linhas_gravadas` no controle;
- última carga das 7 tabelas com `sucesso`;
- colunas = esperadas do config; colunas de dado todas como texto;
- `_arquivo_origem`, `_data_carga` e `_carregado_em` sem nulos;
- `transaction_data` com **2.595.732** linhas e `product` com **92.353** (gabarito);
- versões Delta de cada tabela;
- quadro-resumo final ✅/❌.
Leitura sempre como tabela Delta (F3). Salvar o notebook **com as saídas**.

## 7. Documentação
- `CLAUDE.md`: acrescentar os comandos (ingestão, `espiar.py`, testes).
- `docs/decisoes_arquitetura_lakehouse.md`: registrar decisões pequenas tomadas na construção (ex.: a coluna `_carregado_em` separada da `_data_carga`).
- `docs/validacao/fase1_bronze.md`: relatório da fase — resultado dos testes, contagens por tabela, quadro do notebook e pendências.

## Critérios de aceite
- [ ] `python -m src.bronze.ingest` carrega as 7 tabelas com status `sucesso`.
- [ ] Rodar de novo no mesmo dia não muda as contagens (idempotência), e o controle registra as duas execuções.
- [ ] `transaction_data` = 2.595.732 linhas; `product` = 92.353.
- [ ] Todos os testes passam.
- [ ] Todos os modos do `espiar.py` funcionam na bronze real.
- [ ] Notebook com todas as verificações ✅, salvo com as saídas.
- [ ] Nada em `data/`, `lake/`, `venv/` ou `config.yaml` entra no git.
- [ ] Um commit no fim da fase, depois da minha revisão.
