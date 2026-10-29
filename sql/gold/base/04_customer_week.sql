-- customer_week: um cliente × semana com compra, da semana 1 até a última completa (equivale a vw_cliente_semana).
SELECT household_key, week_no,
       count(DISTINCT basket_id) AS baskets, sum(revenue) AS revenue, sum(quantity) AS items,
       sum(discount) AS discount, sum(gross_value) AS gross_value, max(date) AS last_date
FROM sales_item
GROUP BY household_key, week_no
