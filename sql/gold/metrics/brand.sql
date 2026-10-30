-- brand: marca própria e concentração de fornecedores por período × subconjunto × departamento com venda.
-- O fabricante vem anonimizado (manufacturer, um código). Fornecedores nacionais = fabricantes das vendas com
-- brand = 'National': manufacturers_80 = quantos, do maior para o menor, somam 80% do faturamento nacional do
-- departamento; top_manufacturer_share = parte do maior. Crescimento de cada marca nas lojas comparáveis do período
-- (nulo na base). small_sample: menos de 0,1% do faturamento do subconjunto.
WITH x AS (
    SELECT m.period, m.cut, s.subset, s.subset_mask, m.department, m.brand, m.manufacturer, sum(m.revenue) AS revenue
    FROM _brand_cut m JOIN segment_subset s ON s.segment = m.segment
    GROUP BY ALL
),
dep AS (
    SELECT period, subset, subset_mask, department, sum(revenue) AS revenue,
           coalesce(sum(revenue) FILTER (WHERE brand = 'Private'), 0) AS private_revenue
    FROM x WHERE cut = 'all'
    GROUP BY ALL
),
nat AS (
    SELECT period, subset, department, manufacturer, sum(revenue) AS revenue
    FROM x WHERE cut = 'all' AND brand = 'National'
    GROUP BY ALL
    HAVING sum(revenue) > 0
),
ranked AS (
    SELECT *,
           row_number() OVER (PARTITION BY period, subset, department ORDER BY revenue DESC, manufacturer) AS position,
           share(revenue, sum(revenue) OVER (PARTITION BY period, subset, department)) AS part,
           share(sum(revenue) OVER (PARTITION BY period, subset, department ORDER BY revenue DESC, manufacturer ROWS UNBOUNDED PRECEDING),
                 sum(revenue) OVER (PARTITION BY period, subset, department)) AS cumulative
    FROM nat
),
conc AS (
    SELECT period, subset, department, count(*) AS national_manufacturers,
           min(position) FILTER (WHERE cumulative >= getvariable('concentracao') - 1e-12) AS manufacturers_80,
           max(part) AS top_manufacturer_share
    FROM ranked
    GROUP BY ALL
),
yoy AS (
    SELECT period, subset, department,
           sum(revenue) FILTER (WHERE cut = 'comparable' AND brand = 'Private') AS private_current,
           sum(revenue) FILTER (WHERE cut = 'prior' AND brand = 'Private') AS private_prior,
           sum(revenue) FILTER (WHERE cut = 'comparable' AND brand = 'National') AS national_current,
           sum(revenue) FILTER (WHERE cut = 'prior' AND brand = 'National') AS national_prior
    FROM x WHERE cut <> 'all'
    GROUP BY ALL
)
SELECT d.period, d.subset, d.subset_mask, d.department, d.revenue,
       share(d.revenue, sum(d.revenue) OVER (PARTITION BY d.period, d.subset)) AS share,
       private_label_share(d.private_revenue, d.revenue) AS private_label,
       growth(y.private_current, y.private_prior) AS private_label_growth,
       growth(y.national_current, y.national_prior) AS national_growth,
       c.national_manufacturers, c.manufacturers_80, c.top_manufacturer_share,
       share(d.revenue, sum(d.revenue) OVER (PARTITION BY d.period, d.subset)) < getvariable('departamento_participacao') AS small_sample
FROM dep d
LEFT JOIN conc c ON c.period = d.period AND c.subset = d.subset AND c.department = d.department
LEFT JOIN yoy y ON y.period = d.period AND y.subset = d.subset AND y.department = d.department
WHERE d.revenue > 0
