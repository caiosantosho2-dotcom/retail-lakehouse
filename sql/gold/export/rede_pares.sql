-- rede_pares_<periodo>.json: metrics.network_link do período. Ordem: subconjunto (máscara), nó a, nó b.
SELECT subset AS subconjunto, node_a AS no_a, node_b AS no_b, baskets_pair AS cestas_par, ROUND(lift, 4) AS lift,
       ROUND(lift_index, 4) AS indice, small_sample AS amostra_pequena
FROM network_link
WHERE period = getvariable('periodo')
ORDER BY subset_mask, node_a, node_b
