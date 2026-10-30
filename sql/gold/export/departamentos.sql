-- departamentos.json: metrics.department com os nomes e as casas do contrato.
-- Ordem do contrato: faturamento de 26 s e da base (os valores arredondados, como no painel publicado), nome.
SELECT department AS departamento, ROUND(revenue_26w, 2) AS faturamento_26s, ROUND(share_26w, 4) AS participacao_26s_pct,
       ROUND(revenue_base, 2) AS faturamento_base, small_sample AS amostra_pequena
FROM department
ORDER BY faturamento_26s DESC, faturamento_base DESC, departamento
