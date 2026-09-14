"""Alerting (spec section 47).

Telegram/Discord are supported because they need only a bot token / webhook
URL (no paid API), matching the spec's "can be supported if APIs are
available" framing. Both are best-effort: a failed alert delivery is logged
but must never raise into the trading loop.
"""
from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger("tradingbot.alerts")


class AlertManager:
    def __init__(self, telegram_bot_token: str = "", telegram_chat_id: str = "", discord_webhook_url: str = "") -> None:
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.discord_webhook_url = discord_webhook_url

    async def send(self, message: str) -> None:
        if self.telegram_bot_token and self.telegram_chat_id:
            await self._send_telegram(message)
        if self.discord_webhook_url:
            await self._send_discord(message)
        if not (self.telegram_bot_token or self.discord_webhook_url):
            logger.info("ALERT (no channel configured): %s", message)

    async def _send_telegram(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={"chat_id": self.telegram_chat_id, "text": message}, timeout=aiohttp.ClientTimeout(total=5))
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram_alert_failed: %r", exc)

    async def _send_discord(self, message: str) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.discord_webhook_url, json={"content": message}, timeout=aiohttp.ClientTimeout(total=5))
        except Exception as exc:  # noqa: BLE001
            logger.warning("discord_alert_failed: %r", exc)


# Canonical alert event names (spec section 47), used as the `event` field
# wherever an alert is triggered from the scanner/risk engine so downstream
# filtering/routing can key off a stable vocabulary.
ALERT_EVENTS = (
    "new_valid_setup", "trade_opened", "trade_closed", "stop_loss_hit", "take_profit_hit",
    "large_liquidation_event", "extreme_funding", "extreme_open_interest", "pump_risk_event",
    "dump_risk_event", "api_failure", "data_failure", "daily_loss_limit", "kill_switch_triggered",
    "excessive_leverage", "liquidation_distance_too_small", "unexpected_position", "unprotected_position",
    "order_rejected", "partial_fill", "exchange_outage", "abnormal_slippage", "abnormal_latency",
    "contract_delisted", "margin_mode_mismatch",
)
