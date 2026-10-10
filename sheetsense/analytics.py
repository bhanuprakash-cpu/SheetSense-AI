from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import ipaddress
import re
import socket
from typing import Optional
from urllib.parse import quote, unquote, urlparse

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
    safe_url = _normalize_supported_spreadsheet_url(url)
    response = requests.get(safe_url, timeout=15, allow_redirects=False)
    response.raise_for_status()
    name_from_url = safe_url.split("?")[0].lower()
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
        raise ValueError("URL content is not a valid CSV/Excel document.") from exc


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


def _normalize_supported_spreadsheet_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported.")
    if not parsed.hostname:
        raise ValueError("URL must include a host.")

    host = parsed.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        raise ValueError("Localhost or local-network URLs are not allowed.")

    path = unquote(parsed.path or "/")
    if parsed.hostname.lower() == "github.com":
        parts = [segment for segment in path.split("/") if segment]
        if len(parts) < 5 or parts[2] != "blob":
            raise ValueError("GitHub links must follow /owner/repo/blob/branch/path format.")
        owner, repo, _, branch = parts[:4]
        file_path = "/".join(parts[4:])
        if not file_path.lower().endswith(SUPPORTED_TABULAR_EXTENSIONS):
            raise ValueError("URL must point to a CSV/Excel file.")
        encoded_path = quote(file_path, safe="/")
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{encoded_path}"

    if host == "raw.githubusercontent.com":
        if not path.lower().endswith(SUPPORTED_TABULAR_EXTENSIONS):
            raise ValueError("URL must point to a CSV/Excel file.")
        return f"https://raw.githubusercontent.com{quote(path, safe='/')}"

    raise ValueError(
        "Only GitHub spreadsheet links are supported (github.com blob or raw.githubusercontent.com)."
    )


def _validate_public_http_url(url: str) -> None:
    # Backward-compatible validator kept for tests and input checks.
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported.")
    if not parsed.hostname:
        raise ValueError("URL must include a host.")
    host = parsed.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        raise ValueError("Localhost or local-network URLs are not allowed.")

    try:
        resolved = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("Host cannot be resolved.") from exc

    for _, _, _, _, sockaddr in resolved:
        ip_candidate = sockaddr[0]
        ip = ipaddress.ip_address(ip_candidate)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError("Private or unsafe network destinations are not allowed.")


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
