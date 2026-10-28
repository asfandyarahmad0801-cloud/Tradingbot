"""Configuration loading.

Non-secret operating parameters live in a YAML file (config/config.yaml).
Secrets (API keys) live only in environment variables / .env and are never
merged into the YAML or written to logs.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExchangeConfig(BaseModel):
    id: str = "binanceusdm"
    sandbox: bool = True
    quote_currencies: list[str] = Field(default_factory=lambda: ["USDT"])
    rate_limit_ms: int = 50


class UniverseConfig(BaseModel):
    refresh_interval_seconds: int = 300
    quote_currencies: list[str] = Field(default_factory=lambda: ["USDT"])
    min_quote_volume_24h_usd: float = 5_000_000
    min_orderbook_depth_usd_within_10bps: float = 50_000
    max_spread_bps: float = 8
    min_contract_age_days: int = 3
    max_price_staleness_seconds: int = 10
    exclude_coin_margined: bool = True
    max_symbols_scanned_concurrently: int = 60


class ScalpingHorizon(BaseModel):
    max_holding_seconds: int
    enabled: bool = True


class TimeframesConfig(BaseModel):
    entry: list[str] = Field(default_factory=lambda: ["1m", "3m"])
    confirmation: list[str] = Field(default_factory=lambda: ["5m", "15m"])
    higher_context: list[str] = Field(default_factory=lambda: ["1h"])


class RiskConfig(BaseModel):
    risk_per_trade_pct: float = 0.25
    max_daily_loss_pct: float = 2.0
    max_weekly_loss_pct: float = 5.0
    max_portfolio_exposure_pct: float = 30.0
    max_effective_account_leverage: float = 3.0
    max_position_leverage: float = 5.0
    max_concurrent_positions: int = 4
    max_positions_per_coin: int = 1
    max_correlated_cluster_exposure_pct: float = 12.0
    max_consecutive_losses: int = 4
    max_trades_per_hour: int = 6
    max_trades_per_coin_per_day: int = 3
    min_liquidation_distance_multiple_of_stop: float = 3.0
    max_slippage_bps: float = 15
    max_spread_bps: float = 8
    cooldown_seconds_after_loss: int = 300
    cooldown_seconds_after_exit: int = 60
    # "risk_pct": size from risk_per_trade_pct and stop distance (default).
    # "fixed_margin": every trade posts fixed_margin_usd at fixed_leverage.
    sizing_mode: Literal["risk_pct", "fixed_margin"] = "risk_pct"
    fixed_margin_usd: float = 10.0
    fixed_leverage: float = 10.0
    max_loss_per_trade_usd: float | None = None   # reject trades whose stop loss (+fees) would exceed this
    max_total_loss_usd: float | None = None       # halt all new trading once equity falls this far below start


class LearningConfig(BaseModel):
    enabled: bool = True
    memory_path: str = "state/setup_memory.json"
    loss_streak_for_cooldown: int = 3
    cooldown_minutes: int = 1440
    min_trades_to_judge: int = 15
    ban_t_threshold: float = -1.0
    judge_window: int = 50


class ExpectancyConfig(BaseModel):
    min_expected_value_bps: float = 5.0
    min_reward_to_risk: float = 1.3
    min_win_probability: float = 0.35


class ExecutionConfig(BaseModel):
    default_order_type: str = "limit_post_only"
    max_market_order_slippage_bps: float = 10
    order_timeout_seconds: float = 5
    max_order_split_notional_usd: float = 20_000
    paper_starting_balance: float = 10_000.0


class MacroConfig(BaseModel):
    blackout_minutes_before_event: int = 15
    blackout_minutes_after_event: int = 15
    leverage_multiplier_during_event_window: float = 0.5


class PumpDumpConfig(BaseModel):
    pump_score_block_threshold: float = 85
    dump_score_block_threshold: float = 85


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///./tradingbot.db"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    json_format: bool = Field(default=True, alias="json")

    model_config = {"populate_by_name": True}


class AppConfig(BaseModel):
    mode: Literal["backtest", "paper", "live"] = "paper"
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    timeframes: TimeframesConfig = Field(default_factory=TimeframesConfig)
    scalping_horizons: dict[str, ScalpingHorizon] = Field(default_factory=dict)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    expectancy: ExpectancyConfig = Field(default_factory=ExpectancyConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    macro: MacroConfig = Field(default_factory=MacroConfig)
    pump_dump: PumpDumpConfig = Field(default_factory=PumpDumpConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class Secrets(BaseSettings):
    """Secrets sourced exclusively from environment variables / .env.

    Never populated from YAML, never logged, never serialized.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    exchange_api_key: str = Field(default="", alias="EXCHANGE_API_KEY")
    exchange_api_secret: str = Field(default="", alias="EXCHANGE_API_SECRET")
    exchange_readonly_api_key: str = Field(default="", alias="EXCHANGE_READONLY_API_KEY")
    exchange_readonly_api_secret: str = Field(default="", alias="EXCHANGE_READONLY_API_SECRET")
    news_api_key: str = Field(default="", alias="NEWS_API_KEY")
    social_sentiment_api_key: str = Field(default="", alias="SOCIAL_SENTIMENT_API_KEY")
    onchain_data_api_key: str = Field(default="", alias="ONCHAIN_DATA_API_KEY")
    macro_calendar_api_key: str = Field(default="", alias="MACRO_CALENDAR_API_KEY")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    discord_webhook_url: str = Field(default="", alias="DISCORD_WEBHOOK_URL")
    database_url: str = Field(default="", alias="DATABASE_URL")

    def __repr__(self) -> str:  # pragma: no cover - safety against accidental logging
        return "Secrets(***redacted***)"

    __str__ = __repr__


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load YAML config, applying the TRADINGBOT_CONFIG_PATH / TRADINGBOT_MODE
    environment overrides used by tests and deployment scripts."""
    config_path = Path(path or os.environ.get("TRADINGBOT_CONFIG_PATH", "config/config.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open() as f:
        raw = yaml.safe_load(f) or {}

    mode_override = os.environ.get("TRADINGBOT_MODE")
    if mode_override:
        raw["mode"] = mode_override

    return AppConfig.model_validate(raw)


def load_secrets() -> Secrets:
    return Secrets()
