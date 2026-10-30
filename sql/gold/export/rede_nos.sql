-- rede_nos.json: metrics.network_node (posições já normalizadas na gold). Ordem: nó.
SELECT node AS no, department AS departamento, subcategory AS subcategoria, ROUND(revenue, 2) AS faturamento,
       ROUND(x, 4) AS x, ROUND(y, 4) AS y
FROM network_node
ORDER BY node
