# Kalshi Trading Bot Project Handover

This project is a local trading dashboard for Kalshi Miami highest-temperature markets. It pulls Kalshi market data, displays markets and orderbook levels in a Next.js UI, runs weather-based forecast models in the Django backend, and paper-trades the algorithm recommendation against a local SQLite account.

It currently focuses on the `KXHIGHMIA` series, which is Kalshi's Miami daily high temperature market.

## Project Structure

```text
kalshiTradingBot/
  backend/
    config/                  Django project settings and root URLs
    kalshi_api/              Main backend app
      client.py              Kalshi REST API client and response normalization
      stream.py              Kalshi WebSocket to browser SSE bridge
      algorithm.py           Trading algorithm and recommendation logic
      forecast.py            Background forecast runner
      price_tracker.py       Price velocity and daily-high tracker
      paper.py               Paper trading account/order logic
      models.py              SQLite models for paper trading
      auth.py                Kalshi API key/private-key loading and signing
      views.py               HTTP endpoints used by the frontend
      urls.py                Backend route list
    db.sqlite3               Local paper-trading database
    .env                     Local secrets/config, not for frontend
  frontend/
    app/page.tsx             Main dashboard UI
    app/styles.css           Styling
    next.config.mjs          Rewrites /api/* to Django
  accuweather_forecast.py
  accuweather_forecast_2hour.py
  variable_combined.py
  variable_combined_2hour.py
  kmia_asos_90d.csv          Local ASOS weather cache
```

## How To Run

Backend:

```powershell
cd backend
..\kalshibot\Scripts\python.exe manage.py runserver 8000
```

Frontend:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open the Next.js URL, usually:

```text
http://localhost:3000
```

The frontend does not call Django by absolute URL. `frontend/next.config.mjs` rewrites:

```text
/api/:path* -> http://127.0.0.1:8000/api/:path*
```

So browser calls such as `/api/kalshi/miami-temperature` are forwarded to Django.

## Backend API Endpoints

All backend routes live under:

```text
/api/kalshi/
```

Main endpoints:

```text
GET  /api/kalshi/health/
GET  /api/kalshi/miami-temperature/
GET  /api/kalshi/miami-temperature/?market_ticker=<ticker>
GET  /api/kalshi/miami-temperature/stream/
GET  /api/kalshi/paper/state/
POST /api/kalshi/paper/order/
POST /api/kalshi/paper/reset/
GET  /api/kalshi/algorithm/state/
POST /api/kalshi/algorithm/trade/
POST /api/kalshi/algorithm/refresh/
```

Debug endpoints also exist:

```text
GET /api/kalshi/debug-pem/
GET /api/kalshi/debug-ws/
```

Those are for diagnosing Kalshi private-key and WebSocket auth issues. Do not expose them publicly.

## Kalshi REST API Flow

The Kalshi REST client is in `backend/kalshi_api/client.py`.

Base URL:

```text
https://external-api.kalshi.com/trade-api/v2
```

Hard-coded series:

```python
MIAMI_SERIES_TICKER = "KXHIGHMIA"
```

The daily event ticker is generated from the current date:

```text
KXHIGHMIA-YYMMMDD
```

Example:

```text
KXHIGHMIA-26JUN22
```

The default selected market is:

```text
KXHIGHMIA-YYMMMDD-B94.5
```

### What `GET /miami-temperature/` Does

`views.miami_temperature()` calls:

```python
get_miami_temperature_payload(selected_market_ticker)
```

That function performs three Kalshi REST calls:

```text
GET /series/KXHIGHMIA
GET /events/<today_event_ticker>
GET /markets/<selected_market_ticker>/orderbook?depth=5
```

Then it returns one normalized payload:

```json
{
  "series": {},
  "event": {},
  "markets": [],
  "selected_market": {},
  "orderbook": {
    "yes": [],
    "no": []
  },
  "source": {}
}
```

The backend caches each Kalshi REST URL for 2 seconds with Django's cache:

```python
CACHE_SECONDS = 2
```

That keeps the UI responsive while the frontend polls every 2 seconds.

## Series, Events, And Markets

### Series

Kalshi series endpoint:

```text
/series/KXHIGHMIA
```

The backend normalizes it to:

```json
{
  "ticker": "KXHIGHMIA",
  "title": "...",
  "category": "...",
  "frequency": "...",
  "tags": [],
  "settlement_sources": [],
  "important_info": {
    "title": "...",
    "message": "...",
    "markdown": "..."
  },
  "contract_terms_url": "...",
  "contract_url": "..."
}
```

The frontend uses this mainly for title, settlement information, and the important-info banner.

### Event

Kalshi event endpoint:

```text
/events/KXHIGHMIA-YYMMMDD
```

The event response includes the daily event metadata and all markets/brackets for that day.

The backend normalizes event metadata to:

```json
{
  "event_ticker": "KXHIGHMIA-26JUN22",
  "series_ticker": "KXHIGHMIA",
  "title": "...",
  "subtitle": "...",
  "category": "...",
  "mutually_exclusive": true,
  "strike_date": "..."
}
```

### Markets

Each market is one temperature bracket, for example a bracket around `94.5`.

The backend normalizes every raw Kalshi market into:

```json
{
  "ticker": "...",
  "event_ticker": "...",
  "label": "...",
  "title": "...",
  "status": "open",
  "strike_type": "...",
  "floor_strike": 93.5,
  "cap_strike": 94.5,
  "yes_bid_cents": 42,
  "yes_ask_cents": 45,
  "yes_bid_size": 100,
  "yes_ask_size": 80,
  "no_bid_cents": 55,
  "no_ask_cents": 58,
  "last_price_cents": 44,
  "chance_percent": 44,
  "volume": 1234,
  "volume_24h": 200,
  "open_interest": 500,
  "open_time": "...",
  "close_time": "...",
  "expected_expiration_time": "...",
  "rules_primary": "...",
  "rules_secondary": "..."
}
```

Important conversion detail:

Kalshi sends dollar strings like `"0.45"`. `client.py` converts them to integer cents:

```text
"0.45" -> 45
```

Fixed-point sizes such as `yes_bid_size_fp` are converted to floats.

Markets are sorted by `floor_strike`/`cap_strike` so the frontend displays brackets in temperature order.

## Bid, Ask, And Orderbook Display

There are two different price displays:

1. Market-level top bid/ask from `/events/<event_ticker>`
2. Selected-market orderbook depth from `/markets/<ticker>/orderbook?depth=5`

### Market-Level Bid/Ask

For each market row, the UI displays:

```text
YES <yes_ask_cents>
NO  <no_ask_cents>
```

Those are the prices a buyer would currently pay. The frontend also uses bid prices when selling paper positions:

```text
Buy YES  -> selectedMarket.yes_ask_cents
Sell YES -> selectedMarket.yes_bid_cents
Buy NO   -> selectedMarket.no_ask_cents
Sell NO  -> selectedMarket.no_bid_cents
```

In the live ticker stream, if Kalshi sends updated YES prices, the frontend derives NO prices:

```text
no_ask = 100 - yes_bid
no_bid = 100 - yes_ask
```

That mirrors binary contract math: YES and NO prices are complements around 100 cents.

### Selected Market Orderbook

For the selected market, the backend calls:

```text
GET /markets/<selected_market_ticker>/orderbook?depth=5
```

Kalshi returns `orderbook_fp`, which contains `yes_dollars` and `no_dollars`. The backend normalizes each level:

```json
{
  "price_cents": 45,
  "price_dollars": "0.45",
  "count": 100
}
```

The frontend renders:

```text
Top Orderbook
  YES bids
  NO bids
```

It reverses each side before display:

```typescript
payload.orderbook.yes.slice().reverse()
payload.orderbook.no.slice().reverse()
```

So the most relevant/highest levels appear visually at the top/end depending on Kalshi's returned ordering.

### Live WebSocket Updates

`backend/kalshi_api/stream.py` connects to:

```text
wss://external-api-ws.kalshi.com/trade-api/ws/v2
```

It subscribes to all markets in today's event:

```json
{
  "cmd": "subscribe",
  "params": {
    "channels": ["ticker", "orderbook_delta", "trade"],
    "market_tickers": ["..."]
  }
}
```

Because Django views are synchronous, the backend runs the Kalshi WebSocket in a background thread and pushes messages into a queue. The HTTP response to the browser is Server-Sent Events.

Browser endpoint:

```text
GET /api/kalshi/miami-temperature/stream/
```

Frontend usage:

```typescript
const events = new EventSource("/api/kalshi/miami-temperature/stream");
```

Supported SSE event names:

```text
status
auth_missing
stream_error
ticker
orderbook_delta
trade
kalshi_error
```

The frontend currently applies `ticker` events to update the market table. It does not fully rebuild the local orderbook from `orderbook_delta`; the detailed orderbook still comes from the 2-second REST polling of `/miami-temperature`.

If Kalshi WebSocket credentials are missing or fail, the frontend closes the stream and continues using REST polling every 2 seconds.

## Kalshi Auth

Auth helpers live in `backend/kalshi_api/auth.py`.

Environment variables:

```text
KALSHI_API_KEY_ID
KALSHI_PRIVATE_KEY_PATH
KALSHI_PRIVATE_KEY_PEM
```

Either private-key path or private-key PEM can be used.

For WebSocket auth, the backend signs:

```text
<timestamp> + "GET" + "/trade-api/ws/v2"
```

with RSA-PSS/SHA256, then sends:

```text
KALSHI-ACCESS-KEY
KALSHI-ACCESS-SIGNATURE
KALSHI-ACCESS-TIMESTAMP
```

Important: credentials stay in `backend/.env`. Do not move Kalshi credentials into the frontend.

## Forecast System

Forecast orchestration is in `backend/kalshi_api/forecast.py`.

At Django startup, `kalshi_api/apps.py` starts two daemon threads:

```python
start_background_refresh()
start_price_tracking()
```

The forecast thread runs every 15 minutes:

```python
REFRESH_INTERVAL = 900
```

It runs four model scripts in parallel:

```text
accuweather_forecast.py
accuweather_forecast_2hour.py
variable_combined.py
variable_combined_2hour.py
```

Each script is executed as:

```text
python <script> --json-output
```

The expected JSON from each model includes:

```json
{
  "model": "var_1h",
  "T0": 88.0,
  "mean": 93.2,
  "std": 1.4,
  "mode": 93,
  "p10": 91.0,
  "p25": 92.0,
  "p75": 94.0,
  "p90": 95.0,
  "temps": [90, 91, 92, 93, 94],
  "probs": [0.05, 0.12, 0.25, 0.35, 0.23],
  "fit_source": "...",
  "fetched_at": "..."
}
```

The backend caches these model results in memory:

```python
_cache = {
  "results": {},
  "last_run_at": None,
  "running": False
}
```

Manual refresh:

```text
POST /api/kalshi/algorithm/refresh/
```

This starts a background model refresh and returns immediately.

### Weather Data Used By Models

The model scripts use:

```text
AccuWeather current conditions
AccuWeather hourly forecast
Iowa State Mesonet ASOS data for KMIA/MIA
```

The ASOS data is cached in:

```text
kmia_asos_90d.csv
```

The scripts use 90 days of hourly ASOS observations and refresh that cache weekly.

The backend pre-fetches AccuWeather current and forecast data once per refresh and passes it to the model subprocesses through:

```text
AW_SHARED_DATA=<temp json file>
```

This reduces duplicate AccuWeather API calls.

Note: `forecast.py` currently contains a hard-coded AccuWeather API key. For handover or production, move that key into `backend/.env`.

## Model Logic Summary

There are two model families.

### AccuWeather OU Models

Files:

```text
accuweather_forecast.py
accuweather_forecast_2hour.py
```

These fit an Ornstein-Uhlenbeck style temperature process using recent ASOS history and weather covariates:

```text
temperature
cloud cover
humidity
wind
solar term
pressure/dewpoint derivative
hour-of-day regime effects
```

They simulate 10,000 Monte Carlo paths:

```python
N_PATHS = 10_000
SIM_DT = 0.25
```

The result is a probability distribution over integer settlement temperatures.

The 1-hour model forecasts roughly one hour ahead. The 2-hour model chains a 2-hour forecast path.

### Variable Combined VAR + OU Models

Files:

```text
variable_combined.py
variable_combined_2hour.py
```

These first model weather variables jointly with a VAR(1) process:

```text
cloud
relative humidity
wind_u
wind_v
pressure tendency
```

Then each Monte Carlo path feeds path-specific weather variables into the temperature OU model. This is meant to preserve correlated weather scenarios. For example, cloudy/high-humidity/falling-pressure paths remain internally consistent instead of using one averaged weather scenario.

The 2-hour version chains two VAR steps, making the uncertainty wider than a single-step model.

## Trading Algorithm

Core file:

```text
backend/kalshi_api/algorithm.py
```

The algorithm is model-driven. It does not calculate expected value from market price directly. Instead, it picks the live temperature bracket with the highest ensemble model probability.

Key constants:

```python
PROFIT_TARGET_CENTS = 7
MIN_BRACKET_PROB = 0.15
SWITCH_PROB_ADVANTAGE = 0.10
CUTOFF_LOCAL_HOUR = 16
```

Meaning:

```text
PROFIT_TARGET_CENTS
  If an open position is up at least 7 cents per contract, mark it for exit.

MIN_BRACKET_PROB
  Do not enter a new bracket unless the best model probability is at least 15%.

SWITCH_PROB_ADVANTAGE
  If already holding a bracket, only switch to another bracket if the new bracket's
  model probability is at least 10 percentage points higher.

CUTOFF_LOCAL_HOUR
  Used to show time remaining to 4 PM Miami local cutoff.
```

### Bracket Probability

The algorithm computes each bracket's probability from the full model distributions.

For a market with:

```text
floor_strike = 93.5
cap_strike = 94.5
```

it sums model probability where:

```text
temperature >= floor_strike
temperature < cap_strike
```

It does this for each successful model and averages the probabilities.

### Dead Bracket Filter

A bracket is considered dead when:

```text
daily high >= bracket cap
```

or:

```text
yes ask <= 3 cents
```

The daily high is tracked by `price_tracker.py` from the latest model `T0` values. It resets automatically on date rollover.

### Recommendation Flow

`GET /algorithm/state/` runs:

```text
1. Fetch latest Kalshi market data.
2. Record current bid/ask into price velocity tracker.
3. Load paper account state.
4. Build model probabilities per bracket.
5. Generate recommendation.
6. Return forecast, analysis table, recommendation, temp snapshot, and time-to-cutoff.
```

Recommendation behavior:

```text
No valid model results:
  wait

All brackets dead:
  wait

Held position has +7c or better profit:
  hold response with exit_first set

Held bracket is dead:
  hold response with exit_first set

Holding the best YES bracket:
  hold

Different bracket is better by more than 10 percentage points:
  buy new YES bracket with exit_first set for old position

No position and best bracket probability >= 15%:
  buy YES

No position and best bracket probability < 15%:
  wait
```

The action value can look slightly confusing: exits are represented as `exit_first` inside a `hold` or `buy` recommendation. The trade endpoint knows to sell `exit_first` before buying a new recommendation.

### Algorithm Trade Endpoint

`POST /api/kalshi/algorithm/trade/`

Optional body:

```json
{
  "dollars_cents": 1000
}
```

Flow:

```text
1. Re-fetch live market data.
2. Recompute recommendation.
3. If recommendation has exit_first, sell the existing paper position at current bid.
4. If recommendation action is buy, buy the recommended side/ticker at current ask.
5. Return trades and updated paper account.
```

This is paper trading only. There is no real Kalshi order placement in this codebase.

## Price Velocity Tracker

File:

```text
backend/kalshi_api/price_tracker.py
```

Every time algorithm state is loaded, the backend records each market's YES bid and YES ask.

The tracker also polls Kalshi once per minute in a background thread.

Velocity is calculated over a rolling 5-minute window:

```text
YES velocity = change in YES ask cents per minute
NO velocity  = change in derived NO ask cents per minute
```

The frontend shows these in the Bracket Analysis table as `YES cents/min` and `NO cents/min`. The current algorithm mostly uses model probability; velocity is exposed for human context and ranking display, not as the primary trading signal.

## Paper Trading

Files:

```text
backend/kalshi_api/models.py
backend/kalshi_api/paper.py
```

Database:

```text
backend/db.sqlite3
```

Starting account cash:

```python
STARTING_CASH_CENTS = 100_000
```

That is `$1,000.00` paper cash.

Models:

```text
PaperAccount
  name
  cash_cents

PaperPosition
  account
  market_ticker
  market_label
  side
  contracts
  avg_price_cents

PaperTrade
  account
  market_ticker
  market_label
  action
  side
  price_cents
  contracts
  cash_delta_cents
  realized_pl_cents
```

Manual paper order endpoint:

```text
POST /api/kalshi/paper/order/
```

Body:

```json
{
  "action": "buy",
  "side": "yes",
  "market_ticker": "KXHIGHMIA-26JUN22-B94.5",
  "market_label": "94 to 95",
  "price_cents": 45,
  "dollars_cents": 1000
}
```

Contract calculation:

```text
contracts = dollars_cents / price_cents
```

Example:

```text
$10 at 45 cents -> 1000 / 45 = 22.2222 contracts
```

Buy behavior:

```text
cash decreases
position contracts increase
average price updates by weighted average
```

Sell behavior:

```text
cash increases
position contracts decrease
realized P&L = (sell_price - average_price) * contracts_sold
```

If the requested sell is larger than the position, it sells only the available contracts.

Reset endpoint:

```text
POST /api/kalshi/paper/reset/
```

This deletes paper positions and trades, then resets cash to `$1,000.00`.

## Frontend Behavior

Main file:

```text
frontend/app/page.tsx
```

### Market Data

On page load and whenever the selected market changes, the frontend polls:

```text
GET /api/kalshi/miami-temperature?market_ticker=<selectedTicker>
```

every 2 seconds.

The selected ticker is also stored in the URL:

```text
?market_ticker=<ticker>
```

### Live Stream

The frontend starts:

```typescript
new EventSource("/api/kalshi/miami-temperature/stream")
```

Ticker events patch the in-memory market list. If the stream fails, normal 2-second polling continues.

### Paper Trading UI

The trade card chooses price based on action and side:

```text
buy yes  -> YES ask
sell yes -> YES bid
buy no   -> NO ask
sell no  -> NO bid
```

After placing a paper order, the returned paper state replaces the frontend paper state.

### Portfolio UI

The frontend marks open positions to market using current bid prices:

```text
YES position -> yes_bid_cents
NO position  -> no_bid_cents
```

Net P&L:

```text
cash + open_position_value - starting_cash
```

### Algorithm UI

The frontend polls:

```text
GET /api/kalshi/algorithm/state/
```

every 30 seconds.

The "Refresh Forecast" button posts:

```text
POST /api/kalshi/algorithm/refresh/
```

Then the page polls algorithm state every 5 seconds for up to 2 minutes.

The "Run Cycle" button posts:

```text
POST /api/kalshi/algorithm/trade/
```

The auto-trade checkbox calls the same endpoint every 60 seconds while enabled.

Again: this is auto paper trading, not live Kalshi trading.

## Data Flow Overview

Market display:

```text
Frontend page
  -> /api/kalshi/miami-temperature
    -> Django view
      -> client.py
        -> Kalshi /series/KXHIGHMIA
        -> Kalshi /events/<today>
        -> Kalshi /markets/<selected>/orderbook
      <- normalized JSON
  <- dashboard renders markets, selected contract, orderbook
```

Live prices:

```text
Kalshi WebSocket
  -> stream.py background thread
    -> queue
      -> Django StreamingHttpResponse as SSE
        -> browser EventSource
          -> update market bid/ask in React state
```

Algorithm state:

```text
Frontend algorithm panel
  -> /api/kalshi/algorithm/state
    -> fetch Kalshi markets
    -> record prices for velocity
    -> read forecast cache
    -> read paper positions
    -> compute bracket probabilities
    -> generate recommendation
  <- forecast + analysis + recommendation
```

Forecast refresh:

```text
Django startup or manual refresh
  -> forecast.py
    -> fetch shared AccuWeather data
    -> run 4 model scripts in parallel
    -> cache model JSON in memory
```

Paper trade:

```text
Frontend order card or algorithm trade endpoint
  -> paper.py
    -> validate order
    -> update SQLite PaperAccount/PaperPosition/PaperTrade
  <- updated paper state
```

## Important Assumptions And Caveats

This is a local development app:

```text
DEBUG = True
SECRET_KEY is dev-only
ALLOWED_HOSTS = localhost/127.0.0.1
SQLite database
CSRF exempt on POST endpoints
```

Do not deploy publicly without security work.

The market is hard-coded to Miami:

```text
KXHIGHMIA
MIA/KMIA ASOS data
AccuWeather location 3593859
```

The default selected market is hard-coded as `B94.5`. If Kalshi changes bracket naming or today's event does not include that ticker, the backend falls back to the first available market for `selected_market`, but the frontend selected ticker may still begin with the default until the user selects another row.

The forecast cache is in memory. Restarting Django clears model results until the next refresh completes.

The price tracker is also in memory. Restarting Django clears velocity history and current/daily-high state.

The WebSocket needs valid Kalshi API credentials. Without them, the dashboard still works through REST polling.

The paper account persists in SQLite. To reset it from the UI, use "Reset paper account."

The algorithm currently only buys YES contracts for the selected best bracket. It may sell YES or NO if the existing paper position side is what `exit_first` references, but recommendations are generated for YES entries.

## Good Files To Read First

For a new developer, read in this order:

```text
backend/kalshi_api/client.py
backend/kalshi_api/views.py
frontend/app/page.tsx
backend/kalshi_api/algorithm.py
backend/kalshi_api/forecast.py
backend/kalshi_api/paper.py
backend/kalshi_api/stream.py
```

That covers the whole request/response path before getting into the heavier weather model scripts.

## Suggested Cleanup Before Real Handover

Move the AccuWeather key out of `forecast.py` and into `backend/.env`.

Create `backend/.env.example` with placeholder variables:

```text
KALSHI_API_KEY_ID=
KALSHI_PRIVATE_KEY_PATH=
KALSHI_PRIVATE_KEY_PEM=
ACCUWEATHER_API_KEY=
```

Add `backend/db.sqlite3`, logs, `.next`, `node_modules`, virtualenv folders, and caches to `.gitignore` if this will be shared through Git.

Consider adding a real API schema or small example JSON files for the main endpoints.

Consider renaming "Kalshi Clone" references in README files if this is intended as a trading dashboard rather than a clone.
