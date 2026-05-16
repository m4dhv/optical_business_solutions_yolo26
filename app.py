"""
app.py — FastAPI Backend for Optical Business Solutions
========================================================
Serves HTML pages and REST API on the same port (8000).
WebSocket endpoint streams camera frames with YOLO detections.
"""

import json
import sys
import asyncio
import base64
import hashlib
import hmac
import time
from pathlib import Path
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

# ── Ensure backend/ modules are importable from app.py at project root ──────
APP_DIR      = Path(__file__).resolve().parent          
BACKEND_DIR  = APP_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database_manager import (
    init_db, get_product, get_all_products_list, get_low_stock_list,
    search_products_list, get_recent_transactions_list, update_product,
    decrement_stock, restore_stock, save_transaction, reset_db,
    verify_user_credentials, get_all_users_list, create_user, delete_user,
)
from vision_engine import load_model, run_detection, annotate_frame, frame_bgr_to_rgb, MODEL_MAP
from utils import (
    generate_receipt_pdf, send_telegram_document, send_telegram_text,
    send_stock_update_alert, send_inventory_summary,
)
from checkout import router as checkout_router, init_checkout

# ── Paths ────────────────────────────────────────────────────────────────────
RECEIPTS_DIR = APP_DIR / "receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)

# ── App Init ───────────────────────────────────────────────────────────────
app = FastAPI(title="Optical Business Solutions")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# ── Routers ───────────────────────────────────────────────────────────────────
init_checkout(templates)          # share the same Jinja2 env with checkout router
app.include_router(checkout_router)

# Initialize database on startup
init_db()

@app.middleware("http")
async def prevent_caching_html(request: Request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ── Auth ─────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "optical-business-solutions-secret-key-2026")
# Credentials are stored in the SQLite `users` table (hashed with PBKDF2-SHA256).

ROLE_ACCESS = {
    "Customer":          ["/"],
    "Shopkeeper":        ["/", "/shopkeeper", "/inventory"],
    "Inventory Support": ["/", "/inventory"],
    "Administrator":      ["/", "/shopkeeper", "/inventory", "/admin"],
}


def _sign(data: str) -> str:
    return hmac.HMAC(SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()


def _make_token(username: str, role: str) -> str:
    payload = json.dumps({"user": username, "role": role, "t": int(time.time())})
    sig = _sign(payload)
    return base64.b64encode(f"{payload}|{sig}".encode()).decode()


def _verify_token(token: str) -> dict | None:
    try:
        decoded = base64.b64decode(token).decode()
        payload_str, sig = decoded.rsplit("|", 1)
        if hmac.compare_digest(_sign(payload_str), sig):
            return json.loads(payload_str)
    except Exception:
        pass
    return None


def get_current_user(request: Request) -> dict:
    """Extract user info from cookie. Returns {"user": ..., "role": ...} or guest."""
    token = request.cookies.get("auth_token")
    if token:
        user_data = _verify_token(token)
        if user_data:
            return {"user": user_data["user"], "role": user_data["role"]}
    return {"user": None, "role": "Customer"}


# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def page_customer(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse(request, "customer.html", {
        "user": user,
    })


@app.get("/shopkeeper", response_class=HTMLResponse)
async def page_shopkeeper(request: Request):
    user = get_current_user(request)
    if "/shopkeeper" not in ROLE_ACCESS.get(user["role"], []):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "shopkeeper.html", {
        "user": user,
    })


@app.get("/inventory", response_class=HTMLResponse)
async def page_inventory(request: Request):
    user = get_current_user(request)
    if "/inventory" not in ROLE_ACCESS.get(user["role"], []):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "inventory.html", {
        "user": user,
    })


@app.get("/admin", response_class=HTMLResponse)
async def page_admin(request: Request):
    user = get_current_user(request)
    if "/admin" not in ROLE_ACCESS.get(user["role"], []):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "admin.html", {
        "user": user,
    })


# ══════════════════════════════════════════════════════════════════════════════
# AUTH API
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/login")
async def api_login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    user = verify_user_credentials(username, password)
    if user:
        role = user["role"]
        token = _make_token(username, role)
        response = JSONResponse({"ok": True, "role": role, "user": username})
        response.set_cookie("auth_token", token, httponly=True, samesite="lax", max_age=86400)
        return response

    return JSONResponse({"ok": False, "error": "Invalid credentials"}, status_code=401)


@app.post("/api/logout")
async def api_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("auth_token", httponly=True, samesite="lax")
    return response


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT API
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/products")
async def api_products(q: Optional[str] = None):
    if q:
        return search_products_list(q)
    return get_all_products_list()


@app.get("/api/products/low-stock")
async def api_low_stock(threshold: int = 3):
    return get_low_stock_list(threshold)


@app.get("/api/products/{name}")
async def api_product_detail(name: str):
    prod = get_product(name)
    if prod is None:
        raise HTTPException(404, "Product not found")
    return prod


@app.post("/api/products/update")
async def api_update_product(request: Request):
    body = await request.json()
    name = body.get("name")
    price = body.get("price")
    add_qty = body.get("add_qty")

    if not name:
        raise HTTPException(400, "Product name required")

    update_product(name, price=price, add_qty=add_qty if add_qty and add_qty > 0 else None)

    # Send Telegram alert
    updated = get_product(name)
    if updated:
        send_stock_update_alert(name, updated["quantity"], updated["price"])

    return {"ok": True, "product": get_product(name)}


# ══════════════════════════════════════════════════════════════════════════════
# CHECKOUT API
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/checkout")
async def api_checkout(request: Request):
    body = await request.json()
    cart = body.get("cart", {})     # {name: {qty, price}}
    phone = body.get("phone", "")

    if not cart or not phone or len(phone) < 10:
        raise HTTPException(400, "Cart and valid phone required")

    # Build items list and deduct stock
    items_list = []
    for name, info in cart.items():
        qty = info["qty"]
        price = info["price"]
        subtotal = round(qty * price, 2)
        items_list.append({"name": name, "qty": qty, "price": price, "subtotal": subtotal})

        if not decrement_stock(name, qty):
            raise HTTPException(400, f"Insufficient stock for {name}")

    sub = sum(i["subtotal"] for i in items_list)
    total = round(sub, 2)

    txn_id = save_transaction(phone, items_list, total)

    receipt_path = generate_receipt_pdf(
        items=items_list, subtotal=sub, phone=phone, txn_id=txn_id,
    )

    caption = (
        f"🧾 *New Transaction #{txn_id}*\n"
        f"📱 Phone: {phone}\n"
        f"💰 Total: ₹{total:.2f}\n"
        f"📦 Items: {sum(i['qty'] for i in items_list)}"
    )
    send_telegram_document(receipt_path, caption)

    filename = Path(receipt_path).name
    return {
        "ok": True,
        "txn_id": txn_id,
        "total": total,
        "subtotal": sub,
        "receipt_url": f"/receipts/{filename}",
    }


# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTION & ADMIN API
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/transactions")
async def api_transactions(limit: int = 500):
    return get_recent_transactions_list(limit)


@app.post("/api/reset-db")
async def api_reset():
    reset_db()
    return {"ok": True}


# ── User Management API ───────────────────────────────────────────────────────
@app.get("/api/users")
async def api_get_users(request: Request):
    user = get_current_user(request)
    if user["role"] != "Administrator":
        raise HTTPException(403, "Forbidden")
    return get_all_users_list()


@app.post("/api/users")
async def api_create_user(request: Request):
    user = get_current_user(request)
    if user["role"] != "Administrator":
        raise HTTPException(403, "Forbidden")
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    role = body.get("role", "").strip()
    allowed_roles = {"Inventory Support", "Shopkeeper"}
    if role not in allowed_roles:
        raise HTTPException(400, f"Role must be one of: {', '.join(allowed_roles)}")
    err = create_user(username, password, role)
    if err:
        raise HTTPException(409, err)
    return {"ok": True, "username": username, "role": role}


@app.delete("/api/users/{username}")
async def api_delete_user(username: str, request: Request):
    user = get_current_user(request)
    if user["role"] != "Administrator":
        raise HTTPException(403, "Forbidden")
    if username == user["user"]:
        raise HTTPException(400, "You cannot delete your own account.")
    err = delete_user(username)
    if err:
        raise HTTPException(400, err)
    return {"ok": True}


@app.post("/api/telegram-summary")
async def api_telegram_summary():
    from database_manager import get_all_products
    ok, err = send_inventory_summary(get_all_products())
    if ok:
        return {"ok": True}
    return JSONResponse({"ok": False, "error": err}, status_code=500)


# ══════════════════════════════════════════════════════════════════════════════
# RECEIPT FILE SERVING
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/receipts/{filename}")
async def serve_receipt(filename: str):
    path = RECEIPTS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Receipt not found")
    return FileResponse(str(path), media_type="application/pdf", filename=filename)


# Serve store logo (now lives in static/)
@app.get("/store_logo.png")
async def serve_logo():
    logo = APP_DIR / "static" / "store_logo.png"
    if logo.exists():
        return FileResponse(str(logo))
    raise HTTPException(404)


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET — CAMERA STREAMING
# ══════════════════════════════════════════════════════════════════════════════
@app.websocket("/ws/camera")
async def ws_camera(websocket: WebSocket):
    await websocket.accept()

    try:
        # Receive config from client
        config = await websocket.receive_json()
        model_key = config.get("model", "Medium")
        cam_index = config.get("camera", 0)
        conf = config.get("confidence", 0.5)
        img_size = config.get("img_size", 640)
        mode = config.get("mode", "customer")  # "customer" or "shopkeeper"

        import cv2

        model = load_model(model_key)
        cap = cv2.VideoCapture(int(cam_index))

        if not cap.isOpened():
            await websocket.send_json({"error": "Camera not found"})
            await websocket.close()
            return

        billed_track_ids = set()

        try:
            while True:
                # Check for incoming messages (non-blocking)
                try:
                    msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.01)
                    if msg.get("action") == "stop":
                        break
                    if msg.get("action") == "reset_tracks":
                        billed_track_ids = set()
                except asyncio.TimeoutError:
                    pass

                ok, frame = cap.read()
                if not ok:
                    await websocket.send_json({"error": "Camera feed lost"})
                    break

                result = run_detection(model, frame, conf, img_size)

                # Build stock map for annotation
                stock_map = {}
                for n in result.unique_names:
                    p = get_product(n)
                    stock_map[n] = p["quantity"] if p else 0

                annotated = annotate_frame(frame, result, stock_map)
                rgb = frame_bgr_to_rgb(annotated)

                # Encode frame as JPEG
                _, buffer = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 75])
                frame_b64 = base64.b64encode(buffer).decode("utf-8")

                # Build detection data
                detections = []
                new_items = []
                for item in result.items:
                    det = {
                        "name": item.name,
                        "confidence": round(item.confidence, 3),
                        "track_id": item.track_id,
                    }
                    detections.append(det)

                    # Auto-billing logic (customer mode)
                    if mode == "customer" and item.track_id is not None:
                        if item.track_id not in billed_track_ids:
                            billed_track_ids.add(item.track_id)
                            prod = get_product(item.name)
                            if prod and prod["quantity"] > 0:
                                new_items.append({
                                    "name": item.name,
                                    "price": prod["price"],
                                    "track_id": item.track_id,
                                    "in_stock": True,
                                })
                            else:
                                new_items.append({
                                    "name": item.name,
                                    "price": 0,
                                    "track_id": item.track_id,
                                    "in_stock": False,
                                })

                    # Shopkeeper mode: detect top item
                    if mode == "shopkeeper" and item.track_id is not None:
                        if item.track_id not in billed_track_ids:
                            billed_track_ids.add(item.track_id)
                            prod = get_product(item.name)
                            new_items.append({
                                "name": item.name,
                                "confidence": round(item.confidence, 3),
                                "current_qty": prod["quantity"] if prod else 0,
                                "current_price": prod["price"] if prod else 0,
                            })

                await websocket.send_json({
                    "frame": frame_b64,
                    "detections": detections,
                    "counts": result.label_counts,
                    "new_items": new_items,
                })

                await asyncio.sleep(0.03)  # ~30fps cap

        finally:
            cap.release()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
 
 
