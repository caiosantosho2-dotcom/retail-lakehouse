-- subcategorias_<periodo>.json: metrics.subcategory_top do período.
-- Ordem: 'todos' primeiro, depois o faturamento do departamento no período (sem arredondar), nome, posição.
SELECT s.department AS departamento, s.subcategory AS subcategoria, s.department_origin AS departamento_origem,
       s.position AS posicao, ROUND(s.revenue, 2) AS faturamento, ROUND(s.share, 4) AS participacao_pct
FROM subcategory_top s
LEFT JOIN department_profile d ON d.period = s.period AND d.department = s.department
WHERE s.period = getvariable('periodo')
ORDER BY s.department = 'todos' DESC, d.revenue DESC, s.department, s.position
