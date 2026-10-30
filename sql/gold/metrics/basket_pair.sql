-- basket_pair: pares de subcategorias dentro de UM departamento, por subconjunto, no período getvariable('periodo') e no
-- departamento getvariable('departamento'). O build roda um período × departamento por vez (GROCERY na base passa de 10
-- milhões de linhas de pares antes de agregar) e junta tudo numa tabela.
-- Contagens somadas por grupo e depois por subconjunto (cada cesta tem um só cliente: a soma é exata). O total de cestas
-- é o de todas as cestas do subconjunto no período, não só as do departamento.
-- Ficam os pares com 200 cestas ou mais (com menos, o lift oscila muito entre semanas) e, deles, os 10 de maior lift.
WITH p AS (SELECT week_start, week_end FROM dim_period WHERE period = getvariable('periodo')),
cs AS (
    SELECT c.segment, c.basket_id, c.subcategory
    FROM _basket_subcategory c, p
    WHERE c.department = getvariable('departamento') AND c.week_no BETWEEN p.week_start AND p.week_end
),
n AS (
    SELECT g.segment, count(*) AS n
    FROM basket b, p, customer_group g
    WHERE g.household_key = b.household_key AND b.week_no BETWEEN p.week_start AND p.week_end
    GROUP BY g.segment
),
na AS (SELECT segment, subcategory, count(*) AS n FROM cs GROUP BY ALL),
nab AS (
    SELECT a.segment, a.subcategory AS a, b.subcategory AS b, count(*) AS n
    FROM cs a JOIN cs b ON b.basket_id = a.basket_id AND b.subcategory > a.subcategory
    GROUP BY ALL
),
sn AS (SELECT s.subset, s.subset_mask, sum(n.n) AS n FROM n JOIN segment_subset s ON s.segment = n.segment GROUP BY ALL),
sna AS (SELECT s.subset, na.subcategory, sum(na.n) AS n FROM na JOIN segment_subset s ON s.segment = na.segment GROUP BY ALL),
snab AS (SELECT s.subset, nab.a, nab.b, sum(nab.n) AS n FROM nab JOIN segment_subset s ON s.segment = nab.segment GROUP BY ALL),
pairs AS (
    SELECT q.subset, sn.subset_mask, q.a AS subcategory_a, q.b AS subcategory_b,
           q.n::BIGINT AS baskets_pair, sa.n::BIGINT AS baskets_a, sb.n::BIGINT AS baskets_b, sn.n::BIGINT AS baskets_total
    FROM snab q
    JOIN sn ON sn.subset = q.subset
    JOIN sna sa ON sa.subset = q.subset AND sa.subcategory = q.a
    JOIN sna sb ON sb.subset = q.subset AND sb.subcategory = q.b
)
SELECT getvariable('periodo') AS period, subset, subset_mask, getvariable('departamento') AS department,
       subcategory_a, subcategory_b, baskets_pair, baskets_a, baskets_b, baskets_total,
       support(baskets_pair, baskets_total) AS support,
       confidence(baskets_pair, baskets_a) AS confidence_a_b,
       confidence(baskets_pair, baskets_b) AS confidence_b_a,
       lift(baskets_pair, baskets_a, baskets_b, baskets_total) AS lift
FROM pairs
WHERE baskets_pair >= getvariable('par_cestas')
QUALIFY row_number() OVER (PARTITION BY subset ORDER BY lift DESC, subcategory_a, subcategory_b) <= getvariable('pares_por_departamento')
