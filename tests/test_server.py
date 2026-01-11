from unittest.mock import MagicMock, patch

from mcp_blockchain_rail.server import (
    RPC_CONFIG,
    API_KEYS,
    set_rpc,
    query_rpc_urls,
    check_native_balance,
    set_api_key,
    get_source_code,
    load_config,
    save_config,
    delete_rpc,
    delete_api_key,
    list_configs,
)


class TestSetRpc:
    def test_set_rpc_success(self):
        """Test set_rpc with valid RPC URL."""
        with patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify:
            mock_verify.return_value = True
            result = set_rpc(1, "http://valid-rpc.com")

            assert "Success" in result
            assert "chain ID 1" in result
            assert RPC_CONFIG[1] == "http://valid-rpc.com"

    def test_set_rpc_invalid(self):
        """Test set_rpc with invalid RPC URL."""
        with patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify:
            mock_verify.return_value = False
            result = set_rpc(1, "http://invalid-rpc.com")

            assert "Error" in result
            assert 1 not in RPC_CONFIG

    def test_set_rpc_exception(self):
        """Test set_rpc when verify_rpc raises exception."""
        with patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify:
            mock_verify.side_effect = Exception("Test error")
            result = set_rpc(1, "http://error-rpc.com")

            assert "Error" in result


class TestQueryRpcUrls:
    def test_query_rpc_urls_success(self, tmp_path):
        """Test query_rpc_urls with cached data."""
        chains_data = [
            {
                "chainId": 1,
                "rpc": [
                    "http://rpc1.com",
                    "http://rpc2.com",
                    "https://rpc3.com",
                    "wss://rpc4.com",
                    "http://rpc5.com/${API_KEY}",
                ],
            }
        ]

        with (
            patch(
                "mcp_blockchain_rail.server.CACHE_FILE", str(tmp_path / "cache.json")
            ),
            patch("mcp_blockchain_rail.server.time.time") as mock_time,
            patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify,
            patch("mcp_blockchain_rail.server.random.shuffle") as mock_shuffle,
        ):
            mock_time.return_value = 1000
            mock_verify.return_value = True

            with open(tmp_path / "cache.json", "w") as f:
                import json

                json.dump({"timestamp": 500, "data": chains_data}, f)

            result = query_rpc_urls(1)

            assert isinstance(result, list)
            assert all(isinstance(url, str) for url in result)

    def test_query_rpc_urls_fetch_from_api(self):
        """Test query_rpc_urls when cache is expired."""
        chains_data = [{"chainId": 1, "rpc": ["http://rpc1.com"]}]

        with (
            patch("mcp_blockchain_rail.server.os.path.exists", return_value=False),
            patch("mcp_blockchain_rail.server.requests.get") as mock_get,
            patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify,
            patch("mcp_blockchain_rail.server.random.shuffle") as mock_shuffle,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = chains_data
            mock_get.return_value = mock_response
            mock_verify.return_value = True

            result = query_rpc_urls(1)

            assert isinstance(result, list)

    def test_query_rpc_urls_no_chain_found(self):
        """Test query_rpc_urls when chain ID not found."""
        with (
            patch("mcp_blockchain_rail.server.os.path.exists", return_value=False),
            patch("mcp_blockchain_rail.server.requests.get") as mock_get,
        ):
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_get.return_value = mock_response

            result = query_rpc_urls(999)

            assert len(result) == 1
            assert "Error" in result[0]


class TestCheckNativeBalance:
    def test_check_native_balance_no_rpc_configured(self):
        """Test check_native_balance when no RPC is set."""
        result = check_native_balance(1, "0x1234567890123456789012345678901234567890")
        assert "Error" in result
        assert "No RPC URL configured" in result

    def test_check_native_balance_success(self):
        """Test check_native_balance with valid RPC."""
        RPC_CONFIG[1] = "http://test-rpc.com"

        with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_w3.eth.get_balance.return_value = 1000000000000000000
            mock_w3.from_wei.return_value = "1.0"
            mock_web3.HTTPProvider.return_value = mock_w3
            mock_web3.return_value = mock_w3

            result = check_native_balance(
                1, "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
            )

            assert "1.0 ETH" in result

    def test_check_native_balance_invalid_address(self):
        """Test check_native_balance with invalid address."""
        RPC_CONFIG[1] = "http://test-rpc.com"

        with (
            patch("mcp_blockchain_rail.server.Web3") as mock_web3_class,
            patch(
                "mcp_blockchain_rail.server.Web3.to_checksum_address"
            ) as mock_checksum,
        ):
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.HTTPProvider.return_value = mock_w3
            mock_web3_class.return_value = mock_w3
            mock_checksum.side_effect = ValueError("Invalid address")

            result = check_native_balance(1, "invalid-address")
            assert "Error" in result
            assert "Invalid address format" in result

    def test_check_native_balance_rpc_offline(self):
        """Test check_native_balance when RPC goes offline."""
        RPC_CONFIG[1] = "http://test-rpc.com"

        with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = False
            mock_web3.HTTPProvider.return_value = mock_w3
            mock_web3.return_value = mock_w3

            result = check_native_balance(
                1, "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
            )

            assert "Error" in result
            assert "Could not connect" in result


class TestSetApiKey:
    def test_set_api_key(self):
        """Test set_api_key stores the key."""
        result = set_api_key("etherscan", "test_api_key_123")

        assert "Success" in result
        assert API_KEYS["etherscan"] == "test_api_key_123"


class TestGetSourceCode:
    def test_get_source_code_sourcify_success(self):
        """Test get_source_code from Sourcify."""
        files_response = [
            {"path": "contracts/Contract.sol", "content": "// Solidity code"}
        ]

        with patch("mcp_blockchain_rail.server.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = files_response
            mock_get.return_value = mock_response

            result = get_source_code(1, "0x6B175474E89094C44Da98b954EedeAC495271d0F")

            assert "contracts/Contract.sol" in result
            assert "// Solidity code" in result

    def test_get_source_code_etherscan_success(self):
        """Test get_source_code from Etherscan fallback."""
        API_KEYS["etherscan"] = "test_key"

        etherscan_response = {
            "status": "1",
            "result": [{"SourceCode": "pragma solidity ^0.8.0;"}],
        }

        with (
            patch("mcp_blockchain_rail.server.requests.get") as mock_get,
            patch("mcp_blockchain_rail.server.os.environ.get") as mock_env,
        ):
            mock_env.return_value = None
            mock_get.return_value.json.return_value = etherscan_response

            result = get_source_code(1, "0x6B175474E89094C44Da98b954EedeAC495271d0F")

            assert "pragma solidity" in result

    def test_get_source_code_both_fail(self):
        """Test get_source_code when both sources fail."""
        with (
            patch("mcp_blockchain_rail.server.requests.get") as mock_get,
            patch("mcp_blockchain_rail.server.os.environ.get") as mock_env,
        ):
            mock_env.return_value = None
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            result = get_source_code(1, "0x0000000000000000000000000000000000000000")

            assert "Error" in result
            assert "Contract not found" in result


class TestPersistence:
    def test_save_config_writes_file(self, tmp_path):
        """Test save_config writes data to config file."""
        RPC_CONFIG[1] = "http://rpc1.com"
        API_KEYS["etherscan"] = "test_key_123"

        with patch(
            "mcp_blockchain_rail.server.CONFIG_FILE", str(tmp_path / "config.json")
        ):
            save_config()

            import json

            with open(tmp_path / "config.json") as f:
                data = json.load(f)
                assert data["rpcs"] == {"1": "http://rpc1.com"}
                assert data["api_keys"] == {"etherscan": "test_key_123"}

    def test_load_config_reads_file(self, tmp_path):
        """Test load_config reads data from config file."""
        config_data = {
            "rpcs": {"1": "http://rpc1.com", "137": "http://rpc2.com"},
            "api_keys": {"etherscan": "key123"},
        }

        config_file = tmp_path / "config.json"
        import json

        with open(config_file, "w") as f:
            json.dump(config_data, f)

        with patch("mcp_blockchain_rail.server.CONFIG_FILE", str(config_file)):
            RPC_CONFIG.clear()
            API_KEYS.clear()
            load_config()

            assert RPC_CONFIG == {1: "http://rpc1.com", 137: "http://rpc2.com"}
            assert API_KEYS == {"etherscan": "key123"}

    def test_load_config_creates_empty_if_missing(self):
        """Test load_config handles missing config file gracefully."""
        with patch("mcp_blockchain_rail.server.os.path.exists", return_value=False):
            RPC_CONFIG[1] = "existing"
            API_KEYS["test"] = "test"

            load_config()

            assert RPC_CONFIG[1] == "existing"
            assert API_KEYS["test"] == "test"


class TestDeleteRpc:
    def test_delete_rpc_existing(self, tmp_path):
        """Test delete_rpc removes existing RPC."""
        RPC_CONFIG[1] = "http://rpc1.com"

        with patch(
            "mcp_blockchain_rail.server.CONFIG_FILE", str(tmp_path / "config.json")
        ):
            result = delete_rpc(1)

            assert "Success" in result
            assert 1 not in RPC_CONFIG

    def test_delete_rpc_nonexistent(self):
        """Test delete_rpc when RPC doesn't exist."""
        result = delete_rpc(999)
        assert "Error" in result
        assert "found" in result


class TestDeleteApiKey:
    def test_delete_api_key_existing(self, tmp_path):
        """Test delete_api_key removes existing key."""
        API_KEYS["etherscan"] = "test_key"

        with patch(
            "mcp_blockchain_rail.server.CONFIG_FILE", str(tmp_path / "config.json")
        ):
            result = delete_api_key("etherscan")

            assert "Success" in result
            assert "etherscan" not in API_KEYS

    def test_delete_api_key_nonexistent(self):
        """Test delete_api_key when key doesn't exist."""
        result = delete_api_key("nonexistent")
        assert "Error" in result
        assert "found" in result


class TestListConfigs:
    def test_list_configs_with_data(self):
        """Test list_configs displays existing configs."""
        RPC_CONFIG[1] = "http://rpc1.com"
        RPC_CONFIG[137] = "http://rpc2.com"
        API_KEYS["etherscan"] = "test_key_123456789"

        result = list_configs()

        assert "Chain 1: http://rpc1.com" in result
        assert "Chain 137: http://rpc2.com" in result
        assert "etherscan: test...6789" in result

    def test_list_configs_empty(self):
        """Test list_configs with no configs."""
        RPC_CONFIG.clear()
        API_KEYS.clear()

        result = list_configs()

        assert "No RPCs configured" in result
        assert "No API keys configured" in result
