Parte A concluída, com as revisões G48 e G49: pipeline com código 0, 139 testes passando e só `acionamento_crm.json` mudou entre os 51 arquivos. A calibração no teste agora vem da gold, então a nota do painel não precisa de número fixo. Na métrica de cada objetivo, o modelo ganha da regra simples em **6 de 6** capacidades em pausas e em **5 de 6** em valor. Em N = 100, a regra simples ganha em valor, e isso vai aparecer no painel.

# Validação — v4.1, Parte A: gold dos blocos de decisão (04/11/2026)

> Escopo: Parte A de `docs/spec_v4_1_blocos_decisao.md`, com as revisões G48 e G49. Código nos commits `f53a18a`, `5b10c12` e `9086214`, sem push. Decisões: G45 a G49 no documento de decisões. A Parte B não foi iniciada.

## Bloco 1: dois objetivos, cada um na sua métrica (G48)
A primeira versão ordenava só por `probability × revenue_26s` e perdia da regra simples em precisão (N = 100: 13% × 28%). Quem tende a pausar gasta pouco: a correlação entre a probabilidade e o log do faturamento é de −0,75, e a mediana do faturamento é de US$ 160 entre quem pausou e US$ 703 entre quem não pausou. Com a G48, cada ordem responde a uma pergunta.

**Objetivo `pausas`, ordem pela probabilidade, métrica `precisao_historica`:**

| N | Modelo | Regra simples | Quem ganha |
|---:|---:|---:|---|
| 25 | 42,00% | 32,00% | modelo |
| 50 | 37,00% | 31,00% | modelo |
| 100 | 32,00% | 28,00% | modelo |
| 150 | 29,33% | 25,00% | modelo |
| 200 | 29,50% | 23,00% | modelo |
| 300 | 26,83% | 19,67% | modelo |

**Objetivo `valor`, ordem pela `priority_score`, métricas `valor_capturado_historico` e `fracao_valor_capturado_historica`:**

| N | Modelo | Regra simples | Fração: modelo | Fração: regra simples | Quem ganha |
|---:|---:|---:|---:|---:|---|
| 25 | US$ 1.727,67 | US$ 1.024,05 | 4,28% | 2,54% | modelo |
| 50 | US$ 3.782,72 | US$ 3.410,07 | 9,50% | 8,46% | modelo |
| 100 | US$ 5.987,85 | US$ 6.600,08 | 15,06% | 16,37% | **regra simples** |
| 150 | US$ 9.611,91 | US$ 8.406,54 | 24,31% | 20,94% | modelo |
| 200 | US$ 11.965,58 | US$ 11.903,41 | 30,11% | 29,71% | modelo, por US$ 62,17 |
| 300 | US$ 15.874,25 | US$ 15.025,33 | 39,94% | 37,60% | modelo |

Média das fotos 85 e 93. A taxa de pausa no teste é de 6,2% e 6,6%. O valor capturado é o faturamento de 26 s, até a foto, dos clientes da lista que pausaram de fato.

**E daí?**
- **Evitar mais pausas:** a ordem pela probabilidade acerta mais que a regra simples em todas as capacidades, mas pega pouco valor. Em N = 100, são US$ 1.791 capturados, contra US$ 5.988 da ordem por valor.
- **Proteger mais valor:** a vantagem sobre a regra simples existe, mas é pequena. Com capacidade de 100, a regra simples foi melhor neste teste.
- **Limite do número:** ele mede quem pausou, não quantas pausas a ação do CRM evitaria. A base não tem esse efeito.

**Esta semana (foto 101), método `modelo`:**

| N | Objetivo | Pausas esperadas | Faturamento de 26 s em jogo | Fiéis | Regulares | Esporádicos | Em pausa |
|---:|---|---:|---:|---:|---:|---:|---:|
| 25 | pausas | 12,89 | US$ 1.560,22 | 0 | 0 | 25 | 0 |
| 25 | valor | 5,81 | US$ 21.965,23 | 1 | 18 | 6 | 0 |
| 50 | pausas | 23,38 | US$ 3.456,91 | 0 | 0 | 50 | 0 |
| 50 | valor | 10,16 | US$ 40.321,01 | 3 | 36 | 11 | 0 |
| 100 | pausas | 40,38 | US$ 7.959,67 | 0 | 0 | 100 | 0 |
| 100 | valor | 19,44 | US$ 67.832,63 | 4 | 64 | 32 | 0 |
| 150 | pausas | 54,24 | US$ 16.870,15 | 0 | 3 | 147 | 0 |
| 150 | valor | 26,35 | US$ 105.990,19 | 7 | 94 | 49 | 0 |
| 200 | pausas | 65,27 | US$ 28.915,16 | 0 | 9 | 191 | 0 |
| 200 | valor | 33,36 | US$ 137.709,18 | 9 | 126 | 65 | 0 |
| 300 | pausas | 82,00 | US$ 55.207,66 | 0 | 33 | 267 | 0 |
| 300 | valor | 47,25 | US$ 196.889,13 | 15 | 183 | 102 | 0 |

**Calibração no teste (G49), método `modelo`, colunas `pausas_esperadas_historicas` e `pausas_reais_historicas`:**

| N | `pausas`: esperadas | `pausas`: reais | `valor`: esperadas | `valor`: reais |
|---:|---:|---:|---:|---:|
| 25 | 13,40 | 10,5 | 4,98 | 3,5 |
| 50 | 23,96 | 18,5 | 9,53 | 8,5 |
| 100 | 40,83 | 32,0 | 17,68 | 13,0 |
| 150 | 54,21 | 44,0 | 24,97 | 23,0 |
| 200 | 64,85 | 59,0 | 30,38 | 28,5 |
| 300 | 81,35 | 80,5 | 41,11 | 41,5 |

Média das fotos 85 e 93. No topo da lista, o modelo superestima; em N = 300, a diferença quase some. São duas fotos, então isso descreve o teste e não é uma correção: as pausas esperadas de "esta semana" continuam sendo a soma das probabilidades, sem ajuste. Na regra simples, as duas colunas são nulas.

**Conferências do bloco 1:**

| Conferência | Resultado |
|---|---|
| `pauses_expected` com N = população inteira (2.203), rodando o próprio SQL de `crm_capacity` | `pauses` 135,9520 e `value` 135,9520; gabarito 135,952 ✅ |
| Objetivo `pausas`, N = 100: `hist_precision` por SQL próprio | modelo 0,32 = 0,32 ✅; regra simples 0,28 = 0,28 ✅ |
| Objetivo `valor`, N = 100: `hist_value_caught` por SQL próprio | modelo 5.987,85 = 5.987,85 ✅; regra simples 6.600,08 = 6.600,08 ✅ |
| Objetivo `valor`, N = 100: `hist_value_caught_share` por SQL próprio | modelo 0,1506 = 0,1506 ✅; regra simples 0,1637 = 0,1637 ✅ |
| Objetivo `pausas`, N = 100: pausas esperadas e reais no teste, por SQL próprio | 40,8284 = 40,8284 ✅; 32,0 = 32,0 ✅ |
| Objetivo `valor`, N = 100: pausas esperadas e reais no teste, por SQL próprio | 17,6808 = 17,6808 ✅ (os 18 do pedido, arredondados); 13,0 = 13,0 ✅ |
| Todas as contas do arquivo, com o faturamento vindo direto da silver (inclui os nulos da calibração na regra simples) | 180 de 180 ✅ |
| Regra simples com os mesmos números nos dois objetivos | 6 de 6 capacidades ✅ |
| Grão | 24 linhas: 6 capacidades × 2 objetivos × 2 métodos ✅ |

## O que mudou com a G48 e a G49
| Parte | Mudança |
|---|---|
| G49, `crm_capacity`, exportação e contrato | `hist_pauses_expected` e `hist_pauses_actual`, exportadas como `pausas_esperadas_historicas` e `pausas_reais_historicas` |
| G49, `src/gold/reconcile.py` e `tests/test_gold.py` | Calibração por SQL próprio e caso feito à mão, com valor estragado e valor indevido na regra simples acusados |
| `sql/gold/metrics/crm_capacity.sql` | Grão capacidade × objetivo × método; duas ordens do modelo; `hist_value_caught` e `hist_value_caught_share` |
| `sql/gold/export/acionamento_crm.sql` | `objetivo`, `valor_capturado_historico` e `fracao_valor_capturado_historica` |
| `contracts/acionamento_crm.schema.json` e `src/gold/export.py` | Contrato (ainda 5.1), grão e chave novos |
| `src/gold/reconcile.py` | SQL próprio nos dois objetivos; N = população inteira nos dois; curva na métrica de cada objetivo |
| `tests/test_gold.py` | Dois objetivos, valor capturado feito à mão, zero em vez de nulo e valor estragado acusado |
| `docs/decisoes_arquitetura_lakehouse.md` | G47 aprovada; G48 registrada com o porquê e a tabela medida |

O modelo não mudou: `src/gold/modelos/` ficou fora dos três commits.

## Execução nos dados reais
| Execução | Bronze | Silver | Gold build | Export | Reconcile | Total | Código |
|---|---:|---:|---:|---:|---:|---:|:-:|
| 1ª, antes do commit `9086214` | 27 s | 41 s | 155 s | 38 s | 35 s | 297 s | 0 |
| 2ª, depois do commit `9086214` | 43 s | 40 s | 191 s | 33 s | 28 s | 334 s | 0 |

Testes: `python -m pytest -q` → **139 passed**. Rodaram antes do commit, e o código não mudou depois.

Memória: não medi o pico nesta rodada.

Manifest da 2ª execução:

| Campo | Valor |
|---|---|
| `versao_contrato` | 5.1 |
| `lakehouse_commit` | `90862147d72d49b21ddabdb576a7585d0cb92193` (igual ao HEAD na execução) |
| `lakehouse_sujo` | `false` |
| `arquivos` | 51 |
| `bytes_abertura` | 589.137 (eram 587.523 antes da G49; limite 1.572.864) |
| `acionamento_crm.json` | 24 linhas, 9.095 bytes |

## O resto da exportação não mudou
| Conferência | Resultado |
|---|---|
| 51 arquivos de antes da G49 × 2ª execução, byte a byte (sem o manifest) | 50 iguais; só `acionamento_crm.json` difere |
| 51 arquivos da 1ª execução × 2ª execução (idempotência) | 0 diferentes |
| Exportação × gabarito congelado do painel v3 | 42 de 43 arquivos idênticos; 54.130 de 54.131 linhas; 0 diferenças sem explicação (só a G35) |
| 20 gabaritos fixos | 20 de 20 |

## Bloco 2: `departamentos_quadrante_<p>.json`
| Período | Recortes com linhas | Linhas | `defend` | `invest` | `keep` | `review` | SQL próprio = exportado | Soma de `share` = 1 |
|---|---:|---:|---:|---:|---:|---:|:-:|:-:|
| 4 s | 15 | 192 | 55 | 56 | 44 | 37 | 192 de 192 ✅ | ✅ |
| 13 s | 16 | 202 | 62 | 63 | 40 | 37 | 202 de 202 ✅ | ✅ |
| 26 s | 16 | 213 | 58 | 69 | 49 | 37 | 213 de 213 ✅ | ✅ |

O SQL próprio remonta cada linha a partir da venda: participação, crescimento, cortes, quadrante, gap e destaque. Cada departamento válido cai em exatamente um quadrante. A base inteira não tem linha nem arquivo.

Destaques "defender primeiro", todos os clientes:

| Período | Corte de crescimento | Corte de participação | 1º | 2º | 3º |
|---|---:|---:|---|---|---|
| 4 s | 4,79% | 1,56% | DRUG GM (−US$ 2.412,39) | MEAT (−US$ 1.332,78) | MEAT-PCKGD (−US$ 745,94) |
| 13 s | 4,73% | 1,48% | MEAT (−US$ 2.993,08) | MEAT-PCKGD (−US$ 2.127,97) | PASTRY (−US$ 727,66) |
| 26 s | 3,42% | 1,53% | MEAT (−US$ 9.201,43) | MEAT-PCKGD (−US$ 2.600,03) | PASTRY (−US$ 691,33) |

**E daí?** Carnes (MEAT e MEAT-PCKGD) são o que mais puxa para baixo em 13 s e 26 s. Em 26 s, MEAT sozinho caiu 2,6% num recorte que cresceu 3,4%. É por onde category management começaria a investigar. O número mostra onde olhar, não a causa da queda.

## Limitações e o que a Parte B precisa tratar
- **Nota de calibração:** deve ler `pausas_esperadas_historicas` e `pausas_reais_historicas` da linha da capacidade e do objetivo escolhidos, sem número fixo (G49). A frase "no topo da lista" não serve para todos os casos: em N = 300 os números quase coincidem, e no objetivo `valor` as reais passam das esperadas (41,11 × 41,5). O texto precisa acompanhar isso.
- **Lista de pausas quase só com Esporádicos:** até N = 100, são 100% Esporádicos (US$ 7.960 de faturamento em jogo, contra US$ 67.833 no objetivo `valor`). A barra de mix e os números da semana precisam trocar junto com o seletor.
- **Subtítulo da B2:** decidido pelo Caio, troca com o seletor: "mais chance de pausar" × "mais chance de pausar e mais valor".
- **Regra simples sem números da semana nem calibração:** nas linhas `regra_simples`, `pausas_esperadas`, `faturamento_26s_em_jogo`, `mix_segmentos`, `pausas_esperadas_historicas` e `pausas_reais_historicas` são nulos.
- **Recortes pequenos (bloco 2):** "Em pausa" em 4 s não tem nenhum departamento válido (0 linhas), e em 13 s tem 1. A spec agora pede uma nota curta nesses casos.
- **Menos de 3 destaques:** 13 s (Em pausa com 0; Esporádicos e Esporádicos+Em pausa com 2) e 26 s (Em pausa, Fiéis e Fiéis+Em pausa com 2).
- **Importador do painel:** a exportação é 5.1. O painel continua intacto, e o aceite do 5.1 é a B1.
- **Texto do painel:** a `priority_score` não é exportada e não pode aparecer como dinheiro. "Faturamento de 26 s em jogo" é soma simples, diferente do "dinheiro em risco" da G4.
- **A1 e A3 da spec:** a tabela e a lista de colunas continuam na forma antiga e não citam a G49. Valem as decisões G48 e G49 e o contrato `contracts/acionamento_crm.schema.json`.

## Commits
O código é o `9086214`, e é para ele que o manifest aponta, porque foi esse commit que gerou os dados. Este relatório entra num commit de documentação logo depois, porque usa os números da 2ª execução. Por isso o HEAD fica um commit à frente do manifest, sem nenhuma diferença de código.
