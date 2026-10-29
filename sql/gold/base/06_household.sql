-- household: todos os clientes da dim_household, sem o membro -1 (2.500; denominador e "Sem compra na janela").
SELECT household_key, has_demographics
FROM dim_household
WHERE household_key <> -1
