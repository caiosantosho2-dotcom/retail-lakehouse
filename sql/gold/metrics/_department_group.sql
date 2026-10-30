-- (tabela auxiliar, não gravada) Somas de cada período por grupo × departamento, e a linha 'todos' (o total dos
-- departamentos). Grão: período × grupo × departamento (ou 'todos') com venda no período ou no ano anterior.
-- baskets: no departamento, cestas com ele; em 'todos', cestas distintas. buyers_comparable: compradores nas lojas
-- comparáveis (numerador da penetração); na base não há comparáveis.
SELECT period, segment, department,
       coalesce(sum(revenue) FILTER (WHERE cut = 'all'), 0) AS revenue,
       coalesce(sum(discount) FILTER (WHERE cut = 'all'), 0) AS discount,
       coalesce(sum(gross_value) FILTER (WHERE cut = 'all'), 0) AS gross_value,
       coalesce(sum(private_revenue) FILTER (WHERE cut = 'all'), 0) AS private_revenue,
       coalesce(sum(revenue) FILTER (WHERE cut = 'comparable'), 0) AS revenue_comparable,
       coalesce(sum(revenue) FILTER (WHERE cut = 'prior'), 0) AS revenue_prior_year,
       count(*) FILTER (WHERE cut = 'all') AS baskets,
       count(DISTINCT household_key) FILTER (WHERE cut = 'all') AS buyers,
       count(DISTINCT household_key) FILTER (WHERE cut = 'comparable') AS buyers_comparable
FROM _cut_basket_department
GROUP BY ALL
UNION ALL
SELECT period, segment, 'todos',
       coalesce(sum(revenue) FILTER (WHERE cut = 'all'), 0),
       coalesce(sum(discount) FILTER (WHERE cut = 'all'), 0),
       coalesce(sum(gross_value) FILTER (WHERE cut = 'all'), 0),
       coalesce(sum(private_revenue) FILTER (WHERE cut = 'all'), 0),
       coalesce(sum(revenue) FILTER (WHERE cut = 'comparable'), 0),
       coalesce(sum(revenue) FILTER (WHERE cut = 'prior'), 0),
       count(DISTINCT basket_id) FILTER (WHERE cut = 'all'),
       count(DISTINCT household_key) FILTER (WHERE cut = 'all'),
       count(DISTINCT household_key) FILTER (WHERE cut = 'comparable')
FROM _cut_basket_department
GROUP BY period, segment
