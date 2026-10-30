-- rede_vizinhos_<periodo>.json: metrics.network_neighbor do período.
-- Ordem: subconjunto (máscara), nó, lift arredondado decrescente, outro nó.
SELECT subset AS subconjunto, node AS no, other AS outro, baskets_pair AS cestas_par, ROUND(confidence, 4) AS confianca,
       ROUND(lift, 4) AS lift, ROUND(lift_index, 4) AS indice
FROM network_neighbor
WHERE period = getvariable('periodo')
ORDER BY subset_mask, node, ROUND(lift, 4) DESC, other
