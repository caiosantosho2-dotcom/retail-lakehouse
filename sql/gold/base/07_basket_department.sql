-- basket_department: uma cesta × departamento, da semana 1 até a última completa (as regras de painel.cesta_departamento,
-- reescritas). Uma cesta tem uma só loja, um só cliente e um só dia. private_revenue = parte com brand = 'Private'.
SELECT basket_id, any_value(store_id) AS store_id, any_value(household_key) AS household_key,
       any_value(week_no) AS week_no, any_value(day) AS day, department,
       sum(revenue) AS revenue, sum(quantity) AS items, sum(discount) AS discount, sum(gross_value) AS gross_value,
       coalesce(sum(revenue) FILTER (WHERE brand = 'Private'), 0) AS private_revenue
FROM sales_item
GROUP BY basket_id, department
