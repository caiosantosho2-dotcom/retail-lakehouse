-- faturamento_tempo_<periodo>.json (novo, G2/G3): metrics.revenue_over_time do período. `inicio` é o dia (grão
-- diário) ou o primeiro dia da semana. Ordem: ponto, grupo (ordem do contrato), departamento.
SELECT strftime(r.point_start, '%Y-%m-%d') AS inicio, r.segment AS grupo, r.department AS departamento,
       ROUND(r.revenue, 2) AS faturamento, ROUND(r.revenue_prior_year, 2) AS faturamento_ano_anterior
FROM revenue_over_time r
JOIN group_order g USING (segment)
WHERE r.period = getvariable('periodo')
ORDER BY r.point_start, g.position, r.department
