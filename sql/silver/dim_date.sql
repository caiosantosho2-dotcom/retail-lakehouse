-- dim_date: um dia. Dimensão conformada (shared).
-- week_no vem do arquivo, nunca calculado a partir do day: as semanas começam no day 6, 13, 20... (gabarito).
-- O código confere antes que cada day tem um só week_no (mais de um = erro, não escolha arbitrária).
-- day_of_cycle: 1 a 7, com 1 no primeiro dia da semana do arquivo (day 6, 13, ...). Sem nome de dia (P4).
-- days_in_week / is_complete_week (G11): dias da semana presentes na base; a semana 1 tem 5 e a 102 tem 6.
WITH dias AS (
    SELECT day, any_value(week_no) AS week_no
    FROM clean_transaction_data
    GROUP BY day
)
SELECT
    day,
    (getvariable('data_base') + (day - 1))::DATE  AS date,
    week_no,
    month(getvariable('data_base') + (day - 1))::INTEGER AS month,
    year(getvariable('data_base') + (day - 1))::INTEGER  AS year,
    (((day - 6) % 7 + 7) % 7 + 1)::INTEGER       AS day_of_cycle,
    (count(*) OVER (PARTITION BY week_no))::INTEGER AS days_in_week,
    count(*) OVER (PARTITION BY week_no) = 7      AS is_complete_week
FROM dias
UNION ALL
SELECT -1, NULL, NULL, NULL, NULL, NULL, NULL, NULL
