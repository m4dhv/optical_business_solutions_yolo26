#self checkout page
import time
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database_manager import (
    init_db, get_product, decrement_stock, save_transaction,
)
from vision_engine import load_model, run_detection, annotate_frame, frame_bgr_to_rgb, MODEL_MAP
from utils import generate_receipt_pdf, send_telegram_document, GST_RATE

st.set_page_config(page_title="Self Checkout", page_icon="🧾", layout="wide", initial_sidebar_state="collapsed")
init_db()

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
.main{font-family:'Inter',sans-serif}
.block-container{padding-top:1.2rem}

/* ── Receipt-style bill ──────────────────── */
.bill-header{
  background:linear-gradient(135deg,#0a1f14,#132e1f);
  border:1px solid #1e3d2e;border-radius:18px 18px 0 0;
  padding:1.2rem 1.5rem;text-align:center;
}
.bill-header h2{color:#89d99d;margin:0;font-size:1.3rem;font-weight:800;letter-spacing:.5px}
.bill-header p{color:#6b8072;margin:.2rem 0 0;font-size:.8rem}
.bill-body{
  background:#0c1a14;border-left:1px solid #1e3d2e;border-right:1px solid #1e3d2e;
  padding:0;
}
.bill-row{
  display:flex;align-items:center;padding:.65rem 1.2rem;
  border-bottom:1px solid #162a1f;transition:background .2s;
}
.bill-row:hover{background:#11221a}
.bill-row .sno{width:30px;color:#4a6355;font-size:.8rem;font-weight:600}
.bill-row .name{flex:1;color:#e8f5eb;font-weight:600;font-size:.95rem}
.bill-row .qty{width:50px;text-align:center;color:#89d99d;font-weight:700;font-size:.95rem}
.bill-row .price{width:75px;text-align:right;color:#a8b8ad;font-size:.85rem}
.bill-row .total{width:80px;text-align:right;color:#e8f5eb;font-weight:700;font-size:.95rem}
.bill-row-head{background:#0f2419;border-bottom:2px solid #1e3d2e}
.bill-row-head span{color:#6b8072!important;font-weight:700!important;font-size:.75rem!important;
  text-transform:uppercase;letter-spacing:.8px}
.bill-footer{
  background:linear-gradient(135deg,#132e1f,#0d2517);
  border:1px solid #1e3d2e;border-top:2px solid #3a7d4f;
  border-radius:0 0 18px 18px;padding:1rem 1.5rem;
}
.bill-line{display:flex;justify-content:space-between;padding:.25rem 0}
.bill-line .lbl{color:#6b8072;font-size:.9rem}
.bill-line .val{color:#a8b8ad;font-size:.9rem;font-weight:600}
.bill-grand{
  display:flex;justify-content:space-between;align-items:center;
  padding:.6rem 0 .2rem;margin-top:.4rem;border-top:1px dashed #3a7d4f;
}
.bill-grand .lbl{color:#89d99d;font-size:1rem;font-weight:700}
.bill-grand .val{color:#89d99d;font-size:1.5rem;font-weight:900}

/* ── Toast notifications ─────────────────── */
.scan-toast{
  border-radius:10px;padding:.6rem 1rem;margin:.3rem 0;
  font-size:.9rem;font-weight:600;
  animation:toast-in .35s ease-out;
}
@keyframes toast-in{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
.toast-add{background:#0d2517;border:1px solid #3a7d4f;color:#89d99d}
.toast-dup{background:#1a2520;border:1px solid #2a4535;color:#6b8072}
.toast-oos{background:#2a1515;border:1px solid #5c2828;color:#fca5a5}
.toast-count{
  display:inline-block;background:#3a7d4f;color:#e8f5eb;
  border-radius:6px;padding:0 6px;margin-left:6px;font-size:.75rem;font-weight:800;
}

/* ── Empty bill state ────────────────────── */
.bill-empty{text-align:center;padding:2.5rem 1rem;color:#4a6355}
.bill-empty .icon{font-size:2.5rem;margin-bottom:.5rem}
.bill-empty p{font-size:.9rem}

/* ── Metrics & sidebar ───────────────────── */
div[data-testid="stMetric"]{background:#008000;padding:14px;border-radius:14px;border:1px solid #1e3d2e}
div[data-testid="stMetric"] label{color:#6b8072!important}
div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#89d99d!important;font-weight:700!important}
section[data-testid="stSidebar"]{background:#0a1610;border-right:1px solid #1e3d2e}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
for k, v in {
    "cart": {},                # {item_name: {"qty": int, "price": float}}
    "billed_track_ids": set(), # Track IDs already added — prevents re-billing
    "scan_log": [],            # Recent scan events for the toast feed
    "cust_frames": 0,
    "cust_checkout_done": False,
    "cust_receipt_path": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


def cart_subtotal():
    return sum(v["qty"] * v["price"] for v in st.session_state.cart.values())

def cart_item_count():
    return sum(v["qty"] for v in st.session_state.cart.values())

def cart_line_count():
    return len(st.session_state.cart)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## Scanner Settings")
    model_choice = st.selectbox("Model", list(MODEL_MAP.keys()), index=2, key="cm")
    cam_index = st.number_input("Camera", 0, 10, 0, key="cc")
    conf_threshold = st.slider("Confidence", 0.0, 1.0, 0.5, 0.05, key="cf")
    img_size = st.selectbox("Resolution", [640, 768, 1024], index=0, key="cr")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("# 🧾 Self Checkout")
col_cam, col_bill = st.columns([3, 2], gap="large")

# ── LEFT COLUMN: Camera + scan feed ──────────────────────────────────────────
with col_cam:
    run_camera = st.toggle("Start/Stop Billing", False, key="cust_cam_toggle")
    video_ph = st.empty()
    det_ph = st.empty()

    # Scan event feed (toasts)
    st.markdown("#### Items Added to Cart")
    toast_ph = st.empty()

    # Render any existing scan log
    if st.session_state.scan_log:
        html_parts = []
        for entry in st.session_state.scan_log[-8:]:  # Keep last 8 events
            html_parts.append(entry)
        toast_ph.markdown("".join(html_parts), unsafe_allow_html=True)


# ── RIGHT COLUMN: Live Bill ──────────────────────────────────────────────────
with col_bill:

    # ── Bill Header ──────────────────────────────────────────────────────
    st.markdown("""
    <div class="bill-header">
        <h2>🛒 BILL OF SALE</h2>
    </div>
    """, unsafe_allow_html=True)

    # ── Bill Body ────────────────────────────────────────────────────────
    if st.session_state.cart:
        # Table header row
        header_html = (
            '<div class="bill-body">'
            '<div class="bill-row bill-row-head">'
            '<span class="sno">#</span>'
            '<span class="name">Item</span>'
            '<span class="qty">Qty</span>'
            '<span class="price">Price</span>'
            '<span class="total">Total</span>'
            '</div>'
        )

        rows_html = ""
        for idx, (item_name, info) in enumerate(st.session_state.cart.items(), 1):
            line_total = info["qty"] * info["price"]
            rows_html += (
                f'<div class="bill-row">'
                f'<span class="sno">{idx}</span>'
                f'<span class="name">{item_name}</span>'
                f'<span class="qty">{info["qty"]}</span>'
                f'<span class="price">₹{info["price"]:.2f}</span>'
                f'<span class="total">₹{line_total:.2f}</span>'
                f'</div>'
            )

        st.markdown(header_html + rows_html + "</div>", unsafe_allow_html=True)

        # ── Bill Footer (totals) ─────────────────────────────────────────
        sub = cart_subtotal()
        tax = round(sub * GST_RATE, 2)
        total = round(sub + tax, 2)

        st.markdown(f"""
        <div class="bill-footer">
            <div class="bill-line">
                <span class="lbl">Subtotal ({cart_item_count()} items)</span>
                <span class="val">₹{sub:.2f}</span>
            </div>
            <div class="bill-line">
                <span class="lbl">GST @ {int(GST_RATE*100)}%</span>
                <span class="val">₹{tax:.2f}</span>
            </div>
            <div class="bill-grand">
                <span class="lbl">GRAND TOTAL</span>
                <span class="val">₹{total:.2f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("")  # spacer

        # ── Quantity adjustment & remove ─────────────────────────────────
        with st.expander("🔧 Adjust Quantities", expanded=False):
            for item_name in list(st.session_state.cart.keys()):
                info = st.session_state.cart[item_name]
                ac1, ac2, ac3, ac4 = st.columns([3, 1, 1, 1])
                ac1.markdown(f"**{item_name}**")
                if ac2.button("➖", key=f"dec_{item_name}"):
                    if info["qty"] > 1:
                        st.session_state.cart[item_name]["qty"] -= 1
                    else:
                        del st.session_state.cart[item_name]
                    st.rerun()
                if ac3.button("➕", key=f"inc_{item_name}"):
                    st.session_state.cart[item_name]["qty"] += 1
                    st.rerun()
                if ac4.button("🗑️", key=f"del_{item_name}"):
                    del st.session_state.cart[item_name]
                    st.rerun()

        # ── Clear cart ───────────────────────────────────────────────────
        if st.button("🗑️ Clear Entire Cart", width='stretch'):
            st.session_state.cart = {}
            st.session_state.billed_track_ids = set()
            st.session_state.scan_log = []
            st.rerun()

        # ── Checkout ─────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 📱 Checkout")
        phone = st.text_input(
            "Customer Phone Number", placeholder="e.g. 9876543210",
            key="cust_phone", max_chars=10,
        )

        if st.button(
            "🧾 Generate Bill & Checkout",
            width = 'stretch', type="primary",
            disabled=not phone,
        ):
            if not phone or len(phone) < 10:
                st.error("Please enter a valid 10-digit phone number.")
            else:
                # ── Deduct stock from DB ─────────────────────────────
                items_list = []
                stock_ok = True
                for name, info in st.session_state.cart.items():
                    items_list.append({
                        "name": name,
                        "qty": info["qty"],
                        "price": info["price"],
                        "subtotal": round(info["qty"] * info["price"], 2),
                    })
                    if not decrement_stock(name, info["qty"]):
                        st.error(
                            f"⚠️ Insufficient stock for **{name}** "
                            f"(requested {info['qty']}). Remove or reduce qty."
                        )
                        stock_ok = False
                        break

                if stock_ok:
                    txn_id = save_transaction(phone, items_list, total)

                    receipt_path = generate_receipt_pdf(
                        items=items_list, subtotal=sub,
                        phone=phone, txn_id=txn_id,
                    )
                    st.session_state.cust_receipt_path = receipt_path

                    caption = (
                        f"🧾 *New Transaction #{txn_id}*\n"
                        f"📱 Phone: {phone}\n"
                        f"💰 Total: ₹{total:.2f}\n"
                        f"📦 Items: {cart_item_count()}"
                    )
                    send_telegram_document(receipt_path, caption)

                    st.session_state.cart = {}
                    st.session_state.billed_track_ids = set()
                    st.session_state.scan_log = []
                    st.session_state.cust_checkout_done = True
                    st.rerun()

    elif st.session_state.cust_checkout_done and st.session_state.cust_receipt_path:
        st.markdown("""
        <div class="bill-body" style="border-radius:0 0 18px 18px;padding:2rem;text-align:center">
            <div style="font-size:3rem;margin-bottom:.5rem">✅</div>
            <div style="color:#89d99d;font-size:1.2rem;font-weight:700">Purchase Complete!</div>
            <div style="color:#6b8072;font-size:.85rem;margin-top:.3rem">Receipt has been generated and sent.</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("")
        with open(st.session_state.cust_receipt_path, "rb") as f:
            st.download_button(
                "📥 Print Receipt PDF",
                data=f.read(),
                file_name=Path(st.session_state.cust_receipt_path).name,
                mime="application/pdf",
                width = 'stretch',
            )
        if st.button("🆕 New Transaction", width = 'stretch'):
            st.session_state.cust_checkout_done = False
            st.session_state.cust_receipt_path = None
            st.rerun()
    else:
        st.markdown("""
        <div class="bill-body" style="border-radius:0 0 18px 18px">
            <div class="bill-empty">
                <p>Instructions:<br/> Start the camera and place items in front of the camera to begin billing. <br/>Stop the camera to view the current bill. </p>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# CAMERA LOOP — Track-ID based auto-billing
# ══════════════════════════════════════════════════════════════════════════════
# Each physical object gets a unique track ID from botsort.  Once a track ID
# is added to the bill it goes into `billed_track_ids` and is never counted
# again — even if the object stays in frame for minutes.  This eliminates the
# need for arbitrary debounce timers and prevents duplicate billing entirely.
# ══════════════════════════════════════════════════════════════════════════════
if run_camera:
    import cv2

    model = load_model(model_choice)
    cap = cv2.VideoCapture(int(cam_index))

    if not cap.isOpened():
        st.error("❌ Camera not found. Check your camera index.")
    else:
        try:
            while st.session_state.get("cust_cam_toggle", False):
                ok, frame = cap.read()
                if not ok:
                    st.error("📷 Camera feed lost.")
                    break

                result = run_detection(model, frame, conf_threshold, img_size)

                # Stock map for annotation colouring (red = OOS)
                stock_map = {}
                for n in result.unique_names:
                    p = get_product(n)
                    stock_map[n] = p["quantity"] if p else 0

                annotated = annotate_frame(frame, result, stock_map)
                video_ph.image(frame_bgr_to_rgb(annotated), width=400)

                # Detection summary
                if result.has_items():
                    det_ph.markdown("🔍 " + "  |  ".join(
                        f"**{n}**: {c}" for n, c in result.label_counts.items()))
                else:
                    det_ph.caption("Waiting for products...")

                # ── AUTO-BILLING via track IDs ───────────────────────────
                new_events = False
                for item in result.items:
                    tid = item.track_id
                    if tid is None:
                        continue  # Tracker hasn't assigned an ID yet

                    if tid in st.session_state.billed_track_ids:
                        continue  # Already billed this physical object

                    # Mark as billed so it's never counted again
                    st.session_state.billed_track_ids.add(tid)

                    prod = get_product(item.name)
                    if prod is None or prod["quantity"] <= 0:
                        # Out of stock
                        st.session_state.scan_log.append(
                            f'<div class="scan-toast toast-oos">'
                            f'🔴 <b>{item.name}</b> — out of stock</div>'
                        )
                        new_events = True
                        continue

                    # Check if adding would exceed available stock
                    current_cart_qty = st.session_state.cart.get(
                        item.name, {}
                    ).get("qty", 0)
                    if current_cart_qty >= prod["quantity"]:
                        st.session_state.scan_log.append(
                            f'<div class="scan-toast toast-oos">'
                            f'⚠️ <b>{item.name}</b> — no more in stock '
                            f'({current_cart_qty} already in cart)</div>'
                        )
                        new_events = True
                        continue

                    # ── Add to cart ───────────────────────────────────
                    if item.name in st.session_state.cart:
                        st.session_state.cart[item.name]["qty"] += 1
                    else:
                        st.session_state.cart[item.name] = {
                            "qty": 1,
                            "price": prod["price"],
                        }

                    new_qty = st.session_state.cart[item.name]["qty"]
                    st.session_state.scan_log.append(
                        f'<div class="scan-toast toast-add">'
                        f'✅ <b>{item.name}</b> added'
                        f'<span class="toast-count">×{new_qty}</span></div>'
                    )
                    new_events = True

                # Update toast feed
                if new_events:
                    log_html = "".join(st.session_state.scan_log[-8:])
                    toast_ph.markdown(log_html, unsafe_allow_html=True)

                st.session_state.cust_frames += 1
        except Exception as e:
            st.error(f"Scanner error: {e}")
        finally:
            cap.release()