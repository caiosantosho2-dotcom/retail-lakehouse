-- crm_capacity (G45): se o CRM só aciona N clientes, quem priorizar e o que isso protege. Grão: capacidade × método.
-- Ordem: model = priority_score (probabilidade × faturamento de 26 s) decrescente, empate pelo household_key;
--        baseline = mais semanas sem comprar, empate pelo faturamento de 26 s e depois pelo household_key.
-- Esta semana (foto final, só model): soma das probabilidades, faturamento de 26 s e mix de segmentos dos N primeiros.
-- No teste (fotos 85 e 93, média das duas): precision@N e recall@N pela mesma ordem, com a probabilidade do teste e o
-- faturamento de 26 s ATÉ a foto (churn_features, G21), sem nada posterior à foto.
-- Se a população for menor que N, acionam-se todos: "N primeiros" = quem existe.
WITH final_base AS (
    SELECT s.household_key, s.probability, s.segment, value_from_log1p(f.log_value_26w) AS revenue_26s
    FROM churn_score s
    JOIN churn_features f ON f.household_key = s.household_key AND f.role = 'final'
),
final_rank AS (
    SELECT *, row_number() OVER (ORDER BY priority_score(probability, revenue_26s) DESC, household_key) AS position
    FROM final_base
),
this_week AS (
    SELECT c.capacity, sum(r.probability) AS pauses_expected, sum(r.revenue_26s) AS revenue_26s_at_stake
    FROM config_crm_capacity c JOIN final_rank r ON r.position <= c.capacity
    GROUP BY c.capacity
),
-- Os segmentos do config (ordem do contrato, com zero quando não há ninguém) e qualquer outro que o modelo devolva.
mix_group AS (
    SELECT segment, bit FROM config_segment
    UNION ALL
    SELECT DISTINCT segment, NULL::INTEGER FROM final_base WHERE segment NOT IN (SELECT segment FROM config_segment)
),
mix_count AS (
    SELECT c.capacity, g.segment, g.bit, count(r.household_key) AS customers
    FROM config_crm_capacity c
    CROSS JOIN mix_group g
    LEFT JOIN final_rank r ON r.segment = g.segment AND r.position <= c.capacity
    GROUP BY ALL
),
mix AS (
    SELECT capacity, list(struct_pack(segment := segment, customers := customers) ORDER BY bit NULLS LAST, segment) AS segment_mix
    FROM mix_count GROUP BY capacity
),
test_base AS (
    SELECT t.household_key, t.snapshot_week, t.label, t.model_score, t.baseline_score,
           value_from_log1p(f.log_value_26w) AS revenue_26s
    FROM churn_test_score t
    JOIN churn_features f ON f.household_key = t.household_key AND f.snapshot_week = t.snapshot_week AND f.role = 'teste'
),
test_rank AS (
    SELECT 'model' AS method, snapshot_week, label,
           row_number() OVER (PARTITION BY snapshot_week
                              ORDER BY priority_score(model_score, revenue_26s) DESC, household_key) AS position
    FROM test_base
    UNION ALL
    SELECT 'baseline', snapshot_week, label,
           row_number() OVER (PARTITION BY snapshot_week
                              ORDER BY baseline_score DESC, revenue_26s DESC, household_key)
    FROM test_base
),
by_snapshot AS (
    SELECT c.capacity, r.method, r.snapshot_week,
           precision_at_n(sum(r.label) FILTER (WHERE r.position <= c.capacity), count(*) FILTER (WHERE r.position <= c.capacity)) AS hist_precision,
           recall_at_n(sum(r.label) FILTER (WHERE r.position <= c.capacity), sum(r.label)) AS hist_pauses_caught_share
    FROM config_crm_capacity c CROSS JOIN test_rank r
    GROUP BY ALL
),
history AS (
    SELECT capacity, method, avg(hist_precision) AS hist_precision, avg(hist_pauses_caught_share) AS hist_pauses_caught_share
    FROM by_snapshot GROUP BY ALL
)
SELECT h.capacity, h.method,
       CASE WHEN h.method = 'model' THEN w.pauses_expected END AS pauses_expected,
       CASE WHEN h.method = 'model' THEN w.revenue_26s_at_stake END AS revenue_26s_at_stake,
       CASE WHEN h.method = 'model' THEN m.segment_mix END AS segment_mix,
       h.hist_precision, h.hist_pauses_caught_share
FROM history h
LEFT JOIN this_week w ON w.capacity = h.capacity
LEFT JOIN mix m ON m.capacity = h.capacity
