-- (tabela auxiliar, não gravada) Cesta × subcategoria (commodity_desc), da semana 1 até a última completa, com o grupo
-- do cliente. A unidade da análise de cesta é a cesta reduzida a pares distintos cesta × subcategoria.
SELECT DISTINCT g.segment, i.basket_id, i.week_no, i.department, i.commodity_desc AS subcategory
FROM _item i JOIN customer_group g ON g.household_key = i.household_key
