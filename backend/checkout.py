"""
checkout.py — Razorpay Payment Router
======================================
Mount this in app.py with:

    from checkout import router as checkout_router, init_checkout
    init_checkout(templates)          # pass app.py's Jinja2Templates instance
    app.include_router(checkout_router)

Endpoints:
    GET  /checkout              — Checkout page (Jinja2 template)
    POST /api/razorpay/order    — Create Razorpay order, returns order_id + amount
    POST /api/razorpay/verify   — Verify HMAC signature, finalize transaction, generate receipt
"""

import hashlib
import hmac
import os
import time
from pathlib import Path

import razorpay
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

# ── Razorpay Credentials ──────────────────────────────────────────────────────
RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "rzp_test_placeholder")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "placeholder_secret")

rzp = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter()

# Will be set by init_checkout() called from app.py
_templates: Jinja2Templates | None = None


def init_checkout(templates: Jinja2Templates) -> None:
    """
    Call this from app.py after creating the Jinja2Templates instance,
    so the checkout router uses the same template environment as the rest
    of the app (inherits base.html, globals, filters, etc.).

    Example in app.py:
        from checkout import router as checkout_router, init_checkout
        templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
        init_checkout(templates)
        app.include_router(checkout_router)
    """
    global _templates
    _templates = templates


# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/checkout", response_class=HTMLResponse)
async def page_checkout(request: Request):
    if _templates is None:
        raise RuntimeError(
            "checkout.py: init_checkout(templates) was never called from app.py"
        )

    from app import get_current_user

    user = get_current_user(request)

    return _templates.TemplateResponse(request, "checkout.html", {
        "user":         user,
        "razorpay_key": RAZORPAY_KEY_ID,
    })


# ══════════════════════════════════════════════════════════════════════════════
# RAZORPAY ORDER CREATION
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/razorpay/order")
async def create_razorpay_order(request: Request):
    """
    Creates a Razorpay order.

    Request body:
        cart  : { "ItemName": { "qty": int, "price": float }, ... }
        phone : str (10-digit)

    Returns:
        order_id : str  — Razorpay order ID
        amount   : int  — Amount in paise (INR x 100)
        key      : str  — Razorpay Key ID (safe to expose to frontend)
    """
    body  = await request.json()
    cart  = body.get("cart", {})
    phone = body.get("phone", "").strip()

    if not cart:
        raise HTTPException(400, "Cart is empty")
    if not phone or len(phone) < 10:
        raise HTTPException(400, "Valid 10-digit phone number required")

    sub         = sum(info["qty"] * info["price"] for info in cart.values())
    total_paise = int(round(sub * 100))   # Razorpay requires integer paise

    try:
        order = rzp.order.create({
            "amount":          total_paise,
            "currency":        "INR",
            "receipt":         f"rcpt_{int(time.time())}",
            "payment_capture": 1,
        })
    except Exception as e:
        raise HTTPException(502, f"Razorpay order creation failed: {e}")

    return {
        "order_id": order["id"],
        "amount":   total_paise,
        "key":      RAZORPAY_KEY_ID,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT VERIFICATION + CHECKOUT FINALIZATION
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/api/razorpay/verify")
async def verify_and_finalize(request: Request):
    """
    1. Verifies Razorpay HMAC-SHA256 signature.
    2. Decrements stock for each item.
    3. Saves transaction to DB.
    4. Generates PDF receipt.
    5. Sends receipt + notification to Telegram.

    Request body:
        cart                : { name: {qty, price} }
        phone               : str
        razorpay_order_id   : str
        razorpay_payment_id : str
        razorpay_signature  : str

    Returns:
        ok, txn_id, total, subtotal, tax, receipt_url, payment_id
    """
    from database_manager import decrement_stock, save_transaction
    from utils import generate_receipt_pdf, send_telegram_document

    body       = await request.json()
    cart       = body.get("cart", {})
    phone      = body.get("phone", "").strip()
    order_id   = body.get("razorpay_order_id", "")
    payment_id = body.get("razorpay_payment_id", "")
    signature  = body.get("razorpay_signature", "")

    if not all([cart, phone, order_id, payment_id, signature]):
        raise HTTPException(400, "Missing required payment fields")

    # ── 1. Verify HMAC-SHA256 signature ──────────────────────────────────
    msg      = f"{order_id}|{payment_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        msg.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "Payment signature verification failed")

    # ── 2. Build items list & decrement stock ─────────────────────────────
    items_list = []
    for name, info in cart.items():
        qty   = int(info["qty"])
        price = float(info["price"])
        items_list.append({
            "name":     name,
            "qty":      qty,
            "price":    price,
            "subtotal": round(qty * price, 2),
        })
        if not decrement_stock(name, qty):
            raise HTTPException(400, f"Insufficient stock for '{name}'")

    # ── 3. Compute totals ─────────────────────────────────────────────────
    sub   = sum(i["subtotal"] for i in items_list)
    total = round(sub, 2)

    # ── 4. Save transaction ───────────────────────────────────────────────
    txn_id = save_transaction(phone, items_list, total)

    # ── 5. Generate PDF receipt ───────────────────────────────────────────
    receipt_path = generate_receipt_pdf(
        items=items_list, subtotal=sub, phone=phone, txn_id=txn_id,
    )

    # ── 6. Telegram notification ──────────────────────────────────────────
    caption = (
        f"*Razorpay Payment #{txn_id}*\n"
        f"Phone: `{phone}`\n"
        f"Payment ID: `{payment_id}`\n"
        f"Total: Rs.{total:.2f}\n"
        f"Items: {sum(i['qty'] for i in items_list)}"
    )
    send_telegram_document(receipt_path, caption)

    return {
        "ok":          True,
        "txn_id":      txn_id,
        "total":       total,
        "subtotal":    sub,
        "receipt_url": f"/receipts/{Path(receipt_path).name}",
        "payment_id":  payment_id,
    }
