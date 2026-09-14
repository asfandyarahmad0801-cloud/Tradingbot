# Security Considerations

## API keys

- **Never hard-code keys.** `config/config.yaml` holds only non-secret
  parameters; all credentials come from environment variables / `.env`
  (`src/tradingbot/config.py::Secrets`, `pydantic-settings`), which is
  `.gitignore`d.
- **Never request withdrawal permission.** Exchange API keys used by this
  system should be created with **read + trade only**. There is no code
  path in this repository that calls a withdrawal endpoint.
- **Prefer separate key sets** for market-data-only vs. trading, and always
  separate paper/testnet keys from live keys (`.env.example` documents
  this layout).
- **`Secrets.__repr__`/`__str__` are overridden** to print `***redacted***`
  so an accidental `print(secrets)` or exception traceback that includes
  the object doesn't leak keys into logs.
- **IP-restrict API keys** at the exchange level where the exchange
  supports it — this repository cannot enforce that from the client side.

## Live trading guardrails

- `LiveBroker.__init__` raises unless `confirm_live=True` is passed
  explicitly by the caller.
- `main.py`'s `live` subcommand additionally refuses to start unless
  `--i-understand-live-risk` is passed on the command line **and**
  `mode: live` is set in the loaded config file — two independent, explicit
  confirmations, neither of which can be triggered by a config file alone
  or a CLI flag alone.
- Default `config.yaml` mode is `paper`.

## Position safety

- `execution/order_manager.py` never leaves a filled entry without a
  protective stop: if the stop order fails to place, it immediately issues
  an emergency market close of the just-opened position and logs a
  `critical`-level `UNPROTECTED_POSITION_EMERGENCY_EXIT` event.
- The system never treats exchange liquidation as a substitute stop-loss;
  `risk/leverage.py` selects leverage specifically to keep liquidation a
  configurable multiple of stop-distance away from entry.

## Data handling

- No user personal data is collected or stored. Trade/decision/risk-event
  logs (`storage/db.py`) contain only market/trading data (symbols, prices,
  sizes, reasons) — nothing that identifies the operator to a third party.
- The local SQLite database file (`tradingbot.db`, `.gitignore`d) is
  unencrypted by default; if deployed with real trading history, apply
  filesystem-level or database-level encryption appropriate to your
  threat model, and point `database.url` at a properly access-controlled
  Postgres instance for anything beyond local development.

## Dependency surface

- `ccxt` is the primary external trust boundary for both market data and
  order placement — keep it updated, and pin versions in
  `pyproject.toml`/lockfiles for reproducible, auditable deploys.
- The dashboard (`dashboard/app.py`, Streamlit) reads the trading database
  read-only for display; it does not expose any control surface to place
  or cancel orders, so exposing it (even behind auth) does not by itself
  create a path to unauthorized trading.

## Responsible-use note

This system is a decision-support and execution framework for the
operator's own account. It is not designed or intended to be pointed at
markets in a way that manipulates prices (e.g., coordinated pump/dump
participation) — the pump/dump detection modules exist to help the
operator **avoid** being exit liquidity, not to help identify targets.
