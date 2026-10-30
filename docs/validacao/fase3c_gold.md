tudo verde: os 47 JSONs do painel v4 passam no contrato 5.0. 42 de 43 arquivos que existem no painel publicado são **idênticos byte a byte** (54.130 de 54.131 linhas, na ordem). A única diferença é um texto, explicado (G35). Os 20 gabaritos fixos e os 4 `faturamento_tempo` (11.144 linhas) batem pelo SQL próprio. Ponto de atenção: nenhum novo (exportação 176 MB, conferência 801 MB).

# Validação — Fase 3, parada 3c: exportação e conferência (30/10/2026)

> Escopo: seção 6 (exportação), seção 8 (conferência), seção 9 (testes da exportação) e seção 10 (notebook) da `docs/spec_fase3_gold.md`. Também o ajuste da revisão da 3b, já no commit `6669c4c`: `python -m src.gold.build` roda cada etapa num processo próprio (G33).
> Fontes do gabarito, só leitura: `C:\retail-bi-dashboard\site\data` (painel publicado, commit `dc69cc1`) e a silver. `git status` limpo no RAG e no painel depois de tudo.
> Decisões pequenas desta parada: G34–G41 no documento de decisões.

## O que foi construído
| Parte | Onde |
|---|---|
| Exportação: lista de arquivos, formato compacto, Metodologia, manifest 5.0, validação e troca da pasta só com tudo válido | `src/gold/export.py` (G34, G36) |
| Um SQL por JSON (15): renomeia, arredonda, ordena | `sql/gold/export/*.sql` (G34) |
| Conferência: caminho 1 (painel publicado) e caminho 2 (gabaritos e `faturamento_tempo` por SQL próprio) | `src/gold/reconcile.py` (G40) |
| Contratos: 19 copiados sem mudança e 2 novos (`faturamento_tempo`, `manifest` 5.0) | `contracts/` (G37, G38) |
| Pastas, versão do contrato, limite de bytes, 20 gabaritos e as exceções explicadas | `paths` e `gold.exportacao` / `gold.conferencia` do config (G39) |
| `/export/` no `.gitignore` | (G39) |

## Execução (dados reais)
| Comando | Resultado |
|---|---|
| `python -m src.gold.build` (cada etapa num processo, G33) | código 0; 73 s. Pico por processo: orquestrador 16 MB, modelos 633 MB, métricas 870 MB. **Pico total 885 MB** (antes, num processo só: 1.016–1.032 MB) |
| `python -m src.gold.export` | código 0; 20–23 s, pico **176 MB**; 47 arquivos + manifest validados |
| de novo (idempotência) | código 0; os 47 arquivos idênticos byte a byte; o manifest só muda em `gerado_em` |
| `python -m src.gold.reconcile` | código 0; 12 s, pico **801 MB** (a venda de mercadoria inteira numa tabela temporária, para o SQL próprio) |

### Orçamento de bytes (manifest)
| Carga | Exportado | Publicado (4.0) |
|---|---:|---:|
| abertura | 446.719 (4 `faturamento_tempo` = 236.163) | 295.526 (`cubo_faturamento` = 84.970) |
| categoria (maior período) | 363.179 | 363.179 |
| produtos (maior período) | 716.615 | 716.615 |
| laboratório | 26.471 | 26.478 (7 bytes = " do RAG", G35) |
| limite | 1.572.864 | 1.572.864 |

## Caminho 1: exportado × painel publicado
Linha a linha, **na ordem**, valor a valor, depois de expandir o formato compacto (grão e colunas também). "Pela chave" = quantas linhas batem independentemente da posição.

| Arquivo | Publicado | Exportado | Iguais (na ordem) | Pela chave | Bytes iguais |
|---|---:|---:|---:|---:|:-:|
| departamentos | 37 | 37 | 37 | 37 | sim |
| cubo_periodo | 438 | 438 | 438 | 438 | sim |
| kpis_filtrados | 1.786 | 1.786 | 1.786 | 1.786 | sim |
| departamentos_ficha 4s / 13s / 26s / base | 24 / 25 / 26 / 37 | igual | todas | todas | sim (4) |
| departamentos_segmento 4s / 13s / 26s / base | 341 / 382 / 401 / 539 | igual | todas | todas | sim (4) |
| subcategorias 4s / 13s / 26s / base | 123 / 128 / 130 / 148 | igual | todas | todas | sim (4) |
| departamentos_risco | 401 | 401 | 401 | 401 | sim |
| cesta_subcategorias 4s / 13s / 26s / base | 210 / 393 / 574 / 930 | igual | todas | todas | sim (4) |
| concentracao | 63 | 63 | 63 | 63 | sim |
| marcas 4s / 13s / 26s / base | 326 / 366 / 385 / 523 | igual | todas | todas | sim (4) |
| rede_nos | 80 | 80 | 80 | 80 | sim |
| rede_pares 4s / 13s / 26s / base | 2.756 / 2.891 / 2.991 / 3.008 | igual | todas | todas | sim (4) |
| rede_vizinhos 4s / 13s / 26s / base | 3.708 / 7.905 / 9.493 / 11.299 | igual | todas | todas | sim (4) |
| rede_caracteristicos 4s / 13s / 26s / base | 180 / 180 / 184 / 225 | igual | todas | todas | sim (4) |
| lab_roc | 478 | 478 | 478 | 478 | sim |
| **lab_modelo** | 2 | 2 | **1** | 1 | **não** (explicada, G35) |
| lab_clv / lab_desconto / lab_desconto_segmentos | 5 / 6 / 4 | igual | todas | todas | sim (3) |
| **Total: 43 arquivos** | **54.131** | **54.131** | **54.130** | | **42** |

**Exceções esperadas (spec, seção 8):**
- **`lab_modelo.json`, coluna `descricao`, linha do modelo** (G35). Publicado: "Regressão logística **do RAG**: alerta com risco de 0,17 ou mais (limiar de maior F1 na validação)". Exportado: o mesmo texto sem "do RAG". Os 16 números das duas linhas são iguais.
- **`faturamento_tempo_<p>.json`** não existe no publicado. O de 26 s foi comparado com as semanas 76–101 do `cubo_faturamento.json` publicado: **1.970 de 1.970 linhas iguais**, na ordem. Os quatro passam pelo caminho 2 (abaixo).
- **`manifest.json`:** as seções de conteúdo (períodos, modelo, cesta, rede, Metodologia) são **iguais** às publicadas, incluindo os textos "e daí?". Os campos da geração mudam por definição (data, commit, versões, bytes, lista de arquivos e as mudanças do contrato 5.0, G36).

**A conferência detecta erro** (sanidade, numa cópia da exportação):
- ticket médio de uma linha de `kpis_filtrados` + 0,01: acusou 1 diferença, sem explicação;
- duas linhas trocadas de lugar em `marcas_26s`: acusou a diferença na ordem, com as 385 linhas ainda iguais "pela chave".

## Caminho 2: gabaritos fixos por SQL próprio sobre a silver
O SQL próprio não usa as macros nem as views da gold. Os períodos também são refeitos: o fim é a última semana com 7 dias no calendário da silver = 101.

| Gabarito | Esperado | SQL próprio | Gold |
|---|---:|---:|---:|
| ticket médio, base 1–101 | 29,3813 | 29,3813 | 29,3813 ✅ |
| ticket médio, 26 s | 31,2097 | 31,2097 | 31,2097 ✅ |
| itens por cesta, base | 13,3227 | 13,3227 | 13,3227 ✅ |
| % de desconto, base | 0,161294 | 0,161294 | 0,161294 ✅ |
| lojas comparáveis 4s / 13s / 26s | 123 / 160 / 214 | 123 / 160 / 214 | 123 / 160 / 214 ✅ |
| faturamento 26 s, lojas comparáveis | 2.068.074,67 | 2.068.074,67 | 2.068.074,67 ✅ |
| faturamento do ano anterior, lojas comparáveis | 1.999.776,43 | 1.999.776,43 | 1.999.776,43 ✅ |
| variação 26 s | 0,0342 | 0,0342 | 0,0342 ✅ |
| clientes ativos; ano anterior | 2.205; 2.138 | 2.205; 2.138 | 2.205; 2.138 ✅ |
| Fiéis: % dos clientes; % do faturamento | 0,35; 0,71 | 0,35; 0,71 | 0,35; 0,71 ✅ |
| AUC modelo × regra simples (Mann-Whitney em SQL) | 0,8531 × 0,7378 | 0,8531 × 0,7378 | 0,8531 × 0,7378 ✅ |
| limiar; alertas; pausas esperadas | 0,17; 243; 135,952 | 0,17; 243; 135,952 | 0,17; 243; 135,952 ✅ |
| dinheiro em risco 26 s (G4) | 41.140,15 | 41.140,15 | 41.140,15 ✅ |
| **Total** | | | **20 de 20** |

**`faturamento_tempo` exportado × SQL próprio**, no grão inteiro (ponto × grupo × departamento, 2 casas). Ano anterior: mesmo dia − 364 em 4 s, semana − 52 nos outros. Nos três primeiros, só as lojas comparáveis do período; na base, todas as lojas e ano anterior nulo.

| Período | Grão | SQL próprio | Exportado | Iguais |
|---|---|---:|---:|---:|
| 4s | dia | 1.471 | 1.471 | 1.471 ✅ |
| 13s | semana | 973 | 973 | 973 ✅ |
| 26s | semana | 1.970 | 1.970 | 1.970 ✅ |
| base | semana | 6.730 | 6.730 | 6.730 ✅ |

## Testes e notebook
- **`python -m pytest -q`: 118 passaram** (eram 109 no commit da 3b). Os novos (9):
  - **Formato compacto:** ida e volta num caso feito à mão e em todo arquivo exportado (incluindo um período sem linhas).
  - **Exportação válida:** os 47 arquivos e o manifest passam no contrato, sem sobra de pasta temporária.
  - **Sem conta na exportação:** o KPI exportado é o da gold arredondado.
  - **JSON inválido:** termina com código 1, e a pasta antiga fica igual byte a byte.
  - **Gold de outra versão da silver:** não exporta.
  - **Igualdade da conferência:** 7 = 7.0, booleano ≠ número, a ordem das colunas conta.
  - **Conferência acusa valor e ordem, e aceita uma exceção registrada.**
  - **`faturamento_tempo` sintético = SQL próprio.**
- **Silver sintética:** fator de desconto por perfil (G41), com o mesmo sorteio.
- **Notebook:** `jupyter nbconvert --execute`, **38 de 38 ✅** (bronze 8, silver 16, **gold 14**), 0 erros. A seção Gold (spec, seção 10) cobre:
  - períodos e lojas comparáveis;
  - os 6 KPIs de 26 s e da base;
  - dinheiro em risco;
  - segmentos;
  - AUC, limiar, alertas e pausas;
  - CLV total;
  - veredito do desconto;
  - exportação válida e conferência (42 de 43 iguais, 0 sem explicação).

## Critérios de aceite da fase 3 (spec)
1. **Versões das bibliotecas** iguais às do RAG: ✅ desde a 3a.
2. **`dim_date`** com `days_in_week` / `is_complete_week`: ✅ desde a 3a.
3. **`build`, `export` e `reconcile`** terminam com código 0, e rodar 2 vezes dá o mesmo resultado: ✅. As 33 tabelas da gold e os 47 JSONs ficam iguais, e o manifest só muda na data.
4. **Conferência:** igual ao publicado, com a exceção explicada (G35); gabaritos 20 de 20: ✅.
5. **Contrato:** todo JSON exportado passa no seu: ✅.
6. **pytest e notebook:** 118 testes, 38 de 38 ✅.
7. **`git status`:** nada de `lake/`, `export/`, `data/`, `venv/` nem `config.yaml` (`export/painel_v4` está ignorado, conferido com `git check-ignore`): ✅.
8. **RAG e painel intocados:** `git status` limpo nos dois: ✅.

## Pendências e pontos para revisão
- **Decisões G34–G41.** Em especial:
  - G35: o texto "do RAG" na descrição do modelo. Manter a diferença explicada ou mudar o texto na gold para ficar idêntico?
  - G36: o manifest 5.0 (aba `clientes` fora; `base_hash` a partir das versões da silver);
  - G39: as pastas em `paths`.
- **Fora desta fase** (documento de decisões, pendências): como o painel e o chat passam a ler da nova arquitetura. O painel v4 precisa ler `faturamento_tempo_<p>.json` no lugar do `cubo_faturamento.json`, e o manifest 5.0.
- **Scripts de apoio no scratchpad, fora do repositório:** a sanidade do caminho 1, a medição de memória por processo e os geradores dos contratos novos e das células do notebook. O `reconcile` é a conferência oficial.

## Revisão do Caio (30/10/2026)
- **G34–G41 aprovadas.** A descrição do modelo fica sem "do RAG" (G35). A diferença com o publicado continua explicada: neste relatório, no documento de decisões e em `gold.conferencia.excecoes`.
- **O painel v4 é consumidor do lakehouse (G43):**
  - fica no `retail-bi-dashboard` e lê `export/painel_v4/`;
  - este projeto não altera aquele repositório;
  - o v4 é construído numa sessão aberta lá.
- **Comando único `python -m src.pipeline` (G42):** bronze → silver → gold build → export → reconcile. Cada etapa roda num processo, o comando para no primeiro erro com código 1 e mostra um resumo no fim. Há 3 testes novos em `tests/test_pipeline.py`: a ordem, a parada no erro e o `--config` passado a todas as etapas.
- **Pipeline completo nos dados reais, uma vez:** código 0 em 326 s.
  - Tempos: bronze 55 s, silver 62 s, gold build 166 s (73 s sem o medidor de memória), export 29 s, reconcile 14 s.
  - Maior soma simultânea de memória: 901 MB. Processo mais pesado: as métricas da gold, com 872 MB.
  - Conferência no fim: 42 de 43 arquivos idênticos, 0 diferenças sem explicação, 20 de 20 gabaritos.
- O pico das métricas variou entre execuções, de 870 a 917 MB.
