import pytest

from mcp_blockchain_rail.server import RPC_CONFIG, API_KEYS


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    RPC_CONFIG.clear()
    API_KEYS.clear()
    yield
    RPC_CONFIG.clear()
    API_KEYS.clear()
