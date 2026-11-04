-- acionamento_crm.json: metrics.crm_capacity. Ordem: capacidade, modelo antes da regra simples.
SELECT capacity AS capacidade,
       CASE method WHEN 'model' THEN 'modelo' WHEN 'baseline' THEN 'regra_simples' END AS metodo,
       ROUND(pauses_expected, 4) AS pausas_esperadas,
       ROUND(revenue_26s_at_stake, 2) AS faturamento_26s_em_jogo,
       map_from_entries(segment_mix) AS mix_segmentos,
       ROUND(hist_precision, 4) AS precisao_historica,
       ROUND(hist_pauses_caught_share, 4) AS pausas_capturadas_historica
FROM crm_capacity
ORDER BY capacity, method = 'baseline'
