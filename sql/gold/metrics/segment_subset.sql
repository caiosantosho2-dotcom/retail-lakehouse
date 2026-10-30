-- segment_subset: subconjunto do filtro de segmento × grupo que ele inclui (G7).
-- 'todos' (máscara 0, nenhum chip ligado) = os 4 segmentos + "Sem segmento". Os outros 15 são as combinações não vazias
-- dos 4 segmentos, com os nomes na ordem do config unidos por '+' (ex.: 'Fiéis+Regulares'); subset_mask é a máscara de
-- bits (bit = posição do segmento no config). Cada cliente tem um só grupo: o valor de um subconjunto é a soma dos grupos.
WITH masks AS (SELECT unnest(range(1, (SELECT 1 << count(*)::INTEGER FROM config_segment))) AS subset_mask),
names AS (
    SELECT m.subset_mask, string_agg(s.segment, '+' ORDER BY s.bit) AS subset
    FROM masks m JOIN config_segment s ON (m.subset_mask >> s.bit) & 1 = 1
    GROUP BY m.subset_mask
)
SELECT 'todos' AS subset, 0::BIGINT AS subset_mask, segment
FROM (SELECT segment FROM config_segment UNION ALL SELECT getvariable('sem_segmento'))
UNION ALL
SELECT n.subset, n.subset_mask, s.segment
FROM names n JOIN config_segment s ON (n.subset_mask >> s.bit) & 1 = 1
