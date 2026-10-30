-- basket: uma cesta, da semana 1 até a última completa (a soma dos departamentos da cesta).
SELECT basket_id, any_value(store_id) AS store_id, any_value(household_key) AS household_key,
       any_value(week_no) AS week_no, any_value(day) AS day,
       sum(revenue) AS revenue, sum(items) AS items, sum(discount) AS discount, sum(gross_value) AS gross_value
FROM basket_department
GROUP BY basket_id
