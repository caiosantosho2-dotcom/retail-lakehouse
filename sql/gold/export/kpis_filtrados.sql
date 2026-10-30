-- kpis_filtrados.json: metrics.kpi_filtered (as variações já vêm da gold, G25).
-- Ordem: período, subconjunto (máscara), 'todos' primeiro e depois os departamentos em ordem alfabética.
SELECT k.period AS periodo, k.subset AS subconjunto, k.department AS departamento,
       k.baskets AS cestas, k.baskets_comparable AS cestas_comparavel, k.baskets_prior_year AS cestas_ano_anterior,
       ROUND(k.baskets_growth, 4) AS cestas_variacao_pct,
       ROUND(k.avg_ticket, 2) AS ticket_medio, ROUND(k.avg_ticket_comparable, 2) AS ticket_medio_comparavel,
       ROUND(k.avg_ticket_prior_year, 2) AS ticket_medio_ano_anterior, ROUND(k.avg_ticket_growth, 4) AS ticket_medio_variacao_pct,
       ROUND(k.items_per_basket, 4) AS itens_por_cesta, ROUND(k.items_per_basket_comparable, 4) AS itens_por_cesta_comparavel,
       ROUND(k.items_per_basket_prior_year, 4) AS itens_por_cesta_ano_anterior,
       ROUND(k.items_per_basket_growth, 4) AS itens_por_cesta_variacao_pct,
       k.active_customers AS clientes_ativos, k.active_customers_comparable AS clientes_ativos_comparavel,
       k.active_customers_prior_year AS clientes_ativos_ano_anterior,
       ROUND(k.active_customers_growth, 4) AS clientes_ativos_variacao_pct,
       k.comparable_stores AS lojas_comparaveis, k.small_sample AS amostra_pequena
FROM kpi_filtered k
JOIN dim_period p USING (period)
ORDER BY p.position, k.subset_mask, k.department <> 'todos', k.department
