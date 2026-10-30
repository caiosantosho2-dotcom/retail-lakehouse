-- period_comparable_store: lojas comparáveis de cada período com ano anterior (a regra de vw_lojas_like_for_like do RAG
-- levada a cada período): pelo menos uma cesta no período e no mesmo período um ano antes. A base não tem.
WITH cur AS (
    SELECT DISTINCT p.period, b.store_id
    FROM dim_period p JOIN basket b ON b.week_no BETWEEN p.week_start AND p.week_end
    WHERE p.prior_week_start IS NOT NULL
),
pri AS (
    SELECT DISTINCT p.period, b.store_id
    FROM dim_period p JOIN basket b ON b.week_no BETWEEN p.prior_week_start AND p.prior_week_end
)
SELECT period, store_id FROM cur JOIN pri USING (period, store_id)
