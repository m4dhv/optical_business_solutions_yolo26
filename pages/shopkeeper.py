#Shopkeeper portal accessible only by the shopkeeper

import time
import sys
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database_manager import (
    init_db, get_all_products, get_product, update_product,
    get_low_stock, search_products, reset_db,
)
from vision_engine import load_model, run_detection, annotate_frame, frame_bgr_to_rgb, MODEL_MAP
from utils import send_stock_update_alert, send_inventory_summary

st.set_page_config(page_title="Shopkeeper Page", page_icon="🏪", layout="wide")
init_db()

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
.main{font-family:'Inter',sans-serif}.block-container{padding-top:1.5rem}
.detect-alert{background:linear-gradient(145deg,#132e1f,#0d2517);border:1px solid #3a7d4f;
border-left:4px solid #89d99d;border-radius:12px;padding:1rem 1.2rem;margin-bottom:.8rem}
.detect-alert b{color:#89d99d}.detect-alert span{color:#a8b8ad;font-size:.9rem}
div[data-testid="stMetric"]{background:#11221a;padding:14px;border-radius:14px;border:1px solid #1e3d2e}
div[data-testid="stMetric"] label{color:#6b8072!important}
div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#89d99d!important;font-weight:700!important}
section[data-testid="stSidebar"]{background:#0a1610;border-right:1px solid #1e3d2e}
</style>""", unsafe_allow_html=True)

# ── Session defaults ─────────────────────────────────────────────────────────
for k, v in {
    "sk_debounce_item": None,
    "sk_debounce_t": 0.0,
    "sk_frames": 0,
    "sk_saves": 0,
    "sk_pending_item": None,      # Item name waiting for form interaction
    "sk_pending_conf": 0.0,       # Confidence of the pending detection
    "sk_form_submitted": False,   # Flag to show success after rerun
    "sk_form_result": "",         # Success message after save
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    model_choice = st.selectbox("Model", list(MODEL_MAP.keys()), index=2, key="skm")
    cam_index = st.number_input("Camera", 0, 10, 0, key="skc")
    conf_threshold = st.slider("Confidence", 0.0, 1.0, 0.5, 0.05, key="skf")
    img_size = st.selectbox("Resolution", [640, 768, 1024], index=0, key="skr")
    st.divider()
    search_q = st.text_input("🔍 Search products", key="sks")
    st.divider()
    if st.button("📢 Telegram Summary", width='stretch'):
        ok, err = send_inventory_summary(get_all_products())
        st.success("Sent!") if ok else st.error(err)
    with st.expander("⚠️ Danger"):
        if st.button("🗑️ Reset DB", width='stretch'):
            reset_db(); st.rerun()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("# 🏪 Shopkeeper Portal")
st.caption("Scan products to register or update inventory in real-time.")

# ── Layout ───────────────────────────────────────────────────────────────────
col_cam, col_panel = st.columns([3, 2], gap="large")

with col_cam:
    st.markdown("### 📹 Live Feed")
    run_camera = st.toggle("Start Camera", False, key="sk_cam_toggle")
    video_ph = st.empty()
    det_ph = st.empty()
    mc1, mc2 = st.columns(2)
    mc1.metric("Frames", st.session_state.sk_frames)
    mc2.metric("Saves", st.session_state.sk_saves)

with col_panel:
    st.markdown("### 📦 Inventory")

    # ── Show success message from previous form submission ────────────
    if st.session_state.sk_form_submitted:
        st.success(st.session_state.sk_form_result)
        st.session_state.sk_form_submitted = False
        st.session_state.sk_form_result = ""

    # ── FORM: rendered OUTSIDE the camera loop with a STABLE key ─────
    # This is the critical fix. The form key is just "sk_update_form",
    # so it persists across reruns and submissions are processed.
    if st.session_state.sk_pending_item:
        item_name = st.session_state.sk_pending_item
        prod = get_product(item_name)
        cq = prod["quantity"] if prod else 0
        cp = prod["price"] if prod else 0.0

        st.markdown(
            f'<div class="detect-alert"><b>🆕 {item_name}</b> detected '
            f'({st.session_state.sk_pending_conf:.0%})<br>'
            f'<span>Current Stock: <b>{cq}</b> units</span></div>',
            unsafe_allow_html=True,
        )

        with st.form("sk_update_form", clear_on_submit=True):
            st.markdown(f"**Update inventory for: {item_name}**")
            new_price = st.number_input(
                "Price (₹)", value=float(cp), min_value=0.0, step=1.0,
            )
            add_qty = st.number_input(
                "Add Quantity", value=0, min_value=0, step=1,
            )

            col_save, col_dismiss = st.columns(2)
            save_clicked = col_save.form_submit_button(
                "💾 Save", width='stretch', type="primary",
            )
            dismiss_clicked = col_dismiss.form_submit_button(
                "✖ Dismiss", width='stretch',
            )

            if save_clicked:
                update_product(
                    item_name,
                    price=new_price,
                    add_qty=add_qty if add_qty > 0 else None,
                )
                st.session_state.sk_saves += 1
                updated = get_product(item_name)
                send_stock_update_alert(item_name, updated["quantity"], new_price)
                st.session_state.sk_form_submitted = True
                st.session_state.sk_form_result = (
                    f"✅ {item_name}: {updated['quantity']} units, ₹{new_price:.2f}"
                )
                st.session_state.sk_pending_item = None
                st.rerun()

            if dismiss_clicked:
                st.session_state.sk_pending_item = None
                st.rerun()
    else:
        st.caption("📷 Point the camera at an item to detect and update stock.")

    st.divider()

    # ── Inventory Table ──────────────────────────────────────────────────
    st.markdown("##### 📋 Stock")
    inv_df = search_products(search_q) if search_q else get_all_products()
    if not inv_df.empty:
        st.dataframe(inv_df, hide_index=True, width='stretch')
    else:
        st.info("No products found.")

    st.divider()
    st.markdown("##### 🚨 Alerts")
    low_df = get_low_stock(3)
    if not low_df.empty:
        for _, r in low_df.iterrows():
            (st.error if r["Qty"] == 0 else st.warning)(
                f"{'🔴' if r['Qty'] == 0 else '⚠️'} **{r['Name']}** — {r['Qty']} left"
            )
    else:
        st.success("✅ All stocked!")


# ── Camera Loop ──────────────────────────────────────────────────────────────
# Only run the camera if there's NO pending form (camera pauses for form).
if run_camera and not st.session_state.sk_pending_item:
    import cv2

    model = load_model(model_choice)
    cap = cv2.VideoCapture(int(cam_index))

    if not cap.isOpened():
        st.error("❌ Camera not found.")
    else:
        try:
            while st.session_state.get("sk_cam_toggle", False):
                ok, frame = cap.read()
                if not ok:
                    st.error("📷 Feed lost.")
                    break

                result = run_detection(model, frame, conf_threshold, img_size)

                # Stock info for annotation colour
                stock_map = {}
                for n in result.unique_names:
                    p = get_product(n)
                    stock_map[n] = p["quantity"] if p else 0

                annotated = annotate_frame(frame, result, stock_map)
                video_ph.image(frame_bgr_to_rgb(annotated), width=400)

                if result.has_items():
                    det_ph.markdown("🔍 " + "  |  ".join(
                        f"**{n}**: {c}" for n, c in result.label_counts.items()))
                else:
                    det_ph.caption("No detections.")

                # ── Debounced detection → store in session_state ─────
                now = time.time()
                best = result.highest_confidence_per_label

                if best:
                    top = max(best, key=best.get)
                    is_debounced = (
                        st.session_state.sk_debounce_item == top
                        and now - st.session_state.sk_debounce_t < 2.0
                    )

                    if best[top] >= conf_threshold and not is_debounced:
                        st.session_state.sk_debounce_item = top
                        st.session_state.sk_debounce_t = now
                        # Store the detected item and pause camera for form
                        st.session_state.sk_pending_item = top
                        st.session_state.sk_pending_conf = best[top]
                        cap.release()
                        st.rerun()  # Rerun renders the form above

                st.session_state.sk_frames += 1
        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            cap.release()
