-- crm_capacity (G45, G48): se o CRM só aciona N clientes, quem priorizar e o que isso protege.
-- Grão: capacidade × objetivo × método.
-- Ordem do modelo, por objetivo: pauses = probabilidade decrescente; value = priority_score (probabilidade × faturamento
-- de 26 s) decrescente; nos dois, empate pelo household_key.
-- Regra simples, a mesma nos dois objetivos: mais semanas sem comprar, empate pelo faturamento de 26 s e depois pelo
-- household_key. Por isso as linhas baseline dos dois objetivos têm os mesmos números.
-- Esta semana (foto final, só model): soma das probabilidades, faturamento de 26 s e mix de segmentos dos N primeiros.
-- No teste (fotos 85 e 93, média das duas), pela mesma ordem: precision@N, recall@N e o valor das pausas reais entre os N,
-- em US$ e como fração do valor de todas as pausas reais da foto. Probabilidade do teste e faturamento de 26 s ATÉ a foto
-- (churn_features, G21), sem nada posterior à foto.
-- Calibração no teste (G49, só model): soma das probabilidades dos N primeiros e pausas reais entre eles, média das fotos.
-- Se a população for menor que N, acionam-se todos: "N primeiros" = quem existe.
WITH objectives AS (
    SELECT unnest(['pauses', 'value']) AS objective
),
final_base AS (
    SELECT s.household_key, s.probability, s.segment, value_from_log1p(f.log_value_26w) AS revenue_26s
    FROM churn_score s
    JOIN churn_features f ON f.household_key = s.household_key AND f.role = 'final'
),
final_rank AS (
    SELECT 'pauses' AS objective, *, row_number() OVER (ORDER BY probability DESC, household_key) AS position
    FROM final_base
    UNION ALL
    SELECT 'value', *, row_number() OVER (ORDER BY priority_score(probability, revenue_26s) DESC, household_key)
    FROM final_base
),
this_week AS (
    SELECT c.capacity, r.objective, sum(r.probability) AS pauses_expected, sum(r.revenue_26s) AS revenue_26s_at_stake
    FROM config_crm_capacity c JOIN final_rank r ON r.position <= c.capacity
    GROUP BY c.capacity, r.objective
),
-- Os segmentos do config (ordem do contrato, com zero quando não há ninguém) e qualquer outro que o modelo devolva.
mix_group AS (
    SELECT segment, bit FROM config_segment
    UNION ALL
    SELECT DISTINCT segment, NULL::INTEGER FROM final_base WHERE segment NOT IN (SELECT segment FROM config_segment)
),
mix_count AS (
    SELECT c.capacity, o.objective, g.segment, g.bit, count(r.household_key) AS customers
    FROM config_crm_capacity c
    CROSS JOIN objectives o
    CROSS JOIN mix_group g
    LEFT JOIN final_rank r ON r.objective = o.objective AND r.segment = g.segment AND r.position <= c.capacity
    GROUP BY ALL
),
mix AS (
    SELECT capacity, objective, list(struct_pack(segment := segment, customers := customers) ORDER BY bit NULLS LAST, segment) AS segment_mix
    FROM mix_count GROUP BY capacity, objective
),
test_base AS (
    SELECT t.household_key, t.snapshot_week, t.label, t.model_score, t.baseline_score,
           value_from_log1p(f.log_value_26w) AS revenue_26s
    FROM churn_test_score t
    JOIN churn_features f ON f.household_key = t.household_key AND f.snapshot_week = t.snapshot_week AND f.role = 'teste'
),
-- ranking = a ordem usada: as duas do modelo e a da regra simples.
test_rank AS (
    SELECT 'pauses' AS ranking, snapshot_week, label, revenue_26s, model_score,
           row_number() OVER (PARTITION BY snapshot_week ORDER BY model_score DESC, household_key) AS position
    FROM test_base
    UNION ALL
    SELECT 'value', snapshot_week, label, revenue_26s, model_score,
           row_number() OVER (PARTITION BY snapshot_week
                              ORDER BY priority_score(model_score, revenue_26s) DESC, household_key)
    FROM test_base
    UNION ALL
    SELECT 'baseline', snapshot_week, label, revenue_26s, model_score,
           row_number() OVER (PARTITION BY snapshot_week
                              ORDER BY baseline_score DESC, revenue_26s DESC, household_key)
    FROM test_base
),
by_snapshot AS (
    SELECT c.capacity, r.ranking, r.snapshot_week,
           precision_at_n(sum(r.label) FILTER (WHERE r.position <= c.capacity), count(*) FILTER (WHERE r.position <= c.capacity)) AS hist_precision,
           recall_at_n(sum(r.label) FILTER (WHERE r.position <= c.capacity), sum(r.label)) AS hist_pauses_caught_share,
           -- Nenhuma pausa real entre os N vale zero, não nulo.
           coalesce(sum(r.revenue_26s) FILTER (WHERE r.label = 1 AND r.position <= c.capacity), 0) AS hist_value_caught,
           share(coalesce(sum(r.revenue_26s) FILTER (WHERE r.label = 1 AND r.position <= c.capacity), 0),
                 sum(r.revenue_26s) FILTER (WHERE r.label = 1)) AS hist_value_caught_share,
           sum(r.model_score) FILTER (WHERE r.position <= c.capacity) AS hist_pauses_expected,
           sum(r.label) FILTER (WHERE r.position <= c.capacity) AS hist_pauses_actual
    FROM config_crm_capacity c CROSS JOIN test_rank r
    GROUP BY ALL
),
history AS (
    SELECT capacity, ranking,
           avg(hist_precision) AS hist_precision, avg(hist_pauses_caught_share) AS hist_pauses_caught_share,
           avg(hist_value_caught) AS hist_value_caught, avg(hist_value_caught_share) AS hist_value_caught_share,
           avg(hist_pauses_expected) AS hist_pauses_expected, avg(hist_pauses_actual) AS hist_pauses_actual
    FROM by_snapshot GROUP BY ALL
)
SELECT h.capacity, o.objective, m.method,
       CASE WHEN m.method = 'model' THEN w.pauses_expected END AS pauses_expected,
       CASE WHEN m.method = 'model' THEN w.revenue_26s_at_stake END AS revenue_26s_at_stake,
       CASE WHEN m.method = 'model' THEN x.segment_mix END AS segment_mix,
       h.hist_precision, h.hist_pauses_caught_share, h.hist_value_caught, h.hist_value_caught_share,
       CASE WHEN m.method = 'model' THEN h.hist_pauses_expected END AS hist_pauses_expected,
       CASE WHEN m.method = 'model' THEN h.hist_pauses_actual END AS hist_pauses_actual
FROM objectives o
CROSS JOIN (VALUES ('model'), ('baseline')) AS m(method)
JOIN history h ON h.ranking = CASE WHEN m.method = 'model' THEN o.objective ELSE 'baseline' END
LEFT JOIN this_week w ON w.capacity = h.capacity AND w.objective = o.objective
LEFT JOIN mix x ON x.capacity = h.capacity AND x.objective = o.objective
