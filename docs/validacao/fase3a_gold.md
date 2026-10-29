**tudo verde**: os modelos da gold reproduzem o RAG em **80 de 80** números conferidos, sem nenhum ajuste para forçar; 96 testes passando; notebook com 24 de 24 ✅; duas execuções seguidas dão as mesmas 14 tabelas. Nenhum commit feito.

# Validação — Fase 3, parada 3a: ambiente, silver e modelos (29/10/2026)

Spec: `docs/spec_fase3_gold.md`, seções 0, 1 e 4 (mais o que a base comum e o config precisam). Decisões: **G1–G12** (Caio) e **G13–G20** (tomadas na construção; revisar), em `docs/decisoes_arquitetura_lakehouse.md`.
Ambiente: Python 3.14.7 · duckdb 2.0.0 · deltalake 1.6.6 · pyarrow 26.0.0 · **numpy 2.5.3 · pandas 3.0.6 · scikit-learn 1.9.1 · scipy 1.18.1 · statsmodels 0.15.0** (as do RAG).
Referência: RAG `C:\RAG_Varejo` commit `fffb207`, lido pelo que o painel publicou (`C:\retail-bi-dashboard`, commit `dc69cc1`): `site/data/*.json`, `data/tmp/grupo_cliente.parquet` e `data/tmp/laboratorio.json`. Os dois projetos continuam com `git status` limpo.

## O que foi feito
| Arquivo | O quê |
|---|---|
| `requirements.txt` | as 5 bibliotecas nas versões do RAG (numpy e pandas desceram) e as dependências delas; `narwhals` também na versão do RAG (G18) |
| `sql/silver/dim_date.sql` | `days_in_week` e `is_complete_week` (G11) |
| `config.yaml` / `config.example.yaml` | seção `gold`: semente, janela dos modelos (26 s, offset 52, ativo 8 s) e os parâmetros dos 4 modelos copiados do config do RAG sem mudança |
| `sql/gold/base/*.sql` | base comum: `calendar`, `analysis_window`, `sales_item`, `customer_week`, `customer_metrics`, `household` (G14) |
| `src/gold/modelos/` | `rfm.py`, `churn.py`, `clv.py`, `teste_desconto.py`, `teste_hipotese.py` copiados do RAG, cada um com cabeçalho de origem e a lista de adaptações; `parametros.py` (config → formato do RAG); `roc.py` (novo) |
| `src/gold/build.py` | `python -m src.gold.build`: base comum → modelos → `lake/gold/features/` + `lake/gold/models/` + controle `lake/gold/_controle_gold` |
| `tests/test_gold.py`, `tests/gold_sintetico.py` | 21 testes sobre uma silver sintética (220 clientes, 102 semanas, a 102 incompleta) |
| `tests/test_silver.py` | `dim_date`: dias por semana e semana completa |
| `notebooks/explorando_lakehouse.ipynb` | verificação 19 (semana completa), executado e salvo |
| `CLAUDE.md`, `docs/spec_fase3_gold.md`, documento de decisões | comandos da gold; G12 na spec; G12–G20 |

## 0. Ambiente
| Conferência | Resultado |
|---|---|
| `pip install` das 5 versões do RAG | instalou; `pip check`: sem conflitos |
| 74 testes antigos depois da troca de numpy/pandas | **74 passed** |

## 1. Silver: semana completa
| Conferência | Esperado | Encontrado | |
|---|---|---|---|
| `python -m src.silver.build` depois da mudança | mesmas contagens | 8 de 8 com sucesso; 2.581.266 / 14.466 / 92.354 / 583 / 2.501 / 712, iguais às da fase 2 | ✅ |
| dias por semana | semana 1 = 5, 102 = 6, demais = 7 | 1 semana com 5 dias (a 1), 1 com 6 (a 102), 100 com 7 | ✅ |
| última semana completa | 101 | 101 | ✅ |

## 2. Execução real
| Execução | Resultado |
|---|---|
| `python -m src.gold.build` | código 0, 14 tabelas, **25 a 50 s**, pico de memória **517 a 576 MB** (a silver chegou a 811 MB) |
| de novo (idempotência) | as **14 tabelas idênticas** à versão anterior (conteúdo ordenado, G20) |

### Contagens por tabela
| Área | Tabela | Linhas | Grão |
|---|---|---:|---|
| `features/` | `customer_rfm_features` | **2.421** | cliente com compra nas semanas 76–101 (entrada do K-Means) |
| `features/` | `churn_features` | **30.153** | cliente × foto: treino 21.318 (10 fotos, T = 30..66) · validação 2.207 (T = 77) · teste 4.425 (T = 85 e 93) · final 2.203 (T = 101, sem rótulo) |
| `features/` | `clv_features` | **9.805** | cliente × janela: atual 2.421 (76–101) · calibração 2.384 (24–49) · calibração futuro 2.384 (50–101) · calibração futuro backtest 2.384 (50–75) · análogos futuro 116 (50–101) · análogos futuro backtest 116 (50–75) |
| `models/` | `customer_segment` | 2.421 | cliente segmentado |
| `models/` | `rfm_k_evaluation` | 7 | K de 2 a 8 |
| `models/` | `rfm_segment_profile` | 4 | segmento |
| `models/` | `churn_score` | 2.203 | cliente na foto final |
| `models/` | `churn_test_score` | 4.425 | cliente × foto de teste |
| `models/` | `churn_classifier` | 2 | modelo e regra simples |
| `models/` | `churn_roc` | 478 | classificador × ponto |
| `models/` | `clv_segment` | 5 | 4 segmentos + "Sem compra na janela" |
| `models/` | `discount_test_pair` | 6 | par de segmentos |
| `models/` | `discount_test_segment` | 4 | segmento |
| `models/` | `model_summary` | 54 | modelo × chave (números de uma linha e textos "e daí?") |

### Features conferidas por outro caminho (SQL próprio direto da silver, sem a base comum da gold)
| Conferência | Resultado | |
|---|---|---|
| `customer_rfm_features`: frequência, valor e recência (dias até o `day` 705, último da semana 101) | 2.421 de 2.421 clientes iguais | ✅ |
| `customer_rfm_features`: só valores originais (G21, revisão) | sem colunas `z_*` e `log1p_*`; frequência, valor e recência = `customer_segment` em 2.421 de 2.421 | ✅ |
| `churn_features`, fotos de teste: recência = nota da regra simples e rótulo = rótulo do teste | 4.425 de 4.425 | ✅ |
| `churn_features`, foto final = clientes do `churn_score` | 2.203 = 2.203 | ✅ |
| `churn_features`: 21.318 + 2.207 + 4.425 + 2.203 | = 30.153 | ✅ |
| `clv_features` atual (76–101) | US$ 2.151.812,00 = silver | ✅ |
| `clv_features` calibração (24–49) | US$ 2.018.075,41 = silver | ✅ |
| `clv_features` 50–101: calibração futuro + análogos | 4.170.544,85 + 45.929,92 = **4.216.474,77** = silver | ✅ |
| `clv_features` 50–75: calibração futuro backtest + análogos | 2.050.871,83 + 13.790,94 = **2.064.662,77** = silver | ✅ |
| `clv_features`: calibração + análogos | 2.384 + 116 = 2.500 clientes | ✅ |

## 3. Modelos contra o RAG (80 de 80 iguais)
Comparação exata na precisão publicada. A única folga é de 1e-9, só para a representação binária: o painel guarda 18,301 ÷ 100 como `0.18300999999999998`.

### Os números pedidos
| Número | RAG / painel | Gold | |
|---|---|---|---|
| Fiéis: % dos clientes | 35,4% (857 de 2.421) | 35,4% (857 de 2.421) | ✅ |
| Fiéis: % do faturamento de 26 s | 70,88% (US$ 1.525.211,18) | 70,88% (US$ 1.525.211,18) | ✅ |
| AUC do modelo × regra simples | 0,8531 × 0,7378 | 0,8531 × 0,7378 | ✅ |
| Limiar de alerta | 0,17 | 0,17 | ✅ |
| Alertas na foto final (prob ≥ 0,17) | 243 | 243 | ✅ |
| Pausas esperadas | 135,952 | 135,952 (também pela soma das 2.203 probabilidades) | ✅ |
| CLV total (52 s, margem 25%) | US$ 1.103.220,323 | US$ 1.103.220,323 | ✅ |
| CLV: IC 95% do total | 1.063.209,966 a 1.143.640,883 | igual | ✅ |
| Teste de desconto: veredito | `diferenca_desprezivel` (H = 11,6837, p = 0,0085, eta² = 0,0036) | igual | ✅ |

### O resto da conferência
| Bloco | Itens | |
|---|---|---|
| **RFM** | K = 4. **Segmento cliente a cliente: 2.421 de 2.421** iguais ao `grupo_cliente` do painel, mais os 79 "Sem segmento". Por segmento: clientes, % de clientes, faturamento, % do faturamento e ticket (média dos clientes) | ✅ 23 |
| **Risco de pausa** | k da regra = 4; AUC recalculada pelas notas gravadas; por segmento: clientes, alertas e pausas (Fiéis 857 / 0 / 5,1836, Regulares 966 / 20 / 43,7009, Esporádicos 380 / 223 / 87,0675); matrizes de confusão (modelo 3805/337/147/136, regra 3831/311/189/94); IC da AUC, AUC-PR, precisão, recall, F1, alertas, pausas, falso alarme; diferença de AUC 0,1148 (IC 0,0886 a 0,1495) | ✅ 21 |
| **Curva ROC** | 478 pontos, **0 diferentes** em fpr, tpr e corte | ✅ 2 |
| **Dinheiro em risco (G4)** | faturamento de 26 s dos 243 clientes com `is_high_risk`, por SQL próprio: **US$ 41.140,15** = `departamentos_risco.json` (todos × todos) | ✅ 1 |
| **CLV** | total, IC e receita esperada; backtest (erro −2,93% × −4,05%, ganha em 5 de 5); por segmento: households, CLV médio, IC, total, receita esperada; backtest de cada um (households, real, método, ingênuo); texto da conclusão | ✅ 16 |
| **Teste de desconto** | households (2.421); H, p, eta²; veredito; impacto (US$ 399.891,92, taxa 15,67%, economia US$ 5.607,43); textos "e daí?" (conclusão, evidência, ação); 6 pares (diferença, IC, exclui zero, p de Holm, significativo); 4 segmentos (mediana, quartis, bigodes, taxa ponderada, totais) | ✅ 17 |

## 4. Testes (`python -m pytest -q`)
**96 passed** em 124 s (28 da bronze + 47 da silver + 21 da gold), rodado com `-W error::DeprecationWarning`.

O que a gold cobre (silver sintética, a igualdade com o RAG fica na seção 3):
- **Base comum:**
  - janela termina na última semana completa e recua se ela ficar incompleta;
  - `sales_item` só com mercadoria até o fim, desconto positivo e valor bruto = faturamento + desconto;
  - `customer_metrics` por outro caminho;
  - `household` sem o `-1`.
- **Features:**
  - a entrada do RFM é a padronizada;
  - o churn tem 10 / 1 / 2 / 1 fotos por papel, e o rótulo só é nulo na final;
  - as variáveis do teste geram as notas da regra;
  - o gasto do CLV fecha com o faturamento.
- **Modelos:**
  - um segmento por cliente com os 4 nomes do contrato;
  - probabilidade em [0, 1] e alerta = prob ≥ limiar;
  - alertas e pausas do resumo = soma por cliente;
  - matriz e AUC batem com as notas;
  - ROC de (0, 0) a (1, 1);
  - CLV com o grupo "Sem compra na janela";
  - 6 pares no teste de desconto.
- **Execução:**
  - idempotência (14 tabelas);
  - controle;
  - sem silver → código 1 e nada gravado;
  - `espiar.py` em `gold/features`, `gold/models` e `_controle_gold`.

## 5. Notebook
Verificação nova **19. Semana completa** ✅. Quadro: Bronze 8 de 8, Silver **16 de 16**, **total 24 de 24** ✅. A seção Gold do notebook entra na 3c, como diz a spec.

## Achados
1. **Nenhum número diferente do RAG.** O código do RAG rodou sobre a silver sem mudança de método, e a silver já entregava a mesma base (2.421 clientes na janela, 2.500 no total).
2. **DuckDB 2.0:** depois de um `execute(...).fetchone()`, que o código do RAG usa, a mesma conexão recusa `con.sql(...)`. Só `execute` é aceito. O código da gold usa `execute` (G19). Isso apareceu como erro na primeira execução com as features e foi corrigido antes da validação.
3. **A ordem das linhas de uma tabela Delta lida não é garantida** (apareceu nos dados sintéticos). A idempotência passou a ser conferida pelo conteúdo ordenado (G20).
4. **"Em pausa" não aparece no risco de pausa:** quem está em pausa já não compra nas últimas 8 semanas e fica fora da população do modelo. Dos 2.421 clientes segmentados, 2.203 têm probabilidade. É o mesmo comportamento do RAG. Para o dinheiro em risco (G4) isso não muda nada, porque eles não têm alerta.

## Pendências e pontos para revisão
- **Decisões G13–G20,** tomadas na construção. Em especial:
  - G13: `household` = `dim_household` sem o `-1`;
  - G16: `rfm_segment_profile` a mais e `passed` fora da `rfm_k_evaluation`.
- **`churn_features` guarda as 5 variáveis como o modelo as recebe**, antes da padronização: recência em semanas e os `log1p`. O `StandardScaler` do churn é ajustado no treino e não foi gravado. Se você quiser também as variáveis padronizadas (como no RFM), é uma mudança pequena.
- **`clv_features` não inclui a segmentação refeita pelo backtest** na janela 50–75. Os gastos dessa janela estão lá (`calibracao_futuro_backtest`), mas não o segmento que o backtest atribui a cada cliente nela. Incluir exigiria mudar o retorno de `clv.backtest`.
- O script da conferência da seção 3 ficou fora do repositório (scratchpad), porque a conferência oficial é a etapa `reconcile` da 3c. Se quiser, ele entra agora em `scripts/`.
- Commit da parada 3a, depois da sua revisão. Proposta: `feat: gold 3a (features e modelos do RAG lendo da silver)`.

## Revisão do Caio (29/10/2026)
- **G13–G20 aprovadas.**
- **G21 (regra das features: variável = valor original; padronizar é etapa do modelo):**
  - `churn_features` fica como estava;
  - `customer_rfm_features` perdeu `log1p_frequency`, `log1p_monetary` e `z_recency`/`z_log1p_frequency`/`z_log1p_monetary`.
  - A gold foi reconstruída (14 tabelas, mesmas contagens) e a conferência contra o RAG rodou de novo: **80 de 80 iguais**. Testes: **96 passed**.
- **G22:** o segmento do backtest do CLV fica fora de `clv_features`, como limitação conhecida.
