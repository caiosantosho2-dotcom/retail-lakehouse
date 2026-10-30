-- revenue_over_time: faturamento ao longo do tempo (G2/G3), por período × ponto × grupo × departamento com venda no
-- ponto ou no ponto do ano anterior.
-- Grão do ponto: o point_grain do período ('day' = dia, ano anterior = mesmo dia - 364; 'week' = semana, ano anterior =
-- semana - 52). point_start = a data do dia ou do primeiro dia da semana.
-- Lojas: nos períodos com ano anterior, as duas colunas usam só as lojas comparáveis do período; na base, todas as lojas
-- e revenue_prior_year nulo.
WITH pts AS (
    SELECT p.period, p.point_grain, c.day AS point, c.date AS point_start,
           CASE WHEN p.prior_week_start IS NOT NULL THEN c.day - getvariable('offset_dias') END AS prior_point
    FROM dim_period p JOIN calendar c ON c.week_no BETWEEN p.week_start AND p.week_end
    WHERE p.point_grain = 'day'
    UNION ALL
    SELECT p.period, p.point_grain, c.week_no, min(c.date),
           CASE WHEN p.prior_week_start IS NOT NULL THEN c.week_no - getvariable('offset_semanas') END
    FROM dim_period p JOIN calendar c ON c.week_no BETWEEN p.week_start AND p.week_end
    WHERE p.point_grain = 'week'
    GROUP BY ALL
),
s AS (
    SELECT p.period, CASE p.point_grain WHEN 'day' THEN b.day ELSE b.week_no END AS point, g.segment, b.department,
           sum(b.revenue) AS revenue
    FROM dim_period p
    JOIN basket_department b
      ON b.week_no BETWEEN p.week_start AND p.week_end OR b.week_no BETWEEN p.prior_week_start AND p.prior_week_end
    LEFT JOIN period_comparable_store l ON l.period = p.period AND l.store_id = b.store_id
    JOIN customer_group g ON g.household_key = b.household_key
    WHERE p.prior_week_start IS NULL OR l.store_id IS NOT NULL
    GROUP BY ALL
),
k AS (
    SELECT DISTINCT t.period, t.point, s.segment, s.department
    FROM pts t JOIN s ON s.period = t.period AND (s.point = t.point OR s.point = t.prior_point)
)
SELECT k.period, t.point_grain, k.point::INTEGER AS point, t.point_start, k.segment, k.department,
       coalesce(a.revenue, 0) AS revenue,
       CASE WHEN t.prior_point IS NOT NULL THEN coalesce(y.revenue, 0) END AS revenue_prior_year
FROM k
JOIN pts t ON t.period = k.period AND t.point = k.point
LEFT JOIN s a ON a.period = k.period AND a.point = k.point AND a.segment = k.segment AND a.department = k.department
LEFT JOIN s y ON y.period = k.period AND y.point = t.prior_point AND y.segment = k.segment AND y.department = k.department
