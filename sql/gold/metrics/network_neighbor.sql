-- network_neighbor: os pares do nó selecionado na rede, por período × subconjunto × nó: os 10 de maior lift entre os
-- pares do nó sem amostra pequena. confidence = cestas com os dois ÷ cestas com o nó.
WITH ends AS (
    SELECT period, subset, subset_mask, node_a AS node, node_b AS other, baskets_pair, baskets_a AS baskets_node,
           lift, lift_index, small_sample
    FROM _network_pair
    UNION ALL
    SELECT period, subset, subset_mask, node_b, node_a, baskets_pair, baskets_b, lift, lift_index, small_sample
    FROM _network_pair
)
SELECT period, subset, subset_mask, node, other, baskets_pair, confidence(baskets_pair, baskets_node) AS confidence,
       lift, lift_index
FROM ends
WHERE NOT small_sample
QUALIFY row_number() OVER (PARTITION BY period, subset, node ORDER BY lift DESC, other) <= getvariable('vizinhos_por_no')
