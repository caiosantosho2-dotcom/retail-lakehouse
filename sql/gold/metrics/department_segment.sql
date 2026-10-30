-- department_segment: os 6 atributos do radar por período × subconjunto × departamento (ou 'todos'), com faturamento no
-- período, e o índice de cada um contra todos os clientes (100 = igual). Definições:
--   share          = faturamento do departamento ÷ faturamento do subconjunto (todas as lojas);
--   growth         = faturamento nas lojas comparáveis ÷ o mesmo um ano antes − 1 (nulo na base);
--   penetration    = a do RAG: compradores do departamento ÷ clientes com qualquer compra, os dois nas lojas comparáveis
--                    (nula na base);
--   frequency      = cestas com o departamento ÷ compradores do departamento;
--   discount_rate  = desconto ÷ valor bruto do departamento;
--   private_label  = faturamento com brand = 'Private' ÷ faturamento do departamento.
-- O índice do crescimento compara os fatores: (1 + crescimento do subconjunto) ÷ (1 + crescimento de todos) × 100.
-- small_sample: menos de 30 compradores no subconjunto.
WITH x AS (
    SELECT d.period, s.subset, s.subset_mask, d.department,
           sum(d.revenue) AS revenue, sum(d.discount) AS discount, sum(d.gross_value) AS gross_value,
           sum(d.private_revenue) AS private_revenue, sum(d.revenue_comparable) AS revenue_comparable,
           sum(d.revenue_prior_year) AS revenue_prior_year, sum(d.baskets) AS baskets, sum(d.buyers) AS buyers,
           sum(d.buyers_comparable) AS buyers_comparable
    FROM _department_group d JOIN segment_subset s ON s.segment = d.segment
    GROUP BY ALL
),
group_total AS (
    SELECT p.period, g.segment, sum(b.revenue) AS revenue
    FROM dim_period p
    JOIN basket b ON b.week_no BETWEEN p.week_start AND p.week_end
    JOIN customer_group g ON g.household_key = b.household_key
    GROUP BY ALL
),
group_customers AS (
    SELECT period, segment, count(DISTINCT household_key) AS customers_comparable
    FROM _cut_basket WHERE cut = 'comparable'
    GROUP BY ALL
),
tot AS (
    SELECT t.period, s.subset, sum(t.revenue) AS revenue, coalesce(sum(c.customers_comparable), 0) AS customers_comparable
    FROM group_total t
    LEFT JOIN group_customers c ON c.period = t.period AND c.segment = t.segment
    JOIN segment_subset s ON s.segment = t.segment
    GROUP BY ALL
),
v AS (
    SELECT x.period, x.subset, x.subset_mask, x.department, x.revenue, x.buyers, x.baskets,
           share(x.revenue, tot.revenue) AS share,
           growth(x.revenue_comparable, x.revenue_prior_year) AS growth,
           penetration(x.buyers_comparable, tot.customers_comparable) AS penetration,
           frequency(x.baskets, x.buyers) AS frequency,
           discount_rate(x.discount, x.gross_value) AS discount_rate,
           private_label_share(x.private_revenue, x.revenue) AS private_label
    FROM x JOIN tot ON tot.period = x.period AND tot.subset = x.subset
    WHERE x.revenue > 0
)
SELECT v.period, v.subset, v.subset_mask, v.department, v.revenue, v.buyers, v.baskets,
       v.share, index_vs_all(v.share, t.share) AS share_index,
       v.growth, index_vs_all(1 + v.growth, 1 + t.growth) AS growth_index,
       v.penetration, index_vs_all(v.penetration, t.penetration) AS penetration_index,
       v.frequency, index_vs_all(v.frequency, t.frequency) AS frequency_index,
       v.discount_rate, index_vs_all(v.discount_rate, t.discount_rate) AS discount_rate_index,
       v.private_label, index_vs_all(v.private_label, t.private_label) AS private_label_index,
       v.buyers < getvariable('grupo_compradores') AS small_sample
FROM v JOIN v t ON t.period = v.period AND t.subset = 'todos' AND t.department = v.department
