-- dim_period: um período do filtro global (G1). Todos terminam na última semana completa (G11); o ano anterior são as
-- mesmas semanas - offset. O período sem número de semanas no config (base) começa na semana 1 e não tem ano anterior.
-- point_grain: grão do gráfico de faturamento no tempo (G2): 'day' ou 'week'.
WITH w AS (SELECT week_end_current AS week_end FROM analysis_window),
p AS (
    SELECT c.period, c.position, c.point_grain, c.weeks IS NOT NULL AS has_prior_year, w.week_end,
           CASE WHEN c.weeks IS NULL THEN (SELECT min(week_no) FROM calendar) ELSE w.week_end - c.weeks + 1 END AS week_start
    FROM config_period c CROSS JOIN w
)
SELECT p.period, p.position, p.week_start::INTEGER AS week_start, p.week_end::INTEGER AS week_end,
       (CASE WHEN p.has_prior_year THEN p.week_start - getvariable('offset_semanas') END)::INTEGER AS prior_week_start,
       (CASE WHEN p.has_prior_year THEN p.week_end - getvariable('offset_semanas') END)::INTEGER AS prior_week_end,
       min(c.day) AS day_start, max(c.day) AS day_end, min(c.date) AS date_start, max(c.date) AS date_end,
       p.point_grain
FROM p JOIN calendar c ON c.week_no BETWEEN p.week_start AND p.week_end
GROUP BY ALL
