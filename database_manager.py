"""
database_manager.py — Consolidated Database Layer
===================================================
Single store.db with two tables:
  • products      – Inventory master data (name, price, quantity, last_restocked)
  • transactions  – Billing transaction log (phone, items_json, total_amount)

All SQL queries are centralised here. Thread-safe via short-lived connections.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "store.db"

# ── Seed Data (migrated from PRICE_BOOK) ─────────────────────────────────────
SEED_PRODUCTS = {
    "Blue_Lays": 20.00,
    "Bournvita": 75.00,
    "Britannia 50-50 Sweet and Salty Biscuits": 30.00,
    "Coca_Cola_Can": 40.00,
    "Dabur_Red_Toothpaste": 55.00,
    "Diet_Coke": 50.00,
    "Knorr_Soupy_Noodles": 15.00,
    "Maggi_Noodles": 14.00,
    "Nescafe_Classic_Coffee": 150.00,
    "Oreo_Biscuit": 30.00,
    "Parachute_Coconut_Oil": 60.00,
    "Parle_G_Biscuit": 10.00,
    "Pepsi_Cola": 40.00,
    "Sprite": 40.00,
    "Top_Ramen": 15.00,
    "Tresemme_Hairfall_Defense_conditioner": 350.00,
    "Tresemme_Hairfall_Defense_shampoo": 380.00,
    "Vaseline": 120.00,
    "Yellow_Lays": 20.00,
}

DEFAULT_SEED_QTY = 10  # Initial stock per seeded product


# ── Connection Helper ────────────────────────────────────────────────────────
def _con():
    """Return a new short-lived connection (auto-commit disabled)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read/write
    return conn


# ── Initialisation ───────────────────────────────────────────────────────────
def init_db():
    """Create tables if they don't exist and seed the product catalogue."""
    con = _con()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT    NOT NULL UNIQUE,
            price          REAL    NOT NULL DEFAULT 0.0,
            quantity       INTEGER NOT NULL DEFAULT 0,
            last_restocked TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL,
            customer_phone  TEXT,
            items_json      TEXT    NOT NULL,
            total_amount    REAL    NOT NULL
        )
    """)

    # Seed products (INSERT OR IGNORE so existing data is preserved)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for name, price in SEED_PRODUCTS.items():
        cur.execute(
            """INSERT OR IGNORE INTO products (name, price, quantity, last_restocked)
               VALUES (?, ?, ?, ?)""",
            (name, price, DEFAULT_SEED_QTY, ts),
        )

    con.commit()
    con.close()


# ── Product Queries ──────────────────────────────────────────────────────────
def get_product(name: str) -> dict | None:
    """Fetch a single product by exact name. Returns dict or None."""
    con = _con()
    cur = con.execute(
        "SELECT id, name, price, quantity, last_restocked FROM products WHERE name = ?",
        (name,),
    )
    row = cur.fetchone()
    con.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "price": row[2],
        "quantity": row[3],
        "last_restocked": row[4],
    }


def get_all_products() -> pd.DataFrame:
    """Return all products as a DataFrame."""
    con = _con()
    df = pd.read_sql_query(
        """SELECT id, name AS 'Name', price AS 'Price (₹)',
                  quantity AS 'Qty',
                  CASE WHEN quantity > 0 THEN 'In Stock' ELSE 'Out of Stock' END AS 'Status',
                  last_restocked AS 'Last Restocked'
           FROM products ORDER BY quantity DESC""",
        con,
    )
    con.close()
    return df


def get_low_stock(threshold: int = 2) -> pd.DataFrame:
    """Return products with quantity <= threshold."""
    con = _con()
    df = pd.read_sql_query(
        """SELECT name AS 'Name', price AS 'Price (₹)', quantity AS 'Qty',
                  last_restocked AS 'Last Restocked'
           FROM products WHERE quantity <= ? ORDER BY quantity ASC""",
        con,
        params=(threshold,),
    )
    con.close()
    return df


def search_products(query: str) -> pd.DataFrame:
    """Search products by name (case-insensitive partial match)."""
    con = _con()
    df = pd.read_sql_query(
        """SELECT name AS 'Name', price AS 'Price (₹)', quantity AS 'Qty',
                  CASE WHEN quantity > 0 THEN 'In Stock' ELSE 'Out of Stock' END AS 'Status',
                  last_restocked AS 'Last Restocked'
           FROM products WHERE name LIKE ? ORDER BY quantity DESC""",
        con,
        params=(f"%{query}%",),
    )
    con.close()
    return df


# ── Product Mutations ────────────────────────────────────────────────────────
def update_product(name: str, price: float | None = None, add_qty: int | None = None):
    """
    Upsert a product.
    - If product exists: optionally update price and/or add to quantity.
    - If product doesn't exist: create it with the given price and quantity.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con = _con()
    cur = con.cursor()

    existing = cur.execute("SELECT id, price, quantity FROM products WHERE name = ?", (name,)).fetchone()

    if existing:
        new_price = price if price is not None else existing[1]
        new_qty = existing[2] + (add_qty or 0)
        cur.execute(
            "UPDATE products SET price = ?, quantity = ?, last_restocked = ? WHERE name = ?",
            (new_price, new_qty, ts, name),
        )
    else:
        cur.execute(
            "INSERT INTO products (name, price, quantity, last_restocked) VALUES (?, ?, ?, ?)",
            (name, price or 0.0, add_qty or 0, ts),
        )

    con.commit()
    con.close()


def decrement_stock(name: str, qty: int = 1) -> bool:
    """
    Attempt to decrement stock by qty.
    Returns True if successful, False if insufficient stock.
    """
    con = _con()
    cur = con.cursor()
    row = cur.execute("SELECT quantity FROM products WHERE name = ?", (name,)).fetchone()
    if row is None or row[0] < qty:
        con.close()
        return False
    cur.execute(
        "UPDATE products SET quantity = quantity - ? WHERE name = ?",
        (qty, name),
    )
    con.commit()
    con.close()
    return True


def restore_stock(name: str, qty: int = 1):
    """Re-increment stock (e.g. when customer removes item from cart)."""
    con = _con()
    con.execute(
        "UPDATE products SET quantity = quantity + ? WHERE name = ?",
        (qty, name),
    )
    con.commit()
    con.close()


# ── Transaction Queries ──────────────────────────────────────────────────────
def save_transaction(phone: str, items: list[dict], total: float) -> int:
    """
    Log a billing transaction.
    items: list of dicts with keys 'name', 'qty', 'price', 'subtotal'.
    Returns the transaction ID.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con = _con()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO transactions (timestamp, customer_phone, items_json, total_amount) VALUES (?, ?, ?, ?)",
        (ts, phone, json.dumps(items, ensure_ascii=False), round(total, 2)),
    )
    txn_id = cur.lastrowid
    con.commit()
    con.close()
    return txn_id


def get_recent_transactions(limit: int = 20) -> pd.DataFrame:
    """Return recent transactions."""
    con = _con()
    df = pd.read_sql_query(
        f"""SELECT id AS 'Txn #', timestamp AS 'Date', customer_phone AS 'Phone',
                   total_amount AS 'Total (₹)'
            FROM transactions ORDER BY id DESC LIMIT {limit}""",
        con,
    )
    con.close()
    return df


# ── Utility ──────────────────────────────────────────────────────────────────
def reset_db():
    """Wipe all data and re-seed."""
    con = _con()
    con.execute("DELETE FROM products")
    con.execute("DELETE FROM transactions")
    con.commit()
    con.close()
    init_db()
