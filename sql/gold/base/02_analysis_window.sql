-- analysis_window: uma linha com a janela dos modelos (equivale a vw_janela do RAG).
-- Termina na última semana completa (G11); a janela do ano anterior são as mesmas semanas - offset.
WITH fim AS (
    SELECT max(week_no) AS week_end_current FROM calendar WHERE is_complete_week
),
j AS (
    SELECT week_end_current - getvariable('janela_semanas') + 1                              AS week_start_current,
           week_end_current,
           week_end_current - getvariable('janela_semanas') + 1 - getvariable('offset_semanas') AS week_start_prior,
           week_end_current - getvariable('offset_semanas')                                    AS week_end_prior,
           getvariable('offset_semanas')       AS offset_weeks,
           getvariable('janela_semanas')       AS weeks,
           getvariable('cliente_ativo_semanas') AS active_weeks
    FROM fim
)
SELECT j.*,
       max(c.date) FILTER (WHERE c.week_no BETWEEN j.week_start_current AND j.week_end_current) AS date_end_current,
       max(c.date) FILTER (WHERE c.week_no BETWEEN j.week_start_prior AND j.week_end_prior)     AS date_end_prior
FROM j CROSS JOIN calendar c
GROUP BY ALL
