# QueryMind data dictionary

Source of truth: `pipeline/schema_info.py` and `db/schema.sql`. Dates are ISO text (YYYY-MM-DD).

## customers

Shoppers. city/state is the HOME address on the account, not where orders ship.

| Column | Meaning |
|---|---|
| customer_id | primary key |
| full_name | customer name |
| email | unique email address |
| city | HOME city (use for 'customers in X' or 'X customers') |
| state | home state code |
| segment | standard | prime | business |
| signup_date | YYYY-MM-DD |

## categories

Product categories. parent_category_id gives a two-level tree (e.g. Audio -> Electronics).

| Column | Meaning |
|---|---|
| category_id | primary key |
| name | category name |
| parent_category_id | parent category, NULL for top-level categories |

## products

Products for sale. unit_price is the current list price.

| Column | Meaning |
|---|---|
| product_id | primary key |
| sku | unique SKU |
| name | product name |
| category_id | references categories |
| brand | brand name |
| unit_price | list price |
| cost_price | cost to the store |
| is_active | 1 = listed, 0 = delisted |
| listed_date | YYYY-MM-DD |

## tags

Labels such as eco-friendly or bestseller.

| Column | Meaning |
|---|---|
| tag_id | primary key |
| name | tag name |

## product_tags

Many-to-many link between products and tags.

| Column | Meaning |
|---|---|
| product_id | references products |
| tag_id | references tags |

## orders

One row per order. status: placed, shipped, delivered, cancelled, returned. shipping_city is where the order was sent. total_amount = items - discount + shipping.

| Column | Meaning |
|---|---|
| order_id | primary key |
| customer_id | references customers |
| order_date | YYYY-MM-DD |
| status | placed | shipped | delivered | cancelled | returned |
| shipping_city | city the order was shipped to |
| shipping_state | state the order was shipped to |
| payment_method | card | upi | wallet | cod |
| shipping_fee | shipping charged |
| discount_amount | discount applied |
| total_amount | amount paid for the order |

## order_items

Line items: which products are in which order, and how many.

| Column | Meaning |
|---|---|
| order_item_id | primary key |
| order_id | references orders |
| product_id | references products |
| quantity | units in this line |
| unit_price | price per unit at time of order |
| line_total | quantity * unit_price, before discount |

## payments

Payment attempts for each order. status: captured, failed, refunded.

| Column | Meaning |
|---|---|
| payment_id | primary key |
| order_id | references orders |
| amount | amount charged |
| method | card | upi | wallet | cod |
| paid_at | YYYY-MM-DD |
| status | captured | failed | refunded |

## shipments

Shipment for each order that left the warehouse. delivered_at is NULL until delivered.

| Column | Meaning |
|---|---|
| shipment_id | primary key |
| order_id | references orders |
| carrier | FastShip | MetroExpress | PostLine | SwiftCourier |
| tracking_number | unique tracking number |
| shipped_at | YYYY-MM-DD |
| delivered_at | YYYY-MM-DD, NULL if not yet delivered |

## returns

A return request for one order line.

| Column | Meaning |
|---|---|
| return_id | primary key |
| order_item_id | references order_items |
| reason | damaged | wrong_item | not_as_described | changed_mind |
| requested_at | YYYY-MM-DD |
| refund_amount | amount refunded |

## reviews

Customer ratings of products (1 to 5 stars).

| Column | Meaning |
|---|---|
| review_id | primary key |
| product_id | references products |
| customer_id | references customers |
| rating | 1 to 5 |
| created_at | YYYY-MM-DD |
