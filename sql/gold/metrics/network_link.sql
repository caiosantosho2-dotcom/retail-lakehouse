-- network_link: as ligações desenhadas da rede, com os números de cada período × subconjunto. As ligações são fixas:
-- as 3 de maior lift de cada nó, com todos os clientes, na janela do segmento (26 s) e sem amostra pequena.
WITH t AS (
    SELECT node_a, node_b, lift FROM _network_pair
    WHERE period = getvariable('periodo_segmento') AND subset = 'todos' AND NOT small_sample
),
ends AS (SELECT node_a AS node, node_a, node_b, lift FROM t UNION ALL SELECT node_b, node_a, node_b, lift FROM t),
drawn AS (
    SELECT DISTINCT node_a, node_b
    FROM (SELECT *, row_number() OVER (PARTITION BY node ORDER BY lift DESC, node_a, node_b) AS r FROM ends)
    WHERE r <= getvariable('rede_ligacoes_por_no')
)
SELECT p.period, p.subset, p.subset_mask, p.node_a, p.node_b, p.baskets_pair, p.lift, p.lift_index, p.small_sample
FROM _network_pair p JOIN drawn d ON d.node_a = p.node_a AND d.node_b = p.node_b
