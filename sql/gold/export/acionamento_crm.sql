-- acionamento_crm.json: metrics.crm_capacity. Ordem: capacidade, pausas antes de valor, modelo antes da regra simples.
SELECT capacity AS capacidade,
       CASE objective WHEN 'pauses' THEN 'pausas' WHEN 'value' THEN 'valor' END AS objetivo,
       CASE method WHEN 'model' THEN 'modelo' WHEN 'baseline' THEN 'regra_simples' END AS metodo,
       ROUND(pauses_expected, 4) AS pausas_esperadas,
       ROUND(revenue_26s_at_stake, 2) AS faturamento_26s_em_jogo,
       map_from_entries(segment_mix) AS mix_segmentos,
       ROUND(hist_precision, 4) AS precisao_historica,
       ROUND(hist_pauses_caught_share, 4) AS pausas_capturadas_historica,
       ROUND(hist_value_caught, 2) AS valor_capturado_historico,
       ROUND(hist_value_caught_share, 4) AS fracao_valor_capturado_historica,
       ROUND(hist_pauses_expected, 4) AS pausas_esperadas_historicas,
       ROUND(hist_pauses_actual, 4) AS pausas_reais_historicas
FROM crm_capacity
ORDER BY capacity, objective = 'value', method = 'baseline'
