# Decisões de arquitetura — retail-lakehouse

> Registro das decisões do Caio, camada por camada, com o porquê. Formato de **ADR** (Architecture Decision Record): cada decisão diz o que foi decidido, o motivo e o que fica em aberto. Mudou uma decisão? Não apague: marque como "substituída" e escreva a nova.

## To-do e pendências (atualizado em 28/10/2026)

**A fazer (na ordem):**
- [ ] Terminar o vídeo de arquitetura e encaixar aqui o que fizer sentido
- [ ] Perfil da bronze (consultas sobre os CSVs do RAG em `data/raw/`):
  - [ ] grão da cesta: cada `basket_id` com um cliente, uma loja e um dia só?
  - [ ] formato do `trans_time` (0 a 2359? minuto acima de 59?)
  - [ ] departamentos com faturamento: a lista de "não mercadoria" está completa?
  - [ ] valores "Unknown" e categorias de texto na demografia
  - [ ] ~~marketing~~ — fora da silver por enquanto (S7); perfil só quando for modelar
- [ ] Anotar os resultados em `docs/perfil_bronze.md` (número + conclusão)
- [ ] Fechar as regras específicas da silver com base no perfil
- [x] Replanejar o painel antes da gold (Caio, 28/10/2026) → ver "Painel v4" abaixo
- [ ] Decidir como reaproveitar as análises estatísticas do RAG (segmento, CLV, risco de pausa, teste de desconto) como tabelas gold geradas a partir da silver
- [ ] Desenhar a gold (quem consome e o que cada consumidor precisa: painel, chat, ML)
- [ ] Configuração do Claude (`CLAUDE.md`, skills, MCP, permissões): ver `claude/todo_configuracao_claude.md`
- [ ] Escrever a spec e o prompt da construção (bronze + `espiar.py` primeiro)

**Decisões pendentes:**
- Regras específicas da silver para os casos que o perfil revelar (cesta com mais de um cliente/loja/dia, horários inválidos, "Unknown", resgates órfãos)
- Toda a camada gold
- Como o painel e o chat passam a ler da nova arquitetura (ajuste dos nomes para inglês)

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
| | `fact_sales` com `is_merchandise = false` | 32.805 linhas, US$ 681.121,53 |
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
- **A2. Dinheiro com 4 casas, não 2 (corrige P5):** `decimal(12,4)`. Arredondar para centavos na silver faria os totais semanais se afastarem do gabarito. O arredondamento para exibição acontece só no painel.
- **A3. Regras com número:** `quantity = 0` → rejeitado (14.466 linhas, 0,56%, abaixo do limite); `sales_value >= 0`; descontos `<= 0` com os 2 estornos positivos **mantidos e marcados**, não rejeitados.

**O que o gabarito NÃO cobre (perfil ainda necessário):**
- tabelas de marketing (`campaign_desc`, `campaign_table`, `coupon`, `coupon_redempt`): datas, formato do `coupon_upc`, resgates de cupons que não existem;
- grão da cesta: cada `basket_id` tem um cliente, uma loja e um dia só?
- valores de texto como "Unknown" na demografia;
- conferir a lista de departamentos "não mercadoria" (há outros parecidos que ficaram de fora?);
- formato do `trans_time`.

### Princípio de simplicidade (decidido em 28/10/2026)
- Aplicar o que é **padrão de mercado** e simplificar o resto. Ficou fora, de propósito: hash de arquivo, ferramentas de catálogo e linhagem, banco separado de auditoria e metadados em excesso por linha.
- **Reprodutível:** a silver é reconstruída do zero a partir da bronze com um comando só.

## Gold
*(próxima etapa)*
