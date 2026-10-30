-- rede_caracteristicos_<periodo>.json: metrics.network_characteristic do período.
-- Ordem: subconjunto (máscara), posição.
SELECT subset AS subconjunto, position AS posicao, node_a AS no_a, node_b AS no_b, baskets_pair AS cestas_par,
       ROUND(confidence_a_b, 4) AS confianca_a_b, ROUND(confidence_b_a, 4) AS confianca_b_a, ROUND(lift, 4) AS lift,
       ROUND(lift_all, 4) AS lift_todos, ROUND(lift_index, 4) AS indice
FROM network_characteristic
WHERE period = getvariable('periodo')
ORDER BY subset_mask, position
