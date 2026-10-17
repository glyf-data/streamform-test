# SQL you can test

The engine runs a focused, streaming subset of SQL. Anything outside it is refused before the test runs, with a message naming the construct: `uses a join, which is not supported yet`. Nothing is silently changed.

## Supported

| | |
|---|---|
| Reading | `FROM source('name')`; one source per query |
| Projection | Columns, aliases (`AS`), `SELECT *`, arithmetic (`+ - * /`), `CAST` |
| Filtering | `WHERE` with `= <> < <= > >=`, `AND`, `OR`, `NOT`, `IS NULL`, `IS NOT NULL` |
| Aggregation | `GROUP BY` columns with `SUM`, `COUNT`, `COUNT(*)`, `MIN`, `MAX` |
| After aggregation | `HAVING`, a filter over the aggregate, which deletes a row when it stops matching |
| Windows | Tumbling windows of event time, with `window="5m"`, grouping by `window_start` and `window_end` |
| Literals | Integers, decimals, strings, booleans, `NULL` |

## Not supported yet

| | |
|---|---|
| Joins | `JOIN` of any kind |
| Set and row operations | `UNION`, `DISTINCT`, `LIMIT`, `ORDER BY` |
| Expressions | `CASE`, `IN`, `BETWEEN`, scalar functions (`UPPER`, `COALESCE`, date functions) |
| Aggregates | `AVG` (compute `SUM(x)` and `COUNT(*)` instead), `DISTINCT` or `FILTER` inside an aggregate |
| Analytic windows | `OVER (...)` window functions; sliding and session windows |

Each query reads one source. In a Streamform project, a model can also read another model with `ref('name')`, which is how multi-step pipelines are built and tested.

## Types

| Source type | SQL type |
|---|---|
| `int32`, `int64` | integer |
| `float64` | double |
| `decimal`, `decimal(p,s)` | exact decimal; a bare `decimal` is `decimal(38,9)`, and `SUM` keeps the declared scale |
| `string` | string |
| `boolean` | boolean |
| `timestamp` | timestamp with milliseconds, in UTC |
