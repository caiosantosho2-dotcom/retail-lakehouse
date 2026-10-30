-- cesta_subcategorias_<periodo>.json: metrics.basket_pair do período. Ordem: subconjunto (máscara), departamento pelo
-- faturamento do período (sem arredondar), lift arredondado decrescente, par.
SELECT b.subset AS subconjunto, b.department AS departamento, b.subcategory_a AS subcategoria_a,
       b.subcategory_b AS subcategoria_b, b.baskets_pair AS cestas_par, b.baskets_a AS cestas_a, b.baskets_b AS cestas_b,
       b.baskets_total AS cestas_total, ROUND(b.support, 6) AS suporte, ROUND(b.confidence_a_b, 4) AS confianca_a_b,
       ROUND(b.confidence_b_a, 4) AS confianca_b_a, ROUND(b.lift, 4) AS lift
FROM basket_pair b
LEFT JOIN department_profile d ON d.period = b.period AND d.department = b.department
WHERE b.period = getvariable('periodo')
ORDER BY b.subset_mask, d.revenue DESC, b.department, ROUND(b.lift, 4) DESC, b.subcategory_a, b.subcategory_b
