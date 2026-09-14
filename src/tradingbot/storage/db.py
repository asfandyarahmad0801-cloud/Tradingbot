"""Persistence layer (spec section 52).

SQLite is used by default (see config.yaml `database.url`) for local/dev
use; the schema is plain SQLAlchemy Core-mapped tables with no
SQLite-specific types, so pointing `database.url` at a PostgreSQL DSN (e.g.
with a TimescaleDB extension for the high-frequency tables) is a
configuration change, not a code change.

Every trade, every rejected setup, every no-trade decision, and every risk
/ data-quality / kill-switch event is logged here (spec section 45) -- this
module is deliberately the only place that persists them, so there is one
audit trail rather than scattered log lines.
"""
from __future__ import annotations

import time

from sqlalchemy import JSON, Boolean, Column, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class TradeRecord(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, index=True)
    exchange = Column(String)
    direction = Column(String)
    setup_name = Column(String, index=True)
    entry_price = Column(Float)
    stop_price = Column(Float)
    take_profit_json = Column(JSON)
    qty = Column(Float)
    notional = Column(Float)
    leverage = Column(Float)
    margin_used = Column(Float)
    estimated_liquidation_price = Column(Float)
    actual_liquidation_price = Column(Float, nullable=True)
    market_regime = Column(String)
    signal_score = Column(Float)
    factor_scores_json = Column(JSON)
    confidence = Column(Float)
    expected_value_bps = Column(Float)
    expected_holding_seconds = Column(Integer)
    actual_holding_seconds = Column(Float, nullable=True)
    fees_bps = Column(Float, nullable=True)
    slippage_bps = Column(Float, nullable=True)
    funding_bps = Column(Float, nullable=True)
    order_latency_ms = Column(Float, nullable=True)
    fill_latency_ms = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True)
    pnl_quote = Column(Float, nullable=True)
    return_on_margin_pct = Column(Float, nullable=True)
    return_on_notional_pct = Column(Float, nullable=True)
    opened_at_ms = Column(Integer)
    closed_at_ms = Column(Integer, nullable=True)
    mode = Column(String, default="paper")


class DecisionRecord(Base):
    """Covers NO-TRADE decisions and rejected setups (spec section 45)."""

    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_ms = Column(Integer, index=True)
    symbol = Column(String, index=True)
    setup_name = Column(String, nullable=True)
    decision = Column(String)   # "trade" | "no_trade" | "rejected"
    reasons_json = Column(JSON)
    explanation = Column(String, nullable=True)


class RiskEventRecord(Base):
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_ms = Column(Integer, index=True)
    event_type = Column(String)   # "kill_switch" | "daily_loss_limit" | ...
    detail = Column(String)


class DataQualityEventRecord(Base):
    __tablename__ = "data_quality_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_ms = Column(Integer, index=True)
    symbol = Column(String, index=True)
    check = Column(String)
    detail = Column(String)
    severity = Column(String)


class UniverseSnapshotRecord(Base):
    __tablename__ = "universe_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_ms = Column(Integer, index=True)
    symbol = Column(String, index=True)
    eligible = Column(Boolean)
    rejection_reasons_json = Column(JSON)
    liquidity_score = Column(Float)


def _now_ms() -> int:
    return int(time.time() * 1000)


class Repository:
    """Thin synchronous data-access layer. Kept synchronous deliberately --
    all writes here are small, infrequent relative to the scan loop, and
    async SQLite drivers add complexity the spec doesn't require for a
    research/execution framework of this scale."""

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)
        self._session_factory: sessionmaker[Session] = sessionmaker(bind=self.engine, future=True)

    def log_trade_opened(self, **kwargs) -> int:
        with self._session_factory() as session:
            record = TradeRecord(opened_at_ms=_now_ms(), **kwargs)
            session.add(record)
            session.commit()
            return record.id

    def log_trade_closed(self, trade_id: int, **kwargs) -> None:
        with self._session_factory() as session:
            record = session.get(TradeRecord, trade_id)
            if record is None:
                return
            for k, v in kwargs.items():
                setattr(record, k, v)
            record.closed_at_ms = _now_ms()
            session.commit()

    def log_decision(self, symbol: str, decision: str, reasons: list[str], setup_name: str | None = None, explanation: str | None = None) -> None:
        with self._session_factory() as session:
            session.add(
                DecisionRecord(
                    ts_ms=_now_ms(), symbol=symbol, setup_name=setup_name, decision=decision,
                    reasons_json=reasons, explanation=explanation,
                )
            )
            session.commit()

    def log_risk_event(self, event_type: str, detail: str) -> None:
        with self._session_factory() as session:
            session.add(RiskEventRecord(ts_ms=_now_ms(), event_type=event_type, detail=detail))
            session.commit()

    def log_data_quality_events(self, issues) -> None:
        if not issues:
            return
        with self._session_factory() as session:
            for issue in issues:
                session.add(
                    DataQualityEventRecord(
                        ts_ms=_now_ms(), symbol=issue.symbol, check=issue.check,
                        detail=issue.detail, severity=issue.severity,
                    )
                )
            session.commit()

    def log_universe_snapshot(self, entries) -> None:
        with self._session_factory() as session:
            ts = _now_ms()
            for e in entries:
                session.add(
                    UniverseSnapshotRecord(
                        ts_ms=ts, symbol=e.symbol, eligible=e.eligible,
                        rejection_reasons_json=e.rejection_reasons, liquidity_score=e.liquidity_score,
                    )
                )
            session.commit()
