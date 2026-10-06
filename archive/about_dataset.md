About Dataset
Meridian Supply Chain Dataset
A synthetic, multi-table relational dataset modeling the end-to-end supply chain of Meridian Components, a fictional mid-size industrial manufacturer of engineered parts across five categories: Fasteners, Bearings, Casings, Electronics, and Hydraulics. It spans two full years (2024–2025) of procurement, inventory, production, and logistics operations.

The dataset is designed for teaching and practicing data analysis — from beginner SQL joins and aggregations to advanced time-series, cohort, correlation, and anomaly analysis. Because it is fully relational (11 tables with real primary/foreign keys), it also works as a hands-on data-warehousing exercise: learners can start from the normalized operational tables and build their own star schema (facts + dimensions).

What's inside
11 tables, 85 columns, ~45,000 rows

Entity tables

product (40) — SKU, category, cost, list price, ABC class, hazardous flag, shelf life
supplier (20) — tier, country, lead time, quality rating, payment terms, single-source flag
warehouse (4) — region, capacity, operating cost, automation level
customer (30) — industry segment, region, priority tier, credit limit, contract type
carrier (4) — transport mode, cost per kg, transit days, CO₂ per km, reliability
Transaction tables (header / line)

purchase_order / purchase_order_line — procurement, with qty received/rejected
shipment / shipment_line — outbound logistics, with revenue and freight cost
inventory_snapshot — weekly stock levels, reorder points, reserved & in-transit units
production_run — output, defects, downtime, labor hours, shift
Relationships
Products, suppliers, customers, warehouses, and carriers link to the transaction tables via foreign keys. Purchase orders and shipments use a header/line structure that mirrors real operational systems.

Example analysis questions
Which suppliers cause the most delivery delay?
What's the gross margin by product category? (some may be negative)
How do stockouts cluster with seasonal demand?
Does supplier tier actually predict quality — or does reject rate tell a different story?
What's the cost vs CO₂ trade-off across transport modes?
Built-in analytical patterns
Realistic, discoverable signals are intentionally embedded: a small group of chronically late suppliers, seasonal demand (August dip, Q4 peak), a noisy tier-to-quality correlation, and at least one negative-margin category. This ensures analysis yields genuine findings rather than noise.

Suitable for
SQL practice · pandas / Python analytics · BI dashboards (Power BI, Tableau, Looker Studio) · data modeling & warehousing exercises · teaching and coursework.