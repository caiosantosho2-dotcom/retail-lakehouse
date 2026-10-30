-- marcas_<periodo>.json: metrics.brand do período. Ordem: subconjunto (máscara), faturamento arredondado decrescente,
-- departamento.
SELECT subset AS subconjunto, department AS departamento, ROUND(revenue, 2) AS faturamento, ROUND(share, 4) AS participacao_pct,
       ROUND(private_label, 4) AS marca_propria_pct, ROUND(private_label_growth, 4) AS marca_propria_crescimento_pct,
       ROUND(national_growth, 4) AS nacional_crescimento_pct, national_manufacturers AS fabricantes_nacionais,
       manufacturers_80 AS fabricantes_80, ROUND(top_manufacturer_share, 4) AS maior_fabricante_pct, small_sample AS amostra_pequena
FROM brand
WHERE period = getvariable('periodo')
ORDER BY subset_mask, ROUND(revenue, 2) DESC, department
