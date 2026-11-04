-- departamentos_quadrante_<periodo>.json: metrics.department_quadrant do período. Ordem: subconjunto (máscara), departamento.
SELECT subset AS subconjunto, department AS departamento,
       ROUND(share, 4) AS participacao, ROUND(growth, 4) AS crescimento,
       ROUND(share_cut, 4) AS corte_participacao, ROUND(growth_cut, 4) AS corte_crescimento,
       CASE quadrant WHEN 'invest' THEN 'investir' WHEN 'keep' THEN 'manter' WHEN 'defend' THEN 'defender' WHEN 'review' THEN 'rever' END AS quadrante,
       ROUND(gap_value, 2) AS valor_gap, highlight_rank AS destaque
FROM department_quadrant
WHERE period = getvariable('periodo')
ORDER BY subset_mask, department
