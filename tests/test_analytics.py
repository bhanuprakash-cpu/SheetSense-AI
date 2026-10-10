from __future__ import annotations

from io import BytesIO
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sheetsense.analytics import (
    _validate_public_http_url,
    build_summary,
    load_tabular_from_bytes,
    run_query,
)


def test_load_tabular_from_bytes_csv():
    payload = b"region,sales\nnorth,10\nsouth,20\n"
    df = load_tabular_from_bytes("sales.csv", payload)
    assert list(df.columns) == ["region", "sales"]
    assert df.shape == (2, 2)


def test_load_tabular_from_bytes_excel():
    source = pd.DataFrame({"month": ["Jan", "Feb"], "revenue": [100, 120]})
    stream = BytesIO()
    source.to_excel(stream, index=False)
    df = load_tabular_from_bytes("revenue.xlsx", stream.getvalue())
    assert list(df.columns) == ["month", "revenue"]
    assert df.shape == (2, 2)


def test_run_query_chart_and_summary():
    df = pd.DataFrame({"sales": [1, 2, 3], "profit": [3, 4, 5]})
    result = run_query(df, "create a chart")
    assert "Rows: 3" in result.summary
    assert result.chart_data is not None
    assert result.chart_type == "line"


def test_build_summary_empty_data():
    summary = build_summary(pd.DataFrame())
    assert summary == "No data loaded yet."


def test_validate_public_url_rejects_localhost():
    with pytest.raises(ValueError, match="Localhost"):
        _validate_public_http_url("http://localhost/data.csv")


def test_validate_public_url_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="http/https"):
        _validate_public_http_url("file:///tmp/data.csv")


def test_validate_public_url_rejects_loopback_ip():
    with pytest.raises(ValueError, match="Private or unsafe"):
        _validate_public_http_url("http://127.0.0.1/data.csv")
