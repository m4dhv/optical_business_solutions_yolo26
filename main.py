#Default homepage
import streamlit as st
from database_manager import init_db

# ── Page Configuration ──
st.set_page_config(page_title="Optical Business Solutions", page_icon="🛒", layout="wide", initial_sidebar_state="collapsed")
init_db()

# ── Authentication State ──
if "role" not in st.session_state:
    st.session_state.role = "Customer"  # Default to Customer
if "username" not in st.session_state:
    st.session_state.username = None

# ── Define App Pages ──
page_customer = st.Page("pages/customer.py", title="Smart Billing Kiosk", icon="🧾", default=(st.session_state.role == "Customer"))
page_shopkeeper = st.Page("pages/shopkeeper.py", title="Inventory Scanner", icon="🏪")
page_inventory = st.Page("pages/inventory.py", title="Manual Stock", icon="📦")
page_admin = st.Page("pages/admin.py", title="Backend Management", icon="⚙️")

# ── Sidebar: Subtle Staff Login ──
with st.sidebar:
    if st.session_state.username is None:
        with st.expander("🔐 Staff Access"):
            with st.form("staff_login"):
                user = st.text_input("Username")
                pwd = st.text_input("Password", type="password")
                if st.form_submit_button("Login"):
                    # Credentials for your project
                    creds = {
                        "shop": {"pass": "123", "role": "Shopkeeper"},
                        "inv": {"pass": "123", "role": "Inventory Support"},
                        "admin": {"pass": "123", "role": "Backend Team"}
                    }
                    if user in creds and creds[user]["pass"] == pwd:
                        st.session_state.role = creds[user]["role"]
                        st.session_state.username = user
                        st.rerun()
                    else:
                        st.error("Invalid")
    else:
        st.write(f"Logged in: **{st.session_state.role}**")
        if st.button("Logout to Kiosk Mode"):
            st.session_state.role = "Customer"
            st.session_state.username = None
            st.rerun()

# ── Navigation Mapping ──
# Customers only see the scanner; staff see their tools + the scanner.
if st.session_state.role == "Customer":
    pg = st.navigation([page_customer])
elif st.session_state.role == "Shopkeeper":
    pg = st.navigation([page_shopkeeper, page_inventory, page_customer])
elif st.session_state.role == "Inventory Support":
    pg = st.navigation([page_inventory, page_customer])
elif st.session_state.role == "Backend Team":
    pg = st.navigation([page_admin, page_inventory, page_shopkeeper, page_customer])

pg.run()