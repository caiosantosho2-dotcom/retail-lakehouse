-- dim_store: uma loja. Lojas distintas da venda + membro desconhecido -1 (P2).
SELECT DISTINCT store_id FROM clean_transaction_data
UNION ALL
SELECT -1
