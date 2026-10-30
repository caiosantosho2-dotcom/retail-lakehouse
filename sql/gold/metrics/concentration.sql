-- concentration: quantas subcategorias (departamento × commodity_desc), da maior para a menor, fazem 80% do faturamento
-- (a que cruza 80% ainda conta), e quantas têm venda. Por período × subconjunto, todas as lojas.
WITH v AS (
    SELECT p.period, g.segment, i.department, i.commodity_desc AS subcategory, sum(i.revenue) AS revenue
    FROM _item i
    JOIN customer_group g ON g.household_key = i.household_key
    JOIN dim_period p ON i.week_no BETWEEN p.week_start AND p.week_end
    GROUP BY ALL
),
s AS (
    SELECT v.period, x.subset, x.subset_mask, v.department, v.subcategory, sum(v.revenue) AS revenue
    FROM v JOIN segment_subset x ON x.segment = v.segment
    GROUP BY ALL
    HAVING sum(v.revenue) > 0
),
o AS (
    SELECT *,
           share(sum(revenue) OVER (PARTITION BY period, subset ORDER BY revenue DESC, department, subcategory ROWS UNBOUNDED PRECEDING),
                 sum(revenue) OVER (PARTITION BY period, subset)) AS cumulative,
           share(revenue, sum(revenue) OVER (PARTITION BY period, subset)) AS part
    FROM s
)
SELECT period, subset, subset_mask,
       count(*) FILTER (WHERE cumulative - part < getvariable('concentracao')) AS subcategories_80,
       count(*) AS subcategories
FROM o
GROUP BY ALL
