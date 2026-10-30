-- cubo_periodo.json: metrics.cube_period. Ordem: período, grupo (ordem do contrato), departamento.
SELECT c.period AS periodo, c.segment AS grupo, c.department AS departamento,
       ROUND(c.revenue, 2) AS faturamento, ROUND(c.discount, 2) AS desconto, ROUND(c.gross_value, 2) AS valor_bruto,
       ROUND(c.revenue_comparable, 2) AS faturamento_comparavel, ROUND(c.discount_comparable, 2) AS desconto_comparavel,
       ROUND(c.gross_value_comparable, 2) AS valor_bruto_comparavel,
       ROUND(c.revenue_prior_year, 2) AS faturamento_ano_anterior, ROUND(c.discount_prior_year, 2) AS desconto_ano_anterior,
       ROUND(c.gross_value_prior_year, 2) AS valor_bruto_ano_anterior
FROM cube_period c
JOIN dim_period p USING (period)
JOIN group_order g USING (segment)
ORDER BY p.position, g.position, c.department
