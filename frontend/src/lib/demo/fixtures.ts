/**
 * DEMO FIXTURES — not live data.
 *
 * Used only when demo mode is switched on, so the interface can be explored without a
 * backend. Every screen that shows these values carries a visible "Demo" label.
 * Table and column names mirror SNOWFLAKE_SAMPLE_DATA.TPCH_SF1; result values are
 * illustrative and were NOT produced by executing the SQL shown.
 */
import type { HealthResponse, QueryResponse, SchemaResponse } from "../api-types";

export const DEMO_PROVIDER = "demo";

export const demoHealth: HealthResponse = {
  status: "ok",
  version: "demo",
  providers: [
    {
      id: DEMO_PROVIDER,
      label: "Demo dataset",
      connected: true,
      is_default: true,
      detail: "Sample fixtures bundled with the frontend",
      database: "SNOWFLAKE_SAMPLE_DATA",
      schema: "TPCH_SF1",
    },
  ],
  model: null,
  row_limit: 1000,
};

const col = (name: string, data_type: string, description?: string) => ({ name, data_type, description });

export const demoSchema: SchemaResponse = {
  provider: DEMO_PROVIDER,
  database: "SNOWFLAKE_SAMPLE_DATA",
  schemas: [
    {
      name: "TPCH_SF1",
      tables: [
        {
          name: "CUSTOMER",
          row_count: 150000,
          columns: [
            col("C_CUSTKEY", "NUMBER(38,0)"),
            col("C_NAME", "VARCHAR(25)"),
            col("C_ADDRESS", "VARCHAR(40)"),
            col("C_NATIONKEY", "NUMBER(38,0)"),
            col("C_PHONE", "VARCHAR(15)"),
            col("C_ACCTBAL", "NUMBER(12,2)"),
            col("C_MKTSEGMENT", "VARCHAR(10)"),
            col("C_COMMENT", "VARCHAR(117)"),
          ],
        },
        {
          name: "ORDERS",
          row_count: 1500000,
          columns: [
            col("O_ORDERKEY", "NUMBER(38,0)"),
            col("O_CUSTKEY", "NUMBER(38,0)"),
            col("O_ORDERSTATUS", "VARCHAR(1)"),
            col("O_TOTALPRICE", "NUMBER(12,2)"),
            col("O_ORDERDATE", "DATE"),
            col("O_ORDERPRIORITY", "VARCHAR(15)"),
            col("O_CLERK", "VARCHAR(15)"),
            col("O_SHIPPRIORITY", "NUMBER(38,0)"),
            col("O_COMMENT", "VARCHAR(79)"),
          ],
        },
        {
          name: "LINEITEM",
          row_count: 6001215,
          columns: [
            col("L_ORDERKEY", "NUMBER(38,0)"),
            col("L_PARTKEY", "NUMBER(38,0)"),
            col("L_SUPPKEY", "NUMBER(38,0)"),
            col("L_LINENUMBER", "NUMBER(38,0)"),
            col("L_QUANTITY", "NUMBER(12,2)"),
            col("L_EXTENDEDPRICE", "NUMBER(12,2)"),
            col("L_DISCOUNT", "NUMBER(12,2)"),
            col("L_TAX", "NUMBER(12,2)"),
            col("L_RETURNFLAG", "VARCHAR(1)"),
            col("L_LINESTATUS", "VARCHAR(1)"),
            col("L_SHIPDATE", "DATE"),
            col("L_COMMITDATE", "DATE"),
            col("L_RECEIPTDATE", "DATE"),
            col("L_SHIPINSTRUCT", "VARCHAR(25)"),
            col("L_SHIPMODE", "VARCHAR(10)"),
            col("L_COMMENT", "VARCHAR(44)"),
          ],
        },
        {
          name: "PART",
          row_count: 200000,
          columns: [
            col("P_PARTKEY", "NUMBER(38,0)"),
            col("P_NAME", "VARCHAR(55)"),
            col("P_MFGR", "VARCHAR(25)"),
            col("P_BRAND", "VARCHAR(10)"),
            col("P_TYPE", "VARCHAR(25)"),
            col("P_SIZE", "NUMBER(38,0)"),
            col("P_CONTAINER", "VARCHAR(10)"),
            col("P_RETAILPRICE", "NUMBER(12,2)"),
            col("P_COMMENT", "VARCHAR(23)"),
          ],
        },
        {
          name: "SUPPLIER",
          row_count: 10000,
          columns: [
            col("S_SUPPKEY", "NUMBER(38,0)"),
            col("S_NAME", "VARCHAR(25)"),
            col("S_ADDRESS", "VARCHAR(40)"),
            col("S_NATIONKEY", "NUMBER(38,0)"),
            col("S_PHONE", "VARCHAR(15)"),
            col("S_ACCTBAL", "NUMBER(12,2)"),
            col("S_COMMENT", "VARCHAR(101)"),
          ],
        },
        {
          name: "PARTSUPP",
          row_count: 800000,
          columns: [
            col("PS_PARTKEY", "NUMBER(38,0)"),
            col("PS_SUPPKEY", "NUMBER(38,0)"),
            col("PS_AVAILQTY", "NUMBER(38,0)"),
            col("PS_SUPPLYCOST", "NUMBER(12,2)"),
            col("PS_COMMENT", "VARCHAR(199)"),
          ],
        },
        {
          name: "NATION",
          row_count: 25,
          columns: [col("N_NATIONKEY", "NUMBER(38,0)"), col("N_NAME", "VARCHAR(25)"), col("N_REGIONKEY", "NUMBER(38,0)"), col("N_COMMENT", "VARCHAR(152)")],
        },
        {
          name: "REGION",
          row_count: 5,
          columns: [col("R_REGIONKEY", "NUMBER(38,0)"), col("R_NAME", "VARCHAR(25)"), col("R_COMMENT", "VARCHAR(152)")],
        },
      ],
    },
  ],
};

export const demoSuggestions = [
  "Which regions generate the most revenue?",
  "How has total order value changed by year?",
  "Show the top 10 customers by total spending.",
  "How many customers are in each market segment?",
  "How many orders are there in total?",
];

type Fixture = { match: RegExp; build: (question: string) => Omit<QueryResponse, "query_id"> };

const base = { provider: DEMO_PROVIDER, executed: false } as const;
const execution = { database: "SNOWFLAKE_SAMPLE_DATA", schema: "TPCH_SF1", duration_ms: null, provider_query_id: null };
const validation = (limit: number | null = 1000) => ({ passed: true, read_only: true, limit_applied: limit, messages: [] });

export const demoFixtures: Fixture[] = [
  {
    match: /\b(delete|drop|truncate|update|insert|alter|grant|create)\b/i,
    build: (q) => ({
      ...base,
      status: "refused",
      question: q,
      answer:
        "DataMind only runs read-only questions. Requests that would change or delete data are refused before any SQL is generated.",
      validation: { passed: false, read_only: false, limit_applied: null, messages: ["Write or DDL intent detected in the question."] },
    }),
  },
  {
    match: /\b(weather|temperature|stock price|employees?|salary|salaries)\b/i,
    build: (q) => ({
      ...base,
      status: "refused",
      question: q,
      answer:
        "The connected dataset (TPC-H orders, customers, parts, suppliers) does not contain this information, so DataMind cannot answer it without guessing.",
      explanation: { tables: [], filters: [], assumptions: ["Checked the question against the available tables and columns."] },
    }),
  },
  {
    match: /\bbest customers?\b|\btop customers?\b(?!.*\b(spend|spending|revenue|value|orders?)\b)/i,
    build: (q) => ({
      ...base,
      status: "clarification_needed",
      question: q,
      clarification: {
        question: "“Best” can be measured in different ways. Which one do you mean?",
        options: [
          "Show the top 10 customers by total spending.",
          "Show the top 10 customers by number of orders.",
          "Show the top 10 customers by account balance.",
        ],
      },
    }),
  },
  {
    match: /\b20(1\d|2\d)\b/,
    build: (q) => ({
      ...base,
      status: "success",
      question: q,
      answer: "No orders match that period. The ORDERS table only contains order dates between 1992 and 1998.",
      explanation: {
        summary: "Filtered ORDERS by the requested year and counted matching rows.",
        tables: ["TPCH_SF1.ORDERS"],
        filters: ["YEAR(O_ORDERDATE) = requested year"],
        assumptions: ["Interpreted the year as the order date, not the ship date."],
      },
      sql: "SELECT O_ORDERKEY, O_ORDERDATE, O_TOTALPRICE\nFROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS\nWHERE YEAR(O_ORDERDATE) = 2025\nLIMIT 1000",
      validation: validation(),
      columns: [
        { name: "O_ORDERKEY", data_type: "NUMBER" },
        { name: "O_ORDERDATE", data_type: "DATE" },
        { name: "O_TOTALPRICE", data_type: "NUMBER" },
      ],
      rows: [],
      row_count: 0,
      truncated: false,
      execution,
    }),
  },
  {
    match: /region/i,
    build: (q) => ({
      ...base,
      status: "success",
      question: q,
      answer:
        "Europe and Asia lead revenue in this sample, with the five regions within a few percent of each other. Revenue is the sum of discounted line-item prices.",
      explanation: {
        summary: "Joined line items to orders, customers, nations and regions, then summed discounted revenue per region.",
        tables: ["TPCH_SF1.LINEITEM", "TPCH_SF1.ORDERS", "TPCH_SF1.CUSTOMER", "TPCH_SF1.NATION", "TPCH_SF1.REGION"],
        filters: ["None (all years)"],
        assumptions: ["Revenue = L_EXTENDEDPRICE × (1 − L_DISCOUNT).", "Region is taken from the customer's nation."],
      },
      sql: `SELECT r.R_NAME AS REGION,
       SUM(l.L_EXTENDEDPRICE * (1 - l.L_DISCOUNT)) AS REVENUE
FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.LINEITEM l
JOIN SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS o ON o.O_ORDERKEY = l.L_ORDERKEY
JOIN SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER c ON c.C_CUSTKEY = o.O_CUSTKEY
JOIN SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.NATION n ON n.N_NATIONKEY = c.C_NATIONKEY
JOIN SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.REGION r ON r.R_REGIONKEY = n.N_REGIONKEY
GROUP BY r.R_NAME
ORDER BY REVENUE DESC
LIMIT 1000`,
      validation: validation(),
      columns: [
        { name: "REGION", data_type: "VARCHAR" },
        { name: "REVENUE", data_type: "NUMBER" },
      ],
      rows: [
        { REGION: "EUROPE", REVENUE: 43750214321.47 },
        { REGION: "ASIA", REVENUE: 43581020498.12 },
        { REGION: "AMERICA", REVENUE: 43402316987.9 },
        { REGION: "MIDDLE EAST", REVENUE: 43251189004.55 },
        { REGION: "AFRICA", REVENUE: 43109876544.31 },
      ],
      row_count: 5,
      truncated: false,
      execution,
    }),
  },
  {
    match: /(year|over time|trend|changed)/i,
    build: (q) => ({
      ...base,
      status: "success",
      question: q,
      answer:
        "Total order value is roughly flat from 1992 to 1997. 1998 is much lower because the dataset only covers part of that year.",
      explanation: {
        summary: "Grouped ORDERS by the year of O_ORDERDATE and summed O_TOTALPRICE.",
        tables: ["TPCH_SF1.ORDERS"],
        filters: ["None (all years)"],
        assumptions: ["Order value uses O_TOTALPRICE as recorded on the order.", "1998 is a partial year in this dataset."],
      },
      sql: `SELECT YEAR(O_ORDERDATE) AS ORDER_YEAR,
       SUM(O_TOTALPRICE) AS TOTAL_ORDER_VALUE,
       COUNT(*) AS ORDERS
FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS
GROUP BY ORDER_YEAR
ORDER BY ORDER_YEAR
LIMIT 1000`,
      validation: validation(),
      columns: [
        { name: "ORDER_YEAR", data_type: "NUMBER" },
        { name: "TOTAL_ORDER_VALUE", data_type: "NUMBER" },
        { name: "ORDERS", data_type: "NUMBER" },
      ],
      rows: [
        { ORDER_YEAR: 1992, TOTAL_ORDER_VALUE: 34643481208.62, ORDERS: 228091 },
        { ORDER_YEAR: 1993, TOTAL_ORDER_VALUE: 34567299401.18, ORDERS: 227598 },
        { ORDER_YEAR: 1994, TOTAL_ORDER_VALUE: 34692140773.04, ORDERS: 228483 },
        { ORDER_YEAR: 1995, TOTAL_ORDER_VALUE: 34601187550.77, ORDERS: 228273 },
        { ORDER_YEAR: 1996, TOTAL_ORDER_VALUE: 34785002118.4, ORDERS: 228626 },
        { ORDER_YEAR: 1997, TOTAL_ORDER_VALUE: 34531226947.95, ORDERS: 227089 },
        { ORDER_YEAR: 1998, TOTAL_ORDER_VALUE: 20296519384.11, ORDERS: 131840 },
      ],
      row_count: 7,
      truncated: false,
      warnings: ["1998 contains only part of a year of orders; compare it with care."],
      execution,
    }),
  },
  {
    match: /customers?\b.*\b(spend|spending|spent)\b/i,
    build: (q) => ({
      ...base,
      status: "success",
      question: q,
      answer:
        "The ten highest-spending customers each placed orders worth more than $6.5M in total. Customer#000143500 leads the list.",
      explanation: {
        summary: "Summed O_TOTALPRICE per customer across all orders and kept the ten largest totals.",
        tables: ["TPCH_SF1.ORDERS", "TPCH_SF1.CUSTOMER"],
        filters: ["None (all years)"],
        assumptions: ["Spending = sum of order totals (O_TOTALPRICE), including tax and discounts as recorded."],
      },
      sql: `SELECT c.C_NAME AS CUSTOMER,
       c.C_MKTSEGMENT AS SEGMENT,
       SUM(o.O_TOTALPRICE) AS TOTAL_SPENT
FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER c
JOIN SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS o ON o.O_CUSTKEY = c.C_CUSTKEY
GROUP BY c.C_NAME, c.C_MKTSEGMENT
ORDER BY TOTAL_SPENT DESC
LIMIT 10`,
      validation: validation(10),
      columns: [
        { name: "CUSTOMER", data_type: "VARCHAR" },
        { name: "SEGMENT", data_type: "VARCHAR" },
        { name: "TOTAL_SPENT", data_type: "NUMBER" },
      ],
      rows: [
        { CUSTOMER: "Customer#000143500", SEGMENT: "HOUSEHOLD", TOTAL_SPENT: 7012696.48 },
        { CUSTOMER: "Customer#000095257", SEGMENT: "MACHINERY", TOTAL_SPENT: 6563511.23 },
        { CUSTOMER: "Customer#000087115", SEGMENT: "BUILDING", TOTAL_SPENT: 6457526.26 },
        { CUSTOMER: "Customer#000131113", SEGMENT: "FURNITURE", TOTAL_SPENT: 6311428.86 },
        { CUSTOMER: "Customer#000103834", SEGMENT: "AUTOMOBILE", TOTAL_SPENT: 6306524.23 },
        { CUSTOMER: "Customer#000069682", SEGMENT: "HOUSEHOLD", TOTAL_SPENT: 6286562.1 },
        { CUSTOMER: "Customer#000102022", SEGMENT: "BUILDING", TOTAL_SPENT: 6273787.71 },
        { CUSTOMER: "Customer#000098587", SEGMENT: "MACHINERY", TOTAL_SPENT: 6265089.35 },
        { CUSTOMER: "Customer#000044485", SEGMENT: "FURNITURE", TOTAL_SPENT: 6100120.01 },
        { CUSTOMER: "Customer#000064004", SEGMENT: "AUTOMOBILE", TOTAL_SPENT: 6081953.64 },
      ],
      row_count: 10,
      truncated: false,
      execution,
    }),
  },
  {
    match: /segment/i,
    build: (q) => ({
      ...base,
      status: "success",
      question: q,
      answer: "Customers are spread almost evenly across the five market segments, about 30,000 each.",
      explanation: {
        summary: "Counted CUSTOMER rows per C_MKTSEGMENT.",
        tables: ["TPCH_SF1.CUSTOMER"],
        filters: ["None"],
        assumptions: [],
      },
      sql: `SELECT C_MKTSEGMENT AS MARKET_SEGMENT,
       COUNT(*) AS CUSTOMERS
FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER
GROUP BY C_MKTSEGMENT
ORDER BY CUSTOMERS DESC
LIMIT 1000`,
      validation: validation(),
      columns: [
        { name: "MARKET_SEGMENT", data_type: "VARCHAR" },
        { name: "CUSTOMERS", data_type: "NUMBER" },
      ],
      rows: [
        { MARKET_SEGMENT: "HOUSEHOLD", CUSTOMERS: 30189 },
        { MARKET_SEGMENT: "BUILDING", CUSTOMERS: 30142 },
        { MARKET_SEGMENT: "FURNITURE", CUSTOMERS: 29968 },
        { MARKET_SEGMENT: "MACHINERY", CUSTOMERS: 29949 },
        { MARKET_SEGMENT: "AUTOMOBILE", CUSTOMERS: 29752 },
      ],
      row_count: 5,
      truncated: false,
      execution,
    }),
  },
  {
    match: /how many orders/i,
    build: (q) => ({
      ...base,
      status: "success",
      question: q,
      answer: "There are 1,500,000 orders in the ORDERS table.",
      explanation: { summary: "Counted all rows in ORDERS.", tables: ["TPCH_SF1.ORDERS"], filters: ["None"], assumptions: [] },
      sql: "SELECT COUNT(*) AS TOTAL_ORDERS\nFROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS",
      validation: validation(null),
      columns: [{ name: "TOTAL_ORDERS", data_type: "NUMBER" }],
      rows: [{ TOTAL_ORDERS: 1500000 }],
      row_count: 1,
      truncated: false,
      execution,
    }),
  },
];
