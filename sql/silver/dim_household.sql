-- dim_household: um cliente. Todos os household_key da venda e da demografia (P3).
-- Demografia nula para quem não está na pesquisa, com has_demographics = false (S9.10).
-- Valores "Unknown", "None/Unknown", "U" mantidos como vieram (S9.9).
-- age_band_order / income_band_order: posição da faixa na lista do config (S9.8); nulo se a faixa não estiver lá.
WITH clientes AS (
    SELECT household_key FROM clean_transaction_data
    UNION
    SELECT household_key FROM clean_hh_demographic
)
SELECT
    c.household_key,
    d.household_key IS NOT NULL AS has_demographics,
    d.age_desc,
    d.marital_status_code,
    d.income_desc,
    d.homeowner_desc,
    d.hh_comp_desc,
    d.household_size_desc,
    d.kid_category_desc,
    NULLIF(list_position(getvariable('ordem_idade'), d.age_desc), 0)::INTEGER  AS age_band_order,
    NULLIF(list_position(getvariable('ordem_renda'), d.income_desc), 0)::INTEGER AS income_band_order
FROM clientes c
LEFT JOIN clean_hh_demographic d USING (household_key)
UNION ALL
SELECT -1, false, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
