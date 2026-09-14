"""Monitoring dashboard (spec section 46).

Run with:
    streamlit run src/tradingbot/dashboard/app.py -- --database-url sqlite:///./tradingbot.db

Reads directly from the same SQLite/Postgres database the scanner writes to
(`storage/db.py`) -- there is no separate metrics pipeline to keep in sync.
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default="sqlite:///./tradingbot.db")
    # Streamlit passes its own args through; only parse what comes after `--`.
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1 :]
    else:
        argv = []
    return parser.parse_args(argv)


@st.cache_resource
def get_engine(database_url: str):
    return create_engine(database_url)


def load_table(engine, name: str) -> pd.DataFrame:
    try:
        return pd.read_sql_table(name, engine)
    except Exception:
        return pd.DataFrame()


def main() -> None:
    args = _parse_args()
    st.set_page_config(page_title="Scalping Bot Dashboard", layout="wide")
    st.title("Leveraged Perp Scalping — Monitoring Dashboard")

    engine = get_engine(args.database_url)
    trades = load_table(engine, "trades")
    decisions = load_table(engine, "decisions")
    risk_events = load_table(engine, "risk_events")
    dq_events = load_table(engine, "data_quality_events")
    universe = load_table(engine, "universe_snapshots")

    closed = trades[trades["closed_at_ms"].notna()] if not trades.empty else trades
    open_positions = trades[trades["closed_at_ms"].isna()] if not trades.empty else trades

    col1, col2, col3, col4 = st.columns(4)
    total_pnl = closed["pnl_quote"].sum() if not closed.empty else 0.0
    win_rate = (closed["pnl_quote"] > 0).mean() if not closed.empty else 0.0
    col1.metric("Realized PnL", f"{total_pnl:,.2f}")
    col2.metric("Closed trades", len(closed))
    col3.metric("Win rate", f"{win_rate:.1%}")
    col4.metric("Open positions", len(open_positions))

    st.subheader("Equity curve (cumulative realized PnL)")
    if not closed.empty:
        closed_sorted = closed.sort_values("closed_at_ms").copy()
        closed_sorted["cumulative_pnl"] = closed_sorted["pnl_quote"].cumsum()
        fig = px.line(closed_sorted, x="closed_at_ms", y="cumulative_pnl")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No closed trades yet.")

    st.subheader("Open positions")
    st.dataframe(open_positions[["symbol", "direction", "setup_name", "entry_price", "stop_price", "leverage", "notional", "confidence"]] if not open_positions.empty else open_positions)

    left, right = st.columns(2)
    with left:
        st.subheader("PnL by setup")
        if not closed.empty:
            by_setup = closed.groupby("setup_name")["pnl_quote"].sum().reset_index()
            st.plotly_chart(px.bar(by_setup, x="setup_name", y="pnl_quote"), use_container_width=True)
    with right:
        st.subheader("PnL by symbol")
        if not closed.empty:
            by_symbol = closed.groupby("symbol")["pnl_quote"].sum().reset_index()
            st.plotly_chart(px.bar(by_symbol, x="symbol", y="pnl_quote"), use_container_width=True)

    st.subheader("Recent NO-TRADE / rejected decisions")
    st.dataframe(decisions.sort_values("ts_ms", ascending=False).head(50) if not decisions.empty else decisions)

    st.subheader("Risk events")
    st.dataframe(risk_events.sort_values("ts_ms", ascending=False).head(50) if not risk_events.empty else risk_events)

    st.subheader("Data quality events")
    st.dataframe(dq_events.sort_values("ts_ms", ascending=False).head(50) if not dq_events.empty else dq_events)

    st.subheader("Latest universe scan")
    if not universe.empty:
        latest_ts = universe["ts_ms"].max()
        latest = universe[universe["ts_ms"] == latest_ts]
        st.write(f"{latest['eligible'].sum()} / {len(latest)} symbols eligible")
        st.dataframe(latest.sort_values("liquidity_score", ascending=False))


if __name__ == "__main__":
    main()
