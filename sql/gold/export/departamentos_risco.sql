-- departamentos_risco.json: metrics.department_risk (26 s, G4).
-- Ordem: subconjunto (máscara), 'todos' primeiro, departamento.
SELECT subset AS subconjunto, department AS departamento, ROUND(money_at_risk, 2) AS dinheiro_em_risco,
       ROUND(money_at_risk_share, 4) AS dinheiro_em_risco_pct
FROM department_risk
ORDER BY subset_mask, department = 'todos' DESC, department
