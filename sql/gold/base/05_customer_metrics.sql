-- customer_metrics: um cliente × período ('current' ou 'prior') com compra (equivale a vw_metricas_cliente).
-- recency_days = dias da última compra até o fim do período; discount_pct em 0-100, como no RAG (entrada dos modelos).
WITH c AS (
    SELECT household_key, period,
           sum(revenue) AS revenue, count(DISTINCT basket_id) AS frequency, sum(quantity) AS items,
           max(date) AS last_purchase, max(week_no) AS last_week, count(DISTINCT week_no) AS weeks_with_purchase,
           sum(discount) AS discount, sum(gross_value) AS gross_value
    FROM sales_item
    WHERE period IS NOT NULL
    GROUP BY ALL
)
SELECT c.household_key, c.period, c.revenue, c.frequency, c.items, c.last_purchase, c.weeks_with_purchase,
       date_diff('day', c.last_purchase, CASE c.period WHEN 'current' THEN w.date_end_current ELSE w.date_end_prior END)
           AS recency_days,
       c.last_week >= (CASE c.period WHEN 'current' THEN w.week_end_current ELSE w.week_end_prior END)
           - w.active_weeks + 1 AS is_active,
       CAST(c.revenue AS DOUBLE) / NULLIF(c.frequency, 0) AS avg_ticket,
       c.discount, c.gross_value,
       100.0 * CAST(c.discount AS DOUBLE) / NULLIF(CAST(c.gross_value AS DOUBLE), 0) AS discount_pct,
       h.has_demographics
FROM c CROSS JOIN analysis_window w
LEFT JOIN dim_household h ON h.household_key = c.household_key
