-- customer_group: o grupo de cada cliente (G7): o segmento do RFM de 26 s (models/customer_segment), fixo para todo o
-- histórico e todos os períodos; quem não foi segmentado fica em "Sem segmento". Clientes = household (2.500, G13).
SELECT h.household_key, coalesce(s.segment, getvariable('sem_segmento')) AS segment
FROM household h
LEFT JOIN customer_segment s ON s.household_key = h.household_key
