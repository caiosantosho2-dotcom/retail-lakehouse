-- (view auxiliar, não gravada) O mesmo recorte de _cut_basket_department no grão da cesta.
SELECT p.period, 'all' AS cut, g.segment, b.*
FROM dim_period p
JOIN basket b ON b.week_no BETWEEN p.week_start AND p.week_end
JOIN customer_group g ON g.household_key = b.household_key
UNION ALL
SELECT p.period, 'comparable', g.segment, b.*
FROM dim_period p
JOIN basket b ON b.week_no BETWEEN p.week_start AND p.week_end
JOIN period_comparable_store s ON s.period = p.period AND s.store_id = b.store_id
JOIN customer_group g ON g.household_key = b.household_key
UNION ALL
SELECT p.period, 'prior', g.segment, b.*
FROM dim_period p
JOIN basket b ON b.week_no BETWEEN p.prior_week_start AND p.prior_week_end
JOIN period_comparable_store s ON s.period = p.period AND s.store_id = b.store_id
JOIN customer_group g ON g.household_key = b.household_key
