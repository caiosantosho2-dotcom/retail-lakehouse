-- (tabela auxiliar, não gravada) Faturamento por período × recorte × grupo × departamento × marca × fabricante.
-- Recortes como em _cut_basket_department; o fabricante só importa no recorte 'all' (concentração de fornecedores).
WITH i AS (
    SELECT i.week_no, i.store_id, i.department, i.brand, i.manufacturer, i.revenue, g.segment
    FROM _item i JOIN customer_group g ON g.household_key = i.household_key
)
SELECT p.period, 'all' AS cut, i.segment, i.department, i.brand, i.manufacturer, sum(i.revenue) AS revenue
FROM i JOIN dim_period p ON i.week_no BETWEEN p.week_start AND p.week_end
GROUP BY ALL
UNION ALL
SELECT p.period, 'comparable', i.segment, i.department, i.brand, NULL, sum(i.revenue)
FROM i JOIN dim_period p ON i.week_no BETWEEN p.week_start AND p.week_end
JOIN period_comparable_store l ON l.period = p.period AND l.store_id = i.store_id
GROUP BY ALL
UNION ALL
SELECT p.period, 'prior', i.segment, i.department, i.brand, NULL, sum(i.revenue)
FROM i JOIN dim_period p ON i.week_no BETWEEN p.prior_week_start AND p.prior_week_end
JOIN period_comparable_store l ON l.period = p.period AND l.store_id = i.store_id
GROUP BY ALL
