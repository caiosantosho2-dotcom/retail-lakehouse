-- department_profile: a ficha do departamento (todos os clientes), por período × departamento com faturamento: os 6
-- atributos de department_segment e o percentil de cada um entre os departamentos do período (0–100, percent_rank).
-- Atributo nulo fica com percentil nulo. small_sample: menos de 0,1% do faturamento do período.
SELECT period, department, revenue, buyers, baskets,
       share, CASE WHEN share IS NOT NULL THEN 100 * percent_rank() OVER (PARTITION BY period, share IS NULL ORDER BY share) END AS share_percentile,
       growth, CASE WHEN growth IS NOT NULL THEN 100 * percent_rank() OVER (PARTITION BY period, growth IS NULL ORDER BY growth) END AS growth_percentile,
       penetration, CASE WHEN penetration IS NOT NULL THEN 100 * percent_rank() OVER (PARTITION BY period, penetration IS NULL ORDER BY penetration) END AS penetration_percentile,
       frequency, CASE WHEN frequency IS NOT NULL THEN 100 * percent_rank() OVER (PARTITION BY period, frequency IS NULL ORDER BY frequency) END AS frequency_percentile,
       discount_rate, CASE WHEN discount_rate IS NOT NULL THEN 100 * percent_rank() OVER (PARTITION BY period, discount_rate IS NULL ORDER BY discount_rate) END AS discount_rate_percentile,
       private_label, CASE WHEN private_label IS NOT NULL THEN 100 * percent_rank() OVER (PARTITION BY period, private_label IS NULL ORDER BY private_label) END AS private_label_percentile,
       share < getvariable('departamento_participacao') AS small_sample
FROM department_segment
WHERE subset = 'todos' AND department <> 'todos'
