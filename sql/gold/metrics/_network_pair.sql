-- (tabela auxiliar, não gravada) Pares de nós da rede comprados na mesma cesta, no período getvariable('periodo'), por
-- subconjunto. O build roda um período por vez e junta. Grão: período × subconjunto × par (node_a < node_b) com ao menos
-- uma cesta. O total de cestas é o de todas as cestas do subconjunto no período. small_sample: menos de 200 cestas com
-- o par. lift_index = lift do subconjunto ÷ lift com todos os clientes no mesmo período.
WITH p AS (SELECT week_start, week_end FROM dim_period WHERE period = getvariable('periodo')),
cs AS (
    SELECT DISTINCT g.segment, i.basket_id, n.node
    FROM _item i
    JOIN p ON i.week_no BETWEEN p.week_start AND p.week_end
    JOIN network_node n ON n.department = i.department AND n.subcategory = i.commodity_desc
    JOIN customer_group g ON g.household_key = i.household_key
),
n AS (
    SELECT g.segment, count(*) AS n
    FROM basket b
    JOIN p ON b.week_no BETWEEN p.week_start AND p.week_end
    JOIN customer_group g ON g.household_key = b.household_key
    GROUP BY g.segment
),
na AS (SELECT segment, node, count(*) AS n FROM cs GROUP BY ALL),
nab AS (
    SELECT a.segment, a.node AS a, b.node AS b, count(*) AS n
    FROM cs a JOIN cs b ON b.basket_id = a.basket_id AND b.node > a.node
    GROUP BY ALL
),
sn AS (SELECT s.subset, s.subset_mask, sum(n.n) AS n FROM n JOIN segment_subset s ON s.segment = n.segment GROUP BY ALL),
sna AS (SELECT s.subset, na.node, sum(na.n) AS n FROM na JOIN segment_subset s ON s.segment = na.segment GROUP BY ALL),
snab AS (SELECT s.subset, nab.a, nab.b, sum(nab.n) AS n FROM nab JOIN segment_subset s ON s.segment = nab.segment GROUP BY ALL),
q AS (
    SELECT x.subset, sn.subset_mask, x.a AS node_a, x.b AS node_b,
           x.n::BIGINT AS baskets_pair, sa.n::BIGINT AS baskets_a, sb.n::BIGINT AS baskets_b, sn.n::BIGINT AS baskets_total,
           lift(x.n, sa.n, sb.n, sn.n) AS lift,
           x.n < getvariable('par_cestas') AS small_sample
    FROM snab x
    JOIN sn ON sn.subset = x.subset
    JOIN sna sa ON sa.subset = x.subset AND sa.node = x.a
    JOIN sna sb ON sb.subset = x.subset AND sb.node = x.b
)
SELECT getvariable('periodo') AS period, q.*, t.lift AS lift_all, lift_index(q.lift, t.lift) AS lift_index
FROM q JOIN q t ON t.subset = 'todos' AND t.node_a = q.node_a AND t.node_b = q.node_b
