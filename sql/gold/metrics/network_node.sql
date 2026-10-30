-- network_node: os nós da rede de cestas = as N maiores subcategorias (departamento × commodity_desc) na janela do
-- segmento (26 s), node = 0 é a maior. Fixos em qualquer período. As posições x/y entram depois, no build
-- (src/gold/layout.py, a partir da semelhança entre os nós em _network_pair).
WITH p AS (SELECT week_start, week_end FROM dim_period WHERE period = getvariable('periodo_segmento'))
SELECT node, department, subcategory, revenue
FROM (
    SELECT (row_number() OVER (ORDER BY sum(i.revenue) DESC, i.department, i.commodity_desc) - 1)::INTEGER AS node,
           i.department, i.commodity_desc AS subcategory, sum(i.revenue) AS revenue
    FROM _item i, p
    WHERE i.week_no BETWEEN p.week_start AND p.week_end
    GROUP BY i.department, i.commodity_desc
)
WHERE node < getvariable('rede_nos')
