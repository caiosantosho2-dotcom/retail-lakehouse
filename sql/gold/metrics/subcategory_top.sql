-- subcategory_top: as maiores subcategorias (commodity_desc) de cada departamento em cada período, todas as lojas, e as
-- do total ('todos', em que department_origin diz de qual departamento é a subcategoria: há nomes em mais de um).
-- share = faturamento da subcategoria ÷ faturamento do departamento (ou do total); position = ordem por faturamento.
-- Guarda as top N do config.
WITH v AS (
    SELECT p.period, i.department, i.commodity_desc AS subcategory, sum(i.revenue) AS revenue
    FROM _item i JOIN dim_period p ON i.week_no BETWEEN p.week_start AND p.week_end
    GROUP BY ALL
),
r AS (
    SELECT period, department, subcategory, NULL::VARCHAR AS department_origin, revenue,
           share(revenue, sum(revenue) OVER (PARTITION BY period, department)) AS share,
           row_number() OVER (PARTITION BY period, department ORDER BY revenue DESC, subcategory) AS position
    FROM v
    UNION ALL
    SELECT period, 'todos', subcategory, department, revenue,
           share(revenue, sum(revenue) OVER (PARTITION BY period)),
           row_number() OVER (PARTITION BY period ORDER BY revenue DESC, department, subcategory)
    FROM v
)
SELECT * FROM r WHERE position <= getvariable('top_subcategorias')
