-- network_characteristic: os pares característicos de cada subconjunto (sem 'todos'), por período: os 15 de maior
-- lift_index (lift no subconjunto ÷ lift com todos), sem amostra pequena. São os pares que o grupo compra junto bem mais
-- que a média.
SELECT period, subset, subset_mask, position, node_a, node_b, baskets_pair,
       confidence(baskets_pair, baskets_a) AS confidence_a_b, confidence(baskets_pair, baskets_b) AS confidence_b_a,
       lift, lift_all, lift_index
FROM (
    SELECT *, row_number() OVER (PARTITION BY period, subset ORDER BY lift_index DESC, node_a, node_b) AS position
    FROM _network_pair
    WHERE subset <> 'todos' AND NOT small_sample
)
WHERE position <= getvariable('caracteristicos')
