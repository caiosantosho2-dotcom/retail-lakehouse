-- departamentos_segmento_<periodo>.json: metrics.department_segment do período, com o índice contra todos.
-- Ordem: subconjunto (máscara), 'todos' primeiro, departamento.
SELECT subset AS subconjunto, department AS departamento, ROUND(revenue, 2) AS faturamento, buyers AS compradores,
       ROUND(share, 4) AS participacao_valor, ROUND(share_index, 1) AS participacao_indice,
       ROUND(growth, 4) AS crescimento_valor, ROUND(growth_index, 1) AS crescimento_indice,
       ROUND(penetration, 4) AS penetracao_valor, ROUND(penetration_index, 1) AS penetracao_indice,
       ROUND(frequency, 4) AS frequencia_valor, ROUND(frequency_index, 1) AS frequencia_indice,
       ROUND(discount_rate, 4) AS desconto_valor, ROUND(discount_rate_index, 1) AS desconto_indice,
       ROUND(private_label, 4) AS marca_propria_valor, ROUND(private_label_index, 1) AS marca_propria_indice,
       small_sample AS amostra_pequena
FROM department_segment
WHERE period = getvariable('periodo')
ORDER BY subset_mask, department = 'todos' DESC, department
