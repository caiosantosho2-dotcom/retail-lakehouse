-- fact_sales: um item de uma cesta (grão da transaction_data limpa).
-- Chaves sem correspondência na dimensão apontam para o membro desconhecido -1 (P2) e são contadas pelo código.
-- is_merchandise vem da dim_product (nulo para produto desconhecido).
SELECT
    t.basket_id,
    COALESCE(h.household_key, -1) AS household_key,
    COALESCE(p.product_id, -1)    AS product_id,
    COALESCE(s.store_id, -1)      AS store_id,
    t.day,
    t.week_no,
    t.quantity,
    t.sales_value,
    t.retail_disc,
    t.coupon_disc,
    t.coupon_match_disc,
    t.trans_hour,
    t.trans_minute,
    p.is_merchandise,
    t.is_free_item,
    t.is_refund_discount,
    t._data_carga,
    getvariable('processado_em') AS _processado_em
FROM clean_transaction_data t
LEFT JOIN dim_product   p ON p.product_id    = t.product_id    AND p.product_id    <> -1
LEFT JOIN dim_store     s ON s.store_id      = t.store_id      AND s.store_id      <> -1
LEFT JOIN dim_household h ON h.household_key = t.household_key AND h.household_key <> -1
