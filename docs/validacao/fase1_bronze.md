# Validação — Fase 1: Bronze + `espiar.py` (28/10/2026)

Spec: `docs/spec_fase1_bronze.md`. Decisões novas desta fase: B12–B18 em `docs/decisoes_arquitetura_lakehouse.md`.
Ambiente: Python 3.14.7 · duckdb 2.0.0 · deltalake 1.6.6 · pyarrow 26.0.0 · pytest 9.2.0.

## Conferência antes de codar
- **Cabeçalhos dos 7 CSVs = lista da spec**, nome a nome e na mesma ordem. Sem BOM, separador vírgula.
- A documentação da API foi conferida na **versão instalada** (docstrings do `deltalake` 1.6.6 e do `duckdb` 2.0.0), porque o Context7 não conectou nesta sessão (timeout).

## Carga real (`python -m src.bronze.ingest`, carga 2026-10-28)

| Tabela | Linhas lidas | Linhas gravadas | Status |
|---|---:|---:|---|
| transaction_data | 2.595.732 | 2.595.732 | sucesso |
| product | 92.353 | 92.353 | sucesso |
| hh_demographic | 801 | 801 | sucesso |
| campaign_table | 7.208 | 7.208 | sucesso |
| campaign_desc | 30 | 30 | sucesso |
| coupon | 124.548 | 124.548 | sucesso |
| coupon_redempt | 2.318 | 2.318 | sucesso |

- **Gabarito:** `transaction_data` = 2.595.732 ✅ · `product` = 92.353 ✅ · `hh_demographic` = 801 (bate com os "801 com demografia" do RAG).
- **Idempotência:** segunda execução no mesmo dia → mesmas contagens, uma partição só (`_data_carga=2026-10-28`), versão Delta 0 → 1 com `predicate = _data_carga = '2026-10-28'`. Controle com **14 linhas** (2 execuções × 7 tabelas), todas `sucesso`.
- **Fuso:** `_carregado_em` gravado como `2026-10-28 16:32:03-03` (São Paulo); `_data_carga` = 2026-10-28.
- **Memória e tempo:** carga completa em **22 s**, pico de **367 MB** no processo. `espiar.py ... resumo` (SUMMARIZE das 2,6 milhões de linhas) em **6 s**, pico de **535 MB**. DuckDB com `memory_limit = 1GB` e `threads = 2`.

## Testes (`python -m pytest -q`)
**28 passed** em 17 s, sem avisos de depreciação (rodado com `-W error::DeprecationWarning`).

| Arquivo | O que cobre |
|---|---|
| `test_ingest.py` (12) | carga feliz (lidas = gravadas, rastreio sem nulos, tudo texto); texto preservado (`0001`, `5.55E-17`, vírgula entre aspas); **22h em São Paulo = mesmo dia** (01h UTC do dia seguinte); idempotência; histórico em 2 dias (dia 1 intacto); `--data-carga`; arquivo faltando; coluna errada; colunas fora de ordem; arquivo vazio e só cabeçalho; contagem divergente → `restore` da versão anterior; contagem divergente em tabela nova → partição apagada |
| `test_espiar.py` (16) | os 7 modos; carga mais recente por padrão; controle sem modo; `--carga` e `--versao` válidos e inválidos (lista as opções, exit 2); tabela inexistente (lista as tabelas); `--csv`; `--csv` dentro do lake recusado; **lake inalterado** (tamanho e data de todos os arquivos iguais antes e depois de rodar todos os modos) |

## `espiar.py` na bronze real
Todos os modos rodaram com exit 0 em `bronze/transaction_data`: `topo`, `amostra`, `colunas` (12 colunas VARCHAR + 3 de rastreio), `resumo`, `contagem` (2.595.732), `cargas` (2 execuções), `versoes` (0 WRITE, 1 WRITE com predicado). Erros amigáveis conferidos: tabela inexistente, carga inexistente, versão inexistente (exit 2 com a lista disponível). `--csv` gerou 5 linhas + cabeçalho.

## Notebook `notebooks/explorando_lakehouse.ipynb` (seção bronze, salvo com saídas)

| Verificação | Esperado | Encontrado | |
|---|---|---|---|
| última carga com sucesso | 7 de 7 | 7 de 7 | ✅ |
| contagem Delta = linhas_gravadas do controle | 7 de 7 tabelas | 7 de 7 tabelas | ✅ |
| colunas = config + rastreio | nenhuma divergente | nenhuma divergente | ✅ |
| colunas de dado como texto | 41 de 41 (100%) | 41 de 41 (100%) | ✅ |
| nulos nas colunas de rastreio | 0 | 0 | ✅ |
| transaction_data = gabarito | 2.595.732 | 2.595.732 | ✅ |
| product = gabarito | 92.353 | 92.353 | ✅ |
| leitura Delta não conta arquivos antigos | 2.595.732 | 2.595.732 | ✅ |

**8 de 8 ✅.** O notebook também mostra por que a F3 existe: depois de duas cargas no mesmo dia, a partição tem 2 arquivos `.parquet` e só 1 pertence à versão atual. Ler a pasta direto daria **5.191.464** linhas (o dobro).

## Achados durante a construção
- **DuckDB 2.0 mudou a API:** relação não tem mais `fetchone()` (agora `fetchall()`), e `fetch_record_batch()` foi substituído por `to_arrow_reader()`. No deltalake 1.6, o filtro de partição passou de `partitions=` para `file_pruning_predicate=`. Registrado no `CLAUDE.md`.
- **Fim de linha misturado quebra o leitor de CSV do DuckDB** (um arquivo `\n` com uma linha `\r\n` anexada no Windows → erro de *sniffing*). Não acontece nos CSVs da Dunnhumby; apareceu num teste e foi corrigido no teste. Se um dia acontecer na carga, o arquivo é registrado como `erro` e nada é gravado.
- `requirements.txt` estava em UTF-16 (gerado pelo `pip freeze >` do PowerShell 5). Foi regravado em UTF-8. Para gerar de novo sem esse problema: `pip freeze | Out-File -Encoding utf8 requirements.txt`.
- O `resumo` usa `approx_unique` (aproximado): por exemplo, mostra 2.567 households, mas o gabarito tem 2.500. Para contar valores distintos exatos, o perfil da bronze deve usar `count(DISTINCT ...)`.

## Pendências
- Context7 não conectou nesta sessão (timeout do `npx`). Conferir `/mcp` antes da próxima fase.
- `vacuum` com retenção de 30 dias (L1) ainda não implementado: entra quando houver cargas em vários dias.
- Perfil da bronze (S0): é a próxima etapa, feita pelo Caio.
