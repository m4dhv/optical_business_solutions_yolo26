"""
database_manager.py — Consolidated Database Layer
===================================================
Single store.db with three tables:
  • products      – Inventory master data (name, price, quantity, last_restocked)
  • transactions  – Billing transaction log (phone, items_json, total_amount)
  • users         – Auth accounts (username, hashed_password, role)

Passwords are stored as PBKDF2-SHA256 hashes (hashlib, no extra deps).
All SQL queries are centralised here. Thread-safe via short-lived connections.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent   # .../majorpart2/backend/
DB_PATH     = BACKEND_DIR / "store.db"

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


# ── Password Hashing ─────────────────────────────────────────────────────────
_HASH_ITERS = 260_000  # NIST-recommended PBKDF2-SHA256 iteration count


def _hash_password(password: str, salt: bytes | None = None) -> str:
    """
    Return a storable hash string: '<hex_salt>$<hex_dk>'.
    If *salt* is None a fresh 16-byte random salt is generated.
    """
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _HASH_ITERS)
    return f"{salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison against a stored hash string."""
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _HASH_ITERS)
        return hmac_compare(candidate.hex(), dk_hex)
    except Exception:
        return False


def hmac_compare(a: str, b: str) -> bool:
    """Constant-time string comparison (re-exported for use in app.py)."""
    import hmac as _hmac
    return _hmac.compare_digest(a, b)


# ── Default Users ─────────────────────────────────────────────────────────────
# username → (plain_password, role)  — hashed on first init_db() call
DEFAULT_USERS = [
    ("shop",  "123", "Shopkeeper"),
    ("inv",   "123", "Inventory Support"),
    ("admin", "123", "Administrator"),
]


# ── Initialisation ───────────────────────────────────────────────────────────
def init_db():
    """Create tables if they don't exist and seed the product catalogue and users."""
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL UNIQUE,
            hashed_password TEXT    NOT NULL,
            role            TEXT    NOT NULL
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

    # Seed default users (INSERT OR IGNORE so manual changes are preserved)
    for username, plain_password, role in DEFAULT_USERS:
        cur.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        )
        if cur.fetchone() is None:
            hashed = _hash_password(plain_password)
            cur.execute(
                "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
                (username, hashed, role),
            )
    
    # Migrate any existing roles from 'Backend Team' to 'Administrator'
    cur.execute("UPDATE users SET role = 'Administrator' WHERE role = 'Backend Team'")

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


# ── JSON-friendly query variants (for API responses) ────────────────────────
def get_all_products_list() -> list[dict]:
    """Return all products as a list of dicts (JSON-serializable)."""
    con = _con()
    cur = con.execute(
        """SELECT id, name, price, quantity,
                  CASE WHEN quantity > 0 THEN 'In Stock' ELSE 'Out of Stock' END AS status,
                  last_restocked
           FROM products ORDER BY quantity DESC"""
    )
    rows = cur.fetchall()
    con.close()
    return [
        {"id": r[0], "name": r[1], "price": r[2], "quantity": r[3],
         "status": r[4], "last_restocked": r[5]}
        for r in rows
    ]


def get_low_stock_list(threshold: int = 2) -> list[dict]:
    """Return low-stock products as a list of dicts."""
    con = _con()
    cur = con.execute(
        """SELECT name, price, quantity, last_restocked
           FROM products WHERE quantity <= ? ORDER BY quantity ASC""",
        (threshold,),
    )
    rows = cur.fetchall()
    con.close()
    return [
        {"name": r[0], "price": r[1], "quantity": r[2], "last_restocked": r[3]}
        for r in rows
    ]


def search_products_list(query: str) -> list[dict]:
    """Search products by name, return list of dicts."""
    con = _con()
    cur = con.execute(
        """SELECT id, name, price, quantity,
                  CASE WHEN quantity > 0 THEN 'In Stock' ELSE 'Out of Stock' END AS status,
                  last_restocked
           FROM products WHERE name LIKE ? ORDER BY quantity DESC""",
        (f"%{query}%",),
    )
    rows = cur.fetchall()
    con.close()
    return [
        {"id": r[0], "name": r[1], "price": r[2], "quantity": r[3],
         "status": r[4], "last_restocked": r[5]}
        for r in rows
    ]


def get_recent_transactions_list(limit: int = 20) -> list[dict]:
    """Return recent transactions as a list of dicts."""
    con = _con()
    cur = con.execute(
        f"""SELECT id, timestamp, customer_phone, items_json, total_amount
            FROM transactions ORDER BY id DESC LIMIT {limit}"""
    )
    rows = cur.fetchall()
    con.close()
    return [
        {"id": r[0], "timestamp": r[1], "phone": r[2],
         "items": json.loads(r[3]), "total": r[4]}
        for r in rows
    ]


# ── User Auth Queries ────────────────────────────────────────────────────────
def get_user_by_username(username: str) -> dict | None:
    """Return {id, username, hashed_password, role} for *username*, or None."""
    con = _con()
    cur = con.execute(
        "SELECT id, username, hashed_password, role FROM users WHERE username = ?",
        (username,),
    )
    row = cur.fetchone()
    con.close()
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "hashed_password": row[2], "role": row[3]}


def verify_user_credentials(username: str, password: str) -> dict | None:
    """
    Verify *password* against the stored hash for *username*.
    Returns {username, role} on success, None on failure.
    """
    user = get_user_by_username(username)
    if user is None:
        return None
    if _verify_password(password, user["hashed_password"]):
        return {"username": user["username"], "role": user["role"]}
    return None


# ── User Management ──────────────────────────────────────────────────────────
def get_all_users_list() -> list[dict]:
    """Return all users as a list of dicts (id, username, role) — no passwords."""
    con = _con()
    cur = con.execute("SELECT id, username, role FROM users ORDER BY id ASC")
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "username": r[1], "role": r[2]} for r in rows]


def create_user(username: str, password: str, role: str) -> str | None:
    """
    Create a new user with a hashed password.
    Returns None on success, or an error message string on failure.
    """
    if not username or not password or not role:
        return "Username, password, and role are required."
    con = _con()
    cur = con.cursor()
    existing = cur.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()
    if existing:
        con.close()
        return f"Username '{username}' already exists."
    hashed = _hash_password(password)
    cur.execute(
        "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, ?)",
        (username, hashed, role),
    )
    con.commit()
    con.close()
    return None


def delete_user(username: str) -> str | None:
    """
    Delete a user by username.
    Returns None on success, or an error message string on failure.
    Prevents deletion of the last Administrator account.
    """
    con = _con()
    cur = con.cursor()
    row = cur.execute("SELECT id, role FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        con.close()
        return f"User '{username}' not found."
    if row[1] == "Administrator":
        count = cur.execute("SELECT COUNT(*) FROM users WHERE role = 'Administrator'").fetchone()[0]
        if count <= 1:
            con.close()
            return "Cannot delete the last Administrator account."
    cur.execute("DELETE FROM users WHERE username = ?", (username,))
    con.commit()
    con.close()
    return None


def reset_db():
    """Wipe all data (products & transactions) and re-seed. Users are preserved."""
    con = _con()
    con.execute("DELETE FROM products")
    con.execute("DELETE FROM transactions")
    con.commit()
    con.close()
    init_db()

 
 
