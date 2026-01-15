"""
polymarket websocket client.
provides real-time market data, user events, and live activity streams.
includes both sync (lomond) and async (websockets) implementations.
"""

import json
from collections.abc import AsyncIterator, Callable
from json import JSONDecodeError
from typing import Any, Optional

from lomond import WebSocket
from lomond.persist import persist
from pydantic import ValidationError

from ..types.clob_types import ApiCreds
from ..types.websockets_types import (
    ActivityOrderMatchEvent,
    ActivityTradeEvent,
    CommentEvent,
    CryptoPriceSubscribeEvent,
    CryptoPriceUpdateEvent,
    LastTradePriceEvent,
    LiveDataLastTradePriceEvent,
    LiveDataOrderBookSummaryEvent,
    LiveDataOrderEvent,
    LiveDataPriceChangeEvent,
    LiveDataTickSizeChangeEvent,
    LiveDataTradeEvent,
    MarketStatusChangeEvent,
    OrderBookSummaryEvent,
    OrderEvent,
    PriceChangeEvent,
    QuoteEvent,
    ReactionEvent,
    RequestEvent,
    TickSizeChangeEvent,
    TradeEvent,
)
from ..utilities.exceptions import AuthenticationRequiredError


# --- default event processors (for sync api) ---

def _process_market_event(event):
    """Default market event processor - prints to stdout."""
    try:
        message = event.json
        if isinstance(message, list):
            for item in message:
                try:
                    print(OrderBookSummaryEvent(**item), "\n")
                except ValidationError as e:
                    print(item.text)
                    print(e.errors())
            return
        match message["event_type"]:
            case "book":
                print(OrderBookSummaryEvent(**message), "\n")
            case "price_change":
                print(PriceChangeEvent(**message), "\n")
            case "tick_size_change":
                print(TickSizeChangeEvent(**message), "\n")
            case "last_trade_price":
                print(LastTradePriceEvent(**message), "\n")
            case _:
                print(message)
    except JSONDecodeError:
        print(event.text)
    except ValidationError as e:
        print(e.errors())
        print(event.json)


def _process_user_event(event):
    """Default user event processor - prints to stdout."""
    try:
        message = event.json
        match message["event_type"]:
            case "order":
                print(OrderEvent(**message), "\n")
            case "trade":
                print(TradeEvent(**message), "\n")
    except JSONDecodeError:
        print(event.text)
    except ValidationError as e:
        print(event.text)
        print(e.errors(), "\n")


def _process_live_data_event(event):
    """Default live data event processor - prints to stdout."""
    try:
        message = event.json
        match message["type"]:
            case "trades":
                print(ActivityTradeEvent(**message), "\n")
            case "orders_matched":
                print(ActivityOrderMatchEvent(**message), "\n")
            case "comment_created" | "comment_removed":
                print(CommentEvent(**message), "\n")
            case "reaction_created" | "reaction_removed":
                print(ReactionEvent(**message), "\n")
            case "request_created" | "request_edited" | "request_canceled" | "request_expired":
                print(RequestEvent(**message), "\n")
            case "quote_created" | "quote_edited" | "quote_canceled" | "quote_expired":
                print(QuoteEvent(**message), "\n")
            case "subscribe":
                print(CryptoPriceSubscribeEvent(**message), "\n")
            case "update":
                print(CryptoPriceUpdateEvent(**message), "\n")
            case "agg_orderbook":
                print(LiveDataOrderBookSummaryEvent(**message), "\n")
            case "price_change":
                print(LiveDataPriceChangeEvent(**message), "\n")
            case "last_trade_price":
                print(LiveDataLastTradePriceEvent(**message), "\n")
            case "tick_size_change":
                print(LiveDataTickSizeChangeEvent(**message), "\n")
            case "market_created" | "market_resolved":
                print(MarketStatusChangeEvent(**message), "\n")
            case "order":
                print(LiveDataOrderEvent(**message), "\n")
            case "trade":
                print(LiveDataTradeEvent(**message), "\n")
            case _:
                print(message)
    except JSONDecodeError:
        print(event.text)
    except ValidationError as e:
        print(e.errors(), "\n")
        print(event.text)


# --- event type parsing helpers ---

def parse_market_event(message: dict) -> Any:
    """Parse a market websocket message into typed event."""
    match message.get("event_type"):
        case "book":
            return OrderBookSummaryEvent(**message)
        case "price_change":
            return PriceChangeEvent(**message)
        case "tick_size_change":
            return TickSizeChangeEvent(**message)
        case "last_trade_price":
            return LastTradePriceEvent(**message)
        case _:
            return message


def parse_user_event(message: dict) -> Any:
    """Parse a user websocket message into typed event."""
    match message.get("event_type"):
        case "order":
            return OrderEvent(**message)
        case "trade":
            return TradeEvent(**message)
        case _:
            return message


def parse_live_data_event(message: dict) -> Any:
    """Parse a live data websocket message into typed event."""
    match message.get("type"):
        case "trades":
            return ActivityTradeEvent(**message)
        case "orders_matched":
            return ActivityOrderMatchEvent(**message)
        case "comment_created" | "comment_removed":
            return CommentEvent(**message)
        case "reaction_created" | "reaction_removed":
            return ReactionEvent(**message)
        case "request_created" | "request_edited" | "request_canceled" | "request_expired":
            return RequestEvent(**message)
        case "quote_created" | "quote_edited" | "quote_canceled" | "quote_expired":
            return QuoteEvent(**message)
        case "subscribe":
            return CryptoPriceSubscribeEvent(**message)
        case "update":
            return CryptoPriceUpdateEvent(**message)
        case "agg_orderbook":
            return LiveDataOrderBookSummaryEvent(**message)
        case "price_change":
            return LiveDataPriceChangeEvent(**message)
        case "last_trade_price":
            return LiveDataLastTradePriceEvent(**message)
        case "tick_size_change":
            return LiveDataTickSizeChangeEvent(**message)
        case "market_created" | "market_resolved":
            return MarketStatusChangeEvent(**message)
        case "order":
            return LiveDataOrderEvent(**message)
        case "trade":
            return LiveDataTradeEvent(**message)
        case _:
            return message


class PolymarketWebsocketsClient:
    """
    websocket client for polymarket real-time data.

    provides both sync and async methods:
    - sync: market_socket(), user_socket(), live_data_socket()
    - async: amarket_stream(), auser_stream(), alive_data_stream()

    async methods return async iterators for easy event processing:
        async for event in client.amarket_stream(token_ids):
            print(event)

    for parallel streams, use asyncio.create_task():
        async def process_markets():
            async for event in client.amarket_stream(tokens):
                handle_market(event)

        async def process_user():
            async for event in client.auser_stream(creds):
                handle_user(event)

        await asyncio.gather(process_markets(), process_user())
    """

    def __init__(self):
        self.url_market = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.url_user = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
        self.url_live_data = "wss://ws-live-data.polymarket.com"

    # --- sync api (using lomond) ---

    def market_socket(
        self, token_ids: list[str], process_event: Callable = _process_market_event
    ):
        """
        Connect to market websocket and subscribe to events for specific tokens.

        Args:
            token_ids: List of token IDs to subscribe to
            process_event: Callback function to process received events

        """
        websocket = WebSocket(self.url_market)

        for event in persist(websocket):
            if event.name == "ready":
                websocket.send_json(assets_ids=token_ids)
            elif event.name == "text":
                process_event(event)

    def user_socket(
        self, creds: ApiCreds, process_event: Callable = _process_user_event
    ):
        """
        Connect to user websocket and subscribe to user events.

        Args:
            creds: API credentials for authentication
            process_event: Callback function to process received events

        """
        websocket = WebSocket(self.url_user)

        for event in persist(websocket):
            if event.name == "ready":
                websocket.send_json(auth=creds.model_dump(by_alias=True))
            elif event.name == "text":
                process_event(event)

    def live_data_socket(
        self,
        subscriptions: list[dict[str, Any]],
        process_event: Callable = _process_live_data_event,
        creds: Optional[ApiCreds] = None,
    ):
        """
        Connect to live data websocket and subscribe to specified events.

        Args:
            subscriptions: List of subscription configurations
            process_event: Callback function to process received events
            creds: ApiCreds for authentication if subscribing to clob_user topic

        """
        websocket = WebSocket(self.url_live_data)

        needs_auth = any(sub.get("topic") == "clob_user" for sub in subscriptions)

        for event in persist(websocket):
            if event.name == "ready":
                if needs_auth:
                    if creds is None:
                        msg = "ApiCreds credentials are required for the clob_user topic subscriptions"
                        raise AuthenticationRequiredError(msg)
                    subscriptions_with_creds = []
                    for sub in subscriptions:
                        if sub.get("topic") == "clob_user":
                            sub_copy = sub.copy()
                            sub_copy["clob_auth"] = creds.model_dump()
                            subscriptions_with_creds.append(sub_copy)
                        else:
                            subscriptions_with_creds.append(sub)
                    subscriptions = subscriptions_with_creds

                payload = {"action": "subscribe", "subscriptions": subscriptions}
                websocket.send_json(**payload)

            elif event.name == "text":
                process_event(event)

    # --- async api (using websockets library) ---

    async def amarket_stream(
        self, token_ids: list[str], parse: bool = True
    ) -> AsyncIterator[Any]:
        """
        Async generator for market events.

        Args:
            token_ids: List of token IDs to subscribe to
            parse: If True, parse messages into typed events

        Yields:
            Market events (parsed or raw dict)

        Example:
            async for event in client.amarket_stream(["token1", "token2"]):
                if isinstance(event, OrderBookSummaryEvent):
                    print(f"Book update: {event.market}")

        """
        try:
            import websockets
        except ImportError:
            msg = "websockets package required for async. Install with: pip install websockets"
            raise ImportError(msg) from None

        async for ws in websockets.connect(self.url_market):
            try:
                await ws.send(json.dumps({"assets_ids": token_ids}))

                async for message in ws:
                    try:
                        data = json.loads(message)
                        if isinstance(data, list):
                            for item in data:
                                yield parse_market_event(item) if parse else item
                        else:
                            yield parse_market_event(data) if parse else data
                    except json.JSONDecodeError:
                        yield {"raw": message}
            except websockets.ConnectionClosed:
                continue

    async def auser_stream(
        self, creds: ApiCreds, parse: bool = True
    ) -> AsyncIterator[Any]:
        """
        Async generator for user events.

        Args:
            creds: API credentials for authentication
            parse: If True, parse messages into typed events

        Yields:
            User events (order updates, trades)

        Example:
            async for event in client.auser_stream(creds):
                if isinstance(event, TradeEvent):
                    print(f"Trade executed: {event.size} @ {event.price}")

        """
        try:
            import websockets
        except ImportError:
            msg = "websockets package required for async. Install with: pip install websockets"
            raise ImportError(msg) from None

        async for ws in websockets.connect(self.url_user):
            try:
                await ws.send(json.dumps({"auth": creds.model_dump(by_alias=True)}))

                async for message in ws:
                    try:
                        data = json.loads(message)
                        yield parse_user_event(data) if parse else data
                    except json.JSONDecodeError:
                        yield {"raw": message}
            except websockets.ConnectionClosed:
                continue

    async def alive_data_stream(
        self,
        subscriptions: list[dict[str, Any]],
        creds: Optional[ApiCreds] = None,
        parse: bool = True,
    ) -> AsyncIterator[Any]:
        """
        Async generator for live data events.

        Args:
            subscriptions: List of subscription configurations
            creds: ApiCreds for authentication if subscribing to clob_user topic
            parse: If True, parse messages into typed events

        Yields:
            Live data events (trades, comments, price changes, etc.)

        Subscription topics:
            - "activity": Trade and order match activity
            - "clob_market": Market orderbook and price updates
            - "clob_user": User-specific order and trade events (requires creds)
            - "crypto_prices": Cryptocurrency price updates
            - "comments": Comment events on markets/events
            - "reactions": Reaction events

        Example:
            subscriptions = [
                {"topic": "clob_market", "assets": ["token1", "token2"]},
                {"topic": "activity", "event_slugs": ["event-slug"]},
            ]
            async for event in client.alive_data_stream(subscriptions):
                print(event)

        """
        try:
            import websockets
        except ImportError:
            msg = "websockets package required for async. Install with: pip install websockets"
            raise ImportError(msg) from None

        needs_auth = any(sub.get("topic") == "clob_user" for sub in subscriptions)
        if needs_auth and creds is None:
            msg = "ApiCreds required for clob_user topic subscriptions"
            raise AuthenticationRequiredError(msg)

        # inject creds into clob_user subscriptions
        if needs_auth:
            subs_with_creds = []
            for sub in subscriptions:
                if sub.get("topic") == "clob_user":
                    sub_copy = sub.copy()
                    sub_copy["clob_auth"] = creds.model_dump()
                    subs_with_creds.append(sub_copy)
                else:
                    subs_with_creds.append(sub)
            subscriptions = subs_with_creds

        async for ws in websockets.connect(self.url_live_data):
            try:
                payload = {"action": "subscribe", "subscriptions": subscriptions}
                await ws.send(json.dumps(payload))

                async for message in ws:
                    try:
                        data = json.loads(message)
                        yield parse_live_data_event(data) if parse else data
                    except json.JSONDecodeError:
                        yield {"raw": message}
            except websockets.ConnectionClosed:
                continue
