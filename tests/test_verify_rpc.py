from unittest.mock import MagicMock, patch

from mcp_blockchain_rail.server import verify_rpc


def test_verify_rpc_unreachable():
    """Test verify_rpc returns False when RPC is unreachable."""
    with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = False
        mock_web3.HTTPProvider.return_value = mock_w3
        mock_web3.return_value = mock_w3

        result = verify_rpc("http://unreachable-rpc.com", 1)
        assert result is False


def test_verify_rpc_wrong_chain_id():
    """Test verify_rpc returns False when chain ID doesn't match."""
    with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 2
        mock_web3.HTTPProvider.return_value = mock_w3
        mock_web3.return_value = mock_w3

        result = verify_rpc("http://valid-rpc.com", 1)
        assert result is False


def test_verify_rpc_success():
    """Test verify_rpc returns True for valid RPC."""
    with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 1
        mock_w3.eth.get_balance.return_value = 0
        mock_web3.HTTPProvider.return_value = mock_w3
        mock_web3.return_value = mock_w3

        result = verify_rpc("http://valid-rpc.com", 1)
        assert result is True


def test_verify_rpc_exception():
    """Test verify_rpc returns False when exception occurs."""
    with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
        mock_web3.HTTPProvider.side_effect = Exception("Network error")

        result = verify_rpc("http://error-rpc.com", 1)
        assert result is False
