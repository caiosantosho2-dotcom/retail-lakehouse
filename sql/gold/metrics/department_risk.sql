-- department_risk: dinheiro em risco (G4), a única definição da gold: faturamento da janela do segmento (26 s), todas as
-- lojas, que veio de clientes com probabilidade de pausa >= limiar do modelo (models/churn_score.is_high_risk, foto
-- final). Não pondera pela probabilidade. Por subconjunto × departamento (ou 'todos') com faturamento na janela, e a
-- parte dele no faturamento do departamento.
WITH p AS (SELECT week_start, week_end FROM dim_period WHERE period = getvariable('periodo_segmento')),
r AS (
    SELECT g.segment, b.department, b.revenue, coalesce(c.is_high_risk, false) AS high_risk
    FROM basket_department b
    JOIN p ON b.week_no BETWEEN p.week_start AND p.week_end
    JOIN customer_group g ON g.household_key = b.household_key
    LEFT JOIN churn_score c ON c.household_key = b.household_key
),
grp AS (
    SELECT segment, department, sum(revenue) AS revenue,
           coalesce(sum(revenue) FILTER (WHERE high_risk), 0) AS money_at_risk
    FROM r GROUP BY ALL
    UNION ALL
    SELECT segment, 'todos', sum(revenue), coalesce(sum(revenue) FILTER (WHERE high_risk), 0)
    FROM r GROUP BY segment
),
x AS (
    SELECT s.subset, s.subset_mask, g.department, sum(g.revenue) AS revenue, sum(g.money_at_risk) AS money_at_risk
    FROM grp g JOIN segment_subset s ON s.segment = g.segment
    GROUP BY ALL
)
SELECT getvariable('periodo_segmento') AS period, subset, subset_mask, department, revenue, money_at_risk,
       share(money_at_risk, revenue) AS money_at_risk_share
FROM x
WHERE revenue > 0
