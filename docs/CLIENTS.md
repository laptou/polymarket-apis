# Polymarket API Clients Documentation

This document provides comprehensive documentation for operating the Polymarket API clients. All clients support both synchronous and asynchronous operations, enabling efficient parallel API calls.

## Table of Contents

- [Quick Start](#quick-start)
- [Async Pattern](#async-pattern)
- [PolymarketClobClient](#polymarketclobclient)
- [PolymarketDataClient](#polymarketdataclient)
- [PolymarketGammaClient](#polymarketgammaclient)
- [PolymarketWebsocketsClient](#polymarketwebsocketsclient)
- [PolymarketGraphQLClient](#polymarketgraphqlclient)
- [PolymarketWeb3Client](#polymarketweb3client)
- [Common Types](#common-types)
- [Error Handling](#error-handling)

---

## Quick Start

```python
from polymarket_apis.clients import (
    PolymarketClobClient,
    PolymarketDataClient,
    PolymarketGammaClient,
    PolymarketWebsocketsClient,
)

# CLOB client requires authentication
clob = PolymarketClobClient(
    private_key="0x...",
    address="0x...",
)

# Data and Gamma clients are unauthenticated
data = PolymarketDataClient()
gamma = PolymarketGammaClient()
ws = PolymarketWebsocketsClient()
```

---

## Async Pattern

All HTTP clients provide async methods prefixed with `a`. Use `asyncio.gather()` for parallel requests:

```python
import asyncio

async def fetch_parallel():
    async with PolymarketDataClient() as client:
        # parallel requests - 3x faster than sequential
        positions, trades, activity = await asyncio.gather(
            client.aget_positions(user_address),
            client.aget_trades(user=user_address),
            client.aget_activity(user_address),
        )
        return positions, trades, activity

# run async code
results = asyncio.run(fetch_parallel())
```

### Context Manager Pattern

```python
# sync
with PolymarketDataClient() as client:
    positions = client.get_positions(user)

# async
async with PolymarketDataClient() as client:
    positions = await client.aget_positions(user)
```

---

## PolymarketClobClient

Central Limit Order Book client for trading operations. Requires authentication.

### Initialization

```python
from polymarket_apis.clients import PolymarketClobClient
from polymarket_apis.types.clob_types import ApiCreds

client = PolymarketClobClient(
    private_key="0x...",           # wallet private key
    address="0x...",               # wallet address (proxy or EOA)
    creds=None,                    # optional: pre-existing ApiCreds
    chain_id=137,                  # 137=Polygon, 80002=Amoy testnet
    signature_type=1,              # 0=EOA, 1=Proxy, 2=Gnosis Safe
)
```

### Market Data Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_midpoint(token_id)` | `aget_midpoint` | Get mid-market price |
| `get_midpoints(token_ids)` | `aget_midpoints` | Batch mid prices |
| `get_spread(token_id)` | `aget_spread` | Get bid-ask spread |
| `get_spreads(token_ids)` | `aget_spreads` | Batch spreads |
| `get_price(token_id, side)` | `aget_price` | Get BUY/SELL price |
| `get_prices(params)` | `aget_prices` | Batch prices |
| `get_order_book(token_id)` | `aget_order_book` | Full orderbook |
| `get_order_books(token_ids)` | `aget_order_books` | Batch orderbooks |
| `get_last_trade_price(token_id)` | `aget_last_trade_price` | Last trade |
| `get_tick_size(token_id)` | `aget_tick_size` | Min tick size |
| `get_neg_risk(token_id)` | `aget_neg_risk` | Is neg risk market |

#### Examples

```python
# get orderbook for a token
book = client.get_order_book("12345...")
print(f"Best bid: {book.bids[0].price}, Best ask: {book.asks[0].price}")

# parallel market data fetch
async with client:
    midpoints = await asyncio.gather(
        client.aget_midpoint(token1),
        client.aget_midpoint(token2),
        client.aget_midpoint(token3),
    )
```

### Order Methods

| Method | Async | Description |
|--------|-------|-------------|
| `create_order(order_args, options)` | `acreate_order` | Sign an order |
| `post_order(order, order_type)` | `apost_order` | Submit signed order |
| `create_and_post_order(...)` | `acreate_and_post_order` | Create + submit |
| `post_orders(args)` | `apost_orders` | Batch submit |
| `create_market_order(...)` | `acreate_market_order` | Market order |
| `create_and_post_market_order(...)` | `acreate_and_post_market_order` | Market order + submit |
| `cancel_order(order_id)` | `acancel_order` | Cancel single |
| `cancel_orders(order_ids)` | `acancel_orders` | Cancel multiple |
| `cancel_all()` | `acancel_all` | Cancel all orders |
| `get_orders(...)` | `aget_orders` | List open orders |

#### Order Types

```python
from polymarket_apis.types.clob_types import OrderType

OrderType.GTC   # Good Till Cancelled
OrderType.GTD   # Good Till Date
OrderType.FOK   # Fill Or Kill
```

#### Creating and Posting Orders

```python
from polymarket_apis.types.clob_types import OrderArgs, OrderType

# limit order
order_args = OrderArgs(
    token_id="12345...",
    price=0.55,               # 55 cents
    size=100.0,               # 100 USDC
    side="BUY",
    fee_rate_bps=None,        # auto-detect
)

response = client.create_and_post_order(
    order_args=order_args,
    order_type=OrderType.GTC,
)
print(f"Order ID: {response.order_id}")

# market order (fills immediately at best price)
from polymarket_apis.types.clob_types import MarketOrderArgs

market_args = MarketOrderArgs(
    token_id="12345...",
    amount=50.0,              # 50 USDC worth
    side="BUY",
    order_type=OrderType.FOK,
)
response = client.create_and_post_market_order(market_args)
```

### Account Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_usdc_balance()` | `aget_usdc_balance` | USDC balance |
| `get_token_balance(token_id)` | `aget_token_balance` | Token balance |
| `get_trades(...)` | `aget_trades` | Trade history |
| `get_total_rewards(date)` | `aget_total_rewards` | Daily rewards |
| `get_reward_markets(...)` | `aget_reward_markets` | Reward-eligible markets |

### Market Info Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_market(condition_id)` | `aget_market` | Market by condition |
| `get_markets(next_cursor)` | `aget_markets` | Paginated markets |
| `get_all_markets()` | `aget_all_markets` | All markets |
| `get_recent_history(token_id, interval)` | `aget_recent_history` | Price history |
| `get_history(token_id, start, end)` | `aget_history` | Custom range history |

---

## PolymarketDataClient

Read-only client for market data, positions, trades, and leaderboards. No authentication required.

### Initialization

```python
from polymarket_apis.clients import PolymarketDataClient

client = PolymarketDataClient()
# or with custom base URL
client = PolymarketDataClient(base_url="https://data-api.polymarket.com")
```

### Position Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_positions(user, ...)` | `aget_positions` | User positions with filters |
| `get_all_positions(user)` | `aget_all_positions` | All positions via GraphQL |
| `get_closed_positions(user)` | `aget_closed_positions` | Closed positions |
| `get_value(user, condition_ids)` | `aget_value` | Position value |

#### Position Filters

```python
positions = client.get_positions(
    user="0x...",
    condition_id="0x...",           # filter by market
    event_id=12345,                 # or filter by event
    size_threshold=1.0,             # min position size
    redeemable=False,               # filter redeemable
    mergeable=False,                # filter mergeable
    sort_by="TOKENS",               # TOKENS, CURRENT, INITIAL, CASHPNL, PERCENTPNL, etc.
    sort_direction="DESC",
    limit=100,
    offset=0,
)
```

### Trade Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_trades(...)` | `aget_trades` | Trade history |
| `get_activity(user, ...)` | `aget_activity` | Activity feed |

#### Trade Filters

```python
trades = client.get_trades(
    user="0x...",
    condition_id="0x...",
    side="BUY",                     # or "SELL"
    taker_only=True,
    filter_type="CASH",             # or "TOKENS"
    filter_amount=100.0,            # min amount
    limit=100,
)
```

### Market Info Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_holders(condition_id)` | `aget_holders` | Top token holders |
| `get_open_interest(condition_ids)` | `aget_open_interest` | Open interest |
| `get_live_volume(event_id)` | `aget_live_volume` | Live trading volume |
| `get_total_markets_traded(user)` | `aget_total_markets_traded` | Markets count |

### PnL and Leaderboard

| Method | Async | Description |
|--------|-------|-------------|
| `get_pnl(user, period, frequency)` | `aget_pnl` | PnL timeseries |
| `get_user_metric(user, metric, window)` | `aget_user_metric` | Profit/volume |
| `get_leaderboard_user_rank(user, ...)` | `aget_leaderboard_user_rank` | User rank |
| `get_leaderboard_top_users(...)` | `aget_leaderboard_top_users` | Top traders |

```python
# get user's PnL over last week with hourly granularity
pnl = client.get_pnl(user="0x...", period="1w", frequency="1h")

# get leaderboard
top_traders = client.get_leaderboard_top_users(
    metric="profit",    # or "volume"
    window="30d",       # 1d, 7d, 30d, all
    limit=100,
)
```

---

## PolymarketGammaClient

Client for market/event metadata, search, tags, and AI summaries. No authentication required.

### Initialization

```python
from polymarket_apis.clients import PolymarketGammaClient

client = PolymarketGammaClient()
```

### Search

```python
results = client.search(
    query="bitcoin",
    status="active",                # or "resolved"
    sort="volume",                  # volume, volume_24hr, liquidity, etc.
    limit_per_type=10,
)
# results contains: events, markets, tags, profiles
```

### Market Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_market(market_id)` | `aget_market` | Market by ID |
| `get_markets(...)` | `aget_markets` | Markets with filters |
| `get_market_by_slug(slug)` | `aget_market_by_slug` | Market by URL slug |
| `get_market_tags(market_id)` | `aget_market_tags` | Tags for market |

```python
# get all active markets with high volume
markets = client.get_markets(
    active=True,
    volume_num_min=100000,
    order="volume_num",
    ascending=False,
    limit=50,
)
```

### Event Methods

| Method | Async | Description |
|--------|-------|-------------|
| `get_events(...)` | `aget_events` | Events with filters |
| `get_all_events(...)` | `aget_all_events` | All events (paginated) |
| `get_event_by_id(event_id)` | `aget_event_by_id` | Event by ID |
| `get_event_by_slug(slug)` | `aget_event_by_slug` | Event by slug |
| `get_event_tags(event_id)` | `aget_event_tags` | Tags for event |

```python
# get all active politics events
events = client.get_all_events(
    active=True,
    tag_slug="politics",
)
```

### Tags and Categories

| Method | Async | Description |
|--------|-------|-------------|
| `get_tags(...)` | `aget_tags` | All tags |
| `get_all_tags()` | `aget_all_tags` | Fetch all (paginated) |
| `get_tag(tag_id)` | `aget_tag` | Single tag |
| `get_related_tags_by_tag_id(...)` | `aget_related_tags_by_tag_id` | Related tags |
| `get_related_tags_by_slug(...)` | `aget_related_tags_by_slug` | Related by slug |

### Sports and Teams

| Method | Async | Description |
|--------|-------|-------------|
| `get_sports_metadata()` | `aget_sports_metadata` | Sports list |
| `get_teams(...)` | `aget_teams` | Teams with filters |
| `get_all_teams()` | `aget_all_teams` | All teams |

### Series

| Method | Async | Description |
|--------|-------|-------------|
| `get_series(...)` | `aget_series` | Series with filters |
| `get_all_series()` | `aget_all_series` | All series |
| `get_series_by_id(series_id)` | `aget_series_by_id` | Single series |

### Comments

| Method | Async | Description |
|--------|-------|-------------|
| `get_comments(entity_type, entity_id)` | `aget_comments` | Comments on entity |
| `get_comments_by_id(comment_id)` | `aget_comments_by_id` | Comment thread |
| `get_comments_by_user_address(addr)` | `aget_comments_by_user_address` | User's comments |

### AI Summaries (Sync Only)

```python
# streams AI-generated event summary to stdout
client.grok_event_summary("event-slug")

# election candidate information
client.grok_election_market_explanation("Joe Biden", "2024 Presidential Election")
```

---

## PolymarketWebsocketsClient

Real-time websocket streams for market data and user events.

### Initialization

```python
from polymarket_apis.clients import PolymarketWebsocketsClient

ws = PolymarketWebsocketsClient()
```

### Sync API (Blocking)

```python
# market data stream - blocks forever
ws.market_socket(token_ids=["token1", "token2"])

# user events stream - requires auth
ws.user_socket(creds=api_creds)

# live data stream with subscriptions
subscriptions = [
    {"topic": "clob_market", "assets": ["token1"]},
    {"topic": "activity", "event_slugs": ["some-event"]},
]
ws.live_data_socket(subscriptions)
```

### Async API (Recommended)

Async streams return `AsyncIterator` for easy processing:

```python
import asyncio

async def stream_markets():
    async for event in ws.amarket_stream(["token1", "token2"]):
        if hasattr(event, "bids"):
            print(f"Book update: best bid {event.bids[0].price}")

asyncio.run(stream_markets())
```

#### Async Methods

| Method | Description |
|--------|-------------|
| `amarket_stream(token_ids)` | Orderbook and price updates |
| `auser_stream(creds)` | User order/trade events |
| `alive_data_stream(subscriptions)` | Multi-topic live data |

#### Parallel Streams

```python
async def run_streams():
    async def process_markets():
        async for event in ws.amarket_stream(tokens):
            handle_market_event(event)

    async def process_user():
        async for event in ws.auser_stream(creds):
            handle_user_event(event)

    await asyncio.gather(
        process_markets(),
        process_user(),
    )

asyncio.run(run_streams())
```

### Subscription Topics

For `live_data_socket` / `alive_data_stream`:

| Topic | Description | Required Fields |
|-------|-------------|-----------------|
| `clob_market` | Orderbook updates | `assets`: list of token_ids |
| `clob_user` | User orders/trades | `clob_auth`: ApiCreds |
| `activity` | Trade activity | `event_slugs` or `condition_ids` |
| `crypto_prices` | Crypto prices | `symbols`: ["BTC", "ETH", ...] |
| `comments` | Comment events | `event_ids` |
| `reactions` | Reaction events | `event_ids` |

```python
subscriptions = [
    {"topic": "clob_market", "assets": ["token1", "token2"]},
    {"topic": "activity", "event_slugs": ["presidential-election-2024"]},
    {"topic": "clob_user"},  # requires creds parameter
]

async for event in ws.alive_data_stream(subscriptions, creds=api_creds):
    print(event)
```

---

## PolymarketGraphQLClient

Direct GraphQL access to Polymarket subgraphs.

### Endpoints

- `activity_subgraph` - Activity data
- `fpmm_subgraph` - Fixed product market maker
- `open_interest_subgraph` - Open interest
- `orderbook_subgraph` - Orderbook data
- `pnl_subgraph` - PnL calculations
- `positions_subgraph` - Position data
- `sports_oracle_subgraph` - Sports oracle
- `wallet_subgraph` - Wallet data

### Sync Client

```python
from polymarket_apis.clients import PolymarketGraphQLClient

client = PolymarketGraphQLClient(endpoint_name="positions_subgraph")

result = client.query("""
    query {
        userBalances(where: {user: "0x..."}) {
            balance
            asset { id }
        }
    }
""")
```

### Async Client

```python
from polymarket_apis.clients import AsyncPolymarketGraphQLClient

client = AsyncPolymarketGraphQLClient(endpoint_name="positions_subgraph")

result = await client.query("""
    query {
        userBalances(first: 100) {
            user
            balance
        }
    }
""")
```

---

## PolymarketWeb3Client

Blockchain interactions for deposits, withdrawals, and position management.

### Standard Client (Pays Gas)

```python
from polymarket_apis.clients import PolymarketWeb3Client

client = PolymarketWeb3Client(
    private_key="0x...",
    signature_type=1,       # 0=EOA, 1=Proxy, 2=Safe
    chain_id=137,
)

# check balances
print(f"POL: {client.get_pol_balance()}")
print(f"USDC: {client.get_usdc_balance()}")

# position operations
client.split_position(condition_id, amount=100.0, neg_risk=True)
client.merge_position(condition_id, amount=100.0, neg_risk=True)
client.redeem_position(condition_id, amounts=[50.0, 50.0], neg_risk=True)

# transfers
client.transfer_usdc(recipient="0x...", amount=100.0)
client.transfer_token(token_id, recipient="0x...", amount=50.0)

# approvals
client.set_all_approvals()  # sets all required token approvals
```

### Gasless Client (Relayer)

```python
from polymarket_apis.clients import PolymarketGaslessWeb3Client

client = PolymarketGaslessWeb3Client(
    private_key="0x...",
    signature_type=1,       # 1=Proxy or 2=Safe only
)

# same operations, but submitted via relayer (no gas fees)
client.split_position(condition_id, amount=100.0)
```

---

## Common Types

### EthAddress

```python
from polymarket_apis.types.common import EthAddress

address: EthAddress = "0x1234567890123456789012345678901234567890"
```

### Keccak256

```python
from polymarket_apis.types.common import Keccak256

condition_id: Keccak256 = "0xabcd..."  # 32-byte hash
```

### ApiCreds

```python
from polymarket_apis.types.clob_types import ApiCreds

creds = ApiCreds(
    key="api_key",
    secret="api_secret",
    passphrase="passphrase",
)
```

### OrderArgs

```python
from polymarket_apis.types.clob_types import OrderArgs

args = OrderArgs(
    token_id="12345...",
    price=0.55,
    size=100.0,
    side="BUY",           # or "SELL"
    fee_rate_bps=None,    # auto-detect
    expiration=None,      # optional: unix timestamp
    nonce=None,           # optional: custom nonce
)
```

### MarketOrderArgs

```python
from polymarket_apis.types.clob_types import MarketOrderArgs, OrderType

args = MarketOrderArgs(
    token_id="12345...",
    amount=100.0,
    side="BUY",
    order_type=OrderType.FOK,
    price=None,           # auto-calculate from orderbook
)
```

---

## Error Handling

```python
from polymarket_apis.utilities.exceptions import (
    AuthenticationRequiredError,
    InvalidFeeRateError,
    InvalidPriceError,
    InvalidTickSizeError,
    LiquidityError,
    MissingOrderbookError,
    SafeAlreadyDeployedError,
)

try:
    client.create_and_post_order(order_args)
except InvalidPriceError as e:
    print(f"Price out of range: {e}")
except LiquidityError as e:
    print(f"Insufficient liquidity: {e}")
except httpx.HTTPStatusError as e:
    print(f"API error {e.response.status_code}: {e.response.text}")
```

---

## Best Practices

### 1. Use Context Managers

```python
async with PolymarketDataClient() as client:
    # client automatically cleaned up
    data = await client.aget_positions(user)
```

### 2. Batch Requests When Possible

```python
# bad: sequential requests
for token in tokens:
    book = client.get_order_book(token)

# good: single batch request
books = client.get_order_books(tokens)

# best: parallel async requests
async with client:
    books = await asyncio.gather(*[
        client.aget_order_book(t) for t in tokens
    ])
```

### 3. Cache Market Metadata

```python
# tick_size, neg_risk, and fee_rate are cached automatically
# subsequent calls for same token_id return cached values
tick1 = client.get_tick_size(token)  # API call
tick2 = client.get_tick_size(token)  # cached
```

### 4. Handle Rate Limits

```python
import asyncio

async def fetch_with_backoff(client, token_ids):
    results = []
    for batch in chunks(token_ids, 10):
        data = await asyncio.gather(*[
            client.aget_order_book(t) for t in batch
        ])
        results.extend(data)
        await asyncio.sleep(0.1)  # rate limit buffer
    return results
```

### 5. Use Typed Events for Websockets

```python
from polymarket_apis.types.websockets_types import OrderBookSummaryEvent

async for event in ws.amarket_stream(tokens):
    if isinstance(event, OrderBookSummaryEvent):
        # type-safe access to event fields
        print(event.bids, event.asks)
```
