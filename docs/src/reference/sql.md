# SQL you can test

The engine runs a focused, streaming subset of SQL. Anything outside it is refused before the test runs, with a message naming the construct: `uses a join, which is not supported yet`. Nothing is silently changed.

## Supported

| | |
|---|---|
| Reading | `FROM source('name')`; one source per query |
| Projection | Columns, aliases (`AS`), `SELECT *`, arithmetic (`+ - * /`), `CAST`, `CASE`, `\|\|` |
| Functions | `COALESCE`, `NULLIF`, `UPPER`, `LOWER`, `TRIM`, `LTRIM`, `RTRIM`, `CHAR_LENGTH` (also `LENGTH`), `ABS`, each with Apache Flink's meaning: `CONCAT` and `\|\|` are NULL when any argument is, `TRIM` removes spaces only |
| Filtering | `WHERE` with `= <> < <= > >=`, `AND`, `OR`, `NOT`, `IS NULL`, `IS NOT NULL`, `[NOT] BETWEEN`, `[NOT] IN (...)`, `[NOT] LIKE 'pattern'` |
| Aggregation | `GROUP BY` columns or expressions (or a `SELECT` alias) with `SUM`, `COUNT`, `COUNT(*)`, `COUNT(DISTINCT x)`, `MIN`, `MAX`, `AVG`. `AVG` has Flink's type: an integer average is an integer, truncated toward zero; a decimal one keeps at least six decimal places |
| After aggregation | `HAVING`, a filter over the aggregate, which deletes a row when it stops matching |
| Windows | Tumbling windows of event time, with `window="5m"`, grouping by `window_start` and `window_end` |
| Literals | Integers, decimals, strings, booleans, `NULL` |

## Not supported yet

| | |
|---|---|
| Joins | From `StreamSQL`, which delivers every event to one source. A Streamform project can join two inputs with an inner `JOIN ... ON` and test it with fixtures that name each event's source |
| Set and row operations | `UNION`, `DISTINCT`, `LIMIT`, `ORDER BY` |
| Expressions | `ILIKE`, `LIKE ... ESCAPE`, `SUBSTRING`, `ROUND`, date functions |
| Aggregates | `DISTINCT` inside an aggregate other than `COUNT`, `FILTER` inside an aggregate |
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
