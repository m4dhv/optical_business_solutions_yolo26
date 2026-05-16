#Utility functions for Telegram bot and PDF Receipt Generation

import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent   # .../majorpart2/backend/
ROOT_DIR    = BACKEND_DIR.parent               # .../majorpart2/
LOGO_PATH   = ROOT_DIR / "static" / "store_logo.png"

# ── Telegram Configuration ──────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "bot_token_placeholder")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "chat_id_placeholder")




# ═══════════════════════════════════════════════════════════════════════════════
# TELEGRAM HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def send_telegram_text(message: str) -> tuple[bool, str]:
    """
    Send a Markdown-formatted text message to the admin chat.
    Returns (success: bool, error_message: str).
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": ADMIN_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True, ""
        return False, f"Telegram API Error ({resp.status_code}): {resp.text}"
    except Exception as exc:
        return False, f"Telegram Connection Error: {exc}"


def send_telegram_document(file_path: str, caption: str = "") -> tuple[bool, str]:
    """
    Send a file (e.g. PDF receipt) to the admin Telegram chat.
    Returns (success: bool, error_message: str).
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": ADMIN_CHAT_ID, "caption": caption, "parse_mode": "Markdown"},
                files={"document": (os.path.basename(file_path), f)},
                timeout=30,
            )
        if resp.status_code == 200:
            return True, ""
        return False, f"Telegram API Error ({resp.status_code}): {resp.text}"
    except Exception as exc:
        return False, f"Telegram Connection Error: {exc}"


def send_stock_update_alert(item_name: str, new_qty: int, price: float):
    """Send a formatted stock update notification."""
    msg = (
        f"📦 *Stock Update*\n\n"
        f"🏷️ *{item_name}*\n"
        f"📊 New Quantity: *{new_qty}*\n"
        f"💰 Price: *₹{price:.2f}*\n\n"
        f"🕒 _{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
    )
    return send_telegram_text(msg)


def send_inventory_summary(products_df):
    """Send a complete inventory summary to Telegram."""
    if products_df.empty:
        return send_telegram_text("📦 *Inventory Update*\n\nNo products in database.")

    msg = "📦 *Live Inventory Update*\n\n"
    for _, row in products_df.iterrows():
        qty = row.get("Qty", 0)
        name = row.get("Name", "Unknown")
        icon = "✅" if qty > 0 else "⚠️"
        msg += f"{icon} *{name}*: {qty} units\n"
    msg += f"\n🕒 _Updated at: {datetime.now().strftime('%H:%M:%S')}_"
    return send_telegram_text(msg)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF RECEIPT GENERATION
# ═══════════════════════════════════════════════════════════════════════════════
def generate_receipt_pdf(
    items: list[dict],
    subtotal: float,
    phone: str,
    output_path: str | None = None,
    txn_id: int | None = None,
) -> str:
    """
    Generate a professional PDF receipt.

    items: list of dicts with keys: 'name', 'qty', 'price', 'subtotal'
    subtotal: pre-tax total
    phone: customer phone number
    output_path: where to save (defaults to receipts/ dir)
    txn_id: optional transaction ID

    Returns: path to the generated PDF file.
    """
    from fpdf import FPDF

    grand_total = round(subtotal, 2)
    ts = datetime.now()

    if output_path is None:
        receipts_dir = ROOT_DIR / "receipts"
        receipts_dir.mkdir(exist_ok=True)
        filename = f"receipt_{ts.strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = str(receipts_dir / filename)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    page_w = pdf.w - 2 * pdf.l_margin

    # ── Header with Logo ─────────────────────────────────────────────────
    if LOGO_PATH.exists():
        try:
            pdf.image(str(LOGO_PATH), x=pdf.l_margin, y=10, w=22)
        except Exception:
            pass  # Skip logo if it fails to load

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_xy(pdf.l_margin + 26, 10)
    pdf.cell(0, 10, "Optical Business Solutions", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(pdf.l_margin + 26, 20)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, "Smart Grocery Retail - Powered by AI Vision", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    pdf.ln(10)

    # ── Divider ──────────────────────────────────────────────────────────
    pdf.set_draw_color(26, 107, 60)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(6)

    # ── Transaction Info ─────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 10)
    info_lines = [
        f"Date: {ts.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Phone: {phone}",
    ]
    if txn_id:
        info_lines.insert(0, f"Transaction #: {txn_id}")

    for line in info_lines:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # ── Items Table ──────────────────────────────────────────────────────
    col_widths = [15, page_w - 15 - 20 - 30 - 30, 20, 30, 30]
    headers = ["#", "Item", "Qty", "Price (Rs.)", "Total (Rs.)"]

    # Table header
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(26, 107, 60)
    pdf.set_text_color(255, 255, 255)
    for i, (w, h) in enumerate(zip(col_widths, headers)):
        align = "C" if i != 1 else "L"
        pdf.cell(w, 8, h, border=0, align=align, fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    # Table rows
    pdf.set_font("Helvetica", "", 9)
    for idx, item in enumerate(items, 1):
        fill = idx % 2 == 0
        if fill:
            pdf.set_fill_color(240, 248, 240)

        pdf.cell(col_widths[0], 7, str(idx), border=0, align="C", fill=fill)
        # Truncate long names
        display_name = item["name"][:35]
        pdf.cell(col_widths[1], 7, display_name, border=0, fill=fill)
        pdf.cell(col_widths[2], 7, str(item["qty"]), border=0, align="C", fill=fill)
        pdf.cell(col_widths[3], 7, f"{item['price']:.2f}", border=0, align="R", fill=fill)
        pdf.cell(col_widths[4], 7, f"{item['subtotal']:.2f}", border=0, align="R", fill=fill)
        pdf.ln()

    # ── Divider ──────────────────────────────────────────────────────────
    pdf.ln(2)
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + page_w, pdf.get_y())
    pdf.ln(4)

    # ── Totals ───────────────────────────────────────────────────────────
    totals_x = pdf.l_margin + page_w - 80

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_x(totals_x)
    pdf.cell(40, 9, "Grand Total:", align="R")
    pdf.set_text_color(26, 107, 60)
    pdf.cell(40, 9, f"Rs.{grand_total:.2f}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    # ── Footer ───────────────────────────────────────────────────────────
    pdf.ln(12)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, "Thank you for shopping with us!", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "This is a computer-generated receipt. All prices are inclusive of taxes.", align="C")

    pdf.output(output_path)
    return output_path
 
 
