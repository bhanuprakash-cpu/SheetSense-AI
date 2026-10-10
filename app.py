from __future__ import annotations

import streamlit as st
import pandas as pd

from sheetsense.analytics import (
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_TABULAR_EXTENSIONS,
    build_summary,
    extract_table_from_image,
    load_tabular_from_bytes,
    load_tabular_from_url,
    run_query,
)


st.set_page_config(page_title="SheetSense AI", layout="wide")
st.title("SheetSense AI")
st.caption(
    "AI-powered analytics dashboard for CSV/Excel files, Excel links, screenshots, and data images."
)

if "data" not in st.session_state:
    st.session_state.data = pd.DataFrame()

uploaded_files = st.file_uploader(
    "Upload CSV/Excel files or data screenshots/images",
    type=["csv", "xls", "xlsx", "png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)
data_url = st.text_input("Or paste a CSV/Excel URL")

if st.button("Load data"):
    dataframes = []
    if uploaded_files:
        for uploaded in uploaded_files:
            file_name = uploaded.name.lower()
            payload = uploaded.getvalue()
            if file_name.endswith(SUPPORTED_TABULAR_EXTENSIONS):
                dataframes.append(load_tabular_from_bytes(file_name, payload))
            elif file_name.endswith(SUPPORTED_IMAGE_EXTENSIONS):
                dataframes.append(extract_table_from_image(payload))

    if data_url.strip():
        dataframes.append(load_tabular_from_url(data_url.strip()))

    if dataframes:
        st.session_state.data = pd.concat(dataframes, ignore_index=True, sort=False)
        st.success(f"Loaded {len(dataframes)} source(s).")
    else:
        st.warning("No supported inputs provided.")

if not st.session_state.data.empty:
    st.subheader("Dataset overview")
    st.write(build_summary(st.session_state.data))
    st.dataframe(st.session_state.data.head(100), use_container_width=True)

query = st.text_input(
    "Ask a question (e.g. 'show top 5 rows', 'create a chart', 'give insights')"
)
if st.button("Analyze"):
    result = run_query(st.session_state.data, query)
    st.subheader("Summary")
    st.write(result.summary)
    if result.table is not None:
        st.subheader("Table")
        st.dataframe(result.table, use_container_width=True)
    if result.chart_data is not None:
        st.subheader("Chart")
        if result.chart_type == "line":
            st.line_chart(result.chart_data)
        else:
            st.bar_chart(result.chart_data)

st.divider()
st.markdown(
    "**Coming soon:** automated insights, advanced visualizations, and exportable PDF reports."
)

