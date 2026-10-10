from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Optional

import pandas as pd
import requests


SUPPORTED_TABULAR_EXTENSIONS = (".csv", ".xls", ".xlsx")
SUPPORTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass
class QueryResult:
    summary: str
    table: Optional[pd.DataFrame] = None
    chart_data: Optional[pd.DataFrame] = None
    chart_type: Optional[str] = None


def load_tabular_from_bytes(filename: str, payload: bytes) -> pd.DataFrame:
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        return pd.read_csv(BytesIO(payload))
    if lower_name.endswith((".xls", ".xlsx")):
        return pd.read_excel(BytesIO(payload))
    raise ValueError("Unsupported tabular file type. Use CSV or Excel files.")


def load_tabular_from_url(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    name_from_url = url.split("?")[0].lower()
    if name_from_url.endswith(SUPPORTED_TABULAR_EXTENSIONS):
        return load_tabular_from_bytes(name_from_url, response.content)

    # Fallback: try CSV first, then Excel
    csv_error: Optional[Exception] = None
    try:
        return pd.read_csv(BytesIO(response.content))
    except Exception as exc:  # pragma: no cover - fallback path
        csv_error = exc
    try:
        return pd.read_excel(BytesIO(response.content))
    except Exception as exc:
        raise ValueError("URL content is not a valid CSV/Excel document.") from exc if csv_error else exc


def extract_table_from_image(payload: bytes) -> pd.DataFrame:
    try:
        import pytesseract
        from PIL import Image
    except Exception as exc:
        raise ValueError(
            "Image text extraction requires optional dependencies: pillow and pytesseract."
        ) from exc

    image = Image.open(BytesIO(payload))
    raw_text = pytesseract.image_to_string(image).strip()
    if not raw_text:
        return pd.DataFrame({"extracted_text": []})

    rows = []
    for line in raw_text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if "," in clean:
            rows.append([item.strip() for item in clean.split(",")])
            continue
        if "\t" in clean:
            rows.append([item.strip() for item in clean.split("\t")])
            continue
        rows.append([clean])

    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    columns = [f"column_{idx + 1}" for idx in range(width)]
    return pd.DataFrame(normalized, columns=columns)


def build_summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "No data loaded yet."
    total_rows, total_columns = df.shape
    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    missing_cells = int(df.isna().sum().sum())
    summary = [
        f"Rows: {total_rows}",
        f"Columns: {total_columns}",
        f"Numeric columns: {len(numeric_columns)}",
        f"Missing values: {missing_cells}",
    ]
    return " | ".join(summary)


def _top_n_request(query: str) -> Optional[int]:
    match = re.search(r"\btop\s+(\d+)\b", query.lower())
    if match:
        return int(match.group(1))
    return None


def run_query(df: pd.DataFrame, query: str) -> QueryResult:
    if df.empty:
        return QueryResult(summary="No data available. Upload data first.")

    lower_query = query.lower()
    top_n = _top_n_request(lower_query) or 10
    result_table = df.head(top_n).copy()
    summary = build_summary(df)

    if "insight" in lower_query or "summary" in lower_query:
        return QueryResult(summary=summary, table=result_table)

    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    if any(token in lower_query for token in ("chart", "plot", "graph", "visual")) and numeric_columns:
        if len(numeric_columns) >= 2:
            chart_data = df[[numeric_columns[0], numeric_columns[1]]].dropna().head(top_n)
            return QueryResult(
                summary=summary,
                table=result_table,
                chart_data=chart_data,
                chart_type="line",
            )
        chart_data = df[[numeric_columns[0]]].dropna().head(top_n)
        return QueryResult(
            summary=summary,
            table=result_table,
            chart_data=chart_data,
            chart_type="bar",
        )

    return QueryResult(summary=summary, table=result_table)

