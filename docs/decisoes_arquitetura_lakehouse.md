# Decisões de arquitetura — retail-lakehouse

> Registro das decisões do Caio, camada por camada, com o porquê. Formato de **ADR** (Architecture Decision Record): cada decisão diz o que foi decidido, o motivo e o que fica em aberto. Mudou uma decisão? Não apague: marque como "substituída" e escreva a nova.

## To-do e pendências (atualizado em 30/10/2026)

**A fazer (na ordem):**
- [ ] Terminar o vídeo de arquitetura e encaixar aqui o que fizer sentido
- [x] Perfil da bronze (28/10/2026) → `notebooks/perfil_bronze.ipynb` (consultas, resultados e conclusões no notebook, em vez de `docs/perfil_bronze.md`)
  - [x] grão da cesta · [x] `trans_time` · [x] não mercadoria · [x] "Unknown" na demografia
  - [ ] ~~marketing~~ — fora da silver por enquanto (S7); perfil só quando for modelar
- [x] Fechar as regras específicas da silver com base no perfil → **S9**
- [x] Construir a silver (fase 2) → `docs/spec_fase2_silver.md` · validação em `docs/validacao/fase2_silver.md` (29/10/2026)
- [x] Replanejar o painel antes da gold (Caio, 28/10/2026) → ver "Painel v4" abaixo
- [x] Decidir como reaproveitar as análises estatísticas do RAG como tabelas gold geradas a partir da silver → G5, G6 (29/10/2026)
- [x] Desenhar a gold: levantamento em `docs/levantamento_gold.md`, decisões G1–G11, spec em `docs/spec_fase3_gold.md` (29/10/2026)
- [x] Construir a gold (fase 3) — concluída em 30/10/2026
  - [x] Parada 3a: features e modelos → `docs/validacao/fase3a_gold.md` (aprovada em 29/10/2026)
  - [x] Parada 3b: base comum e métricas → `docs/validacao/fase3b_gold.md` (aprovada em 30/10/2026, com o ajuste G33)
  - [x] Parada 3c: exportação e reconciliação → `docs/validacao/fase3c_gold.md` (aprovada em 30/10/2026)
  - [x] Comando único do pipeline, `python -m src.pipeline` (G42)
- [ ] **Próximo passo: construir o painel v4** no repositório `retail-bi-dashboard`, como consumidor de `export/painel_v4/` (G43). Isso acontece numa sessão aberta lá; este projeto não altera aquele repositório.
- [ ] Configuração do Claude (`CLAUDE.md`, skills, MCP, permissões): ver `claude/todo_configuracao_claude.md`
- [x] Escrever a spec e o prompt da construção (bronze + `espiar.py` primeiro)

**Decisões pendentes:**
- ~~Regras específicas da silver~~ → fechadas na S9 (28/10/2026). Ficam abertos: significado de `A`/`B` no estado civil (S9.9).
- ~~Toda a camada gold~~ → G1–G11 (29/10/2026)
- ~~Como o painel passa a ler da nova arquitetura~~ → G43 (30/10/2026): o painel v4 lê `export/painel_v4/` (contratos 5.0, nomes em português no JSON).
- Como o chat (projeto de RAG) passa a ler da nova arquitetura (ajuste dos nomes para inglês)

---

## L1. Lakehouse de verdade: Delta Lake em todas as camadas (decidido em 28/10/2026; bronze incluída na mesma data)
- **Decisão:** **bronze, silver e gold** são gravadas em **Delta Lake** (biblioteca `deltalake` para gravar; extensão `delta` do DuckDB para ler, com `delta_scan`). Padronizar o formato em todas as camadas, como no padrão do Databricks.
- **Bronze em Delta:** cada carga entra com `_data_carga` como **coluna de partição**. Rodar de novo no mesmo dia **substitui só a partição daquele dia** (idempotência). Uma carga que falha no meio **não é gravada** (transação do Delta), o que substitui a regra manual de apagar a pasta.
- **Por quê:** sem um formato de tabela, o projeto seria um *data lake em camadas medalhão*, não um lakehouse. O Delta acrescenta o que define um lakehouse:
  - **transações:** uma gravação entra inteira ou não entra, nunca fica pela metade;
  - **histórico de versões** (*time travel*): dá para consultar a tabela como estava numa versão anterior;
  - **esquema garantido:** gravação com coluna ou tipo errado é recusada.
  É o formato padrão do Databricks, e o projeto da NBA já começa com ele.
- **Substitui:** a P7 (Parquet simples na silver).
- **Efeito na P8 (reconstrução completa):** cada execução grava a tabela em modo *overwrite*, o que gera uma **versão nova** sem apagar as anteriores. Assim a reconstrução completa continua, mas com histórico.
- **Efeito no `espiar.py`:** lê Delta em todas as camadas; ganha o modo `versoes` (lista as versões de uma tabela) e a opção `--versao N`.
- **Retenção (confirmada em 28/10/2026):** manter as versões dos últimos **30 dias**; versões mais antigas são limpas com o comando `vacuum` do Delta.

---

## R1. Relação com o projeto de RAG (decidido pelo Caio em 28/10/2026)
- **O projeto de RAG não muda.** O `retail-lakehouse` é independente: não altera o RAG, não é lido pelo chat e o chat **deixa de ser consumidor** desta arquitetura.
- **Do RAG reaproveitamos só:**
  1. os **dados brutos** (CSVs da Dunnhumby);
  2. as **regras e decisões já estabelecidas** (limpeza, janela, lojas comparáveis, definições de métrica);
  3. os **cálculos estatísticos prontos** (segmentação RFM, CLV, risco de pausa, teste de desconto), trazidos para cá e adaptados para ler da silver e gravar na gold;
  4. os **números do RAG e do painel atual como gabarito** (só leitura, para conferir).
- **Consumidores da gold:** o painel v4 e a página de Metodologia. Nada mais por enquanto.
- **Emenda (29/10/2026, G9):** além do código do RAG, pode ser copiado o `scripts/layout.py` do painel publicado (posições da rede de cestas). O restante do painel serve só como fonte das regras.
- **Efeito na S7:** marketing fica só na bronze (confirmado pelo Caio em 28/10/2026). A silver passa a ter 5 tabelas: `fact_sales`, `dim_household`, `dim_product`, `dim_store`, `dim_date`.

## Painel v4: escopo que a gold vai atender (decidido pelo Caio em 28/10/2026)
> Vale para o painel reconstruído sobre o lakehouse. O painel publicado hoje não muda até lá.

| Aba | Decisão |
|---|---|
| **Visão Geral** | **Sai** "O que puxou a variação". **Faturamento semanal mostra só o período selecionado** (não mais 52 semanas com o período sombreado), com o ano anterior tracejado no mesmo período. Ficam: 6 KPIs, faturamento por segmento, faturamento por departamento (com o traço do ano anterior). |
| **Categorias** | fica como está |
| **Clientes & Lojas** | **sai inteira** (Roda, migração, regiões, perfil das lojas, ranking, ficha da loja, CSV de risco) |
| **Cestas & Marcas** | fica como está |
| **Metodologia** (rodapé) | fica como está |

**Proposta a confirmar (faturamento semanal só do período):** com "Últimas 4 semanas" a linha teria só 4 pontos. Proposta: o detalhe se ajusta ao período — **diário** nas 4 semanas (~28 pontos), **semanal** em 13, 26 semanas e base inteira.

**O que isso tira da gold:** regiões inferidas, perfil das lojas, ranking e ficha de loja, migração de segmentos, lista de ação e valor em risco por loja.
**O que continua precisando de modelos na gold:** segmento do cliente (filtros e "faturamento por segmento"), risco de pausa ("dinheiro em risco" em Categorias), CLV, curva ROC e teste de desconto (página de Metodologia).

---

## Contexto
Refazer toda a arquitetura de dados do painel BI de varejo no padrão **lakehouse medalhão**, reaproveitando o visual, as abas e as perguntas do painel atual. O painel atual (988/988 na reconciliação) é o **gabarito**: a nova arquitetura está certa quando produz os mesmos números.

---

## Bronze

### B1. Carga completa, sem atualizações semanais (por enquanto)
- **Decisão:** a base da Dunnhumby entra inteira, de uma vez.
- **Por quê:** começar simples. A carga incremental (simular semanas chegando) fica para depois, como evolução.

### B2. Motor: DuckDB
- **Decisão:** a bronze lê os CSVs e grava em Parquet com o DuckDB, não com o pandas.
- **Por quê:** o DuckDB processa sem carregar o arquivo inteiro na RAM. O pandas carrega tudo em memória (o DataFrame vive na RAM), e o notebook já ficou sem memória antes.

### B3. Fluxo da bronze
1. Montar o caminho do arquivo de entrada a partir da configuração.
2. **Conferir se o arquivo existe.** Se não existir, parar com erro claro.
3. **Conferir se o arquivo não está vazio** e se tem as **colunas esperadas**.
4. Ler com todas as colunas como **texto** (`all_varchar = true`).
5. Acrescentar as colunas de rastreabilidade (B4).
6. Gravar a tabela **Delta** da bronze, na partição da data de carga (ver L1).
7. Conferir que **linhas lidas = linhas gravadas** e registrar a carga na tabela de controle (B5).

### B4. Rastreabilidade: colunas em cada linha
- `_arquivo_origem`: nome do CSV de onde a linha veio.
- `_data_carga`: data e hora da carga.
- **Por quê:** saber de onde cada linha veio e quando, mesmo meses depois.

### B5. Tabela de controle das cargas
Uma linha por arquivo carregado, em `lake/bronze/_controle_cargas.parquet`:

| Coluna | O que guarda |
|---|---|
| arquivo | nome do CSV |
| data_carga | quando foi carregado |
| linhas_lidas / linhas_gravadas | precisam ser iguais |
| colunas_esperadas_ok | verdadeiro ou falso |
| status | sucesso ou erro, com a mensagem |

- **Por quê:** auditoria. Responde "o que foi carregado, quando, e deu certo?" sem abrir os dados.
- **Atualizada em 28/10/2026 (B13):** o controle virou tabela **Delta** em `lake/bronze/_controle_cargas` (append), não mais `.parquet`, e ganhou as colunas `tabela`, `carregado_em` e `mensagem`.

### B6. Tudo como texto na bronze
- **Decisão:** nenhuma conversão de tipo na bronze.
- **Por quê:** a bronze guarda o dado **exatamente como chegou**. Tipos (número, data) e limpeza são da silver, onde ficam documentados e testados.

### B7. Idempotência
- **Decisão:** rodar a bronze duas vezes dá o mesmo resultado, sem duplicar dados.

### B8. Vários arquivos, uma lógica
- **Decisão:** a mesma função carrega todos os arquivos, a partir de uma **lista na configuração**.

### B9. Arquivos que entram: 7 de 8
- **Decisão:** entram transaction_data, product, hh_demographic, campaign_table, campaign_desc, coupon e coupon_redempt. **Fica fora o `causal_data`.**
- **Por quê:** o `causal_data` (encarte e ponta de gôndola) é enorme e está fora do escopo atual.

### B10. Histórico de cargas guardado
- **Decisão:** cada carga é guardada como uma **partição** da tabela Delta (`_data_carga = AAAA-MM-DD`). Nada de cargas anteriores é sobrescrito. *(Atualizado pela L1: antes eram pastas de Parquet.)*
- **Por quê:** é o padrão da arquitetura, mesmo sem uso imediato. Guarda o histórico, permite auditar e reprocessar, e é a base da carga incremental (projeto da NBA).
- **Consequência para a silver:** ela lê a **carga mais recente** de cada tabela, ou uma carga específica quando for preciso reprocessar.
- **Idempotência (B7) com histórico:** rodar de novo no mesmo dia substitui a pasta daquele dia, sem duplicar.

> ✅ **Plano da bronze finalizado em 28/10/2026.**

### Visão completa da bronze

**Estrutura de pastas**
```
retail-lakehouse/
  config.yaml                  # caminhos e lista de arquivos (fora do git)
  config.example.yaml          # modelo do config, sem caminhos reais
  data/raw/                    # os 7 CSVs da Dunnhumby (fora do git)
  lake/                        # o lakehouse (fora do git)
    bronze/
      transaction_data/
        _delta_log/                    # registro de versões do Delta
        _data_carga=2026-10-28/…parquet  # uma partição por carga
      product/
        _delta_log/
        _data_carga=2026-10-28/…parquet
      ... (uma pasta por arquivo)
      _controle_cargas.parquet
  src/bronze/ingest.py         # a lógica da bronze
  scripts/espiar.py
  docs/
```

**O que vai no `config.yaml`**
- a pasta de entrada (`data/raw/`) e a pasta do lake (`lake/`);
- a lista dos 7 arquivos, cada um com o nome da tabela e as **colunas esperadas**.

**Uma execução, passo a passo** (`python -m src.bronze.ingest`):
1. Lê o `config.yaml`.
2. Para cada arquivo da lista:
   1. confere se ele existe, se não está vazio e se tem as colunas esperadas;
   2. lê com o DuckDB, tudo como texto;
   3. acrescenta `_arquivo_origem` e `_data_carga`;
   4. grava na tabela Delta `lake/bronze/<tabela>`, na partição de hoje, substituindo só essa partição se ela já existir;
   5. confere que linhas lidas = linhas gravadas;
   6. registra uma linha no `_controle_cargas` (sucesso ou erro, com a mensagem).
3. No fim, mostra um resumo no terminal: tabela, linhas e status.

**Quando algo dá errado (B11, confirmado):**
- **Arquivo faltando, vazio ou com coluna errada:** aquele arquivo é registrado com status de erro e a execução **segue para os outros**, porque na bronze os arquivos são independentes. No fim, o comando termina **com erro**, para ninguém achar que deu tudo certo.
- **Contagem diferente entre lido e gravado:** a gravação daquela carga não é confirmada (o Delta desfaz a transação) e o erro é registrado.

**O que fica fora do git:** `config.yaml`, `data/` e `lake/`. Só o código, o `config.example.yaml` e a documentação vão para o repositório.

### Decisões tomadas na construção da fase 1 (28/10/2026)
- **B12. Data da carga no fuso local (pedido do Caio na aprovação do plano):** `_data_carga` é a data **local** em `America/Sao_Paulo` (texto `AAAA-MM-DD`, coluna de partição), nunca a data de UTC. Por quê: em UTC, uma carga depois das 21h cairia na partição do dia seguinte. `_carregado_em` é separado e guarda data, hora e **fuso explícito** (`timestamp with time zone`, ex.: `2026-10-28 16:32:03-03`). O fuso fica no config (`bronze.fuso`). Teste: 22h em São Paulo (01h UTC do dia 29) continua na partição do dia 28.
- **B13. Controle de cargas em Delta:** ver a atualização da B5. Append de uma linha por tabela por execução, logo depois de cada tabela (se o processo cair no meio, o que já carregou fica registrado).
- **B14. Leitura Delta sem a extensão `delta` do DuckDB:** `DeltaTable(...).to_pyarrow_dataset()` entregue ao DuckDB (`src/comum.py`, função `ler_delta`). Continua lendo pelo `_delta_log` (F3), sem precisar baixar extensão, e o DuckDB só puxa as colunas e partições usadas. Uma função só para ingestão, `espiar.py`, notebook e testes.
- **B15. Arquivo só com cabeçalho é erro:** 0 linhas de dado → status `erro` ("arquivo só com cabeçalho"). Um CSV da Dunnhumby nunca vem vazio de verdade; se vier, algo deu errado na origem.
- **B16. Desfazer quando a contagem não bate:** tabela que já existia → `restore` para a versão de antes da gravação. Tabela criada nessa mesma execução (não há versão anterior) → `delete` da partição do dia. Nos dois casos o status é `erro` e a mensagem diz o que foi feito.
- **B17. `--data-carga` na ingestão:** `python -m src.bronze.ingest --data-carga AAAA-MM-DD` grava numa data escolhida, para reprocessar ou simular outro dia (base da carga incremental futura). Sem a opção, vale a data de hoje no fuso do config.
- **B18. Validação do cabeçalho exige a mesma ordem:** colunas iguais em outra ordem também é erro, porque a silver vai depender dos nomes e a ordem diferente indica arquivo diferente do documentado.

---

## Ferramentas

### F1. Script de inspeção `scripts/espiar.py`
- **Decisão:** uma das primeiras coisas a construir é um script para inspecionar qualquer tabela de qualquer camada pelo terminal, usando DuckDB (sem carregar tudo na RAM). Exemplos:
  - `python scripts/espiar.py silver/transacoes amostra 20` → amostra aleatória (`USING SAMPLE`);
  - `python scripts/espiar.py silver/transacoes topo 20` → primeiras linhas (`LIMIT`);
  - `python scripts/espiar.py silver/transacoes colunas` → nomes e tipos (`DESCRIBE`);
  - `python scripts/espiar.py silver/transacoes resumo` → qualidade na tabela inteira (`SUMMARIZE`: mínimo, máximo, nulos, distintos);
  - `python scripts/espiar.py bronze/_controle_cargas` → últimas cargas.
- **Por quê:** conferir com os próprios olhos cada camada antes de seguir, de forma rápida e repetível. Amostra para olhar, tabela inteira para medir qualidade.

**Esboço do funcionamento (sem código):**
- **Entrada:** `camada/tabela` (ex.: `bronze/product`) + um modo + um número opcional.
- **Qual carga ler (bronze):** por padrão, a **mais recente** (maior `_data_carga`). Com `--carga 2026-10-28`, uma carga específica. Na silver e na gold, `--versao N` mostra uma versão anterior.
- **Modos:**
  | Modo | O que mostra | Lê a tabela inteira? |
  |---|---|---|
  | `topo N` | as primeiras N linhas | não |
  | `amostra N` | N linhas aleatórias | não |
  | `colunas` | nome e tipo de cada coluna | não |
  | `resumo` | por coluna: tipo, mínimo, máximo, nulos, distintos | sim, mas sem carregar na RAM |
  | `contagem` | número de linhas | sim |
  | `cargas` | as cargas existentes daquela tabela, com data e linhas | só o controle |
- **Erros amigáveis:** tabela que não existe → lista as tabelas disponíveis; carga que não existe → lista as datas disponíveis.
- **Segurança:** só lê, nunca grava nem apaga nada.
- **Saída:** uma tabela formatada no terminal. Opcional: `--csv` salva o resultado num arquivo, para abrir no Excel.

### F2. Notebook de tour do lakehouse `notebooks/explorando_lakehouse.ipynb` (decidido em 28/10/2026)
- **Decisão:** além do `espiar.py`, um notebook que passa pelas três camadas mostrando tabelas, versões Delta, contagens, amostras e **as conferências** (contagem esperada = obtida, bronze = silver + rejeitados).
- **Papéis:** `espiar.py` + testes automáticos = verificação do dia a dia (rodam e param o pipeline); notebook = **entender e mostrar** (visual, narrado, saídas guardadas). Serve de vitrine no GitHub.
- O **perfil da bronze** (S0) também é feito em notebook: consultas, resultados e conclusões juntos.
- Inspirado no notebook do vídeo de arquitetura, acrescentando as conferências que lá não aparecem.

**Verificações do notebook (simples, uma por célula, cada uma mostrando ✅/❌ com o esperado e o encontrado):**

| Camada | Verificação | Esperado |
|---|---|---|
| **Bronze** | contagem de cada tabela = `linhas_gravadas` no `_controle_cargas` | iguais |
| | última carga de cada tabela com status de sucesso | 7 de 7 |
| | colunas presentes = colunas esperadas do `config.yaml` | iguais |
| | todas as colunas de dado como texto | 100% texto |
| | `_arquivo_origem` e `_data_carga` sem nulos | 0 nulos |
| | `transaction_data` | 2.595.732 linhas (gabarito) |
| **Silver** | por tabela: linhas da bronze = linhas da silver + rejeitados | iguais |
| | % rejeitado por tabela | abaixo de 1% |
| | chave de cada `dim_` sem nulos e sem repetição | 0 e 0 |
| | vendas apontando para o membro "desconhecido" (-1) | 0 (gabarito: zero órfãos) |
| | `sales_value >= 0` e `quantity > 0` na `fact_sales` | 0 violações |
| | `fact_sales` com `is_merchandise = false` | **32.604** linhas, US$ **681.121,43** (os 32.805 do gabarito menos 201 linhas com quantidade zero, que vão para os rejeitados; ver S9) |
| | soma de `sales_value` por semana = soma da bronze por semana | 102 semanas, diferença até US$ 0,01 |
| | `dim_household` com `has_demographics = true` | 801 de 2.500 |
| | `dim_date`: dias e semanas | 711 dias, semanas 1 a 102 vindas do arquivo |
| **Gold** | faturamento da gold = faturamento de mercadoria da silver | iguais |
| | grão de cada tabela gold sem linhas repetidas | 0 |
| | indicadores contra o gabarito do RAG: ticket médio, itens por cesta, % de desconto | US$ 29,39 · 13,3 · 16,1% |
| | comparação com o ano anterior (lojas comparáveis) | 214 lojas, +3,4% no faturamento |

- **No fim do notebook:** um quadro-resumo com todas as verificações, ✅ ou ❌, para ver a saúde do lakehouse de uma olhada.
- As verificações da gold serão revisadas quando a gold for desenhada.

### F3. Regra de leitura: tabela Delta se lê como tabela, nunca pelos arquivos (decidido em 28/10/2026)
- **Decisão:** nunca ler os arquivos `.parquet` direto da pasta de uma tabela Delta. Ler sempre como tabela Delta: `DeltaTable(...)` no Python ou `delta_scan('caminho')` no DuckDB.
- **Por quê:** quando o Delta grava uma versão nova, os arquivos antigos **continuam na pasta** até o `vacuum` (é o que permite voltar no tempo). Quem decide quais arquivos fazem parte da versão atual é o `_delta_log`. Ler a pasta com `*.parquet` pode somar arquivos antigos e **contar em dobro**.
- **Vale para:** `espiar.py`, notebooks, testes, consultas manuais e o código das camadas. Vai também para o `CLAUDE.md` do projeto.

---

## Silver
*(em construção)*

### S0. Conhecer a base antes de escrever as regras (guia de boas práticas, item 2)
- **Decisão:** antes de fixar qualquer regra de limpeza, fazer o **perfil da bronze** com o `espiar.py` e registrar em `docs/perfil_bronze.md`, tabela por tabela:
  - **grão** (o que é uma linha) e contagem;
  - **cobertura** (período, quantos clientes, lojas e produtos);
  - **chaves:** são únicas? têm nulos?
  - **nulos, zeros e negativos** por coluna;
  - **outliers:** valores muito acima do normal (ex.: quantidades enormes em combustível);
  - **significado de negócio** de cada coluna, principalmente as que confundem (`sales_value` já é líquido; descontos são negativos).
- **Por quê:** a regra nasce do dado, não do palpite. As regras de S3 só são confirmadas depois desse perfil.

### S1. Nomes: snake_case, minúsculas, em inglês, o mais próximo do original
- **Decisão:** tabelas e colunas em **snake_case**, tudo **minúsculo**, em **inglês**, mantendo ao máximo os nomes originais da Dunnhumby: `SALES_VALUE` → `sales_value`, `BASKET_ID` → `basket_id`, `household_key` continua `household_key`.
- **Por quê:** a base original mistura maiúsculas e minúsculas, e o projeto anterior misturava inglês e português. Manter o original facilita conferir com a documentação da base. Inglês é o padrão de mercado.
- **Fora do escopo agora:** o painel e os textos em português serão ajustados depois. A silver só trata os dados.

### S2. Modelagem: star schema na silver, organizado por contexto
- **Decisão:** o star schema fica na **silver** (não na gold), com prefixos `fact_`, `dim_` e `bridge_`, e as tabelas são **organizadas por assunto de negócio** (silver de contexto). A gold fica só com as regras de negócio.
- **Por quê:** cada tabela tem assunto e grão claros. Separar por contexto deixa visível o que pertence a vendas, a clientes, a produtos e a marketing. A gold vai concentrar as regras do painel e dos modelos, então não deve carregar também a modelagem.

**Organização em duas etapas dentro da silver (confirmada pelo Caio em 28/10/2026):**
1. **`silver/clean/`:** uma tabela por arquivo da bronze, já com tipos, nomes padronizados e regras de qualidade aplicadas. É onde nascem os rejeitados. Grão igual ao do arquivo de origem.
2. **`silver/context/`:** o star schema montado a partir da `clean`, em pastas por assunto:

| Contexto | Tabelas |
|---|---|
| `sales/` | `fact_sales`, `dim_store` |
| `customer/` | `dim_household` |
| `product/` | `dim_product` |
| ~~`marketing/`~~ | ~~`dim_campaign`, `fact_campaign_received`, `bridge_coupon_product`, `fact_coupon_redemption`~~ — fora por enquanto (S7) |
| `shared/` | `dim_date`: **dimensão conformada**, ou seja, compartilhada por todos os contextos, para que "semana 50" signifique a mesma coisa em vendas e em campanhas |

- **Por que duas etapas, se há uma fonte só:** a limpeza (tipos, regras, rejeitados) fica separada da modelagem (juntar e organizar). Quando uma regra de limpeza muda, a modelagem não precisa ser mexida, e vice-versa. E o padrão já fica pronto para quando houver várias fontes, como no projeto da NBA.

**Tabelas propostas (a confirmar):**

| Tabela | Origem | Grão (o que é uma linha) |
|---|---|---|
| `fact_sales` | transaction_data | um item de uma cesta |
| `dim_household` | transaction_data + hh_demographic | um cliente (household); a demografia fica vazia para quem não tem |
| `dim_product` | product | um produto |
| `dim_store` | transaction_data (lojas distintas) | uma loja |
| `dim_date` | `day` e `week_no` | um dia (`day` 1..711 → data real a partir de 2016-01-01, igual ao projeto anterior) |
| `dim_campaign` | campaign_desc | uma campanha |
| `fact_campaign_received` | campaign_table | um cliente que recebeu uma campanha |
| `bridge_coupon_product` | coupon | um cupom × um produto (um cupom vale para vários produtos) |
| `fact_coupon_redemption` | coupon_redempt | um resgate de cupom |

### S3. Qualidade: nada é apagado em silêncio
- **Decisão:** toda linha que falhar numa regra vai para uma tabela de **rejeitados** (`silver/_rejected/<tabela>`) com o **motivo**, e a contagem entra no controle. A silver nunca "some" com uma linha sem registrar.
- **Por quê:** auditoria e confiança. Dá para responder "quantas linhas saíram e por quê".
- **Limite de alarme (proposta):** se mais de 1% das linhas de uma tabela forem rejeitadas, o pipeline para com erro, porque provavelmente a regra ou o arquivo estão errados.

**Regras (proposta, a confirmar depois de olhar os dados com o `espiar.py`):**
- **Chaves preenchidas:** `basket_id`, `household_key`, `product_id`, `store_id`, `day`.
- **Valores:** `sales_value >= 0` e `quantity >= 0`. Conferir antes se existem linhas com valor 0 legítimas (brinde, item devolvido) antes de decidir entre `> 0` e `>= 0`.
- **Descontos:** `retail_disc`, `coupon_disc` e `coupon_match_disc` são **negativos por definição** na Dunnhumby. A regra é `<= 0`, nunca `> 0`.
- **Faixas válidas:** `day` entre 1 e 711, `week_no` entre 1 e 102, `trans_time` entre 0000 e 2359.
- **Dimensões:** chave única (sem `product_id` repetido em `dim_product`).
- **Integridade entre tabelas:** todo `product_id` da `fact_sales` existe na `dim_product`, e o mesmo para loja e cliente. Os órfãos são contados e registrados.
- **Duplicatas:** linhas idênticas na `fact_sales` são contadas e decididas caso a caso, porque podem ser compras legítimas repetidas.

### S4. Tipos
- **Decisão (proposta):** a conversão de texto para os tipos certos acontece aqui. IDs como inteiro (`basket_id` como `bigint`, porque é um número grande), dinheiro como `decimal(10,2)`, `quantity` como inteiro e datas como `date`. **Códigos que parecem número mas são código** (`coupon_upc`) continuam como texto, para não perder zeros à esquerda.

### S5. Gabarito
- A silver nova deve reproduzir os totais limpos do projeto anterior (faturamento semana a semana). Se uma regra nova mudar um total, a diferença precisa ser explicada e registrada.

### S6. Relatório de limpeza e conferência por outro caminho (guia de boas práticas, itens 3 e 7) — versão simplificada
- **Relatório de limpeza:** não é uma tabela à parte. É uma **consulta-resumo dos rejeitados** (um `GROUP BY` por tabela e regra, com linhas afetadas e %). O motivo de negócio de cada regra fica escrito uma vez, no código da regra.
- **Conferência por outro caminho:** poucas verificações, bem escolhidas, com SQL próprio direto da bronze: (1) linhas da bronze = linhas da silver + rejeitados, por tabela; (2) soma de `sales_value` por semana. Não reaproveita o código da silver, para não ser circular.

### Silver: pendências de decisão
> P1 a P8 **confirmadas pelo Caio em 28/10/2026**.

**Detalhe da P3 (demografia), opção A escolhida:** as colunas de demografia ficam na própria `dim_household`, vazias para quem não tem, mais a coluna `has_demographics`.
- **Por quê:**
  - um lugar só para consultar o cliente (pessoa, painel ou LLM não precisam lembrar de juntar duas tabelas);
  - a `has_demographics` diz o que o vazio significa ("fora da pesquisa", não "não respondeu") e permite filtrar direto;
  - deixa visível que análises com demografia valem só para a parte da base que tem esses dados (cerca de um terço, a confirmar no perfil), que pode não representar o todo.
- **Alternativa descartada:** uma tabela separada `dim_household_demographics`. Mais "pura" na teoria, mas acrescenta uma junção sem ganho real para uma base deste tamanho.

| # | Decisão em aberto | Proposta |
|---|---|---|
| P1 | Lista de tabelas (S2) | confirmar a tabela de S2, com `dim_household` e `bridge_coupon_product` |
| P2 | Produto, loja ou cliente da venda que não existe na dimensão (órfão) | **membro "desconhecido"** (id -1) na dimensão em vez de rejeitar a venda: o faturamento total não muda e o órfão fica visível e contado |
| P3 | Onde fica a demografia | colunas na `dim_household`, vazias para quem não tem, mais `has_demographics` (verdadeiro/falso) |
| P4 | `dim_date` | data-base 2016-01-01 (igual ao projeto anterior, para o gabarito bater); colunas: `date`, `day`, `week_no`, `month`, `year`, `day_of_cycle` (1 a 7, **sem nome de dia**, porque o calendário é reconstruído) |
| P5 | Tipos (S4) | `bigint` para IDs; `decimal(10,2)` para dinheiro; `integer` para `quantity`; `trans_time` vira `hour` e `minute` inteiros; códigos (`coupon_upc`) continuam texto |
| P6 | Limite de rejeição | 1% por tabela para o pipeline parar |
| P7 | Formato da silver | ~~Parquet simples~~ **Substituída em 28/10/2026 pela L1 (Delta Lake na silver e na gold).** |
| P8 | Como a silver roda | **reconstrução completa** a cada execução, a partir da carga mais recente da bronze (base pequena, mais simples e idempotente) |
| — | Regras de qualidade (S3), duplicatas e outliers | **só depois do perfil da bronze (S0)**: a regra nasce do dado |

### S7. Marketing ~~modelado na silver (opção A)~~ — **substituída em 28/10/2026**
- ~~Campanhas e cupons entram na silver (`context/marketing/`), porque o chat usava essas tabelas.~~
- **Nova decisão:** com o chat fora (R1), nenhum consumidor usa campanhas e cupons. As 4 tabelas de marketing ficam **só na bronze** e entram na silver quando algum consumidor precisar (o dado já está guardado).

### S8. Estrutura preparada para crescer: regras globais + regras específicas
- **Decisão:** acrescentar uma tabela nova na silver deve ser **somar uma peça**, sem reescrever o resto.
- **Como:**
  1. **Regras globais**, aplicadas automaticamente a **toda** tabela da silver, nova ou antiga:
     - nomes em snake_case, minúsculo, inglês (S1);
     - tipos padrão (P5/A2);
     - colunas de rastreio herdadas da bronze;
     - rejeitados com motivo (S3) e limite de 1% (P6);
     - conferência linhas da bronze = silver + rejeitados (S6);
     - chave da tabela não nula e única.
  2. **Regras específicas** da tabela, quando houver (ex.: `quantity = 0` → rejeitado, só na venda).
  3. **Cada tabela é declarada num arquivo de configuração**: de qual tabela da bronze vem, colunas e tipos, chave, regras específicas e contexto (`sales`, `customer`, …). O código lê a declaração e aplica as regras globais + as específicas.
- **Adicionar uma tabela nova = 3 passos:**
  1. declarar a tabela na configuração;
  2. escrever a consulta que monta a tabela, se ela for do `context` (junções e modelagem);
  3. rodar a silver e conferir com o `espiar.py`. Os testes globais rodam sozinhos.
- **Regra de ouro:** acrescentar sem quebrar. Preferir tabela ou coluna nova a mudar o significado de uma existente.
- **Paralelo de mercado:** é o mesmo modelo do dbt (cada tabela é um "model", e os testes ficam declarados num arquivo ao lado) e das *expectations* do Databricks.

### Achados do gabarito (projeto de RAG, `relatorios/qualidade.md`, base ddb4d8032cc2)
- 2.595.732 linhas brutas = 2.548.662 limpas + 47.070 em "ajustes". Vendas: US$ 8.057.463,08 bruto = 7.376.322,37 limpo + 681.140,71 ajustes. Reconciliação semanal: 102 semanas, diferença máxima US$ 0,00.
- **Zero** nulos nas chaves e valores, **zero** duplicatas, **zero** produtos órfãos, `product_id` único (92.353 produtos).
- `quantity <= 0`: só zeros (14.466 linhas, US$ 19,18). Sem devoluções.
- Itens grátis (`sales_value = 0` com `quantity > 0`): 3.994 linhas, **mantidas** → a regra é `sales_value >= 0`, não `> 0`.
- `retail_disc` positivo: 2 linhas (estorno), **mantidas**.
- "Não mercadoria": departamentos KIOSK-GAS, MISC SALES TRAN, MISC. TRANS., COUP/STR & MFG e commodity COUPON/MISC ITEMS → 32.805 linhas, US$ 681.121,53 (pseudo-itens chegam a 89 mil unidades).
- Ruído de ponto flutuante: 29 `sales_value` e 34 `retail_disc` com mais de 4 casas (ex.: 5,55E-17); valores lidos com **4 casas decimais**.
- Cobertura: 2.500 households (1.699 sem demografia = 68%; **801 com**), 582 lojas, 102 semanas (semana 1 com 5 dias e 102 com 6 dias), `day` 1–711.
- Do `CLAUDE.md` do RAG ("Decisões registradas"):
  - dinheiro lido como `DECIMAL(18,4)`: em 2 casas a soma divergia US$ 0,10 do CSV (confirma A2; usar o mesmo tipo);
  - **data = 2016-01-01 + (`day` − 1)**;
  - **as semanas (`week_no`) começam no `day` 6, 13, 20…** e não coincidem com `ceil(day/7)`: a `dim_date` deve usar o `week_no` do arquivo, nunca calcular a semana a partir do dia;
  - `TRANS_TIME` vem como texto.

**Ajustes a partir do gabarito (A1, A2 e A3 confirmados pelo Caio em 28/10/2026):**
- **A1. "Não mercadoria" não é dado sujo:** são vendas reais de outro tipo (combustível, cupons). Na silver elas **ficam**, com uma coluna `is_merchandise` (verdadeiro/falso). Quem exclui é a **gold**, nas métricas que pedem isso (ticket, itens por cesta). Motivo: a silver guarda a verdade, e a regra de negócio é da gold. Efeito colateral: se fossem rejeitadas, os 1,8% de rejeição (47.070 linhas) passariam do limite de 1% e o pipeline pararia.
- **A2. Dinheiro com 4 casas, não 2 (corrige P5):** `decimal(12,4)` → **`decimal(18,4)`**, o mesmo tipo do RAG (ajuste de 28/10/2026, S9). Arredondar para centavos na silver faria os totais semanais se afastarem do gabarito. O arredondamento para exibição acontece só no painel.
- **A3. Regras com número:** `quantity = 0` → rejeitado (14.466 linhas, 0,56%, abaixo do limite); `sales_value >= 0`; descontos `<= 0` com os 2 estornos positivos **mantidos e marcados**, não rejeitados.

**O que o gabarito NÃO cobre (perfil ainda necessário):**
- tabelas de marketing (`campaign_desc`, `campaign_table`, `coupon`, `coupon_redempt`): datas, formato do `coupon_upc`, resgates de cupons que não existem;
- grão da cesta: cada `basket_id` tem um cliente, uma loja e um dia só?
- valores de texto como "Unknown" na demografia;
- conferir a lista de departamentos "não mercadoria" (há outros parecidos que ficaram de fora?);
- formato do `trans_time`.

### S9. Regras da silver a partir do perfil da bronze (28/10/2026)
> Origem: `notebooks/perfil_bronze.ipynb` (números da bronze, carga de 28/10/2026). Propostas no perfil e **aprovadas pelo Caio para a fase 2**; a validação da fase 2 confirma os números.

**O que o perfil confirmou (vira teste automático, não regra de limpeza):** todo texto converte para número (0 inválidos); cada `basket_id` tem 1 cliente, 1 loja e 1 dia (0 problemas); `trans_time` entre 0000 e 2359, sempre 4 caracteres; `product_id` único no cadastro; 0 vendas sem cadastro; 0 duplicatas; 0 valores e quantidades negativos; `coupon_disc` e `coupon_match_disc` nunca positivos.

| # | Regra | Linhas (bronze) | Ação |
|---|---|---|---|
| S9.1 | `quantity = 0` | 14.466 (US$ 19,28) | **rejeitar**, motivo `quantity_zero`. 7.839 delas são dos 15 produtos sem departamento. 201 delas são não mercadoria (US$ 0,10) |
| S9.2 | Não mercadoria: departamentos KIOSK-GAS, MISC SALES TRAN, MISC. TRANS., COUP/STR & MFG **ou** commodity COUPON/MISC ITEMS | 32.805 (US$ 681.121,53) | **manter**, `is_merchandise = false` (A1). Explica as quantidades de até ~90 mil |
| S9.3 | Item grátis (`sales_value = 0` e `quantity > 0`) | 4.451 (3.994 em mercadoria) | **manter**, `is_free_item = true` |
| S9.4 | `retail_disc > 0` (estorno) | 10 na bronze, todas de mercadoria; 8 têm `quantity = 0` e saem pela S9.1 → **2 na `fact_sales`** *(corrigido em 29/10/2026; antes dizia "10 (2 em mercadoria)")* | **manter**, `is_refund_discount = true` |
| S9.5 | Conversão de tipo falha, chave nula, faixa inválida (`day` 1–711, `week_no` 1–102, `trans_time` válido), `sales_value < 0`, `coupon_disc > 0`, `coupon_match_disc > 0` | 0 | **rejeitar** com o motivo; existem para pegar cargas futuras |
| S9.6 | `trans_time` | 0 inválidos | vira `trans_hour` e `trans_minute` (inteiros, como na P5) |
| S9.7 | Texto vazio no cadastro de produto | 15 sem departamento/commodity · 30.607 sem tamanho | `TRIM` e vazio → nulo na `clean`; na `dim_product`, departamento e commodity nulos viram `'UNKNOWN'` |
| S9.8 | Demografia: faixas de idade e renda | 6 e 12 faixas | colunas de ordem `age_band_order` e `income_band_order` para gráficos ordenados |
| S9.9 | Demografia: "sem informação" (`Unknown`, `None/Unknown`, `U`) | 233 · 73 · 558 · 344 | **mantidos como vieram** (são respostas de quem está na pesquisa). `None/Unknown` não dá para separar. `A`/`B` do estado civil **não são traduzidos** até confirmar o significado na documentação |
| S9.10 | Clientes sem demografia | 1.699 de 2.500 | segue a **P3**: colunas nulas + `has_demographics = false` (a proposta do perfil de preencher `'Unknown'` foi descartada para não confundir "fora da pesquisa" com "respondeu Unknown") |
| S9.11 | Duplicatas | 0 | sem deduplicação; teste automático |

**Ordem de rejeição:** cada linha rejeitada leva **um** motivo, o da primeira regra que falhar, na ordem da configuração. Assim, bronze = silver + rejeitados fecha sem contar linha duas vezes.

**Conta que a silver tem que fechar (gabarito):**
- `transaction_data`: 2.595.732 = **2.581.266** (`fact_sales`) + **14.466** rejeitadas (0,56%).
- Mercadoria na `fact_sales`: **2.548.662** linhas, US$ **7.376.322,37** (= números "limpos" do RAG).
- Não mercadoria na `fact_sales`: **32.604** linhas, US$ **681.121,43**.
- Total na `fact_sales`: US$ **8.057.443,80** (= 8.057.463,08 da bronze − 19,28 das rejeitadas).

### Decisões tomadas na construção da fase 2 (28/10/2026, sem supervisão; a opção mais conservadora em cada dúvida)
> Tomadas pelo Claude durante a construção noturna, seguindo a spec (`docs/spec_fase2_silver.md`). Revisar.

- **S10. Chave repetida numa tabela de dimensão da `clean`:** **todas** as linhas com a chave repetida vão para `_rejected` com o motivo `duplicate_key`. Nenhuma é escolhida no lugar das outras. Ordem global dos motivos: `invalid_number` → `null_key` → regras específicas do config (em ordem) → `duplicate_key`. Hoje: 0 casos.
- **S11. Nulos nas regras e marcações:** uma condição de rejeição que dá nulo **não rejeita** (só rejeita o que comprovadamente falha). Uma marcação que dá nulo **fica nula**, não vira `false`. Por isso `week_no` ou `trans_time` nulos passariam, porque não estão na lista de chaves obrigatórias da spec. Hoje: 0 casos.
- **S12. Membro desconhecido (-1):** na `dim_product`, departamento e commodity `'UNKNOWN'` e `is_merchandise` **nulo** (não se sabe o que é; a venda órfã não entra como mercadoria nem como não mercadoria). Na `dim_household`, `has_demographics = false`. Na `dim_date`, todas as colunas nulas. As dimensões não levam `_data_carga` nem `_processado_em`, porque a spec lista essas colunas só na `fact_sales`.
- **S13. Falha na silver:**
  - Se qualquer tabela da `clean` falhar (incluindo rejeição acima de 1%), a `context` não é montada e não ganha linha no controle. O comando termina com 1.
  - Na `context`, a execução para na primeira tabela que falhar, porque as seguintes dependem dela.
  - Uma dimensão só é gravada depois de conferir que a chave não tem nulos nem repetições. A `dim_date` só é gravada se nenhum `day` tiver mais de um `week_no` (pré-condição declarada no config).
  - Nos dois casos, a versão anterior da `context` continua no lake até uma execução com sucesso. O controle mostra o erro.
- **S14. Parâmetros como variáveis SQL:** faixas, data-base, lista de não mercadoria e ordem das faixas vão do config para o DuckDB com `SET VARIABLE` e são lidos com `getvariable(...)` nas regras e nas consultas da `context` (`sql/silver/*.sql`). O config também declara as pré-condições e as contagens de órfãos.
- **S15. Leitura das tabelas Delta como views:** `src.comum.registrar_delta` faz o mesmo que `ler_delta` (lê pelo `_delta_log`, F3), mas registra o dataset na conexão. Assim a view continua válida entre funções. A `fact_sales` lê as dimensões já gravadas em Delta, não a consulta em memória.
- **S16. Gravação da silver com `schema_mode="overwrite"`:** a silver é reconstruída por inteiro (P8). Uma mudança de colunas no config gera uma versão nova com o esquema novo, em vez de erro.
- **S17. `trans_time`:** convertido para `INTEGER`, depois `trans_hour = trans_time // 100` e `trans_minute = trans_time % 100`. É fora de faixa se for negativo, se a hora passar de 23 ou se o minuto passar de 59.
- **S18. `dim_date` a partir dos dias com venda:** os 711 dias vêm da `fact_sales` (o `week_no` só existe no arquivo e não pode ser calculado). Um dia sem nenhuma venda não apareceria. Hoje são os 711.
- **S19. Barra de progresso do DuckDB desligada em toda conexão** (`src.comum.conectar_duckdb`), não só no notebook.
- **Achado (não é regra nova): `is_refund_discount`** dá **2** na `fact_sales`, e não os "2 / 10" esperados. As 10 linhas da bronze com `retail_disc > 0` são todas de mercadoria, e 8 delas têm `quantity = 0`: são rejeitadas (S9.1) antes de virar venda. O "10 (2 em mercadoria)" da S9.4 contava antes da regra da quantidade zero. A regra não foi mudada. **Resolvido pelo Caio em 29/10/2026:** esperado corrigido para "2 / 2" na S9.4 e no notebook. A conciliação 2 + 8 = 10 continua no notebook.
- **Limitação conhecida (decidido pelo Caio em 29/10/2026): commodity `COUPON` conta como mercadoria.** São 3 produtos (AUTOMOTIVE, MEAT-WHSE, ELECT &PLUMBING), 68 vendas, US$ 459,66, fora da lista de não mercadoria da S9.2. Ficam como mercadoria **para bater com o gabarito do RAG** (US$ 7.376.322,37). Efeito: a mercadoria pode estar superestimada em até US$ 459,66 (0,006%). Se um dia entrarem na lista, a mercadoria passa a US$ 7.375.862,71 e a diferença com o RAG tem de ser registrada.

### Princípio de simplicidade (decidido em 28/10/2026)
- Aplicar o que é **padrão de mercado** e simplificar o resto. Ficou fora, de propósito: hash de arquivo, ferramentas de catálogo e linhagem, banco separado de auditoria e metadados em excesso por linha.
- **Reprodutível:** a silver é reconstruída do zero a partir da bronze com um comando só.

## Gold
> Origem: `docs/levantamento_gold.md` (29/10/2026). As respostas do Caio às 11 perguntas do levantamento viraram as decisões G1–G11, todas de 29/10/2026. O que construir está em `docs/spec_fase3_gold.md`.

### G1. "Base inteira" = semanas 1–101
- **Decisão:** o período `base` vai da semana 1 à 101, a última semana completa. É a mesma janela do painel publicado.
- **Diferença registrada (regra 3 do `CLAUDE.md`):** o relatório de qualidade do RAG calcula sobre as **semanas 1–102**. Por isso o ticket médio dele é **US$ 29,39**: faturamento US$ 7.376.322,37 ÷ 250.975 cestas = 29,3907. A gold dá **29,38**: US$ 7.310.849,82 ÷ 248.827 = 29,3813. Os dois números estão certos para as suas janelas. **O 29,39 fica como número do relatório do RAG**, e só ele. Na gold não existe métrica sobre as 102 semanas.

### G2. Faturamento ao longo do tempo (Visão Geral)
- **(a) O grão acompanha o período:**
  - **diário** em 4 s (semanas 98–101, 28 dias);
  - **semanal** em 13 s, 26 s e base inteira.
- **Ano anterior:**
  - no diário, é o **mesmo dia − 364** (`day − 364`), que cai no mesmo dia da semana;
  - no semanal, continua sendo a semana − 52.
- **(b) Lojas:**
  - em 4 s, 13 s e 26 s, o atual e o ano anterior usam as **lojas comparáveis do próprio período** (123, 160 e 214), como nos KPIs;
  - isso substitui a regra do painel publicado, que usava as comparáveis de 26 s em todas as semanas.
- **(c) Base inteira:** não tem ano anterior. A linha mostra o faturamento de **todas as lojas** (sem ano anterior não existe loja comparável), e a coluna do ano anterior fica nula.

### G3. O gráfico semanal de Categorias acompanha a Visão Geral
- Ele usa a mesma tabela da gold e o mesmo grão: diário em 4 s, semanal no resto, com o ano anterior e as lojas comparáveis do período.
- As 52 semanas com sombreado deixam de existir nas duas abas.

### G4. Dinheiro em risco: uma definição só
- **Definição:** é o **faturamento de 26 semanas** (76–101), por departamento, que veio de clientes com **probabilidade de pausa ≥ limiar** do modelo (0,17). A probabilidade vem da foto final do modelo (T = 101). Soma todas as lojas e não pondera pela probabilidade.
- **Fórmulas descartadas** (não entram na gold):
  - **RAG, `churn.risco_por_segmento.valor_em_risco_usd`:** `Σ prob × (gasto de 26 s ÷ 26) × 8`, o gasto esperado que se perde em 8 semanas;
  - **painel publicado, lista de ação (`faturamento_em_risco`):** `prob × faturamento de 26 s` por cliente. Ela sai junto com a aba Clientes & Lojas.

### G5. Escopo dos modelos na gold
- **Entram:**
  - segmentação RFM;
  - CLV com backtest;
  - risco de pausa;
  - teste de desconto;
  - a **curva ROC**;
  - os **textos "e daí?"** que a Metodologia mostra.
- **A cópia do `churn` muda em um ponto:** ela passa a devolver também a **probabilidade por cliente** na foto final e as **notas do conjunto de teste** (modelo e regra simples). É isso que alimenta o dinheiro em risco (G4) e a curva ROC. Assim acaba a reprodução do treino por fora que o painel publicado fazia (`rag_modelos._reproduzir`). O treino, as fotos, o limiar e a regra simples não mudam.
- **A curva ROC** é escrita aqui com `sklearn.metrics.roc_curve(drop_intermediate=True)`, sobre as notas do teste. Não é copiada do painel.

### G6. Igualdade com o RAG e versões travadas
- **Versões:** o venv do lakehouse instala as **mesmas versões do RAG** destas 5 bibliotecas:
  - numpy 2.5.3 (hoje 2.5.4);
  - pandas 3.0.6 (hoje 3.1.0);
  - scikit-learn 1.9.1;
  - scipy 1.18.1;
  - statsmodels 0.15.0.
  O RAG roda no mesmo Python 3.14.7.
- **Exige-se igualdade, não tolerância.** Os números dos modelos e dos cubos têm de ser iguais aos do RAG e do painel publicado, na precisão em que foram publicados. Uma diferença só é aceita com explicação registrada aqui.

### G7. Segmento fixo
- O segmento de cada cliente é o RFM da janela de **26 semanas (76–101)**, e vale para **todo o histórico e todos os períodos**.
- Quem não comprou nas 26 semanas fica em **"Sem segmento"**. É um grupo nos cubos, não um chip do filtro.
- O filtro combina os 4 segmentos em **15 subconjuntos**. Nenhum chip ligado significa todos os clientes, com "Sem segmento" incluído.

### G8. Formato da gold e entrega ao painel
- **Gold em Delta no grão dos cubos que o painel usa:**
  - uma tabela por cubo (período × grupo ou subconjunto × departamento etc.), com as métricas já calculadas;
  - as tabelas que vêm dos modelos.
- **Etapa de exportação separada:** lê a gold e grava os **JSONs com os contratos atuais** (`contracts/*.schema.json`, formato compacto 2.0). O painel v4 continua lendo JSON.
- **Exceções:** os cubos que mudaram de grão por decisão do Caio (G2/G3) e os arquivos que saem com a aba Clientes & Lojas. Detalhes na spec.

### G9. Emenda à R1: `layout.py` do painel pode ser copiado
- A R1 só autorizava reaproveitar código do **RAG**. **Emenda (Caio, 29/10/2026):** o `scripts/layout.py` do painel publicado também pode ser copiado e adaptado. Ele calcula as posições x/y da rede de cestas, com MDS e semente fixa.
- O resto do código do painel continua fora: ele serve **só como fonte das regras** (lido, não copiado).

### G10. Métricas com um departamento: mantém as do painel
- Quando um único departamento está selecionado, valem as definições do painel publicado:
  - cestas = **cestas que têm o departamento**;
  - ticket = faturamento do departamento ÷ essas cestas;
  - itens por cesta = itens do departamento ÷ essas cestas;
  - clientes ativos = **compraram o departamento** nas 8 semanas finais.
- Com 2 ou mais departamentos, esses cards não têm número ("selecione um departamento"). Faturamento e % de desconto somam e aceitam vários departamentos.

### G11. Semana completa na `dim_date` da silver
- A `dim_date` ganha **`days_in_week`** (quantos dias da semana existem na base) e **`is_complete_week`** (`days_in_week = 7`).
- Hoje a semana 1 tem 5 dias, a 102 tem 6 e as demais têm 7.
- A gold encontra o fim dos dados (semana 101) por essa coluna, não por um número fixo.
- É uma mudança pequena na silver, feita dentro da fase 3, com teste e verificação no notebook.

### G12. Três áreas na gold: `features/`, `models/` e `metrics/` (decidido pelo Caio em 29/10/2026, durante a parada 3a)
- **Decisão:** a gold tem três áreas:
  - **`gold/features/`:** as variáveis que entram nos modelos;
  - **`gold/models/`:** os resultados dos modelos;
  - **`gold/metrics/`:** as métricas do painel (3b).
- **Na 3a, cada modelo continua calculando as variáveis do jeito do RAG,** sem mudar método nem ordem. Ele grava em `gold/features/` exatamente as variáveis que usou:
  - **`customer_rfm_features`:** cliente × janela de 26 s (76–101). É a entrada do K-Means: recência, frequência e valor, nos valores originais (G21). Também leva ticket, desconto e demografia, que vêm junto da base do RFM;
  - **`churn_features`:** cliente × foto, com as 5 variáveis e o rótulo, nas fotos de treino, validação, teste e na foto final. A foto final não tem rótulo, porque o rótulo dela é o futuro;
  - **`clv_features`:** gasto por cliente por janela usada pelo método (atual, calibração, as 52 e as 26 semanas seguintes à calibração, e os análogos).
- **Por quê:** fica visível e auditável o que alimentou cada modelo, e as variáveis podem ser conferidas por outro caminho sem rodar o modelo.
- **Como foi feito:**
  - As cópias do `churn` e do `clv` passam a **devolver** as matrizes e os vetores que já calculavam. Nenhuma conta foi refeita fora do modelo.
  - O RFM grava a base que o próprio modelo carrega (`rfm.carregar_base`), sem a transformação de `rfm.matriz` (G21).

### Decisões tomadas na construção da parada 3a (29/10/2026)
> Tomadas pelo Claude seguindo a spec da fase 3. **Aprovadas pelo Caio em 29/10/2026.**

- **G13. `household` da base comum = `dim_household` sem o `-1`.**
  - O RAG contava os households da venda bruta; a silver junta venda e demografia.
  - Hoje são os mesmos **2.500** (os 801 da demografia todos compraram).
  - Se um dia aparecer um cliente só na demografia, ele entra no denominador dos modelos. Isso tem de ser revisto.
- **G14. Base comum como views do DuckDB** (`sql/gold/base/*.sql`, criadas em ordem pelo prefixo numérico):
  - `calendar`, `analysis_window`, `sales_item`, `customer_week`, `customer_metrics` e `household`, equivalentes a `dim_data`, `vw_janela`, `vw_vendas_item`, `vw_cliente_semana`, `vw_metricas_cliente` e `dim_household` do RAG;
  - `customer_week` e `customer_metrics` viram tabela temporária, como as views materializadas do RAG, porque os modelos as leem muitas vezes.
- **G15. O que saiu das cópias do RAG:**
  - o decorador `registrar_chamada`, que gravava em `logs/` do RAG;
  - as ferramentas do chat (`segmentar_clientes`, `prever_churn`, `calcular_clv`, `testar_desconto_entre_segmentos`) e a `coorte_retencao`, que o painel v4 não usa;
  - o cache em memória, trocado por um dicionário da execução (`parametros.MEMO`). O RFM é usado por três modelos e a escolha do K não é refeita a cada chamada; o resultado é o mesmo.
  - Os nomes das colunas da gold estão em inglês (S1). As consultas das cópias renomeiam de volta para os nomes que o resto do código do RAG espera, e assim a lógica fica idêntica.
- **G16. Tabelas a mais em `models/` e uma coluna a menos:**
  - **`rfm_segment_profile`**, que não estava na spec, guarda o perfil por segmento (% de clientes e % do faturamento, os 35% / 71%);
  - a `rfm_k_evaluation` ficou sem a coluna `passed`, porque calculá-la repetiria a regra do K fora do modelo; a regra e os K que passaram ficam no texto `metodo_escolha_k` do `model_summary`.
- **G17. Percentuais nos modelos ficam em 0–100,** como no RAG (é a escala que o código usa, ex.: diferença de 1 pp). A conversão para fração (contratos do painel) acontece na exportação (3c).
- **G18. Ambiente:**
  - além das 5 bibliotecas da G6, o `narwhals` (dependência do statsmodels) foi travado na versão do RAG (2.26.0);
  - o `requirements.txt` foi regerado com `pip freeze`.
- **G19. Detalhes de implementação:**
  - a coluna da janela em `clv_features` se chama `spend_window` (`window` é palavra reservada no SQL);
  - no DuckDB 2.0, depois de um `execute(...).fetchone()` (código do RAG), só `execute` é aceito na mesma conexão (não `sql`). O código da gold usa `execute`.
- **G20. Idempotência conferida pelo conteúdo ordenado:** a leitura de uma tabela Delta não garante a ordem das linhas. Por isso duas execuções são comparadas pelas tabelas ordenadas, nos testes e na validação.

### Revisão da parada 3a (decidido pelo Caio em 29/10/2026)
- **G21. Regra das features: variável = valor original; padronizar é etapa do modelo.**
  - `gold/features/` guarda as variáveis como o modelo as calcula a partir dos dados, **antes** de qualquer transformação que o próprio modelo faça (escala, `log1p` dentro do ajuste, padronização).
  - **`churn_features`:** fica como está: as 5 variáveis, sem padronizar. O `StandardScaler` é ajustado no treino dentro do modelo. Os `log` de `log_purchases_8w` e `log_value_26w` ficam porque fazem parte da **definição** da variável no RAG (calculados na montagem da foto, antes do modelo).
  - **`customer_rfm_features`:** saem `log1p_frequency`, `log1p_monetary` e `z_*`. Ficam recência, frequência e valor originais (+ ticket, desconto, demografia). O `log1p` e a padronização acontecem em `rfm.matriz`, que é etapa do modelo.
  - **Conferido:** os 80 números do RAG continuam iguais depois da troca (`docs/validacao/fase3a_gold.md`, seção "Revisão do Caio"); testes: 96 passed.
- **G22. Limitação conhecida: o segmento do backtest do CLV fica fora de `clv_features`.**
  - `clv_features` traz o gasto de cada cliente na janela do backtest (`calibracao_futuro_backtest`), mas não o segmento que o backtest atribui a cada cliente nela.
  - Incluir exigiria mudar o retorno de `clv.backtest`, uma função copiada do RAG. O resultado do backtest por segmento continua em `models/clv_segment` (`backtest_*`).

### Decisões tomadas na construção da parada 3b (29/10/2026)
> Tomadas pelo Claude seguindo a spec da fase 3. G23–G32 aprovadas pelo Caio em 30/10/2026.

- **G23. Base comum: atributos do produto e dois grãos de cesta.**
  - `sales_item` ganha `department`, `commodity_desc`, `brand` e `manufacturer`, com `LEFT JOIN` na `dim_product`, como a `vw_vendas_item` do RAG (hoje todo produto vendido está na `dim_product`).
  - Entram `basket_department` (cesta × departamento) e `basket` (cesta), as regras de `painel.cesta_departamento` e `painel.cestas` reescritas. Ficam materializadas como tabela temporária, porque quase todo cubo as lê.
  - **Conferido:** os 80 números dos modelos continuam iguais depois da mudança na base.
- **G24. Macros:**
  - além das da spec, entram `jaccard` (semelhança entre nós, para as posições da rede) e `lift_index` (lift do subconjunto ÷ lift de todos);
  - cada macro repete a ordem das operações do SQL do painel publicado (ex.: `lift = n_ab × n ÷ (n_a × n_b)`), para dar o mesmo número em ponto flutuante;
  - a regra "uma definição por métrica" é testada por texto: **nenhum `/`** no código dos SQL de `sql/gold/metrics/`. Toda razão passa por uma macro.
- **G25. Métricas sem arredondar, em fração (0–1).**
  - O arredondamento é da exportação (3c), nas casas do painel publicado.
  - As variações dos KPIs (`*_growth`) ficam prontas na gold. No painel elas eram calculadas no SQL de exportação; aqui a exportação só renomeia e arredonda.
- **G26. Tabelas auxiliares não gravadas** (nome com `_` em `sql/gold/metrics/`):
  - `_item`, `_cut_basket_department`, `_cut_basket`, `_department_group`, `_brand_cut`, `_basket_subcategory` e `_network_pair`;
  - `_network_pair` (todos os pares dos 80 nós, por período × subconjunto) não vira tabela da gold: gravam-se só os 3 recortes que o painel usa (`network_link`, `network_neighbor`, `network_characteristic`).
- **G27. Parâmetros das métricas:**
  - ficam na seção `gold.metricas` do config (períodos, offset diário de 364, segmentos, limites de amostra e da cesta) e entram no SQL como variáveis do DuckDB;
  - o período `base` é o que não tem semanas, e o período do segmento é o que tem as semanas da janela (26);
  - ficam escritos no SQL só rótulos do contrato (`'todos'`, `'day'`/`'week'`) e valores do dado (`'Private'`, `'National'`).
- **G28. Execução em etapas:**
  - `python -m src.gold.build` roda modelos e depois métricas;
  - `--etapa modelos` ou `--etapa metricas` roda uma parte só. A etapa de métricas lê `customer_segment` e `churn_score` já gravados na gold e para com código 1 se eles não existirem.
- **G29. Memória:**
  - as métricas por produto leem uma cópia enxuta dos itens (`_item`), materializada uma vez, e as auxiliares saem da memória depois do último uso;
  - com isso, a etapa caiu de 279 s para cerca de 80 s e o pico de 1.161 MB para cerca de 1.000 MB;
  - **ponto de atenção:** o pico do build completo (1.016–1.032 MB) passa o da silver (~810 MB). O DuckDB respeita o limite de 1 GB do config; o resto é o Python.
- **G30. Atributos de departamento definidos uma vez:**
  - `department_segment` calcula os 6 atributos por período × subconjunto × departamento;
  - `department_profile` (a ficha) lê dela os de `todos` e acrescenta o percentil;
  - `department_risk` é a única conta do dinheiro em risco (G4).
- **G31. Ordem das linhas fica para a exportação.** As tabelas não guardam a ordem do contrato (grupos, subconjuntos, departamentos pelo faturamento do período). A 3c ordena; a 3b conferiu o conteúdo pela chave, não a ordem.
- **G32. `layout.py` copiado sem mudança** para `src/gold/layout.py`, só com o cabeçalho de origem (G9). O texto abaixo do cabeçalho é idêntico ao do painel (conferido).

### Ajuste da revisão da parada 3b (30/10/2026)
- **G33. `python -m src.gold.build` roda cada etapa num processo próprio** (pedido do Caio na revisão da 3b; complementa G28 e G29).
  - **Por quê:** a memória que o Python e o DuckDB pegam na etapa de modelos não volta inteira ao sistema enquanto o processo vive. Com um processo por etapa, a memória fica zerada entre elas.
  - **Como:** sem `--etapa` (ou com `--etapa tudo`), o comando abre `python -m src.gold.build --etapa modelos` e, se der certo, `--etapa metricas`, em sequência. Uma etapa com erro interrompe as seguintes, e o código de saída é 1. `--etapa modelos` / `--etapa metricas` continuam rodando uma parte só, no mesmo processo. `executar(cfg)` em Python (testes, notebook) segue rodando tudo num processo só.
  - **Processo que orquestra leve:** a linha de comando fica no começo de `build.py`, antes dos imports pesados, e esse processo nunca carrega pandas, DuckDB nem os modelos. Os modelos (scikit-learn e cia.) são importados só dentro das funções da etapa de modelos, então a etapa de métricas também não os carrega.
  - **Medido nos dados reais** (pico de cada processo, amostrado a cada 0,1 s):

    | | Antes (um processo) | Agora |
    |---|---:|---:|
    | Processo que orquestra | – | 16 MB |
    | Etapa de modelos | – | 633 MB |
    | Etapa de métricas | – | 870 MB |
    | **Pico total** | **1.016–1.032 MB** | **885 MB** |
    | Tempo | 67–82 s | 73 s |

    A primeira tentativa, com os imports no topo, deu pico total de 1.120 MB (orquestrador com 173 MB + métricas com 950 MB): pior que antes. Daí os dois ajustes de imports.
  - **Resultado igual:** as 33 tabelas da gold ficaram iguais à versão anterior, do processo único. Também conferidos: 39 de 39 arquivos do painel publicado (55.606 linhas), 20 de 20 gabaritos fixos e 80 de 80 números do RAG. Nos testes, a gold sintética é construída uma vez num processo só e outra pela linha de comando; o teste de idempotência compara as duas.
  - **Ponto de atenção que fica:** a etapa de métricas sozinha ainda chega a 870 MB, acima dos ~810 MB da silver.

### Decisões tomadas na construção da parada 3c (30/10/2026)
> Tomadas pelo Claude seguindo a spec da fase 3 (com os pontos de revisão 1, 2, 3 e 5 da spec aplicados como propostos, "plano aprovado"). Aprovadas pelo Caio em 30/10/2026.

- **G34. Exportação: um SQL por arquivo em `sql/gold/export/`.**
  - Cada SQL só renomeia as colunas, arredonda nas casas do painel publicado e ordena como o contrato (G31). Nenhuma métrica é calculada.
  - **Ordem:** onde o painel ordenava pelo valor arredondado (o apelido da coluna exportada), ordena pelo arredondado: `departamentos`, `marcas`, o lift de `cesta_subcategorias` e de `rede_vizinhos`. Onde ordenava pelo valor cheio, ordena pelo cheio: `departamentos_ficha`. O "faturamento do departamento no período" que ordena `subcategorias` e `cesta_subcategorias` vem de `department_profile.revenue`.
  - **Metodologia (`lab_*`):** sai dos modelos em Python, com as mesmas expressões do exportador do painel (`round` do Python, ÷ 100 de G17), porque o arredondamento do Python e o do DuckDB podem diferir no último dígito.
  - O corte da regra simples sai inteiro (k, em semanas), como no painel.
  - **Arquivo de um período sem nenhuma linha:** leva as colunas do contrato. O exportador do painel gravava só as colunas de dimensão e o arquivo falharia no contrato. Achado nos dados sintéticos; nos reais nenhum arquivo fica vazio.
- **G35. Diferença explicada: a descrição do modelo em `lab_modelo.json`.**
  - Publicado: "Regressão logística **do RAG**: alerta com risco de 0,17 ou mais…". Exportado: "Regressão logística: alerta com risco de 0,17 ou mais…". O texto vem de `models/churn_classifier` (3a): o modelo agora roda no lakehouse.
  - Está em `gold.conferencia.excecoes` do config. **Decisão do Caio (30/10/2026):** a descrição fica sem "do RAG", e a diferença fica explicada.
- **G36. Manifest 5.0** (ponto 3 da spec):
  - saem `parametros_regioes`, `parametros_migracao` e `minimo_cestas_loja`;
  - `rag_commit` / `rag_sujo` viram `lakehouse_commit` / `lakehouse_sujo`, o commit e o "tem mudança não commitada" deste repositório;
  - **entra `silver_versoes`:** a versão Delta das 4 tabelas da silver que a gold lê;
  - **`base_hash`** = os 12 primeiros caracteres do sha256 de `silver_versoes`. No painel era a versão da base do RAG; aqui muda quando a silver muda.
  - **A aba `clientes` sai** de `bytes_por_aba` e da lista de cargas: os arquivos dela saíram todos do v4.
  - `bytes_abertura` soma os 4 `faturamento_tempo` com os outros arquivos da abertura (446.719 bytes, abaixo de 1,5 MB).
  - **Contas de resumo no manifest:** `corte_medio` (limiar ÷ 2) e as somas do risco por segmento repetem o exportador do painel. São resumo para o painel, não métricas. A cobertura da rede usa a macro `share`.
  - **Proveniência lida da silver:** `periodo_base` (datas mínima e máxima da `dim_date`) e as versões. É a única leitura da silver na exportação.
  - A exportação **recusa** uma gold construída com outra versão da `fact_sales` (comparada com o controle da gold) e pede para rodar o build.
- **G37. `faturamento_tempo_<periodo>.json`** (ponto 1 da spec, como proposto):
  - colunas `inicio`, `grupo`, `departamento`, `faturamento`, `faturamento_ano_anterior`;
  - carga `abertura`, formato compacto com as 3 dimensões;
  - contrato `contracts/faturamento_tempo.schema.json`, gerado do `cubo_faturamento.schema.json` trocando `semana_inicio` por `inicio`;
  - o `cubo_faturamento.json` não é mais exportado.
- **G38. Contratos (ponto 2 da spec):**
  - os 19 contratos dos arquivos que ficam foram copiados para `contracts/` sem mudança (conferido byte a byte);
  - os 2 novos (`faturamento_tempo`, `manifest` 5.0) foram gerados a partir dos do painel por um script, só com as mudanças acima.
- **G39. Pastas da exportação em `paths`, não na seção `gold`:**
  - `paths.export`, `paths.contratos` e `paths.painel_publicado`, porque `paths` é a seção que o `carregar_config` resolve a partir da pasta do config (os testes usam uma pasta temporária);
  - o `config.example.yaml` leva o caminho relativo `../retail-bi-dashboard/site/data`;
  - versão do contrato e limite de bytes ficam em `gold.exportacao`; gabaritos e exceções, em `gold.conferencia`;
  - no `.gitignore` entrou `/export/` (com a barra: `export/` também esconderia `sql/gold/export/`).
- **G40. Conferência (`reconcile`):**
  - **Caminho 1:** linha a linha e **na ordem**, com o grão e as colunas. A coluna "pela chave" mostra, para diagnóstico, quantas linhas batem independentemente da posição: separa erro de valor de erro de ordem.
  - **Igualdade exata:** 7 = 7.0, mas um booleano nunca é igual a um número.
  - **`faturamento_tempo_26s`** também é comparado com as semanas do `cubo_faturamento.json` publicado que ele cobre (76–101).
  - **Manifest:** comparam-se só as seções de conteúdo (períodos, modelo, cesta, rede, Metodologia).
  - **Caminho 2:** refaz os períodos (o fim é a última semana com 7 dias no calendário da silver). Confere os 20 gabaritos (os 15 da spec mais faturamento comparável e do ano anterior de 26 s, variação e dinheiro em risco, já usados na 3b) e os 4 `faturamento_tempo` no grão inteiro (ponto × grupo × departamento).
  - Uma diferença só passa se estiver em `gold.conferencia.excecoes` (arquivo + coluna + motivo).
- **G41. Silver sintética dos testes:** o desconto sorteado passa a ser multiplicado por um fator fixo do perfil. O sorteio é o mesmo, e recência, frequência e valor não mudam.
  - **Por quê:** com desconto igual entre segmentos, o teste de Kruskal-Wallis não dá diferença, o RAG não roda o pós-teste, e `lab_desconto.json` (que exige o p ajustado) e o eta² do manifest (que tem de ser ≥ 0) falham no contrato.
  - Com o fator, a exportação sintética passa no contrato inteiro.

### Revisão da parada 3c e decisões do Caio (30/10/2026)
- **G34–G41 aprovadas.** Em G35, o Caio decidiu que a descrição do modelo fica **sem "do RAG"**. A diferença com o painel publicado continua registrada como explicada: no relatório e em `gold.conferencia.excecoes`.
- **G42. Comando único do pipeline: `python -m src.pipeline`** (pedido do Caio na revisão da 3c).
  - **O que faz:** roda, em ordem, bronze (`src.bronze.ingest`), silver (`src.silver.build`), gold (`src.gold.build`), exportação (`src.gold.export`) e conferência (`src.gold.reconcile`). Cada etapa roda num processo Python novo, como na G33.
  - **Erro:** para na primeira etapa com erro e sai com código 1; as etapas seguintes aparecem como "não rodou".
  - **Resumo:** no fim, mostra o tempo e o status de cada etapa. `--config` passa para todas.
  - **Leveza:** o processo que orquestra não importa nada pesado.
  - **Primeira execução completa, nos dados reais** (com o medidor de memória amostrando a cada 0,1 s, o que deixa o build da gold mais lento):

    | Etapa | Tempo | Pico de memória do processo |
    |---|---:|---:|
    | bronze | 55 s | 372 MB |
    | silver | 62 s | 821 MB |
    | gold build | 166 s (73 s sem o medidor) | modelos 721 MB; métricas 872 MB |
    | gold export | 29 s | 177 MB |
    | gold reconcile | 14 s | 792 MB |
    | **total** | **326 s, código 0** | **maior soma simultânea: 901 MB** |

    A bronze grava a carga do dia (partição `_data_carga` de hoje), e a silver e a gold são reconstruídas a partir dela. A conferência saiu igual à da 3c: 42 de 43 arquivos idênticos, 0 diferenças sem explicação e 20 de 20 gabaritos.
- **G43. O painel v4 é um consumidor do lakehouse** (decisão do Caio, 30/10/2026). Atualiza R1 e a pendência "como o painel passa a ler da nova arquitetura".
  - **Onde fica:** o painel v4 continua no repositório `retail-bi-dashboard` e lê os JSONs de `export/painel_v4/` deste projeto. Eles são a interface, com os contratos de `contracts/`, versão 5.0.
  - **Somente leitura:** este projeto continua sem alterar o `retail-bi-dashboard` (regra 5 do `CLAUDE.md`).
  - **Como é construído:** o v4 é construído numa sessão aberta lá, que lê daqui. O que o painel precisa mudar (o `faturamento_tempo_<p>.json` no lugar do `cubo_faturamento.json`, o manifest 5.0 e a aba Clientes & Lojas fora) é trabalho daquela sessão.
