# Dashboard_Lakehouse

Lakehouse medalhão local sobre a base pública **Dunnhumby "The Complete Journey"**, alimentando o painel BI de varejo (v4).
**Fonte das regras:** `docs/decisoes_arquitetura_lakehouse.md` (decisões com o porquê, to-do e pendências). Leia antes de qualquer fase. Se algo aqui divergir de lá, vale o documento de decisões.

## Arquitetura em 6 linhas
- **Bronze:** os CSVs como chegaram, tudo como texto, com `_arquivo_origem` e `_data_carga`; uma partição por carga; controle de cargas.
- **Silver `clean`:** uma tabela por arquivo, com tipos, nomes padronizados e regras de qualidade; o que falhar vai para `_rejected` com o motivo.
- **Silver `context`:** star schema por assunto (`sales`, `customer`, `product`, `shared`).
- **Gold:** métricas (uma definição cada) e as tabelas vindas dos modelos estatísticos, para o painel v4 e a página de Metodologia.
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
.\venv\Scripts\Activate.ps1          # ativar o ambiente
pip install -r requirements.txt      # instalar dependências
```
*(comandos da bronze, da silver, do `espiar.py` e dos testes entram aqui conforme forem criados)*
