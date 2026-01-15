"""
Polymarket clob (central limit order book) client.

Handles order management, market data, and trading operations.
All http methods have async variants prefixed with 'a' (e.g., aget_midpoint).
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from urllib.parse import urljoin

import httpx
from httpx import HTTPStatusError
from py_order_utils.model import SignedOrder

from ..types.clob_types import (
    ApiCreds,
    BidAsk,
    BookParams,
    ClobMarket,
    CreateOrderOptions,
    DailyEarnedReward,
    MarketOrderArgs,
    MarketRewards,
    Midpoint,
    OpenOrder,
    OrderArgs,
    OrderBookSummary,
    OrderCancelResponse,
    OrderPostResponse,
    OrderType,
    PaginatedResponse,
    PartialCreateOrderOptions,
    PolygonTrade,
    PostOrdersArgs,
    Price,
    PriceHistory,
    RequestArgs,
    RewardMarket,
    Spread,
    TickSize,
    TokenBidAskDict,
    TokenValueDict,
)
from ..types.common import EthAddress, Keccak256
from ..utilities.constants import END_CURSOR, POLYGON
from ..utilities.endpoints import (
    ARE_ORDERS_SCORING,
    CANCEL,
    CANCEL_ALL,
    CANCEL_ORDERS,
    CREATE_API_KEY,
    CREATE_READONLY_API_KEY,
    DELETE_API_KEY,
    DELETE_READONLY_API_KEY,
    DERIVE_API_KEY,
    GET_API_KEYS,
    GET_BALANCE_ALLOWANCE,
    GET_FEE_RATE,
    GET_LAST_TRADE_PRICE,
    GET_LAST_TRADES_PRICES,
    GET_MARKET,
    GET_MARKETS,
    GET_NEG_RISK,
    GET_ORDER_BOOK,
    GET_ORDER_BOOKS,
    GET_PRICES,
    GET_READONLY_API_KEYS,
    GET_SPREAD,
    GET_SPREADS,
    GET_TICK_SIZE,
    IS_ORDER_SCORING,
    MID_POINT,
    MID_POINTS,
    ORDERS,
    POST_ORDER,
    POST_ORDERS,
    PRICE,
    TIME,
    TRADES,
)
from ..utilities.exceptions import (
    InvalidFeeRateError,
    InvalidPriceError,
    InvalidTickSizeError,
    LiquidityError,
    MissingOrderbookError,
)
from ..utilities.headers import create_level_1_headers, create_level_2_headers
from ..utilities.http import DualHttpClient
from ..utilities.order_builder.builder import OrderBuilder
from ..utilities.order_builder.helpers import (
    is_tick_size_smaller,
    order_to_json,
    price_valid,
)
from ..utilities.signing.signer import Signer

logger = logging.getLogger(__name__)


class PolymarketClobClient:
    """
    client for the polymarket clob api.

    provides both sync and async methods for all operations.
    async methods are prefixed with 'a' (e.g., aget_midpoint, apost_order).
    use async methods with asyncio.gather() for parallel requests.

    example parallel usage:
        async with client:
            results = await asyncio.gather(
                client.aget_midpoint(token1),
                client.aget_midpoint(token2),
                client.aget_order_book(token3),
            )
    """

    def __init__(
        self,
        private_key: str,
        address: EthAddress,
        creds: ApiCreds | None = None,
        chain_id: Literal[137, 80002] = POLYGON,
        signature_type: Literal[0, 1, 2] = 1,
        # 0 - EOA wallet, 1 - Proxy wallet, 2 - Gnosis Safe wallet
    ):
        self.address = address
        self.http = DualHttpClient(timeout=30.0)
        self.base_url: str = "https://clob.polymarket.com"
        self.signer = Signer(private_key=private_key, chain_id=chain_id)
        self.signature_type = signature_type
        self.builder = OrderBuilder(
            signer=self.signer,
            sig_type=signature_type,
            funder=address,
        )
        self.creds = creds if creds else self.create_or_derive_api_creds()

        # local cache
        self.__tick_sizes: dict[str, TickSize] = {}
        self.__neg_risk: dict[str, bool] = {}
        self.__fee_rates: dict[str, int] = {}

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    # --- health check ---

    def get_ok(self) -> str:
        response = self.http.get(self.base_url)
        response.raise_for_status()
        return response.json()

    async def aget_ok(self) -> str:
        response = await self.http.aget(self.base_url)
        response.raise_for_status()
        return response.json()

    # --- api key management ---

    def create_api_creds(self, nonce: int | None = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.http.post(self._build_url(CREATE_API_KEY), headers=headers)
        response.raise_for_status()
        return ApiCreds(**response.json())

    async def acreate_api_creds(self, nonce: int | None = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = await self.http.apost(
            self._build_url(CREATE_API_KEY), headers=headers
        )
        response.raise_for_status()
        return ApiCreds(**response.json())

    def derive_api_key(self, nonce: int | None = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = self.http.get(self._build_url(DERIVE_API_KEY), headers=headers)
        response.raise_for_status()
        return ApiCreds(**response.json())

    async def aderive_api_key(self, nonce: int | None = None) -> ApiCreds:
        headers = create_level_1_headers(self.signer, nonce)
        response = await self.http.aget(
            self._build_url(DERIVE_API_KEY), headers=headers
        )
        response.raise_for_status()
        return ApiCreds(**response.json())

    def create_or_derive_api_creds(self, nonce: int | None = None) -> ApiCreds:
        try:
            return self.create_api_creds(nonce)
        except HTTPStatusError:
            return self.derive_api_key(nonce)

    async def acreate_or_derive_api_creds(self, nonce: int | None = None) -> ApiCreds:
        try:
            return await self.acreate_api_creds(nonce)
        except HTTPStatusError:
            return await self.aderive_api_key(nonce)

    def set_api_creds(self, creds: ApiCreds) -> None:
        self.creds = creds

    def get_api_keys(self) -> dict:
        request_args = RequestArgs(method="GET", request_path=GET_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.http.get(self._build_url(GET_API_KEYS), headers=headers)
        response.raise_for_status()
        return response.json()

    async def aget_api_keys(self) -> dict:
        request_args = RequestArgs(method="GET", request_path=GET_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = await self.http.aget(
            self._build_url(GET_API_KEYS), headers=headers
        )
        response.raise_for_status()
        return response.json()

    def delete_api_keys(self) -> Literal["OK"]:
        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.http.delete(self._build_url(DELETE_API_KEY), headers=headers)
        response.raise_for_status()
        return response.json()

    async def adelete_api_keys(self) -> Literal["OK"]:
        request_args = RequestArgs(method="DELETE", request_path=DELETE_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = await self.http.adelete(
            self._build_url(DELETE_API_KEY), headers=headers
        )
        response.raise_for_status()
        return response.json()

    def create_readonly_api_key(self) -> str:
        request_args = RequestArgs(method="POST", request_path=CREATE_READONLY_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.http.post(
            self._build_url(CREATE_READONLY_API_KEY), headers=headers
        )
        response.raise_for_status()
        return response.json()["apiKey"]

    async def acreate_readonly_api_key(self) -> str:
        request_args = RequestArgs(method="POST", request_path=CREATE_READONLY_API_KEY)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = await self.http.apost(
            self._build_url(CREATE_READONLY_API_KEY), headers=headers
        )
        response.raise_for_status()
        return response.json()["apiKey"]

    def get_readonly_api_keys(self) -> list[str]:
        request_args = RequestArgs(method="GET", request_path=GET_READONLY_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.http.get(
            self._build_url(GET_READONLY_API_KEYS), headers=headers
        )
        response.raise_for_status()
        return response.json()["readonlyApiKeys"]

    async def aget_readonly_api_keys(self) -> list[str]:
        request_args = RequestArgs(method="GET", request_path=GET_READONLY_API_KEYS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = await self.http.aget(
            self._build_url(GET_READONLY_API_KEYS), headers=headers
        )
        response.raise_for_status()
        return response.json()["readonlyApiKeys"]

    def delete_readonly_api_key(self, key: str) -> str:
        body = {"key": key}
        request_args = RequestArgs(
            method="DELETE",
            request_path=DELETE_READONLY_API_KEY,
            body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.http.request(
            "DELETE",
            self._build_url(DELETE_READONLY_API_KEY),
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        response.raise_for_status()
        return response.json()

    async def adelete_readonly_api_key(self, key: str) -> str:
        body = {"key": key}
        request_args = RequestArgs(
            method="DELETE",
            request_path=DELETE_READONLY_API_KEY,
            body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = await self.http.arequest(
            "DELETE",
            self._build_url(DELETE_READONLY_API_KEY),
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        response.raise_for_status()
        return response.json()

    # --- server time ---

    def get_utc_time(self) -> datetime:
        response = self.http.get(self._build_url(TIME))
        response.raise_for_status()
        return datetime.fromtimestamp(response.json(), tz=UTC)

    async def aget_utc_time(self) -> datetime:
        response = await self.http.aget(self._build_url(TIME))
        response.raise_for_status()
        return datetime.fromtimestamp(response.json(), tz=UTC)

    # --- market metadata ---

    def get_tick_size(self, token_id: str) -> TickSize:
        if token_id in self.__tick_sizes:
            return self.__tick_sizes[token_id]

        params = {"token_id": token_id}
        response = self.http.get(self._build_url(GET_TICK_SIZE), params=params)
        response.raise_for_status()
        self.__tick_sizes[token_id] = cast(
            "TickSize", str(response.json()["minimum_tick_size"])
        )
        return self.__tick_sizes[token_id]

    async def aget_tick_size(self, token_id: str) -> TickSize:
        if token_id in self.__tick_sizes:
            return self.__tick_sizes[token_id]

        params = {"token_id": token_id}
        response = await self.http.aget(self._build_url(GET_TICK_SIZE), params=params)
        response.raise_for_status()
        self.__tick_sizes[token_id] = cast(
            "TickSize", str(response.json()["minimum_tick_size"])
        )
        return self.__tick_sizes[token_id]

    def get_neg_risk(self, token_id: str) -> bool:
        if token_id in self.__neg_risk:
            return self.__neg_risk[token_id]

        params = {"token_id": token_id}
        response = self.http.get(self._build_url(GET_NEG_RISK), params=params)
        response.raise_for_status()
        self.__neg_risk[token_id] = response.json()["neg_risk"]
        return self.__neg_risk[token_id]

    async def aget_neg_risk(self, token_id: str) -> bool:
        if token_id in self.__neg_risk:
            return self.__neg_risk[token_id]

        params = {"token_id": token_id}
        response = await self.http.aget(self._build_url(GET_NEG_RISK), params=params)
        response.raise_for_status()
        self.__neg_risk[token_id] = response.json()["neg_risk"]
        return self.__neg_risk[token_id]

    def get_fee_rate_bps(self, token_id: str) -> int:
        if token_id in self.__fee_rates:
            return self.__fee_rates[token_id]

        params = {"token_id": token_id}
        response = self.http.get(self._build_url(GET_FEE_RATE), params=params)
        response.raise_for_status()
        fee_rate = response.json().get("base_fee") or 0
        self.__fee_rates[token_id] = fee_rate
        return fee_rate

    async def aget_fee_rate_bps(self, token_id: str) -> int:
        if token_id in self.__fee_rates:
            return self.__fee_rates[token_id]

        params = {"token_id": token_id}
        response = await self.http.aget(self._build_url(GET_FEE_RATE), params=params)
        response.raise_for_status()
        fee_rate = response.json().get("base_fee") or 0
        self.__fee_rates[token_id] = fee_rate
        return fee_rate

    def __resolve_tick_size(
        self,
        token_id: str,
        tick_size: TickSize | None = None,
    ) -> TickSize:
        min_tick_size = self.get_tick_size(token_id)
        if tick_size is not None:
            if is_tick_size_smaller(tick_size, min_tick_size):
                msg = f"invalid tick size ({tick_size!s}), minimum for the market is {min_tick_size!s}"
                raise InvalidTickSizeError(msg)
        else:
            tick_size = min_tick_size
        return tick_size

    async def __aresolve_tick_size(
        self,
        token_id: str,
        tick_size: TickSize | None = None,
    ) -> TickSize:
        min_tick_size = await self.aget_tick_size(token_id)
        if tick_size is not None:
            if is_tick_size_smaller(tick_size, min_tick_size):
                msg = f"invalid tick size ({tick_size!s}), minimum for the market is {min_tick_size!s}"
                raise InvalidTickSizeError(msg)
        else:
            tick_size = min_tick_size
        return tick_size

    def __resolve_fee_rate(
        self,
        token_id: str,
        user_fee_rate: int | None = None,
    ) -> int:
        market_fee_rate_bps = self.get_fee_rate_bps(token_id)
        if (
            market_fee_rate_bps > 0
            and user_fee_rate is not None
            and user_fee_rate > 0
            and user_fee_rate != market_fee_rate_bps
        ):
            msg = f"invalid user provided fee rate: ({user_fee_rate}), fee rate for the market must be {market_fee_rate_bps}"
            raise InvalidFeeRateError(msg)
        return market_fee_rate_bps

    async def __aresolve_fee_rate(
        self,
        token_id: str,
        user_fee_rate: int | None = None,
    ) -> int:
        market_fee_rate_bps = await self.aget_fee_rate_bps(token_id)
        if (
            market_fee_rate_bps > 0
            and user_fee_rate is not None
            and user_fee_rate > 0
            and user_fee_rate != market_fee_rate_bps
        ):
            msg = f"invalid user provided fee rate: ({user_fee_rate}), fee rate for the market must be {market_fee_rate_bps}"
            raise InvalidFeeRateError(msg)
        return market_fee_rate_bps

    # --- market pricing ---

    def get_midpoint(self, token_id: str) -> Midpoint:
        """Get the mid-market price for the given token."""
        params = {"token_id": token_id}
        response = self.http.get(self._build_url(MID_POINT), params=params)
        response.raise_for_status()
        return Midpoint(token_id=token_id, value=float(response.json()["mid"]))

    async def aget_midpoint(self, token_id: str) -> Midpoint:
        """Get the mid-market price for the given token (async)."""
        params = {"token_id": token_id}
        response = await self.http.aget(self._build_url(MID_POINT), params=params)
        response.raise_for_status()
        return Midpoint(token_id=token_id, value=float(response.json()["mid"]))

    def get_midpoints(self, token_ids: list[str]) -> dict:
        """Get the mid-market prices for a set of tokens."""
        data = [{"token_id": token_id} for token_id in token_ids]
        response = self.http.post(self._build_url(MID_POINTS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    async def aget_midpoints(self, token_ids: list[str]) -> dict:
        """Get the mid-market prices for a set of tokens (async)."""
        data = [{"token_id": token_id} for token_id in token_ids]
        response = await self.http.apost(self._build_url(MID_POINTS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    def get_spread(self, token_id: str) -> Spread:
        """Get the spread for the given token."""
        params = {"token_id": token_id}
        response = self.http.get(self._build_url(GET_SPREAD), params=params)
        response.raise_for_status()
        return Spread(token_id=token_id, value=float(response.json()["mid"]))

    async def aget_spread(self, token_id: str) -> Spread:
        """Get the spread for the given token (async)."""
        params = {"token_id": token_id}
        response = await self.http.aget(self._build_url(GET_SPREAD), params=params)
        response.raise_for_status()
        return Spread(token_id=token_id, value=float(response.json()["mid"]))

    def get_spreads(self, token_ids: list[str]) -> dict:
        """Get the spreads for a set of tokens."""
        data = [{"token_id": token_id} for token_id in token_ids]
        response = self.http.post(self._build_url(GET_SPREADS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    async def aget_spreads(self, token_ids: list[str]) -> dict:
        """Get the spreads for a set of tokens (async)."""
        data = [{"token_id": token_id} for token_id in token_ids]
        response = await self.http.apost(self._build_url(GET_SPREADS), json=data)
        response.raise_for_status()
        return TokenValueDict(**response.json()).root

    def get_price(self, token_id: str, side: Literal["BUY", "SELL"]) -> Price:
        """Get the market price for the given token and side."""
        params = {"token_id": token_id, "side": side}
        response = self.http.get(self._build_url(PRICE), params=params)
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id, side=side)

    async def aget_price(self, token_id: str, side: Literal["BUY", "SELL"]) -> Price:
        """Get the market price for the given token and side (async)."""
        params = {"token_id": token_id, "side": side}
        response = await self.http.aget(self._build_url(PRICE), params=params)
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id, side=side)

    def get_prices(self, params: list[BookParams]) -> dict[str, BidAsk]:
        """Get the market prices for a set of tokens and sides."""
        data = [{"token_id": param.token_id, "side": param.side} for param in params]
        response = self.http.post(self._build_url(GET_PRICES), json=data)
        response.raise_for_status()
        return TokenBidAskDict(**response.json()).root

    async def aget_prices(self, params: list[BookParams]) -> dict[str, BidAsk]:
        """Get the market prices for a set of tokens and sides (async)."""
        data = [{"token_id": param.token_id, "side": param.side} for param in params]
        response = await self.http.apost(self._build_url(GET_PRICES), json=data)
        response.raise_for_status()
        return TokenBidAskDict(**response.json()).root

    def get_last_trade_price(self, token_id) -> Price:
        """Fetches the last trade price for a token_id."""
        params = {"token_id": token_id}
        response = self.http.get(self._build_url(GET_LAST_TRADE_PRICE), params=params)
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id)

    async def aget_last_trade_price(self, token_id) -> Price:
        """Fetches the last trade price for a token_id (async)."""
        params = {"token_id": token_id}
        response = await self.http.aget(
            self._build_url(GET_LAST_TRADE_PRICE), params=params
        )
        response.raise_for_status()
        return Price(**response.json(), token_id=token_id)

    def get_last_trades_prices(self, token_ids: list[str]) -> list[Price]:
        """Fetches the last trades prices for a set of token ids."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.http.post(self._build_url(GET_LAST_TRADES_PRICES), json=body)
        response.raise_for_status()
        return [Price(**price) for price in response.json()]

    async def aget_last_trades_prices(self, token_ids: list[str]) -> list[Price]:
        """Fetches the last trades prices for a set of token ids (async)."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = await self.http.apost(
            self._build_url(GET_LAST_TRADES_PRICES), json=body
        )
        response.raise_for_status()
        return [Price(**price) for price in response.json()]

    # --- orderbook ---

    def get_order_book(self, token_id) -> OrderBookSummary:
        """Get the orderbook for the given token."""
        params = {"token_id": token_id}
        response = self.http.get(self._build_url(GET_ORDER_BOOK), params=params)
        response.raise_for_status()
        return OrderBookSummary(**response.json())

    async def aget_order_book(self, token_id) -> OrderBookSummary:
        """Get the orderbook for the given token (async)."""
        params = {"token_id": token_id}
        response = await self.http.aget(self._build_url(GET_ORDER_BOOK), params=params)
        response.raise_for_status()
        return OrderBookSummary(**response.json())

    def get_order_books(self, token_ids: list[str]) -> list[OrderBookSummary]:
        """Get the orderbook for a set of tokens."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = self.http.post(self._build_url(GET_ORDER_BOOKS), json=body)
        response.raise_for_status()
        return [OrderBookSummary(**obs) for obs in response.json()]

    async def aget_order_books(self, token_ids: list[str]) -> list[OrderBookSummary]:
        """Get the orderbook for a set of tokens (async)."""
        body = [{"token_id": token_id} for token_id in token_ids]
        response = await self.http.apost(self._build_url(GET_ORDER_BOOKS), json=body)
        response.raise_for_status()
        return [OrderBookSummary(**obs) for obs in response.json()]

    # --- markets ---

    def get_market(self, condition_id) -> ClobMarket:
        """Get a ClobMarket by condition_id."""
        response = self.http.get(self._build_url(GET_MARKET + condition_id))
        response.raise_for_status()
        return ClobMarket(**response.json())

    async def aget_market(self, condition_id) -> ClobMarket:
        """Get a ClobMarket by condition_id (async)."""
        response = await self.http.aget(self._build_url(GET_MARKET + condition_id))
        response.raise_for_status()
        return ClobMarket(**response.json())

    def get_markets(self, next_cursor="MA==") -> PaginatedResponse[ClobMarket]:
        """Get paginated ClobMarkets."""
        params = {"next_cursor": next_cursor}
        response = self.http.get(self._build_url(GET_MARKETS), params=params)
        response.raise_for_status()
        return PaginatedResponse[ClobMarket](**response.json())

    async def aget_markets(self, next_cursor="MA==") -> PaginatedResponse[ClobMarket]:
        """Get paginated ClobMarkets (async)."""
        params = {"next_cursor": next_cursor}
        response = await self.http.aget(self._build_url(GET_MARKETS), params=params)
        response.raise_for_status()
        return PaginatedResponse[ClobMarket](**response.json())

    def get_all_markets(self, next_cursor="MA==") -> list[ClobMarket]:
        """Recursively fetch all ClobMarkets using pagination."""
        if next_cursor == "LTE=":
            print("Reached the last page of markets.")
            return []

        paginated_response = self.get_markets(next_cursor=next_cursor)
        current_markets = paginated_response.data
        next_page_markets = self.get_all_markets(
            next_cursor=paginated_response.next_cursor,
        )
        return current_markets + next_page_markets

    async def aget_all_markets(self, next_cursor="MA==") -> list[ClobMarket]:
        """Recursively fetch all ClobMarkets using pagination (async)."""
        if next_cursor == "LTE=":
            return []

        paginated_response = await self.aget_markets(next_cursor=next_cursor)
        current_markets = paginated_response.data
        next_page_markets = await self.aget_all_markets(
            next_cursor=paginated_response.next_cursor,
        )
        return current_markets + next_page_markets

    # --- price history ---

    def get_recent_history(
        self,
        token_id: str,
        interval: Literal["1h", "6h", "1d", "1w", "1m", "max"] = "1d",
        fidelity: int = 1,
    ) -> PriceHistory:
        """Get the recent price history of a token (up to now) - 1h, 6h, 1d, 1w, 1m."""
        min_fidelities: dict[str, int] = {
            "1h": 1,
            "6h": 1,
            "1d": 1,
            "1w": 5,
            "1m": 10,
            "max": 2,
        }

        if fidelity < min_fidelities[interval]:
            msg = f"invalid filters: minimum fidelity' for '{interval}' range is {min_fidelities.get(interval)}"
            raise ValueError(msg)

        params: dict[str, int | str] = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity,
        }
        response = self.http.get(self._build_url("/prices-history"), params=params)
        response.raise_for_status()
        return PriceHistory(**response.json(), token_id=token_id)

    async def aget_recent_history(
        self,
        token_id: str,
        interval: Literal["1h", "6h", "1d", "1w", "1m", "max"] = "1d",
        fidelity: int = 1,
    ) -> PriceHistory:
        """Get the recent price history of a token (async)."""
        min_fidelities: dict[str, int] = {
            "1h": 1,
            "6h": 1,
            "1d": 1,
            "1w": 5,
            "1m": 10,
            "max": 2,
        }

        if fidelity < min_fidelities[interval]:
            msg = f"invalid filters: minimum fidelity' for '{interval}' range is {min_fidelities.get(interval)}"
            raise ValueError(msg)

        params: dict[str, int | str] = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity,
        }
        response = await self.http.aget(
            self._build_url("/prices-history"), params=params
        )
        response.raise_for_status()
        return PriceHistory(**response.json(), token_id=token_id)

    def get_history(
        self,
        token_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        fidelity: int = 2,
    ) -> PriceHistory:
        """Get the price history of a token between a selected date range of max 15 days or from start_time to now."""
        if start_time is None and end_time is None:
            msg = "At least 'start_time' or ('start_time' and 'end_time') must be provided"
            raise ValueError(msg)

        if (
            start_time
            and end_time
            and start_time + timedelta(days=15, seconds=1) < end_time
        ):
            msg = "'start_time' - 'end_time' range cannot exceed 15 days. Remove 'end_time' to get prices up to now or set a shorter range."
            raise ValueError(msg)

        params: dict[str, int | str] = {
            "market": token_id,
            "fidelity": fidelity,
        }
        if start_time:
            params["startTs"] = int(start_time.timestamp())
        if end_time:
            params["endTs"] = int(end_time.timestamp())

        response = self.http.get(self._build_url("/prices-history"), params=params)
        response.raise_for_status()
        return PriceHistory(**response.json(), token_id=token_id)

    async def aget_history(
        self,
        token_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        fidelity: int = 2,
    ) -> PriceHistory:
        """Get the price history of a token (async)."""
        if start_time is None and end_time is None:
            msg = "At least 'start_time' or ('start_time' and 'end_time') must be provided"
            raise ValueError(msg)

        if (
            start_time
            and end_time
            and start_time + timedelta(days=15, seconds=1) < end_time
        ):
            msg = "'start_time' - 'end_time' range cannot exceed 15 days."
            raise ValueError(msg)

        params: dict[str, int | str] = {
            "market": token_id,
            "fidelity": fidelity,
        }
        if start_time:
            params["startTs"] = int(start_time.timestamp())
        if end_time:
            params["endTs"] = int(end_time.timestamp())

        response = await self.http.aget(
            self._build_url("/prices-history"), params=params
        )
        response.raise_for_status()
        return PriceHistory(**response.json(), token_id=token_id)

    def get_all_history(self, token_id: str) -> PriceHistory:
        """Get the full price history of a token."""
        return self.get_history(
            token_id=token_id,
            start_time=datetime(2020, 1, 1, tzinfo=UTC),
        )

    async def aget_all_history(self, token_id: str) -> PriceHistory:
        """Get the full price history of a token (async)."""
        return await self.aget_history(
            token_id=token_id,
            start_time=datetime(2020, 1, 1, tzinfo=UTC),
        )

    # --- balances ---

    def get_usdc_balance(self) -> float:
        params = {
            "asset_type": "COLLATERAL",
            "signature_type": self.signature_type,
        }
        request_args = RequestArgs(method="GET", request_path=GET_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.http.get(
            self._build_url(GET_BALANCE_ALLOWANCE), headers=headers, params=params
        )
        response.raise_for_status()
        return int(response.json()["balance"]) / 10**6

    async def aget_usdc_balance(self) -> float:
        params = {
            "asset_type": "COLLATERAL",
            "signature_type": self.signature_type,
        }
        request_args = RequestArgs(method="GET", request_path=GET_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = await self.http.aget(
            self._build_url(GET_BALANCE_ALLOWANCE), headers=headers, params=params
        )
        response.raise_for_status()
        return int(response.json()["balance"]) / 10**6

    def get_token_balance(self, token_id: str) -> float:
        params = {
            "asset_type": "CONDITIONAL",
            "token_id": token_id,
            "signature_type": self.signature_type,
        }
        request_args = RequestArgs(method="GET", request_path=GET_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = self.http.get(
            self._build_url(GET_BALANCE_ALLOWANCE), headers=headers, params=params
        )
        response.raise_for_status()
        return int(response.json()["balance"]) / 10**6

    async def aget_token_balance(self, token_id: str) -> float:
        params = {
            "asset_type": "CONDITIONAL",
            "token_id": token_id,
            "signature_type": self.signature_type,
        }
        request_args = RequestArgs(method="GET", request_path=GET_BALANCE_ALLOWANCE)
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        response = await self.http.aget(
            self._build_url(GET_BALANCE_ALLOWANCE), headers=headers, params=params
        )
        response.raise_for_status()
        return int(response.json()["balance"]) / 10**6

    # --- orders ---

    def get_orders(
        self,
        order_id: str | None = None,
        condition_id: Keccak256 | None = None,
        token_id: str | None = None,
        next_cursor: str = "MA==",
    ) -> list[OpenOrder]:
        """Gets your active orders, filtered by order_id, condition_id, token_id."""
        params = {}
        if order_id:
            params["id"] = order_id
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id

        request_args = RequestArgs(method="GET", request_path=ORDERS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            params["next_cursor"] = next_cursor
            response = self.http.get(
                self._build_url(ORDERS), headers=headers, params=params
            )
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [OpenOrder(**order) for order in response.json()["data"]]

        return results

    async def aget_orders(
        self,
        order_id: str | None = None,
        condition_id: Keccak256 | None = None,
        token_id: str | None = None,
        next_cursor: str = "MA==",
    ) -> list[OpenOrder]:
        """Gets your active orders (async)."""
        params = {}
        if order_id:
            params["id"] = order_id
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id

        request_args = RequestArgs(method="GET", request_path=ORDERS)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            params["next_cursor"] = next_cursor
            response = await self.http.aget(
                self._build_url(ORDERS), headers=headers, params=params
            )
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [OpenOrder(**order) for order in response.json()["data"]]

        return results

    def create_order(
        self, order_args: OrderArgs, options: PartialCreateOrderOptions | None = None
    ) -> SignedOrder:
        """Creates and signs an order."""
        tick_size = self.__resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if not price_valid(order_args.price, tick_size):
            msg = f"price ({order_args.price}), min: {tick_size} - max: {1 - float(tick_size)}"
            raise InvalidPriceError(msg)

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk is not None
            else self.get_neg_risk(order_args.token_id)
        )

        fee_rate_bps = self.__resolve_fee_rate(
            order_args.token_id, order_args.fee_rate_bps
        )
        order_args.fee_rate_bps = fee_rate_bps

        return self.builder.create_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    async def acreate_order(
        self, order_args: OrderArgs, options: PartialCreateOrderOptions | None = None
    ) -> SignedOrder:
        """Creates and signs an order (async)."""
        tick_size = await self.__aresolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if not price_valid(order_args.price, tick_size):
            msg = f"price ({order_args.price}), min: {tick_size} - max: {1 - float(tick_size)}"
            raise InvalidPriceError(msg)

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk is not None
            else await self.aget_neg_risk(order_args.token_id)
        )

        fee_rate_bps = await self.__aresolve_fee_rate(
            order_args.token_id, order_args.fee_rate_bps
        )
        order_args.fee_rate_bps = fee_rate_bps

        return self.builder.create_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    def post_order(
        self, order: SignedOrder, order_type: OrderType = OrderType.GTC
    ) -> OrderPostResponse | None:
        """Posts a SignedOrder."""
        body = order_to_json(order, self.creds.key, order_type)
        headers = create_level_2_headers(
            self.signer,
            self.creds,
            RequestArgs(method="POST", request_path=POST_ORDER, body=body),
        )

        try:
            response = self.http.post(
                self._build_url("/order"),
                headers=headers,
                content=json.dumps(body).encode("utf-8"),
            )
            response.raise_for_status()
            return OrderPostResponse(**response.json())
        except httpx.HTTPStatusError as exc:
            msg = f"Client Error '{exc.response.status_code} {exc.response.reason_phrase}' while posting order"
            logger.warning(msg)
            error_json = exc.response.json()
            print("Details:", error_json["error"])
            return None

    async def apost_order(
        self, order: SignedOrder, order_type: OrderType = OrderType.GTC
    ) -> OrderPostResponse | None:
        """Posts a SignedOrder (async)."""
        body = order_to_json(order, self.creds.key, order_type)
        headers = create_level_2_headers(
            self.signer,
            self.creds,
            RequestArgs(method="POST", request_path=POST_ORDER, body=body),
        )

        try:
            response = await self.http.apost(
                self._build_url("/order"),
                headers=headers,
                content=json.dumps(body).encode("utf-8"),
            )
            response.raise_for_status()
            return OrderPostResponse(**response.json())
        except httpx.HTTPStatusError as exc:
            msg = f"Client Error '{exc.response.status_code} {exc.response.reason_phrase}' while posting order"
            logger.warning(msg)
            error_json = exc.response.json()
            print("Details:", error_json["error"])
            return None

    def create_and_post_order(
        self,
        order_args: OrderArgs,
        options: PartialCreateOrderOptions | None = None,
        order_type: OrderType = OrderType.GTC,
    ) -> OrderPostResponse | None:
        """Utility function to create and publish an order."""
        order = self.create_order(order_args, options)
        return self.post_order(order=order, order_type=order_type)

    async def acreate_and_post_order(
        self,
        order_args: OrderArgs,
        options: PartialCreateOrderOptions | None = None,
        order_type: OrderType = OrderType.GTC,
    ) -> OrderPostResponse | None:
        """Utility function to create and publish an order (async)."""
        order = await self.acreate_order(order_args, options)
        return await self.apost_order(order=order, order_type=order_type)

    def post_orders(self, args: list[PostOrdersArgs]) -> list[OrderPostResponse] | None:
        """Posts multiple SignedOrders at once."""
        body = [
            order_to_json(arg.order, self.creds.key, arg.order_type) for arg in args
        ]
        headers = create_level_2_headers(
            self.signer,
            self.creds,
            RequestArgs(method="POST", request_path=POST_ORDERS, body=body),
        )

        try:
            response = self.http.post(
                self._build_url("/orders"),
                headers=headers,
                content=json.dumps(body).encode("utf-8"),
            )
            response.raise_for_status()
            order_responses = []
            for index, item in enumerate(response.json()):
                resp = OrderPostResponse(**item)
                order_responses.append(resp)
                if resp.error_msg:
                    msg = (
                        f"Error posting order in position {index} \n"
                        f"Details: {resp.error_msg}"
                    )
                    logger.warning(msg)
        except httpx.HTTPStatusError as exc:
            msg = f"Client Error '{exc.response.status_code} {exc.response.reason_phrase}' while posting order"
            logger.warning(msg)
            error_json = exc.response.json()
            print("Details:", error_json["error"])
            return None
        else:
            return order_responses

    async def apost_orders(
        self, args: list[PostOrdersArgs]
    ) -> list[OrderPostResponse] | None:
        """Posts multiple SignedOrders at once (async)."""
        body = [
            order_to_json(arg.order, self.creds.key, arg.order_type) for arg in args
        ]
        headers = create_level_2_headers(
            self.signer,
            self.creds,
            RequestArgs(method="POST", request_path=POST_ORDERS, body=body),
        )

        try:
            response = await self.http.apost(
                self._build_url("/orders"),
                headers=headers,
                content=json.dumps(body).encode("utf-8"),
            )
            response.raise_for_status()
            order_responses = []
            for index, item in enumerate(response.json()):
                resp = OrderPostResponse(**item)
                order_responses.append(resp)
                if resp.error_msg:
                    logger.warning(
                        f"Error posting order in position {index}\nDetails: {resp.error_msg}"
                    )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"Client Error '{exc.response.status_code} {exc.response.reason_phrase}' while posting orders"
            )
            print("Details:", exc.response.json()["error"])
            return None
        else:
            return order_responses

    def create_and_post_orders(
        self, args: list[OrderArgs], order_types: list[OrderType]
    ) -> list[OrderPostResponse] | None:
        """Utility function to create and publish multiple orders at once."""
        return self.post_orders(
            [
                PostOrdersArgs(
                    order=self.create_order(order_args), order_type=order_type
                )
                for order_args, order_type in zip(args, order_types, strict=True)
            ],
        )

    async def acreate_and_post_orders(
        self, args: list[OrderArgs], order_types: list[OrderType]
    ) -> list[OrderPostResponse] | None:
        """Utility function to create and publish multiple orders at once (async)."""
        orders = [await self.acreate_order(order_args) for order_args in args]
        return await self.apost_orders(
            [
                PostOrdersArgs(order=order, order_type=order_type)
                for order, order_type in zip(orders, order_types, strict=True)
            ],
        )

    # --- market orders ---

    def calculate_market_price(
        self, token_id: str, side: str, amount: float, order_type: OrderType
    ) -> float:
        """Calculates the matching price considering an amount and the current orderbook."""
        book = self.get_order_book(token_id)
        if book is None:
            msg = "Order book is None"
            raise MissingOrderbookError(msg)
        if side == "BUY":
            if book.asks is None:
                msg = "No ask orders available"
                raise LiquidityError(msg)
            return self.builder.calculate_buy_market_price(
                book.asks,
                amount,
                order_type,
            )
        if side == "SELL":
            if book.bids is None:
                msg = "No bid orders available"
                raise LiquidityError(msg)
            return self.builder.calculate_sell_market_price(
                book.bids,
                amount,
                order_type,
            )
        msg = 'Side must be "BUY" or "SELL"'
        raise ValueError(msg)

    async def acalculate_market_price(
        self, token_id: str, side: str, amount: float, order_type: OrderType
    ) -> float:
        """Calculates the matching price (async)."""
        book = await self.aget_order_book(token_id)
        if book is None:
            msg = "Order book is None"
            raise MissingOrderbookError(msg)
        if side == "BUY":
            if book.asks is None:
                msg = "No ask orders available"
                raise LiquidityError(msg)
            return self.builder.calculate_buy_market_price(book.asks, amount, order_type)
        if side == "SELL":
            if book.bids is None:
                msg = "No bid orders available"
                raise LiquidityError(msg)
            return self.builder.calculate_sell_market_price(
                book.bids, amount, order_type
            )
        msg = 'Side must be "BUY" or "SELL"'
        raise ValueError(msg)

    def create_market_order(
        self,
        order_args: MarketOrderArgs,
        options: PartialCreateOrderOptions | None = None,
    ):
        """Creates and signs a market order."""
        tick_size = self.__resolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if order_args.price is None or order_args.price <= 0:
            order_args.price = self.calculate_market_price(
                order_args.token_id,
                order_args.side,
                order_args.amount,
                order_args.order_type,
            )

        if not price_valid(order_args.price, tick_size):
            msg = f"price ({order_args.price}), min: {tick_size} - max: {1 - float(tick_size)}"
            raise InvalidPriceError(msg)

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk is not None
            else self.get_neg_risk(order_args.token_id)
        )

        fee_rate_bps = self.__resolve_fee_rate(
            order_args.token_id, order_args.fee_rate_bps
        )
        order_args.fee_rate_bps = fee_rate_bps

        return self.builder.create_market_order(
            order_args,
            CreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            ),
        )

    async def acreate_market_order(
        self,
        order_args: MarketOrderArgs,
        options: PartialCreateOrderOptions | None = None,
    ):
        """Creates and signs a market order (async)."""
        tick_size = await self.__aresolve_tick_size(
            order_args.token_id,
            options.tick_size if options else None,
        )

        if order_args.price is None or order_args.price <= 0:
            order_args.price = await self.acalculate_market_price(
                order_args.token_id,
                order_args.side,
                order_args.amount,
                order_args.order_type,
            )

        if not price_valid(order_args.price, tick_size):
            msg = f"price ({order_args.price}), min: {tick_size} - max: {1 - float(tick_size)}"
            raise InvalidPriceError(msg)

        neg_risk = (
            options.neg_risk
            if options and options.neg_risk is not None
            else await self.aget_neg_risk(order_args.token_id)
        )

        fee_rate_bps = await self.__aresolve_fee_rate(
            order_args.token_id, order_args.fee_rate_bps
        )
        order_args.fee_rate_bps = fee_rate_bps

        return self.builder.create_market_order(
            order_args,
            CreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
        )

    def create_and_post_market_order(
        self,
        order_args: MarketOrderArgs,
        options: PartialCreateOrderOptions | None = None,
        order_type: OrderType = OrderType.FOK,
    ) -> OrderPostResponse | None:
        """Utility function to create and publish a market order."""
        order = self.create_market_order(order_args, options)
        return self.post_order(order=order, order_type=order_type)

    async def acreate_and_post_market_order(
        self,
        order_args: MarketOrderArgs,
        options: PartialCreateOrderOptions | None = None,
        order_type: OrderType = OrderType.FOK,
    ) -> OrderPostResponse | None:
        """Utility function to create and publish a market order (async)."""
        order = await self.acreate_market_order(order_args, options)
        return await self.apost_order(order=order, order_type=order_type)

    # --- order cancellation ---

    def cancel_order(self, order_id: Keccak256) -> OrderCancelResponse:
        """Cancels an order."""
        body = {"orderID": order_id}
        request_args = RequestArgs(method="DELETE", request_path=CANCEL, body=body)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.http.request(
            "DELETE",
            self._build_url(CANCEL),
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    async def acancel_order(self, order_id: Keccak256) -> OrderCancelResponse:
        """Cancels an order (async)."""
        body = {"orderID": order_id}
        request_args = RequestArgs(method="DELETE", request_path=CANCEL, body=body)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = await self.http.arequest(
            "DELETE",
            self._build_url(CANCEL),
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def cancel_orders(self, order_ids: list[Keccak256]) -> OrderCancelResponse:
        """Cancels orders."""
        body = order_ids
        request_args = RequestArgs(
            method="DELETE",
            request_path=CANCEL_ORDERS,
            body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.http.request(
            "DELETE",
            self._build_url(CANCEL_ORDERS),
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    async def acancel_orders(self, order_ids: list[Keccak256]) -> OrderCancelResponse:
        """Cancels orders (async)."""
        body = order_ids
        request_args = RequestArgs(
            method="DELETE", request_path=CANCEL_ORDERS, body=body
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = await self.http.arequest(
            "DELETE",
            self._build_url(CANCEL_ORDERS),
            headers=headers,
            content=json.dumps(body).encode("utf-8"),
        )
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    def cancel_all(self) -> OrderCancelResponse:
        """Cancels all available orders for the user."""
        request_args = RequestArgs(method="DELETE", request_path=CANCEL_ALL)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.http.delete(self._build_url(CANCEL_ALL), headers=headers)
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    async def acancel_all(self) -> OrderCancelResponse:
        """Cancels all available orders for the user (async)."""
        request_args = RequestArgs(method="DELETE", request_path=CANCEL_ALL)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = await self.http.adelete(
            self._build_url(CANCEL_ALL), headers=headers
        )
        response.raise_for_status()
        return OrderCancelResponse(**response.json())

    # --- order scoring ---

    def is_order_scoring(self, order_id: Keccak256) -> bool:
        """Check if the order is currently scoring."""
        request_args = RequestArgs(method="GET", request_path=IS_ORDER_SCORING)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.http.get(
            self._build_url(IS_ORDER_SCORING),
            headers=headers,
            params={"order_id": order_id},
        )
        response.raise_for_status()
        return response.json()["scoring"]

    async def ais_order_scoring(self, order_id: Keccak256) -> bool:
        """Check if the order is currently scoring (async)."""
        request_args = RequestArgs(method="GET", request_path=IS_ORDER_SCORING)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = await self.http.aget(
            self._build_url(IS_ORDER_SCORING),
            headers=headers,
            params={"order_id": order_id},
        )
        response.raise_for_status()
        return response.json()["scoring"]

    def are_orders_scoring(self, order_ids: list[Keccak256]) -> dict[Keccak256, bool]:
        """Check if the orders are currently scoring."""
        body = order_ids
        request_args = RequestArgs(
            method="POST",
            request_path=ARE_ORDERS_SCORING,
            body=body,
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        headers["Content-Type"] = "application/json"

        response = self.http.post(
            self._build_url(ARE_ORDERS_SCORING), headers=headers, json=body
        )
        response.raise_for_status()
        return response.json()

    async def aare_orders_scoring(
        self, order_ids: list[Keccak256]
    ) -> dict[Keccak256, bool]:
        """Check if the orders are currently scoring (async)."""
        body = order_ids
        request_args = RequestArgs(
            method="POST", request_path=ARE_ORDERS_SCORING, body=body
        )
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        headers["Content-Type"] = "application/json"

        response = await self.http.apost(
            self._build_url(ARE_ORDERS_SCORING), headers=headers, json=body
        )
        response.raise_for_status()
        return response.json()

    # --- rewards ---

    def get_market_rewards(self, condition_id: Keccak256) -> MarketRewards:
        """Get the MarketRewards for a given market (condition_id)."""
        request_args = RequestArgs(method="GET", request_path="/rewards/markets/")
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = self.http.get(
            self._build_url("/rewards/markets/" + condition_id), headers=headers
        )
        response.raise_for_status()
        return next(MarketRewards(**market) for market in response.json()["data"])

    async def aget_market_rewards(self, condition_id: Keccak256) -> MarketRewards:
        """Get the MarketRewards for a given market (async)."""
        request_args = RequestArgs(method="GET", request_path="/rewards/markets/")
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        response = await self.http.aget(
            self._build_url("/rewards/markets/" + condition_id), headers=headers
        )
        response.raise_for_status()
        return next(MarketRewards(**market) for market in response.json()["data"])

    # --- trades ---

    def get_trades(
        self,
        condition_id: Keccak256 | None = None,
        token_id: str | None = None,
        trade_id: str | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
        address: EthAddress | None = None,
        next_cursor="MA==",
    ) -> list[PolygonTrade]:
        """Fetches the trade history for a user."""
        params: dict[str, str | int] = {}
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id
        if trade_id:
            params["id"] = trade_id
        if before:
            params["before"] = int(before.replace(microsecond=0).timestamp())
        if after:
            params["after"] = int(after.replace(microsecond=0).timestamp())
        if address:
            params["maker_address"] = address

        request_args = RequestArgs(method="GET", request_path=TRADES)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            params["next_cursor"] = next_cursor
            response = self.http.get(
                self._build_url(TRADES), headers=headers, params=params
            )
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [PolygonTrade(**trade) for trade in response.json()["data"]]

        return results

    async def aget_trades(
        self,
        condition_id: Keccak256 | None = None,
        token_id: str | None = None,
        trade_id: str | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
        address: EthAddress | None = None,
        next_cursor="MA==",
    ) -> list[PolygonTrade]:
        """Fetches the trade history for a user (async)."""
        params: dict[str, str | int] = {}
        if condition_id:
            params["market"] = condition_id
        if token_id:
            params["asset_id"] = token_id
        if trade_id:
            params["id"] = trade_id
        if before:
            params["before"] = int(before.replace(microsecond=0).timestamp())
        if after:
            params["after"] = int(after.replace(microsecond=0).timestamp())
        if address:
            params["maker_address"] = address

        request_args = RequestArgs(method="GET", request_path=TRADES)
        headers = create_level_2_headers(self.signer, self.creds, request_args)

        results = []
        next_cursor = next_cursor if next_cursor is not None else "MA=="
        while next_cursor != END_CURSOR:
            params["next_cursor"] = next_cursor
            response = await self.http.aget(
                self._build_url(TRADES), headers=headers, params=params
            )
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [PolygonTrade(**trade) for trade in response.json()["data"]]

        return results

    def get_total_rewards(self, date: datetime | None = None) -> DailyEarnedReward:
        """Get the total rewards earned on a given date."""
        if date is None:
            date = datetime.now(UTC)
        params = {
            "authenticationType": "magic",
            "date": f"{date.strftime('%Y-%m-%d')}",
        }

        request_args = RequestArgs(method="GET", request_path="/rewards/user/total")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        response = self.http.get(
            "https://polymarket.com/api/rewards/totalEarnings", params=params
        )
        response.raise_for_status()
        if response.json():
            return DailyEarnedReward(**response.json()[0])
        return DailyEarnedReward(
            date=date,
            asset_address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            maker_address=self.address,
            earnings=0.0,
            asset_rate=0.0,
        )

    async def aget_total_rewards(self, date: datetime | None = None) -> DailyEarnedReward:
        """Get the total rewards earned on a given date (async)."""
        if date is None:
            date = datetime.now(UTC)
        params = {
            "authenticationType": "magic",
            "date": f"{date.strftime('%Y-%m-%d')}",
        }

        request_args = RequestArgs(method="GET", request_path="/rewards/user/total")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        response = await self.http.aget(
            "https://polymarket.com/api/rewards/totalEarnings", params=params
        )
        response.raise_for_status()
        if response.json():
            return DailyEarnedReward(**response.json()[0])
        return DailyEarnedReward(
            date=date,
            asset_address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            maker_address=self.address,
            earnings=0.0,
            asset_rate=0.0,
        )

    def get_reward_markets(
        self,
        query: str | None = None,
        sort_by: Literal[
            "market",
            "max_spread",
            "min_size",
            "rate_per_day",
            "spread",
            "price",
            "earnings",
            "earning_percentage",
        ]
        | None = "market",
        sort_direction: Literal["ASC", "DESC"] | None = None,
        show_favorites: bool = False,
    ) -> list[RewardMarket]:
        """Search through markets that offer rewards."""
        results = []
        desc = {"ASC": False, "DESC": True}
        params: dict[str, bool | str] = {
            "authenticationType": "magic",
            "showFavorites": show_favorites,
        }
        if sort_by:
            params["orderBy"] = sort_by
        if query:
            params["query"] = query
            params["desc"] = False
        if sort_direction:
            params["desc"] = desc[sort_direction]

        request_args = RequestArgs(method="GET", request_path="/rewards/user/markets")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        next_cursor = "MA=="
        while next_cursor != END_CURSOR:
            params["nextCursor"] = next_cursor
            response = self.http.get(
                "https://polymarket.com/api/rewards/markets", params=params
            )
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [RewardMarket(**reward) for reward in response.json()["data"]]

        return results

    async def aget_reward_markets(
        self,
        query: str | None = None,
        sort_by: Literal[
            "market",
            "max_spread",
            "min_size",
            "rate_per_day",
            "spread",
            "price",
            "earnings",
            "earning_percentage",
        ]
        | None = "market",
        sort_direction: Literal["ASC", "DESC"] | None = None,
        show_favorites: bool = False,
    ) -> list[RewardMarket]:
        """Search through markets that offer rewards (async)."""
        results = []
        desc = {"ASC": False, "DESC": True}
        params: dict[str, bool | str] = {
            "authenticationType": "magic",
            "showFavorites": show_favorites,
        }
        if sort_by:
            params["orderBy"] = sort_by
        if query:
            params["query"] = query
            params["desc"] = False
        if sort_direction:
            params["desc"] = desc[sort_direction]

        request_args = RequestArgs(method="GET", request_path="/rewards/user/markets")
        headers = create_level_2_headers(self.signer, self.creds, request_args)
        params["l2Headers"] = json.dumps(headers)

        next_cursor = "MA=="
        while next_cursor != END_CURSOR:
            params["nextCursor"] = next_cursor
            response = await self.http.aget(
                "https://polymarket.com/api/rewards/markets", params=params
            )
            response.raise_for_status()
            next_cursor = response.json()["next_cursor"]
            results += [RewardMarket(**reward) for reward in response.json()["data"]]

        return results

    # --- context managers ---

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.http.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.http.close()
        await self.http.aclose()
