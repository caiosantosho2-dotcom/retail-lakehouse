-- kpi_filtered: os KPIs que não somam (uma cesta tem vários departamentos; um cliente compra em vários), por período ×
-- subconjunto × departamento ('todos' ou um só). Com um departamento valem as definições do painel (G10): cestas = cestas
-- com o departamento; ticket = faturamento do departamento ÷ essas cestas; itens por cesta = itens do departamento ÷
-- essas cestas; clientes ativos = compraram o departamento nas últimas 8 semanas. Sem departamento, clientes ativos é a
-- regra de customer_metrics (a do RAG).
-- Comparável e ano anterior: lojas comparáveis do período. Clientes ativos não dependem de loja nem de período: o mesmo
-- número em todos (todos terminam na última semana completa); comparável = valor; ano anterior = o mesmo estoque um ano
-- antes, sem filtro de loja. small_sample: menos de 100 cestas.
WITH basket_group AS (
    SELECT period, cut, segment, 'todos' AS department, count(*) AS baskets, sum(revenue) AS revenue, sum(items) AS items
    FROM _cut_basket
    GROUP BY ALL
    UNION ALL
    SELECT period, cut, segment, department, count(*), sum(revenue), sum(items)
    FROM _cut_basket_department
    GROUP BY ALL
),
w AS (SELECT week_end_current AS week_end, offset_weeks, active_weeks FROM analysis_window),
active_group AS (
    SELECT CASE m.period WHEN 'current' THEN 'all' ELSE 'prior' END AS cut, g.segment, 'todos' AS department,
           count(*) AS customers
    FROM customer_metrics m JOIN customer_group g ON g.household_key = m.household_key
    WHERE m.is_active
    GROUP BY ALL
    UNION ALL
    SELECT q.cut, g.segment, b.department, count(DISTINCT b.household_key)
    FROM basket_department b
    JOIN (SELECT 'all' AS cut, week_end - active_weeks + 1 AS ws, week_end AS we FROM w
          UNION ALL
          SELECT 'prior', week_end - offset_weeks - active_weeks + 1, week_end - offset_weeks FROM w) q
      ON b.week_no BETWEEN q.ws AND q.we
    JOIN customer_group g ON g.household_key = b.household_key
    GROUP BY ALL
),
c AS (
    SELECT x.period, s.subset, s.subset_mask, x.department,
           sum(x.baskets) FILTER (WHERE x.cut = 'all') AS b_all,
           sum(x.baskets) FILTER (WHERE x.cut = 'comparable') AS b_cmp,
           sum(x.baskets) FILTER (WHERE x.cut = 'prior') AS b_pri,
           sum(x.revenue) FILTER (WHERE x.cut = 'all') AS r_all,
           sum(x.revenue) FILTER (WHERE x.cut = 'comparable') AS r_cmp,
           sum(x.revenue) FILTER (WHERE x.cut = 'prior') AS r_pri,
           sum(x.items) FILTER (WHERE x.cut = 'all') AS i_all,
           sum(x.items) FILTER (WHERE x.cut = 'comparable') AS i_cmp,
           sum(x.items) FILTER (WHERE x.cut = 'prior') AS i_pri
    FROM basket_group x JOIN segment_subset s ON s.segment = x.segment
    GROUP BY ALL
),
a AS (
    SELECT s.subset, s.subset_mask, x.department,
           sum(x.customers) FILTER (WHERE x.cut = 'all') AS act_all,
           sum(x.customers) FILTER (WHERE x.cut = 'prior') AS act_pri
    FROM active_group x JOIN segment_subset s ON s.segment = x.segment
    GROUP BY ALL
),
keys AS (
    SELECT period, subset, subset_mask, department FROM c
    UNION
    SELECT p.period, a.subset, a.subset_mask, a.department FROM dim_period p CROSS JOIN a
),
stores AS (SELECT period, count(*) AS stores FROM period_comparable_store GROUP BY period),
v AS (
    SELECT k.period, k.subset, k.subset_mask, k.department, p.prior_week_start IS NOT NULL AS has_prior_year,
           coalesce(c.b_all, 0)::BIGINT AS baskets,
           (CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(c.b_cmp, 0) END)::BIGINT AS baskets_comparable,
           (CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(c.b_pri, 0) END)::BIGINT AS baskets_prior_year,
           avg_ticket(c.r_all, c.b_all) AS avg_ticket,
           CASE WHEN p.prior_week_start IS NOT NULL THEN avg_ticket(c.r_cmp, c.b_cmp) END AS avg_ticket_comparable,
           CASE WHEN p.prior_week_start IS NOT NULL THEN avg_ticket(c.r_pri, c.b_pri) END AS avg_ticket_prior_year,
           items_per_basket(c.i_all, c.b_all) AS items_per_basket,
           CASE WHEN p.prior_week_start IS NOT NULL THEN items_per_basket(c.i_cmp, c.b_cmp) END AS items_per_basket_comparable,
           CASE WHEN p.prior_week_start IS NOT NULL THEN items_per_basket(c.i_pri, c.b_pri) END AS items_per_basket_prior_year,
           coalesce(a.act_all, 0)::BIGINT AS active_customers,
           (CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(a.act_all, 0) END)::BIGINT AS active_customers_comparable,
           (CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(a.act_pri, 0) END)::BIGINT AS active_customers_prior_year,
           stores.stores AS comparable_stores,
           coalesce(c.b_all, 0) < getvariable('kpi_cestas') AS small_sample
    FROM keys k
    JOIN dim_period p ON p.period = k.period
    LEFT JOIN c ON c.period = k.period AND c.subset = k.subset AND c.department = k.department
    LEFT JOIN a ON a.subset = k.subset AND a.department = k.department
    LEFT JOIN stores ON stores.period = k.period
)
SELECT period, subset, subset_mask, department, has_prior_year,
       baskets, baskets_comparable, baskets_prior_year, growth(baskets_comparable, baskets_prior_year) AS baskets_growth,
       avg_ticket, avg_ticket_comparable, avg_ticket_prior_year,
       growth(avg_ticket_comparable, avg_ticket_prior_year) AS avg_ticket_growth,
       items_per_basket, items_per_basket_comparable, items_per_basket_prior_year,
       growth(items_per_basket_comparable, items_per_basket_prior_year) AS items_per_basket_growth,
       active_customers, active_customers_comparable, active_customers_prior_year,
       growth(active_customers_comparable, active_customers_prior_year) AS active_customers_growth,
       comparable_stores, small_sample
FROM v
