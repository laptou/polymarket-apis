"""
client modules for polymarket apis.

all clients provide both sync and async methods:
- sync methods: get_*, post_*, create_*, etc.
- async methods: aget_*, apost_*, acreate_*, etc.

async methods enable easy parallelization via asyncio.gather().
"""

from .clob_client import PolymarketClobClient
from .data_client import PolymarketDataClient
from .gamma_client import PolymarketGammaClient
from .graphql_client import AsyncPolymarketGraphQLClient, PolymarketGraphQLClient
from .web3_client import PolymarketGaslessWeb3Client, PolymarketWeb3Client
from .websockets_client import (
    PolymarketWebsocketsClient,
    parse_live_data_event,
    parse_market_event,
    parse_user_event,
)

__all__ = [
    # graphql clients
    "AsyncPolymarketGraphQLClient",
    "PolymarketGraphQLClient",
    # main api clients
    "PolymarketClobClient",
    "PolymarketDataClient",
    "PolymarketGammaClient",
    # web3 clients
    "PolymarketGaslessWeb3Client",
    "PolymarketWeb3Client",
    # websocket client and helpers
    "PolymarketWebsocketsClient",
    "parse_live_data_event",
    "parse_market_event",
    "parse_user_event",
]
