-- departamentos_ficha_<periodo>.json: metrics.department_profile do período. O Python junta <atributo>_valor e
-- <atributo>_percentil no objeto `atributos`. Ordem: faturamento sem arredondar, decrescente; nome.
SELECT department AS departamento, ROUND(revenue, 2) AS faturamento, buyers AS compradores, baskets AS cestas,
       ROUND(share, 4) AS participacao_valor, ROUND(share_percentile, 1) AS participacao_percentil,
       ROUND(growth, 4) AS crescimento_valor, ROUND(growth_percentile, 1) AS crescimento_percentil,
       ROUND(penetration, 4) AS penetracao_valor, ROUND(penetration_percentile, 1) AS penetracao_percentil,
       ROUND(frequency, 4) AS frequencia_valor, ROUND(frequency_percentile, 1) AS frequencia_percentil,
       ROUND(discount_rate, 4) AS desconto_valor, ROUND(discount_rate_percentile, 1) AS desconto_percentil,
       ROUND(private_label, 4) AS marca_propria_valor, ROUND(private_label_percentile, 1) AS marca_propria_percentil,
       small_sample AS amostra_pequena
FROM department_profile
WHERE period = getvariable('periodo')
ORDER BY revenue DESC, department
