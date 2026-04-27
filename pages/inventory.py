#inventory management page accessible by inventory manager
import streamlit as st
from database_manager import get_all_products, update_product, search_products

st.markdown("# Manual Inventory Management")
st.caption("Update stock quantities and prices manually.")

search_q = st.text_input("🔍 Search Product by Name")
inv_df = search_products(search_q) if search_q else get_all_products()

if not inv_df.empty:
    st.dataframe(inv_df, hide_index=True,width='stretch')
    
    st.divider()
    st.markdown("###  Quick Update")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        item = st.selectbox("Select Item", inv_df['Name'].tolist())
    with col2:
        qty_add = st.number_input("Add Quantity", min_value=0, step=1)
    with col3:
        new_price = st.number_input("Update Price (₹)", min_value=0.0, step=1.0)
    with col4:
        st.markdown("<br>", unsafe_allow_html=True) # padding
        if st.button("Save Changes", type="primary", width='stretch'):
            update_product(item, price=new_price if new_price > 0 else None, add_qty=qty_add)
            st.success(f"Updated {item}!")
            st.rerun()
else:
    st.info("No products found in the database.")