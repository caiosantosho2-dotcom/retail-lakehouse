-- Macros do DuckDB: a definição de cada métrica do painel, escrita uma vez (regra 4). Todo SQL de sql/gold/metrics/ usa
-- estas macros e nunca reescreve a conta (há um teste de texto para isso). Divisão por zero dá nulo.
-- Percentuais em fração (0–1), como nos contratos do painel. As expressões seguem a ordem de operações do SQL do painel
-- publicado, para o mesmo número em ponto flutuante.

-- Ticket médio = faturamento ÷ cestas.
CREATE OR REPLACE MACRO avg_ticket(revenue, baskets) AS revenue / NULLIF(baskets, 0);

-- Itens por cesta = quantidade de itens ÷ cestas.
CREATE OR REPLACE MACRO items_per_basket(items, baskets) AS items / NULLIF(baskets, 0);

-- % de desconto = desconto ÷ valor bruto (valor antes do desconto).
CREATE OR REPLACE MACRO discount_rate(discount, gross_value) AS discount / NULLIF(gross_value, 0);

-- Variação = atual ÷ ano anterior − 1 (nas lojas comparáveis, quando há ano anterior).
CREATE OR REPLACE MACRO growth(current_value, prior_value) AS current_value / NULLIF(prior_value, 0) - 1;

-- Participação = parte ÷ total.
CREATE OR REPLACE MACRO share(part, total) AS part / NULLIF(total, 0);

-- Marca própria = faturamento com brand = 'Private' ÷ faturamento.
CREATE OR REPLACE MACRO private_label_share(private_revenue, revenue) AS private_revenue / NULLIF(revenue, 0);

-- Penetração (a do RAG) = clientes que compraram o departamento ÷ clientes com qualquer compra, nas lojas comparáveis.
CREATE OR REPLACE MACRO penetration(buyers, customers) AS buyers / NULLIF(customers, 0);

-- Frequência = cestas com o departamento ÷ clientes que compraram o departamento.
CREATE OR REPLACE MACRO frequency(baskets, buyers) AS baskets / NULLIF(buyers, 0);

-- Análise de cesta: suporte = cestas com A e B ÷ total de cestas; confiança A→B = cestas com A e B ÷ cestas com A;
-- lift = confiança ÷ (cestas com B ÷ total), simétrico; Jaccard = cestas com A e B ÷ cestas com A ou B.
CREATE OR REPLACE MACRO support(baskets_ab, baskets_total) AS baskets_ab::DOUBLE / baskets_total;
CREATE OR REPLACE MACRO confidence(baskets_ab, baskets_a) AS baskets_ab::DOUBLE / baskets_a;
CREATE OR REPLACE MACRO lift(baskets_ab, baskets_a, baskets_b, baskets_total) AS
    baskets_ab::DOUBLE * baskets_total / (baskets_a::DOUBLE * baskets_b);
CREATE OR REPLACE MACRO jaccard(baskets_ab, baskets_a, baskets_b) AS
    baskets_ab::DOUBLE / (baskets_a + baskets_b - baskets_ab);

-- Índice contra todos os clientes = valor do subconjunto ÷ valor de todos × 100 (100 = igual).
CREATE OR REPLACE MACRO index_vs_all(subset_value, all_value) AS 100 * subset_value / NULLIF(all_value, 0);

-- Índice de um par = lift no subconjunto ÷ lift com todos os clientes (1 = igual).
CREATE OR REPLACE MACRO lift_index(subset_lift, all_lift) AS subset_lift / all_lift;

-- Bloco "Quem acionar" (G45). priority_score só ORDENA a fila do CRM: NÃO é o "dinheiro em risco" da G4 (department_risk).
CREATE OR REPLACE MACRO priority_score(probability, revenue_26s) AS probability * revenue_26s;

-- Valor original de uma variável gravada em log1p nas features (G21): log_value_26w -> faturamento de 26 s.
CREATE OR REPLACE MACRO value_from_log1p(log_value) AS exp(log_value) - 1;

-- precision@N = pausas reais entre os acionados ÷ acionados; recall@N = pausas reais entre os acionados ÷ pausas reais da foto.
CREATE OR REPLACE MACRO precision_at_n(hits, acted) AS hits::DOUBLE / NULLIF(acted, 0);
CREATE OR REPLACE MACRO recall_at_n(hits, pauses) AS hits::DOUBLE / NULLIF(pauses, 0);

-- Bloco "Onde agir no mix" (G46). Valor igual ao corte conta como "acima".
CREATE OR REPLACE MACRO quadrant_of(share_value, share_cut, growth_value, growth_cut) AS
    CASE WHEN growth_value >= growth_cut THEN (CASE WHEN share_value >= share_cut THEN 'keep' ELSE 'invest' END)
         ELSE (CASE WHEN share_value >= share_cut THEN 'defend' ELSE 'review' END) END;

-- US$ abaixo (negativo) ou acima do crescimento do recorte = faturamento do ano anterior × (crescimento − corte).
CREATE OR REPLACE MACRO gap_value(revenue_prior_year, growth_value, growth_cut) AS
    revenue_prior_year::DOUBLE * (growth_value - growth_cut);
