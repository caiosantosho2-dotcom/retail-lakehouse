-- concentracao.json: metrics.concentration. Ordem: período, subconjunto (máscara).
SELECT c.period AS periodo, c.subset AS subconjunto, c.subcategories_80 AS subcategorias_80, c.subcategories AS subcategorias
FROM concentration c
JOIN dim_period p USING (period)
ORDER BY p.position, c.subset_mask
