-- DataMind evaluation fixture: "retail" (synthetic, written by the DataMind team).
-- Licence: same as this repository. No real people or companies.
-- Four related tables with foreign keys, used to test join and multi-step
-- questions. Loaded into a throwaway DuckDB file by backend/eval/datasets.py;
-- never loaded into Snowflake or the dev database.

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    name         VARCHAR NOT NULL,
    city         VARCHAR NOT NULL,
    signup_year  INTEGER NOT NULL
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    name         VARCHAR NOT NULL,
    category     VARCHAR NOT NULL,
    unit_price   DOUBLE  NOT NULL
);

CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers (customer_id),
    order_date   DATE    NOT NULL,
    status       VARCHAR NOT NULL  -- 'completed' or 'cancelled'
);

CREATE TABLE order_items (
    order_id     INTEGER NOT NULL REFERENCES orders (order_id),
    product_id   INTEGER NOT NULL REFERENCES products (product_id),
    quantity     INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

INSERT INTO customers VALUES
    (1, 'Asha',  'Mumbai', 2023),
    (2, 'Ben',   'Delhi',  2024),
    (3, 'Chen',  'Mumbai', 2024),
    (4, 'Divya', 'Pune',   2025),
    (5, 'Elena', 'Delhi',  2025),
    (6, 'Farah', 'Pune',   2025);   -- has no orders

INSERT INTO products VALUES
    (1, 'Laptop',     'Electronics', 50000),
    (2, 'Phone',      'Electronics', 20000),
    (3, 'Headphones', 'Electronics',  1500),
    (4, 'Desk',       'Furniture',   12000),
    (5, 'Chair',      'Furniture',    2500),
    (6, 'Notebook',   'Stationery',    100);

INSERT INTO orders VALUES
    (101, 1, DATE '2025-01-05', 'completed'),
    (102, 2, DATE '2025-01-17', 'completed'),
    (103, 1, DATE '2025-02-02', 'completed'),
    (104, 3, DATE '2025-02-20', 'cancelled'),
    (105, 4, DATE '2025-03-03', 'completed'),
    (106, 5, DATE '2025-03-15', 'completed'),
    (107, 2, DATE '2025-03-28', 'completed'),
    (108, 3, DATE '2025-04-02', 'completed');

INSERT INTO order_items VALUES
    (101, 1, 1), (101, 3, 2),
    (102, 2, 1), (102, 6, 10),
    (103, 5, 4),
    (104, 1, 1),
    (105, 4, 1), (105, 5, 2),
    (106, 3, 3), (106, 6, 5),
    (107, 2, 2),
    (108, 6, 20), (108, 5, 1);
