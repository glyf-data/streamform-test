SELECT
    customer_id,
    SUM(amount) AS total_spend
FROM source('orders')
GROUP BY customer_id
