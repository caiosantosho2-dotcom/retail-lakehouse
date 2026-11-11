-- sales_item: um item de cesta de MERCADORIA (A1), até a última semana completa.
-- Único lugar onde desconto e valor bruto são calculados: discount = -(retail + coupon + coupon_match), positivo;
-- gross_value = sales_value + discount. period: 'current' (janela) ou 'prior' (mesmas semanas - offset); nulo fora delas.
-- Atributos do produto como em vw_vendas_item do RAG (LEFT JOIN; hoje todo produto vendido está na dim_product).
-- Data também por LEFT JOIN: não há teste de órfãos de data na silver, então um day fora da dim_date não pode sumir
-- em silêncio (hoje a dim_date nasce dos days da própria transaction_data e cobre todos).
SELECT f.household_key, f.basket_id, f.store_id, f.product_id, f.day, c.date, f.week_no,
       CASE WHEN f.week_no BETWEEN w.week_start_current AND w.week_end_current THEN 'current'
            WHEN f.week_no BETWEEN w.week_start_prior AND w.week_end_prior THEN 'prior' END AS period,
       p.department, p.commodity_desc, p.brand, p.manufacturer,
       f.quantity,
       f.sales_value                                              AS revenue,
       -(f.retail_disc + f.coupon_disc + f.coupon_match_disc)     AS discount,
       f.sales_value - (f.retail_disc + f.coupon_disc + f.coupon_match_disc) AS gross_value
FROM fact_sales f
LEFT JOIN calendar c ON c.day = f.day
LEFT JOIN dim_product p ON p.product_id = f.product_id
CROSS JOIN analysis_window w
WHERE f.is_merchandise AND f.week_no <= w.week_end_current
