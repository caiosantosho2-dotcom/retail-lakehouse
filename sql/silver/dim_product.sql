-- dim_product: um produto. Grão = product_id (chave única).
-- department e commodity_desc nulos viram 'UNKNOWN' (S9.7).
-- is_merchandise = false se o departamento OU a commodity estiver na lista de não mercadoria do config (S9.2, A1).
-- Membro desconhecido -1 (P2): is_merchandise nulo, porque não se sabe o que é.
SELECT
    product_id,
    manufacturer,
    COALESCE(department, 'UNKNOWN')     AS department,
    brand,
    COALESCE(commodity_desc, 'UNKNOWN') AS commodity_desc,
    sub_commodity_desc,
    curr_size_of_product,
    NOT (COALESCE(list_contains(getvariable('departamentos_nao_mercadoria'), department), false)
         OR COALESCE(list_contains(getvariable('commodities_nao_mercadoria'), commodity_desc), false)) AS is_merchandise
FROM clean_product
UNION ALL
SELECT -1, NULL, 'UNKNOWN', NULL, 'UNKNOWN', NULL, NULL, NULL
