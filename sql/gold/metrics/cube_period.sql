-- cube_period: só o que soma (faturamento, desconto, valor bruto), por período × grupo × departamento com venda no
-- período ou no ano anterior. O painel soma no navegador para qualquer seleção de segmentos e departamentos.
-- Comparável e ano anterior: lojas comparáveis do período; nulos na base.
WITH s AS (
    SELECT period, cut, segment, department,
           sum(revenue) AS revenue, sum(discount) AS discount, sum(gross_value) AS gross_value
    FROM _cut_basket_department
    GROUP BY ALL
),
k AS (SELECT DISTINCT period, segment, department FROM s)
SELECT k.period, k.segment, k.department,
       coalesce(a.revenue, 0) AS revenue, coalesce(a.discount, 0) AS discount, coalesce(a.gross_value, 0) AS gross_value,
       CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(c.revenue, 0) END AS revenue_comparable,
       CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(c.discount, 0) END AS discount_comparable,
       CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(c.gross_value, 0) END AS gross_value_comparable,
       CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(y.revenue, 0) END AS revenue_prior_year,
       CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(y.discount, 0) END AS discount_prior_year,
       CASE WHEN p.prior_week_start IS NOT NULL THEN coalesce(y.gross_value, 0) END AS gross_value_prior_year
FROM k
JOIN dim_period p ON p.period = k.period
LEFT JOIN s a ON a.period = k.period AND a.segment = k.segment AND a.department = k.department AND a.cut = 'all'
LEFT JOIN s c ON c.period = k.period AND c.segment = k.segment AND c.department = k.department AND c.cut = 'comparable'
LEFT JOIN s y ON y.period = k.period AND y.segment = k.segment AND y.department = k.department AND y.cut = 'prior'
