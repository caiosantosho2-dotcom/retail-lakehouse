-- (tabela auxiliar, não gravada) Os itens de sales_item só com as colunas que as métricas por produto usam,
-- materializados uma vez: as métricas de subcategoria, marca e rede leem daqui em vez de reler a silver a cada consulta.
SELECT household_key, basket_id, store_id, week_no, department, commodity_desc, brand, manufacturer, revenue
FROM sales_item
