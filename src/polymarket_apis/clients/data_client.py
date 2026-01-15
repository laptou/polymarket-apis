"""
polymarket data api client.
provides market data, positions, trades, activity, and leaderboard information.
all http methods have async variants prefixed with 'a' (e.g., aget_positions).
"""

from datetime import datetime
from typing import Literal, Optional, Union
from urllib.parse import urljoin

from ..clients.graphql_client import AsyncPolymarketGraphQLClient, PolymarketGraphQLClient
from ..types.common import EthAddress, TimeseriesPoint
from ..types.data_types import (
    Activity,
    EventLiveVolume,
    GQLPosition,
    HolderResponse,
    MarketValue,
    Position,
    Trade,
    UserMetric,
    UserRank,
    ValueResponse,
)
from ..utilities.http import DualHttpClient


class PolymarketDataClient:
    """
    client for the polymarket data api.

    provides both sync and async methods for all operations.
    async methods are prefixed with 'a' (e.g., aget_positions, aget_trades).
    use async methods with asyncio.gather() for parallel requests.

    example parallel usage:
        async with client:
            positions, trades, activity = await asyncio.gather(
                client.aget_positions(user_address),
                client.aget_trades(user=user_address),
                client.aget_activity(user_address),
            )
    """

    def __init__(self, base_url: str = "https://data-api.polymarket.com"):
        self.base_url = base_url
        self.http = DualHttpClient(timeout=30.0)
        self.gql_positions_client = PolymarketGraphQLClient(
            endpoint_name="positions_subgraph"
        )
        self.async_gql_positions_client = AsyncPolymarketGraphQLClient(
            endpoint_name="positions_subgraph"
        )

    def _build_url(self, endpoint: str) -> str:
        return urljoin(self.base_url, endpoint)

    # --- health check ---

    def get_ok(self) -> str:
        response = self.http.get(self.base_url)
        response.raise_for_status()
        return response.json()["data"]

    async def aget_ok(self) -> str:
        response = await self.http.aget(self.base_url)
        response.raise_for_status()
        return response.json()["data"]

    # --- positions ---

    def get_all_positions(
        self,
        user: EthAddress,
        size_threshold: float = 0.0,
    ) -> list[GQLPosition]:
        """Fetch all positions via graphql subgraph (no filters on condition_id/event_id)."""
        query = f"""query {{
                  userBalances(where: {{
                  user: "{user.lower()}",
                  balance_gt: "{int(size_threshold * 10**6)}"
                  }}) {{
                    user
                    asset {{
                      id
                      condition {{
                        id
                      }}
                      complement
                      outcomeIndex
                    }}
                    balance
                  }}
                }}
                """
        response = self.gql_positions_client.query(query)
        return [GQLPosition(**pos) for pos in response["userBalances"]]

    async def aget_all_positions(
        self,
        user: EthAddress,
        size_threshold: float = 0.0,
    ) -> list[GQLPosition]:
        """Fetch all positions via graphql subgraph (async)."""
        query = f"""query {{
                  userBalances(where: {{
                  user: "{user.lower()}",
                  balance_gt: "{int(size_threshold * 10**6)}"
                  }}) {{
                    user
                    asset {{
                      id
                      condition {{
                        id
                      }}
                      complement
                      outcomeIndex
                    }}
                    balance
                  }}
                }}
                """
        response = await self.async_gql_positions_client.query(query)
        return [GQLPosition(**pos) for pos in response["userBalances"]]

    def get_positions(
        self,
        user: EthAddress,
        condition_id: Optional[Union[str, list[str]]] = None,
        event_id: Optional[Union[int, list[int]]] = None,
        size_threshold: float = 1.0,
        redeemable: bool = False,
        mergeable: bool = False,
        title: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: Literal[
            "TOKENS", "CURRENT", "INITIAL", "CASHPNL", "PERCENTPNL",
            "TITLE", "RESOLVING", "PRICE", "AVGPRICE",
        ] = "TOKENS",
        sort_direction: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Position]:
        """Get positions for a user with optional filters."""
        params: dict[str, str | list[str] | int | float] = {
            "user": user,
            "sizeThreshold": size_threshold,
            "limit": min(limit, 500),
            "offset": offset,
        }
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
        if isinstance(event_id, str):
            params["eventId"] = event_id
        if isinstance(event_id, list):
            params["eventId"] = [str(i) for i in event_id]
        if redeemable is not None:
            params["redeemable"] = redeemable
        if mergeable is not None:
            params["mergeable"] = mergeable
        if title:
            params["title"] = title
        if sort_by:
            params["sortBy"] = sort_by
        if sort_direction:
            params["sortDirection"] = sort_direction

        response = self.http.get(self._build_url("/positions"), params=params)
        response.raise_for_status()
        return [Position(**pos) for pos in response.json()]

    async def aget_positions(
        self,
        user: EthAddress,
        condition_id: Optional[Union[str, list[str]]] = None,
        event_id: Optional[Union[int, list[int]]] = None,
        size_threshold: float = 1.0,
        redeemable: bool = False,
        mergeable: bool = False,
        title: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: Literal[
            "TOKENS", "CURRENT", "INITIAL", "CASHPNL", "PERCENTPNL",
            "TITLE", "RESOLVING", "PRICE", "AVGPRICE",
        ] = "TOKENS",
        sort_direction: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Position]:
        """Get positions for a user (async)."""
        params: dict[str, str | list[str] | int | float] = {
            "user": user,
            "sizeThreshold": size_threshold,
            "limit": min(limit, 500),
            "offset": offset,
        }
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
        if isinstance(event_id, str):
            params["eventId"] = event_id
        if isinstance(event_id, list):
            params["eventId"] = [str(i) for i in event_id]
        if redeemable is not None:
            params["redeemable"] = redeemable
        if mergeable is not None:
            params["mergeable"] = mergeable
        if title:
            params["title"] = title
        if sort_by:
            params["sortBy"] = sort_by
        if sort_direction:
            params["sortDirection"] = sort_direction

        response = await self.http.aget(self._build_url("/positions"), params=params)
        response.raise_for_status()
        return [Position(**pos) for pos in response.json()]

    # --- trades ---

    def get_trades(
        self,
        limit: int = 100,
        offset: int = 0,
        taker_only: bool = True,
        filter_type: Optional[Literal["CASH", "TOKENS"]] = None,
        filter_amount: Optional[float] = None,
        condition_id: Optional[str | list[str]] = None,
        event_id: Optional[int | list[int]] = None,
        user: Optional[str] = None,
        side: Optional[Literal["BUY", "SELL"]] = None,
    ) -> list[Trade]:
        """Get trades with optional filters."""
        params: dict[str, int | bool | float | str | list[str]] = {
            "limit": min(limit, 500),
            "offset": offset,
            "takerOnly": taker_only,
        }
        if filter_type:
            params["filterType"] = filter_type
        if filter_amount:
            params["filterAmount"] = filter_amount
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
        if isinstance(event_id, str):
            params["eventId"] = event_id
        if isinstance(event_id, list):
            params["eventId"] = [str(i) for i in event_id]
        if user:
            params["user"] = user
        if side:
            params["side"] = side

        response = self.http.get(self._build_url("/trades"), params=params)
        response.raise_for_status()
        return [Trade(**trade) for trade in response.json()]

    async def aget_trades(
        self,
        limit: int = 100,
        offset: int = 0,
        taker_only: bool = True,
        filter_type: Optional[Literal["CASH", "TOKENS"]] = None,
        filter_amount: Optional[float] = None,
        condition_id: Optional[str | list[str]] = None,
        event_id: Optional[int | list[int]] = None,
        user: Optional[str] = None,
        side: Optional[Literal["BUY", "SELL"]] = None,
    ) -> list[Trade]:
        """Get trades (async)."""
        params: dict[str, int | bool | float | str | list[str]] = {
            "limit": min(limit, 500),
            "offset": offset,
            "takerOnly": taker_only,
        }
        if filter_type:
            params["filterType"] = filter_type
        if filter_amount:
            params["filterAmount"] = filter_amount
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
        if isinstance(event_id, str):
            params["eventId"] = event_id
        if isinstance(event_id, list):
            params["eventId"] = [str(i) for i in event_id]
        if user:
            params["user"] = user
        if side:
            params["side"] = side

        response = await self.http.aget(self._build_url("/trades"), params=params)
        response.raise_for_status()
        return [Trade(**trade) for trade in response.json()]

    # --- activity ---

    def get_activity(
        self,
        user: EthAddress,
        limit: int = 100,
        offset: int = 0,
        condition_id: Optional[Union[str, list[str]]] = None,
        event_id: Optional[Union[int, list[int]]] = None,
        type: Optional[
            Union[
                Literal["TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"],
                list[Literal["TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"]],
            ]
        ] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        side: Optional[Literal["BUY", "SELL"]] = None,
        sort_by: Literal["TIMESTAMP", "TOKENS", "CASH"] = "TIMESTAMP",
        sort_direction: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Activity]:
        """Get activity history for a user."""
        params: dict[str, str | list[str] | int] = {
            "user": user,
            "limit": min(limit, 500),
            "offset": offset,
        }
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
        if isinstance(event_id, str):
            params["eventId"] = event_id
        if isinstance(event_id, list):
            params["eventId"] = [str(i) for i in event_id]
        if isinstance(type, str):
            params["type"] = type
        if isinstance(type, list):
            params["type"] = ",".join(type)
        if start:
            params["start"] = int(start.timestamp())
        if end:
            params["end"] = int(end.timestamp())
        if side:
            params["side"] = side
        if sort_by:
            params["sortBy"] = sort_by
        if sort_direction:
            params["sortDirection"] = sort_direction

        response = self.http.get(self._build_url("/activity"), params=params)
        response.raise_for_status()
        return [Activity(**activity) for activity in response.json()]

    async def aget_activity(
        self,
        user: EthAddress,
        limit: int = 100,
        offset: int = 0,
        condition_id: Optional[Union[str, list[str]]] = None,
        event_id: Optional[Union[int, list[int]]] = None,
        type: Optional[
            Union[
                Literal["TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"],
                list[Literal["TRADE", "SPLIT", "MERGE", "REDEEM", "REWARD", "CONVERSION"]],
            ]
        ] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        side: Optional[Literal["BUY", "SELL"]] = None,
        sort_by: Literal["TIMESTAMP", "TOKENS", "CASH"] = "TIMESTAMP",
        sort_direction: Literal["ASC", "DESC"] = "DESC",
    ) -> list[Activity]:
        """Get activity history for a user (async)."""
        params: dict[str, str | list[str] | int] = {
            "user": user,
            "limit": min(limit, 500),
            "offset": offset,
        }
        if isinstance(condition_id, str):
            params["market"] = condition_id
        if isinstance(condition_id, list):
            params["market"] = ",".join(condition_id)
        if isinstance(event_id, str):
            params["eventId"] = event_id
        if isinstance(event_id, list):
            params["eventId"] = [str(i) for i in event_id]
        if isinstance(type, str):
            params["type"] = type
        if isinstance(type, list):
            params["type"] = ",".join(type)
        if start:
            params["start"] = int(start.timestamp())
        if end:
            params["end"] = int(end.timestamp())
        if side:
            params["side"] = side
        if sort_by:
            params["sortBy"] = sort_by
        if sort_direction:
            params["sortDirection"] = sort_direction

        response = await self.http.aget(self._build_url("/activity"), params=params)
        response.raise_for_status()
        return [Activity(**activity) for activity in response.json()]

    # --- holders ---

    def get_holders(
        self,
        condition_id: str,
        limit: int = 500,
        min_balance: int = 1,
    ) -> list[HolderResponse]:
        """Get top holders for each token_id in a market."""
        params: dict[str, int | str] = {
            "market": condition_id,
            "limit": limit,
            "min_balance": min_balance,
        }
        response = self.http.get(self._build_url("/holders"), params=params)
        response.raise_for_status()
        return [HolderResponse(**holder_data) for holder_data in response.json()]

    async def aget_holders(
        self,
        condition_id: str,
        limit: int = 500,
        min_balance: int = 1,
    ) -> list[HolderResponse]:
        """Get top holders (async)."""
        params: dict[str, int | str] = {
            "market": condition_id,
            "limit": limit,
            "min_balance": min_balance,
        }
        response = await self.http.aget(self._build_url("/holders"), params=params)
        response.raise_for_status()
        return [HolderResponse(**holder_data) for holder_data in response.json()]

    # --- value ---

    def get_value(
        self,
        user: EthAddress,
        condition_ids: Optional[Union[str, list[str]]] = None,
    ) -> ValueResponse:
        """Get the current value of a user's position in a set of markets."""
        params = {"user": user}
        if isinstance(condition_ids, str):
            params["market"] = condition_ids
        if isinstance(condition_ids, list):
            params["market"] = ",".join(condition_ids)

        response = self.http.get(self._build_url("/value"), params=params)
        response.raise_for_status()
        return ValueResponse(**response.json()[0])

    async def aget_value(
        self,
        user: EthAddress,
        condition_ids: Optional[Union[str, list[str]]] = None,
    ) -> ValueResponse:
        """Get the current value of a user's position (async)."""
        params = {"user": user}
        if isinstance(condition_ids, str):
            params["market"] = condition_ids
        if isinstance(condition_ids, list):
            params["market"] = ",".join(condition_ids)

        response = await self.http.aget(self._build_url("/value"), params=params)
        response.raise_for_status()
        return ValueResponse(**response.json()[0])

    # --- closed positions ---

    def get_closed_positions(
        self,
        user: EthAddress,
        condition_ids: Optional[Union[str, list[str]]] = None,
    ) -> list[Position]:
        """Get all closed positions."""
        params = {"user": user}
        if isinstance(condition_ids, str):
            params["market"] = condition_ids
        if isinstance(condition_ids, list):
            params["market"] = ",".join(condition_ids)

        response = self.http.get(self._build_url("/closed-positions"), params=params)
        response.raise_for_status()
        return [Position(**pos) for pos in response.json()]

    async def aget_closed_positions(
        self,
        user: EthAddress,
        condition_ids: Optional[Union[str, list[str]]] = None,
    ) -> list[Position]:
        """Get all closed positions (async)."""
        params = {"user": user}
        if isinstance(condition_ids, str):
            params["market"] = condition_ids
        if isinstance(condition_ids, list):
            params["market"] = ",".join(condition_ids)

        response = await self.http.aget(
            self._build_url("/closed-positions"), params=params
        )
        response.raise_for_status()
        return [Position(**pos) for pos in response.json()]

    # --- markets traded ---

    def get_total_markets_traded(self, user: EthAddress) -> int:
        """Get the total number of markets a user has traded in."""
        params = {"user": user}
        response = self.http.get(self._build_url("/traded"), params=params)
        response.raise_for_status()
        return response.json()["traded"]

    async def aget_total_markets_traded(self, user: EthAddress) -> int:
        """Get the total number of markets a user has traded in (async)."""
        params = {"user": user}
        response = await self.http.aget(self._build_url("/traded"), params=params)
        response.raise_for_status()
        return response.json()["traded"]

    # --- open interest ---

    def get_open_interest(
        self,
        condition_ids: Optional[Union[str, list[str]]] = None,
    ) -> list[MarketValue]:
        """Get open interest."""
        params = {}
        if isinstance(condition_ids, str):
            params["market"] = condition_ids
        if isinstance(condition_ids, list):
            params["market"] = ",".join(condition_ids)

        response = self.http.get(self._build_url("/oi"), params=params)
        response.raise_for_status()
        return [MarketValue(**oi) for oi in response.json()]

    async def aget_open_interest(
        self,
        condition_ids: Optional[Union[str, list[str]]] = None,
    ) -> list[MarketValue]:
        """Get open interest (async)."""
        params = {}
        if isinstance(condition_ids, str):
            params["market"] = condition_ids
        if isinstance(condition_ids, list):
            params["market"] = ",".join(condition_ids)

        response = await self.http.aget(self._build_url("/oi"), params=params)
        response.raise_for_status()
        return [MarketValue(**oi) for oi in response.json()]

    # --- live volume ---

    def get_live_volume(self, event_id: int) -> EventLiveVolume:
        """Get live volume for a given event."""
        params = {"id": str(event_id)}
        response = self.http.get(self._build_url("/live-volume"), params=params)
        response.raise_for_status()
        return EventLiveVolume(**response.json()[0])

    async def aget_live_volume(self, event_id: int) -> EventLiveVolume:
        """Get live volume for a given event (async)."""
        params = {"id": str(event_id)}
        response = await self.http.aget(self._build_url("/live-volume"), params=params)
        response.raise_for_status()
        return EventLiveVolume(**response.json()[0])

    # --- pnl and metrics ---

    def get_pnl(
        self,
        user: EthAddress,
        period: Literal["all", "1m", "1w", "1d"] = "all",
        frequency: Literal["1h", "3h", "12h", "1d"] = "1h",
    ) -> list[TimeseriesPoint]:
        """Get a user's PnL timeseries."""
        params = {
            "user_address": user,
            "interval": period,
            "fidelity": frequency,
        }
        response = self.http.get(
            "https://user-pnl-api.polymarket.com/user-pnl", params=params
        )
        response.raise_for_status()
        return [TimeseriesPoint(**point) for point in response.json()]

    async def aget_pnl(
        self,
        user: EthAddress,
        period: Literal["all", "1m", "1w", "1d"] = "all",
        frequency: Literal["1h", "3h", "12h", "1d"] = "1h",
    ) -> list[TimeseriesPoint]:
        """Get a user's PnL timeseries (async)."""
        params = {
            "user_address": user,
            "interval": period,
            "fidelity": frequency,
        }
        response = await self.http.aget(
            "https://user-pnl-api.polymarket.com/user-pnl", params=params
        )
        response.raise_for_status()
        return [TimeseriesPoint(**point) for point in response.json()]

    def get_user_metric(
        self,
        user: EthAddress,
        metric: Literal["profit", "volume"] = "profit",
        window: Literal["1d", "7d", "30d", "all"] = "all",
    ) -> UserMetric:
        """Get a user's overall profit or volume."""
        params: dict[str, int | str] = {
            "address": user,
            "window": window,
            "limit": 1,
        }
        response = self.http.get(
            "https://lb-api.polymarket.com/" + metric, params=params
        )
        response.raise_for_status()
        return UserMetric(**response.json()[0])

    async def aget_user_metric(
        self,
        user: EthAddress,
        metric: Literal["profit", "volume"] = "profit",
        window: Literal["1d", "7d", "30d", "all"] = "all",
    ) -> UserMetric:
        """Get a user's overall profit or volume (async)."""
        params: dict[str, int | str] = {
            "address": user,
            "window": window,
            "limit": 1,
        }
        response = await self.http.aget(
            "https://lb-api.polymarket.com/" + metric, params=params
        )
        response.raise_for_status()
        return UserMetric(**response.json()[0])

    # --- leaderboard ---

    def get_leaderboard_user_rank(
        self,
        user: EthAddress,
        metric: Literal["profit", "volume"] = "profit",
        window: Literal["1d", "7d", "30d", "all"] = "all",
    ) -> UserRank:
        """Get a user's rank on the leaderboard."""
        params = {
            "address": user,
            "window": window,
            "rankType": "pnl" if metric == "profit" else "vol",
        }
        response = self.http.get("https://lb-api.polymarket.com/rank", params=params)
        response.raise_for_status()
        return UserRank(**response.json()[0])

    async def aget_leaderboard_user_rank(
        self,
        user: EthAddress,
        metric: Literal["profit", "volume"] = "profit",
        window: Literal["1d", "7d", "30d", "all"] = "all",
    ) -> UserRank:
        """Get a user's rank on the leaderboard (async)."""
        params = {
            "address": user,
            "window": window,
            "rankType": "pnl" if metric == "profit" else "vol",
        }
        response = await self.http.aget(
            "https://lb-api.polymarket.com/rank", params=params
        )
        response.raise_for_status()
        return UserRank(**response.json()[0])

    def get_leaderboard_top_users(
        self,
        metric: Literal["profit", "volume"] = "profit",
        window: Literal["1d", "7d", "30d", "all"] = "all",
        limit: int = 100,
    ) -> list[UserMetric]:
        """Get the leaderboard of top users by profit or volume."""
        params = {
            "window": window,
            "limit": limit,
        }
        response = self.http.get(
            "https://lb-api.polymarket.com/" + metric, params=params
        )
        response.raise_for_status()
        return [UserMetric(**user) for user in response.json()]

    async def aget_leaderboard_top_users(
        self,
        metric: Literal["profit", "volume"] = "profit",
        window: Literal["1d", "7d", "30d", "all"] = "all",
        limit: int = 100,
    ) -> list[UserMetric]:
        """Get the leaderboard of top users (async)."""
        params = {
            "window": window,
            "limit": limit,
        }
        response = await self.http.aget(
            "https://lb-api.polymarket.com/" + metric, params=params
        )
        response.raise_for_status()
        return [UserMetric(**user) for user in response.json()]

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
