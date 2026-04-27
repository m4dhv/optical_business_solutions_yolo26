import streamlit as st
from database_manager import get_recent_transactions, reset_db

st.markdown("# ⚙️ Backend & Admin Dashboard")

tab1, tab2, tab3 = st.tabs(["📊 Transactions", "🛠️ System Settings", "👥 User Management"])

with tab1:
    st.markdown("### Recent Transactions")
    txns = get_recent_transactions(limit=500)
    if not txns.empty:
        st.dataframe(txns, use_container_width=True)
    else:
        st.info("No recent transactions.")

with tab2:
    st.markdown("### Model Configuration Defaults")
    st.selectbox("Default YOLO Model", ["Nano", "Small", "Medium"])
    st.slider("System-wide Confidence Threshold", 0.0, 1.0, 0.5)
    
    st.divider()
    st.markdown("### ⚠️ Danger Zone")
    st.error("Actions here cannot be undone.")
    if st.button("🗑️ Factory Reset Database"):
        reset_db()
        st.success("Database completely cleared.")
        st.rerun()

with tab3:
    st.markdown("### Manage Staff Access")
    st.caption("Future feature: Add/remove staff users and change passwords here.")
    st.dataframe({
        "Username": ["shop", "inv", "admin"],
        "Role": ["Shopkeeper", "Inventory Support", "Backend Team"],
        "Status": ["Active", "Active", "Active"]
    }, hide_index=True)