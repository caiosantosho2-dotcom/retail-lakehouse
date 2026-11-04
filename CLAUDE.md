# Dashboard_Lakehouse

Lakehouse medalhão local sobre a base pública **Dunnhumby "The Complete Journey"**, alimentando o painel BI de varejo (v4).
**Fonte das regras:** `docs/decisoes_arquitetura_lakehouse.md` (decisões com o porquê, to-do e pendências). Leia antes de qualquer fase. Se algo aqui divergir de lá, vale o documento de decisões.

## Arquitetura em 6 linhas
- **Bronze:** os CSVs como chegaram, tudo como texto, com `_arquivo_origem` e `_data_carga`; uma partição por carga; controle de cargas.
- **Silver `clean`:** uma tabela por arquivo, com tipos, nomes padronizados e regras de qualidade; o que falhar vai para `_rejected` com o motivo.
- **Silver `context`:** star schema por assunto (`sales`, `customer`, `product`, `shared`).
- **Gold:** três áreas (G12): `features/` (variáveis dos modelos), `models/` (resultados dos modelos estatísticos) e `metrics/` (métricas do painel, uma definição cada), para o painel v4 e a página de Metodologia.
- **Formato:** Delta Lake em todas as camadas. **Motor:** DuckDB.
- **Ferramentas:** `scripts/espiar.py` (inspeção pelo terminal) e `notebooks/explorando_lakehouse.ipynb` (tour com verificações).

## Regras inegociáveis deste projeto
1. **Tabela Delta se lê como tabela** (`delta_scan` no DuckDB, `DeltaTable` no Python), **nunca** pelos `.parquet` da pasta: arquivos de versões antigas ficam lá e contariam em dobro.
2. **Nada some em silêncio:** toda linha rejeitada vai para `_rejected` com o motivo. Rejeição acima de 1% numa tabela para o pipeline.
3. **Gabarito:** os números do projeto de RAG e do painel atual (relatório de qualidade, KPIs) têm que bater. Diferença só com explicação registrada.
4. **Uma definição por métrica** na gold.
5. **Projeto de RAG (`C:\RAG_Varejo`) e painel atual (`C:\retail-bi-dashboard`) são somente leitura.** Deles se reaproveita só: dados brutos, regras já decididas e o código estatístico (copiado para cá e adaptado para ler da silver).
6. **Nomes:** snake_case, minúsculo, em inglês, o mais próximo do original da Dunnhumby.
7. **Bronze sem tipos e sem limpeza:** conversões e regras são da silver.
8. **Idempotência:** rodar de novo dá o mesmo resultado, sem duplicar.
9. **A regra nasce do dado:** regras específicas da silver só depois do perfil da bronze.

## Pastas
- `data/raw/` — os 7 CSVs (fora do git) · `lake/` — bronze, silver, gold (fora do git)
- `src/bronze`, `src/silver`, `src/gold` — código das camadas · `scripts/` — `espiar.py` e utilitários
- `sql/perfil/` — consultas do perfil · `notebooks/` — perfil e tour · `tests/` — testes · `docs/` — decisões e validações

## Comandos
```
.\venv\Scripts\Activate.ps1                        # ativar o ambiente
pip install -r requirements.txt                    # instalar dependências
python -m src.bronze.ingest                        # carga da bronze (hoje, fuso de São Paulo); sai com 1 se alguma tabela falhar
python -m src.bronze.ingest --data-carga 2026-10-28  # grava numa data escolhida (reprocesso)
python scripts/espiar.py bronze/product topo 10    # modos: topo N | amostra N | colunas | resumo | contagem | cargas | versoes
python scripts/espiar.py bronze/_controle_cargas   # últimas cargas
python scripts/espiar.py bronze/product topo --carga 2026-10-28 --versao 0 --csv saida.csv
python -m src.silver.build                         # reconstrói a silver (clean + context) da carga mais recente da bronze; sai com 1 em erro
python scripts/espiar.py silver/context/sales/fact_sales contagem   # silver: clean/<t>, context/<assunto>/<t>, _rejected/<t>, _controle_silver
python -m src.gold.build                          # gold a partir da silver: modelos e depois métricas, cada etapa num processo próprio (G33); sai com 1 em erro
python -m src.gold.build --etapa metricas         # só as métricas, neste processo (lê os modelos já gravados); --etapa modelos = só os modelos
python -m src.gold.export                         # gold -> JSONs do painel v4 em export/painel_v4/ (validados em contracts/); sai com 1 e mantém a pasta antiga se algo falhar
python -m src.gold.reconcile                      # confere a exportação com o gabarito congelado do painel v3 (data/gabarito/painel_v3, G44) e os gabaritos do config; sai com 1 em diferença sem explicação
python scripts/espiar.py gold/models/churn_score contagem   # gold: features/<t>, models/<t>, metrics/<t>, _controle_gold
python -m src.pipeline                            # tudo em ordem: bronze, silver, gold build, export, reconcile (um processo por etapa); para no 1º erro com código 1 e mostra tempo e status de cada etapa
python -m pytest -q                                # testes (CSVs mínimos em pasta temporária)
jupyter nbconvert --to notebook --execute --inplace notebooks/explorando_lakehouse.ipynb   # roda o tour e salva com saídas
```
- Leitura de tabela Delta no código: `src.comum.ler_delta(con, caminho, carga=None, versao=None)`; como view nomeada na conexão: `src.comum.registrar_delta(con, nome, caminho, ...)`.
- Silver declarada no `config.yaml` (seção `silver`); consultas da `context` em `sql/silver/*.sql`, com parâmetros via `getvariable(...)`.
- DuckDB 2.0: relação não tem mais `fetchone()` (usar `fetchall()`) e `fetch_record_batch()` virou `to_arrow_reader()`. Depois de `execute(...).fetchone()` na conexão, use `execute` (não `sql`) na mesma conexão.
- Gold: base comum em `sql/gold/base/*.sql` (views sobre a silver); modelos copiados do RAG em `src/gold/modelos/` (cabeçalho com origem e adaptações), parâmetros na seção `gold` do config.
- Métricas: um SQL por tabela em `sql/gold/metrics/` (nome com `_` = auxiliar, não gravada), ordem e tipo em `METRICAS` de `src/gold/build.py`; toda razão usa uma macro de `sql/gold/metricas.sql` (nenhum `/` nos SQL dos cubos, há teste); parâmetros em `gold.metricas` como variáveis do DuckDB.
- Exportação: um SQL por JSON em `sql/gold/export/` (só renomeia, arredonda e ordena; nenhuma conta), lista e ordem em `ARQUIVOS` de `src/gold/export.py`; contratos em `contracts/` (5.1); pastas em `paths` (`export`, `contratos`, `painel_publicado`); gabaritos e exceções explicadas em `gold.conferencia`.
- Gabarito congelado (G44): `paths.painel_publicado` aponta para `data/gabarito/painel_v3/`, o `site/data` da tag `v3-rag`, fora do git como todo `data/`; nunca apontar para o `site/data` vivo do painel. Num clone novo, recrie no PowerShell (`tar` por arquivo, porque o pipe do PowerShell pode corromper dados binários):
  ```
  New-Item -ItemType Directory -Force data\gabarito\painel_v3
  git -C C:\retail-bi-dashboard archive --format=tar -o "$PWD\data\gabarito\painel_v3.tar" v3-rag site/data
  tar -xf data\gabarito\painel_v3.tar -C data\gabarito\painel_v3 --strip-components=2
  Remove-Item data\gabarito\painel_v3.tar
  ```

*(comandos da silver e da gold entram aqui conforme forem criados)*
