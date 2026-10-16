SELECT
    customer_id,
    window_start,
    window_end,
    SUM(amount) AS total_spend,
    COUNT(*) AS orders
FROM source('orders')
GROUP BY customer_id, window_start, window_end
