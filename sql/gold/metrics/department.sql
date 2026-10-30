-- department: a lista do filtro de departamento, um por departamento com venda na base. share_26w = parte do
-- faturamento da janela do segmento (26 s); small_sample = menos de 0,1% dele (ou sem venda nele).
WITH d AS (
    SELECT department,
           sum(revenue) FILTER (WHERE period = getvariable('periodo_segmento')) AS revenue_26w,
           sum(revenue) FILTER (WHERE period = getvariable('periodo_base')) AS revenue_base
    FROM cube_period
    GROUP BY department
)
SELECT department, coalesce(revenue_26w, 0) AS revenue_26w,
       share(coalesce(revenue_26w, 0), sum(revenue_26w) OVER ()) AS share_26w,
       revenue_base,
       share(coalesce(revenue_26w, 0), sum(revenue_26w) OVER ()) < getvariable('departamento_participacao') AS small_sample
FROM d
WHERE revenue_base > 0
