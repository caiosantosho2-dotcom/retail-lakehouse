-- calendar: um dia da dim_date (sem o membro -1), com a marca de semana completa (G11).
SELECT day, date, week_no, days_in_week, is_complete_week
FROM dim_date
WHERE day <> -1
