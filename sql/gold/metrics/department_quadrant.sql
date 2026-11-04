-- department_quadrant (G46): onde agir no mix. Grão: período × subconjunto × departamento válido; a base inteira fica
-- fora (sem crescimento comparável, G2c). Nada é recalculado: participação, crescimento e ano anterior vêm de
-- department_segment. Válido = sem amostra pequena em nenhuma das duas definições (department_profile: menos de 0,1% do
-- faturamento do período; department_segment: menos de 30 compradores no subconjunto) e com crescimento calculável.
-- share_cut = mediana da participação dos válidos no recorte; growth_cut = crescimento do total do recorte (a linha
-- 'todos' de department_segment). highlight_rank: os 3 de 'defend' com gap_value mais negativo (empate: departamento).
WITH valid AS (
    SELECT s.period, s.subset, s.subset_mask, s.department, s.share, s.growth, s.revenue_prior_year
    FROM department_segment s
    JOIN department_profile p ON p.period = s.period AND p.department = s.department
    WHERE s.period <> getvariable('periodo_base') AND s.department <> 'todos'
      AND NOT s.small_sample AND NOT p.small_sample AND s.growth IS NOT NULL
),
cut AS (
    SELECT v.period, v.subset, median(v.share) AS share_cut, any_value(t.growth) AS growth_cut
    FROM valid v
    JOIN department_segment t ON t.period = v.period AND t.subset = v.subset AND t.department = 'todos'
    GROUP BY v.period, v.subset
),
placed AS (
    SELECT v.period, v.subset, v.subset_mask, v.department, v.share, v.growth, c.share_cut, c.growth_cut,
           quadrant_of(v.share, c.share_cut, v.growth, c.growth_cut) AS quadrant,
           gap_value(v.revenue_prior_year, v.growth, c.growth_cut) AS gap_value
    FROM valid v JOIN cut c ON c.period = v.period AND c.subset = v.subset
),
ranked AS (
    SELECT *, row_number() OVER (PARTITION BY period, subset, quadrant ORDER BY gap_value, department) AS position
    FROM placed
)
SELECT period, subset, subset_mask, department, share, growth, share_cut, growth_cut, quadrant, gap_value,
       (CASE WHEN quadrant = 'defend' AND position <= 3 THEN position END)::INTEGER AS highlight_rank
FROM ranked
