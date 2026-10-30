tudo verde: as 19 tabelas de `gold/metrics/` batem com o painel publicado (39 de 39 arquivos, 55.606 de 55.606 linhas) e os 20 gabaritos fixos batem pelos dois caminhos. Ponto de atenção: pico de memória de ~1 GB (G29).

# Validação — Fase 3, parada 3b: base comum e métricas (29/10/2026)

> Escopo: seção 3 (base comum) e seção 5 (métricas) da `docs/spec_fase3_gold.md`, com as tabelas de `gold/metrics/`. Exportação para os JSONs e a etapa `reconcile` ficam para a 3c.
> Fontes do gabarito, só leitura: `C:\retail-bi-dashboard\site\data` (painel publicado, commit `dc69cc1`) e a silver. `git status` limpo no RAG e no painel depois de tudo.
> Decisões pequenas desta parada: G23–G32 no documento de decisões.

## O que foi construído
| Parte | Onde |
|---|---|
| Base comum: `sales_item` com os atributos do produto; `basket_department` e `basket` | `sql/gold/base/03, 07, 08` (G23) |
| Macros, uma por métrica (14) | `sql/gold/metricas.sql` (G24) |
| Um SQL por tabela de métrica (19) e 7 auxiliares não gravadas | `sql/gold/metrics/*.sql` (G26) |
| Etapa de métricas, parâmetros como variáveis, layout da rede | `src/gold/build.py` (G27, G28), `src/gold/layout.py` (G32) |
| Parâmetros | seção `gold.metricas` do `config.yaml` e do `config.example.yaml` |

## Execução (dados reais)
| Comando | Resultado |
|---|---|
| `python -m src.gold.build` (modelos + métricas) | código 0; **82 s**, pico de memória **1.016 MB** |
| de novo (idempotência) | código 0; 67 s, pico 1.032 MB; **33 de 33 tabelas** da gold iguais à versão anterior (conteúdo ordenado, G20) |
| `python -m src.gold.build --etapa metricas` | código 0; cerca de 80 s, pico 998 MB |

### Contagens (`gold/metrics/`)
| Tabela | Linhas | Grão | Vira o JSON (3c) |
|---|---:|---|---|
| `dim_period` | 4 | período | (manifest) |
| `period_comparable_store` | 497 | período × loja (123 + 160 + 214) | — |
| `customer_group` | 2.500 | cliente | — |
| `segment_subset` | 37 | subconjunto × grupo (`todos` com 5 + 15 subconjuntos) | — |
| `cube_period` | 438 | período × grupo × departamento | `cubo_periodo` |
| `department` | 37 | departamento | `departamentos` |
| `revenue_over_time` | 11.144 | período × ponto (dia em 4 s, semana no resto) × grupo × departamento | **novo** `faturamento_tempo_<p>` |
| `kpi_filtered` | 1.786 | período × subconjunto × departamento (ou `todos`) | `kpis_filtrados` |
| `department_segment` | 1.663 | período × subconjunto × departamento (ou `todos`) | `departamentos_segmento_<p>` |
| `department_profile` | 112 | período × departamento | `departamentos_ficha_<p>` |
| `department_risk` | 401 | subconjunto × departamento (ou `todos`), 26 s | `departamentos_risco` |
| `subcategory_top` | 529 | período × departamento (ou `todos`) × subcategoria (top 10) | `subcategorias_<p>` |
| `concentration` | 63 | período × subconjunto | `concentracao` |
| `brand` | 1.600 | período × subconjunto × departamento | `marcas_<p>` |
| `basket_pair` | 2.107 | período × subconjunto × departamento × par (top 10, ≥ 200 cestas) | `cesta_subcategorias_<p>` |
| `network_node` | 80 | nó | `rede_nos` |
| `network_link` | 11.646 | período × subconjunto × ligação desenhada | `rede_pares_<p>` |
| `network_neighbor` | 32.405 | período × subconjunto × nó × par (top 10) | `rede_vizinhos_<p>` |
| `network_characteristic` | 769 | período × subconjunto × par (top 15 por índice) | `rede_caracteristicos_<p>` |

## Caminho 1: cada tabela contra o painel publicado (antes da exportação)
- **Como:** um SQL por arquivo do painel renomeia as colunas da gold para o contrato e arredonda como o SQL de exportação do painel (ROUND do DuckDB, mesmas casas). O arquivo publicado é expandido do formato compacto. As linhas são casadas pela chave do grão e comparadas **valor a valor, por igualdade exata**.
- **A ordem das linhas não foi conferida:** ela é da exportação (G31, 3c).
- **Prova de que a conferência acusa erro:** somei US$ 0,01 a um faturamento e multipliquei um índice por 1,001. A conferência acusou 37 diferenças em `departamentos.json` e 2.991 em `rede_pares_26s.json` (e nos outros 3 períodos).

| Arquivo publicado | Publicado | Gold | Iguais | Diferentes |
|---|---:|---:|---:|---:|
| `departamentos.json` | 37 | 37 | 37 | 0 |
| `cubo_periodo.json` | 438 | 438 | 438 | 0 |
| `kpis_filtrados.json` | 1.786 | 1.786 | 1.786 | 0 |
| `departamentos_risco.json` | 401 | 401 | 401 | 0 |
| `concentracao.json` | 63 | 63 | 63 | 0 |
| `rede_nos.json` (com x/y do layout) | 80 | 80 | 80 | 0 |
| `departamentos_ficha_<p>.json` (4 s / 13 s / 26 s / base) | 24 / 25 / 26 / 37 | iguais | 112 | 0 |
| `departamentos_segmento_<p>.json` | 341 / 382 / 401 / 539 | iguais | 1.663 | 0 |
| `subcategorias_<p>.json` | 123 / 128 / 130 / 148 | iguais | 529 | 0 |
| `cesta_subcategorias_<p>.json` | 210 / 393 / 574 / 930 | iguais | 2.107 | 0 |
| `marcas_<p>.json` | 326 / 366 / 385 / 523 | iguais | 1.600 | 0 |
| `rede_pares_<p>.json` | 2.756 / 2.891 / 2.991 / 3.008 | iguais | 11.646 | 0 |
| `rede_vizinhos_<p>.json` | 3.708 / 7.905 / 9.493 / 11.299 | iguais | 32.405 | 0 |
| `rede_caracteristicos_<p>.json` | 180 / 180 / 184 / 225 | iguais | 769 | 0 |
| `cubo_faturamento.json`, semanas 76–101 | 1.970 | 1.970 | 1.970 | 0 |
| **Total: 39 arquivos** | **55.606** | | **55.606** | **0** |

**Fora desta comparação, com o motivo:**
- **`cubo_faturamento.json`, semanas 50–75 (2.022 linhas):** a G2/G3 trocou o gráfico de 52 semanas pelo período selecionado. No publicado, essas semanas usavam as lojas comparáveis de 26 s sem ser um período do filtro. As semanas 76–101 têm a mesma regra nos dois (lojas comparáveis de 26 s, ano anterior = semana − 52) e batem. Os outros períodos de `revenue_over_time` são conferidos pelo caminho 2.
- **`lab_*.json`:** vêm de `gold/models/` e foram conferidos na 3a (80 de 80). Os números continuam iguais depois desta parada (abaixo).
- **`manifest.json` e os arquivos que saem com a aba Clientes & Lojas:** a exportação e o manifest são da 3c.

## Caminho 2: gabaritos fixos (seção 8) por SQL próprio direto da silver
O SQL próprio lê só `fact_sales` e `dim_date` da silver, sem as macros e sem as views da gold. As colunas mostram o valor esperado da spec, o SQL próprio e o que a gold gravou.

| Gabarito | Esperado | SQL próprio | Gold | |
|---|---:|---:|---:|---|
| Ticket médio, base 1–101 | 29,3813 | 29,3813 | 29,3813 | ✅ |
| Itens por cesta, base 1–101 | 13,3227 | 13,3227 | 13,3227 | ✅ |
| % de desconto, base 1–101 | 16,1294% | 16,1294% | 16,1294% | ✅ |
| Ticket médio, 26 s | 31,2097 | 31,2097 | 31,2097 | ✅ |
| Lojas comparáveis 4 s / 13 s / 26 s | 123 / 160 / 214 | 123 / 160 / 214 | 123 / 160 / 214 | ✅ |
| Faturamento 26 s, lojas comparáveis | 2.068.074,67 | 2.068.074,67 | 2.068.074,67 | ✅ |
| Faturamento 24–49, lojas comparáveis | 1.999.776,43 | 1.999.776,43 | 1.999.776,43 | ✅ |
| Variação 26 s | +3,42% | +3,42% | +3,42% | ✅ |
| Clientes ativos (ano anterior) | 2.205 (2.138) | 2.205 (2.138) | 2.205 (2.138) | ✅ |
| Fiéis: % dos clientes / % do faturamento | 35% / 71% | 35% / 71% | 35% / 71% | ✅ |
| AUC modelo × regra simples (Mann-Whitney em SQL sobre `churn_test_score`) | 0,8531 × 0,7378 | 0,8531 × 0,7378 | 0,8531 × 0,7378 | ✅ |
| Limiar / alertas / pausas esperadas | 0,17 / 243 / 135,952 | 0,17 / 243 / 135,952 | 0,17 / 243 / 135,952 | ✅ |
| Dinheiro em risco, 26 s (G4) | 41.140,15 | 41.140,15 | 41.140,15 | ✅ |

**20 de 20 gabaritos** (as linhas com dois ou três números contam um gabarito cada).

### `revenue_over_time` (o JSON novo `faturamento_tempo`), ponto a ponto
Para cada ponto, a soma de todos os grupos e departamentos foi comparada com o SQL próprio.

| Período | Grão | Pontos (SQL próprio / gold / iguais) | Ano anterior | Lojas | |
|---|---|---|---|---|---|
| 4 s | dia | 28 / 28 / 28 | dia − 364 | comparáveis do período (123) | ✅ |
| 13 s | semana | 13 / 13 / 13 | semana − 52 | comparáveis do período (160) | ✅ |
| 26 s | semana | 26 / 26 / 26 | semana − 52 | comparáveis do período (214) | ✅ |
| base | semana | 101 / 101 / 101 | nulo | todas | ✅ |

## Os modelos depois desta parada
A base comum mudou (G23), então a conferência da 3a rodou de novo sobre a gold reconstruída: **80 de 80 iguais** ao RAG e ao painel.

## Testes e notebook
- `python -m pytest -q`: **107 passed**. Eram 96; entraram 11 testes da gold, e o teste da janela que recua ganhou os períodos.
  - **Macros:** casos feitos à mão, incluindo divisão por zero → nulo.
  - **Uma definição por métrica:** nenhum `/` nos SQL dos cubos (teste de texto).
  - **Períodos:** terminam na última semana completa e recuam com a semana incompleta.
  - **Lojas comparáveis:** uma loja sem venda no ano anterior fica fora do comparável, mas continua em todas as lojas.
  - **Faturamento no tempo:** diário em 4 s com dia − 364; semanal no resto; a base com todas as lojas e sem ano anterior.
  - **Grupos:** "Sem segmento" e os 15 subconjuntos + `todos`.
  - **Métricas:** KPIs com um departamento (G10); dinheiro em risco só de quem tem alerta (G4); o cubo soma o faturamento do período; pares de cesta e rede.
  - **Execução:** idempotência e controle nas 33 tabelas, e `espiar.py` em `gold/metrics/`.
- **Silver sintética dos testes:** ganhou uma `dim_product` com 2 departamentos e uma loja sem ano anterior. Os valores sorteados não mudaram, então os modelos veem os mesmos dados.
- **Notebook:** `jupyter nbconvert --execute`, **24 de 24 verificações ✅**. Ele foi rodado porque o `config.yaml` mudou. A seção Gold do tour (spec, seção 10) entra na 3c, junto com o resultado da `reconcile`.

## Achados
1. **Nenhum número diferente do painel publicado.** As regras dos SQL do painel, reescritas sobre a silver com as macros, reproduzem os 39 arquivos na precisão publicada.
2. **Desempenho na primeira versão:** a etapa de métricas levava 279 s com pico de 1.161 MB. Cada métrica por produto relia os itens da silver (via Arrow) nos 4 períodos. Com uma cópia enxuta dos itens materializada uma vez (`_item`) e as auxiliares liberadas depois do último uso, caiu para cerca de 80 s e cerca de 1.000 MB, com os mesmos resultados (G29).
3. **O pico do build completo (~1 GB) passa o maior pico anterior (~810 MB, na silver).** O DuckDB fica no limite de 1 GB do config; o restante é o Python (modelos e pandas). Se a máquina sofrer, a saída mais simples é rodar as etapas separadas (`--etapa modelos`, depois `--etapa metricas`) ou baixar o `memory_limit`.

## Pendências e pontos para revisão
- **Decisões G23–G32,** tomadas na construção. Em especial:
  - G25: as variações dos KPIs ficam prontas na gold;
  - G26: `_network_pair` não é gravada;
  - G29: o pico de memória.
- **Scripts da conferência no scratchpad, fora do repositório:** `conferir_3b.py` (caminho 1) e `conferir_3b_caminho2.py`. A conferência oficial é a etapa `reconcile` da 3c, que vai comparar os JSONs exportados e ler os gabaritos do config.
- **Para a 3c:**
  - exportação com a ordem do contrato (G31) e o `export/` no `.gitignore`;
  - os 5 pontos de revisão da spec que ainda valem: nome do JSON novo, cópia dos contratos, manifest 5.0, nomes em inglês;
  - a seção Gold do notebook.
- Commit da parada 3b depois da sua revisão. Proposta: `feat: gold 3b (base comum e métricas do painel em gold/metrics)`.

## Revisão do Caio (30/10/2026)
- **G23–G32 aprovadas.** Um ajuste antes do commit: o comando `python -m src.gold.build` roda cada etapa num processo próprio (G33).
- **Memória, medida de novo nos dados reais** (pico de cada processo):
  - processo que orquestra: 16 MB;
  - etapa de modelos: 633 MB;
  - etapa de métricas: 870 MB;
  - **pico total: 885 MB**, contra 1.016–1.032 MB num processo só. Tempo: 73 s.
  - O ganho veio de três coisas: processos separados, orquestrador antes dos imports pesados e modelos importados só na etapa deles. Sem os dois ajustes de imports, a primeira medida deu 1.120 MB.
- **Resultados iguais depois do ajuste:**
  - 33 de 33 tabelas da gold iguais à versão anterior (feita num processo só);
  - 39 de 39 arquivos do painel publicado e 55.606 de 55.606 linhas;
  - 20 de 20 gabaritos fixos;
  - 80 de 80 números do RAG.
- **Testes:** 109 passaram, com 2 novos:
  - o `tudo` abre um processo por etapa e para no primeiro erro;
  - `--etapa` roda no mesmo processo.
  - A fixture constrói a gold sintética uma vez num processo só e outra pela linha de comando, e a idempotência compara as duas.
- **Ponto de atenção que fica:** a etapa de métricas sozinha chega a 870 MB, acima dos ~810 MB da silver.
