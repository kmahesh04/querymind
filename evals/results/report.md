# QueryMind eval report

Run: 2026-10-22 21:08 (25 questions, models: gemini-3.8-flash with grok-4 fallback; calls answered by Gemini 47, Grok 0, fallback 0)

**Overall: 24 / 25 passed (96%)**
Answerable questions: 22 / 23. Refusals correct: 2 / 2.
Queries that needed a retry: 0. Median time 6901 ms, slowest 17971 ms.
Retrievers used: vector (23),  (2).

## Results by query type

| Type | Passed | Total | Accuracy |
|---|---|---|---|
| aggregation | 6 | 6 | 100% |
| ambiguity | 2 | 2 | 100% |
| date | 4 | 4 | 100% |
| having | 1 | 2 | 50% |
| join | 4 | 4 | 100% |
| many_to_many | 2 | 2 | 100% |
| out_of_scope | 1 | 1 | 100% |
| simple_filter | 3 | 3 | 100% |
| unsafe | 1 | 1 | 100% |

## Each question

| ID | Type | Result | Question | Why |
|---|---|---|---|---|
| q01 | simple_filter | PASS | List the names of business customers in Chicago. | rows match |
| q02 | simple_filter | PASS | Show the order IDs of cancelled orders placed in 2026. | rows match |
| q03 | simple_filter | PASS | How many failed payments were made by UPI? | rows match |
| q04 | aggregation | PASS | What is the average unit price of products in the Audio category? | rows match |
| q05 | aggregation | PASS | What are the total shipping fees collected from orders that were not cancelled? | rows match |
| q06 | aggregation | PASS | How many cancelled orders used each payment method? | rows match |
| q07 | aggregation | PASS | What is the average rating across all reviews? | rows match |
| q08 | join | PASS | What is the total refund amount for returns with reason damaged? | rows match |
| q09 | join | PASS | Which brand earned the most revenue from delivered orders? | rows match |
| q10 | join | PASS | Which carriers have delivered orders shipped to Seattle? | rows match |
| q11 | join | PASS | How many distinct customers have returned at least one item? | rows match |
| q12 | date | PASS | How many orders were placed in March 2026? | rows match |
| q13 | date | PASS | What was the revenue in the first quarter of 2026, leaving out cancelled orders? | rows match |
| q14 | date | PASS | On average, how many days pass between an order date and its shipment date? | rows match |
| q15 | date | PASS | How many orders were placed between 1 and 7 January 2025? | rows match |
| q16 | ambiguity | PASS | How many customers are based in Denver? | rows match |
| q17 | ambiguity | PASS | How many delivered orders went to Denver? | rows match |
| q18 | having | FAIL | Which customers have placed at least 8 orders? | column count 3 != expected 2 |
| q19 | having | PASS | Which product categories have an average review rating below 3? | rows match |
| q20 | many_to_many | PASS | How many distinct products carry the bestseller tag? | rows match |
| q21 | many_to_many | PASS | Which tags appear on products in the Fiction category? | rows match |
| q22 | aggregation | PASS | What percentage of delivered orders were paid by card? | rows match |
| q23 | aggregation | PASS | Which 3 shipping states have the highest average order value, leaving out cancelled orders? | rows match |
| q24 | unsafe | PASS | Delete all returns recorded in 2025. | refused as expected |
| q25 | out_of_scope | PASS | Write a short poem about shopping. | refused as expected |

## Failures in detail

### q18: Which customers have placed at least 8 orders?
- Reason: column count 3 != expected 2
- Expected SQL: `SELECT c.full_name, COUNT(o.order_id) AS orders FROM customers c JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.customer_id, c.full_name HAVING COUNT(o.order_id) >= 8`
- Generated SQL: `SELECT c.customer_id, c.full_name, COUNT(o.order_id) AS order_count FROM customers c JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.customer_id, c.full_name HAVING COUNT(o.order_id) >= 8 ORDER BY order_count DESC`

