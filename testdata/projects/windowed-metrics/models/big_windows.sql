SELECT
    customer_id,
    window_start,
    total_spend
FROM ref('spend_per_5m')
WHERE total_spend > 100
