-- (view auxiliar, não gravada) Cesta × departamento em cada período e recorte, com o grupo do cliente.
-- cut: 'all' (todas as lojas, semanas do período), 'comparable' (lojas comparáveis do período), 'prior' (as mesmas lojas
-- comparáveis, um ano antes). A base só tem 'all'.
SELECT p.period, 'all' AS cut, g.segment, b.*
FROM dim_period p
JOIN basket_department b ON b.week_no BETWEEN p.week_start AND p.week_end
JOIN customer_group g ON g.household_key = b.household_key
UNION ALL
SELECT p.period, 'comparable', g.segment, b.*
FROM dim_period p
JOIN basket_department b ON b.week_no BETWEEN p.week_start AND p.week_end
JOIN period_comparable_store s ON s.period = p.period AND s.store_id = b.store_id
JOIN customer_group g ON g.household_key = b.household_key
UNION ALL
SELECT p.period, 'prior', g.segment, b.*
FROM dim_period p
JOIN basket_department b ON b.week_no BETWEEN p.prior_week_start AND p.prior_week_end
JOIN period_comparable_store s ON s.period = p.period AND s.store_id = b.store_id
JOIN customer_group g ON g.household_key = b.household_key
