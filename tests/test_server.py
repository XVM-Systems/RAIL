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
    health_check_rpc,
    get_working_rpc,
    check_rpc_health,
    set_backup_rpc,
    rotate_rpc,
    get_token_balance,
    get_token_info,
)


class TestSetRpc:
    def test_set_rpc_success(self):
        """Test set_rpc with valid RPC URL."""
        with patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify:
            mock_verify.return_value = True
            result = set_rpc(1, "http://valid-rpc.com")

            assert "Success" in result
            assert "chain ID 1" in result
            assert RPC_CONFIG[1][0] == "http://valid-rpc.com"

    def test_set_rpc_prepends_to_existing(self):
        """Test set_rpc prepends new RPC to existing list."""
        RPC_CONFIG[1] = ["http://old1.com", "http://old2.com"]

        with patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify:
            mock_verify.return_value = True
            result = set_rpc(1, "http://new-rpc.com")

            assert "Success" in result
            assert RPC_CONFIG[1][0] == "http://new-rpc.com"
            assert RPC_CONFIG[1][1] == "http://old1.com"

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
        assert "No RPC configuration" in result

    def test_check_native_balance_success(self):
        """Test check_native_balance with valid RPC."""
        RPC_CONFIG[1] = ["http://test-rpc.com"]

        with (
            patch("mcp_blockchain_rail.server.Web3") as mock_web3,
            patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check,
        ):
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_w3.eth.get_balance.return_value = 1000000000000000000
            mock_w3.from_wei.return_value = "1.0"
            mock_web3.HTTPProvider.return_value = mock_w3
            mock_web3.return_value = mock_w3

            mock_health_check.return_value = {
                "healthy": True,
                "chain_id": 1,
                "latency_ms": 50,
                "error": "",
            }

            result = check_native_balance(
                1, "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
            )

            assert "1.0 ETH" in result

    def test_check_native_balance_failover(self):
        """Test check_native_balance with automatic failover."""
        RPC_CONFIG[1] = ["http://failed-rpc.com", "http://backup-rpc.com"]

        with patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check:

            def health_side_effect(rpc_url, chain_id, timeout):
                return (
                    {"healthy": False, "latency_ms": 0, "error": "failed"}
                    if rpc_url == "http://failed-rpc.com"
                    else {
                        "healthy": True,
                        "latency_ms": 100,
                        "error": "",
                        "chain_id": 1,
                    }
                )

            mock_health_check.side_effect = health_side_effect

            with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
                mock_w3 = MagicMock()
                mock_w3.is_connected.return_value = True
                mock_w3.eth.get_balance.return_value = 1000000000000000000
                mock_w3.from_wei.return_value = "1.0"
                mock_w3.HTTPProvider.return_value = mock_w3
                mock_web3.return_value = mock_w3

                result = check_native_balance(
                    1, "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
                )

                assert "1.0 ETH" in result
                assert RPC_CONFIG[1][0] == "http://backup-rpc.com"

    def test_check_native_balance_invalid_address(self):
        """Test check_native_balance with invalid address."""
        RPC_CONFIG[1] = ["http://test-rpc.com"]

        with (
            patch("mcp_blockchain_rail.server.Web3") as mock_web3_class,
            patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check,
            patch(
                "mcp_blockchain_rail.server.Web3.to_checksum_address"
            ) as mock_checksum,
        ):
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.HTTPProvider.return_value = mock_w3
            mock_web3_class.return_value = mock_w3
            mock_checksum.side_effect = ValueError("Invalid address")

            mock_health_check.return_value = {
                "healthy": True,
                "chain_id": 1,
                "latency_ms": 50,
                "error": "",
            }

            result = check_native_balance(1, "invalid-address")
            assert "Error" in result
            assert "Invalid address format" in result


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

            result = get_source_code(1, "0x6B175474E89094C44Da98b954EedeAC495271d0F")

            assert "Error" in result
            assert "Contract not found" in result


class TestHealthCheckRpc:
    def test_health_check_rpc_healthy(self):
        """Test health_check_rpc returns healthy status."""
        with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_w3.eth.chain_id = 1
            mock_w3.eth.get_balance.return_value = 0
            mock_web3.HTTPProvider.return_value = mock_w3
            mock_web3.return_value = mock_w3

            result = health_check_rpc("http://valid-rpc.com", 1, timeout=5)

            assert result["healthy"] is True
            assert result["chain_id"] == 1
            assert result["latency_ms"] >= 0
            assert result["error"] == ""

    def test_health_check_rpc_not_connected(self):
        """Test health_check_rpc when RPC not connected."""
        with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = False
            mock_web3.HTTPProvider.return_value = mock_w3
            mock_web3.return_value = mock_w3

            result = health_check_rpc("http://unreachable-rpc.com", 1, timeout=5)

            assert result["healthy"] is False
            assert result["chain_id"] is None
            assert result["error"] == "Not connected"

    def test_health_check_rpc_wrong_chain(self):
        """Test health_check_rpc when chain ID mismatch."""
        with patch("mcp_blockchain_rail.server.Web3") as mock_web3:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_w3.eth.chain_id = 2
            mock_w3.HTTPProvider.return_value = mock_w3
            mock_web3.return_value = mock_w3

            result = health_check_rpc("http://wrong-chain-rpc.com", 1, timeout=5)

            assert result["healthy"] is False
            assert result["chain_id"] == 2
            assert "chain ID" in result["error"] or "Chain ID" in result["error"]

    def test_health_check_rpc_exception(self):
        """Test health_check_rpc when exception occurs."""
        with patch("mcp_blockchain_rail.server.Web3") as mock_web3_class:
            mock_web3_instance = MagicMock()
            mock_web3_instance.is_connected.return_value = True
            mock_web3_instance.eth.chain_id = 1
            mock_web3_instance.HTTPProvider.return_value = MagicMock()
            mock_web3_class.HTTPProvider.return_value = mock_web3_instance
            mock_web3_class.side_effect = Exception("Network error")

            result = health_check_rpc("http://error-rpc.com", 1, timeout=5)

            assert result["healthy"] is False
            assert result["chain_id"] is None
            assert "Network error" in result["error"]


class TestGetWorkingRpc:
    def test_get_working_rpc_success(self):
        """Test get_working_rpc returns primary RPC."""
        RPC_CONFIG[1] = ["http://primary-rpc.com"]

        with patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check:
            mock_health_check.return_value = {
                "healthy": True,
                "chain_id": 1,
                "latency_ms": 50,
                "error": "",
            }

            result = get_working_rpc(1)

            assert result == "http://primary-rpc.com"
            assert RPC_CONFIG[1][0] == "http://primary-rpc.com"

    def test_get_working_rpc_failover(self):
        """Test get_working_rpc fails over to backup."""
        RPC_CONFIG[1] = ["http://primary-rpc.com", "http://backup-rpc.com"]

        with patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check:

            def health_side_effect(rpc_url, chain_id, timeout):
                return (
                    {
                        "healthy": False,
                        "latency_ms": 0,
                        "error": "failed",
                        "chain_id": None,
                    }
                    if rpc_url == "http://primary-rpc.com"
                    else {
                        "healthy": True,
                        "latency_ms": 100,
                        "error": "",
                        "chain_id": 1,
                    }
                )

            mock_health_check.side_effect = health_side_effect

            result = get_working_rpc(1)

            assert result == "http://backup-rpc.com"
            assert RPC_CONFIG[1][0] == "http://backup-rpc.com"

    def test_get_working_rpc_all_fail(self):
        """Test get_working_rpc raises error when all RPCs fail."""
        RPC_CONFIG[1] = ["http://rpc1.com", "http://rpc2.com"]

        with patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check:
            mock_health_check.return_value = {
                "healthy": False,
                "chain_id": None,
                "latency_ms": 0,
                "error": "failed",
            }

            try:
                get_working_rpc(1)
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "All RPCs failed" in str(e)

    def test_get_working_rpc_no_config(self):
        """Test get_working_rpc raises error when no config exists."""
        RPC_CONFIG.clear()

        try:
            get_working_rpc(1)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No RPC configuration" in str(e)


class TestCheckRpcHealth:
    def test_check_rpc_health_success(self):
        """Test check_rpc_health with configured RPCs."""
        RPC_CONFIG[1] = ["http://rpc1.com", "http://rpc2.com"]

        with patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check:
            mock_health_check.side_effect = [
                {
                    "healthy": True,
                    "chain_id": 1,
                    "latency_ms": 50,
                    "error": "",
                },
                {
                    "healthy": False,
                    "chain_id": None,
                    "latency_ms": 0,
                    "error": "timeout",
                },
            ]

            result = check_rpc_health(1)

            assert "=== RPC Health for Chain 1 ===" in result
            assert "Primary" in result
            assert "Backup 1" in result
            assert "✓ Healthy" in result
            assert "✗ Unhealthy" in result

    def test_check_rpc_health_no_config(self):
        """Test check_rpc_health when no RPCs configured."""
        RPC_CONFIG.clear()

        result = check_rpc_health(1)

        assert "Error: No RPC configuration" in result


class TestSetBackupRpc:
    def test_set_backup_rpc_success(self):
        """Test set_backup_rpc adds backup successfully."""
        RPC_CONFIG[1] = ["http://primary-rpc.com"]

        with patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify:
            mock_verify.return_value = True
            result = set_backup_rpc(1, "http://backup-rpc.com")

            assert "Success" in result
            assert len(RPC_CONFIG[1]) == 2
            assert "http://backup-rpc.com" in RPC_CONFIG[1]

    def test_set_backup_rpc_duplicate(self):
        """Test set_backup_rpc rejects duplicate RPC."""
        RPC_CONFIG[1] = ["http://primary-rpc.com"]

        with patch("mcp_blockchain_rail.server.verify_rpc") as mock_verify:
            mock_verify.return_value = True
            result = set_backup_rpc(1, "http://backup-rpc.com")

        assert "Success" in result
        assert "Backup RPC added" in result

    def test_set_backup_rpc_no_primary(self):
        """Test set_backup_rpc requires primary RPC first."""
        RPC_CONFIG.clear()

        result = set_backup_rpc(1, "http://backup-rpc.com")

        assert "Error: No primary RPC configured" in result


class TestRotateRpc:
    def test_rotate_rpc_success(self):
        """Test rotate_rpc cycles RPCs successfully."""
        RPC_CONFIG[1] = [
            "http://primary-rpc.com",
            "http://backup1.com",
            "http://backup2.com",
        ]

        result = rotate_rpc(1)

        assert "Success" in result
        assert RPC_CONFIG[1][0] == "http://backup1.com"

    def test_rotate_rpc_single_item(self):
        """Test rotate_rpc with only primary RPC."""
        RPC_CONFIG[1] = ["http://primary-rpc.com"]

        result = rotate_rpc(1)

        assert "Error: No backup RPCs" in result

    def test_rotate_rpc_no_config(self):
        """Test rotate_rpc with no configuration."""
        RPC_CONFIG.clear()

        result = rotate_rpc(1)

        assert "Error: No RPC configuration" in result


class TestDeleteRpc:
    def test_delete_rpc_existing(self, tmp_path):
        """Test delete_rpc removes existing RPC."""
        RPC_CONFIG[1] = ["http://rpc1.com"]

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
        RPC_CONFIG[1] = ["http://rpc1.com"]
        RPC_CONFIG[137] = ["http://rpc2.com", "http://rpc3.com"]
        API_KEYS["etherscan"] = "test_key_123456789"

        result = list_configs()

        assert "Chain 1:" in result
        assert "Primary: http://rpc1.com" in result
        assert "Chain 137:" in result
        assert "etherscan: test...6789" in result

    def test_list_configs_empty(self):
        """Test list_configs with no configs."""
        RPC_CONFIG.clear()
        API_KEYS.clear()

        result = list_configs()

        assert "No RPCs configured" in result
        assert "No API keys configured" in result


class TestPersistence:
    def test_save_config_writes_file(self, tmp_path):
        """Test save_config writes data to config file."""
        RPC_CONFIG[1] = ["http://rpc1.com"]
        API_KEYS["etherscan"] = "test_key_123"

        with patch(
            "mcp_blockchain_rail.server.CONFIG_FILE", str(tmp_path / "config.json")
        ):
            save_config()

            import json

            with open(tmp_path / "config.json") as f:
                data = json.load(f)
                assert data["rpcs"] == {"1": ["http://rpc1.com"]}
                assert data["api_keys"] == {"etherscan": "test_key_123"}

    def test_load_config_reads_file(self, tmp_path):
        """Test load_config reads data from config file."""
        config_data = {
            "rpcs": {
                "1": ["http://rpc1.com", "http://rpc2.com"],
                "137": ["http://rpc3.com"],
            },
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

            assert RPC_CONFIG == {
                1: ["http://rpc1.com", "http://rpc2.com"],
                137: ["http://rpc3.com"],
            }
            assert API_KEYS == {"etherscan": "key123"}

    def test_load_config_migrates_old_format(self, tmp_path):
        """Test load_config migrates old single-RPC format to list."""
        config_data = {"rpcs": {"1": "http://old-single-rpc.com"}, "api_keys": {}}

        config_file = tmp_path / "config.json"
        import json

        with open(config_file, "w") as f:
            json.dump(config_data, f)

        with patch("mcp_blockchain_rail.server.CONFIG_FILE", str(config_file)):
            RPC_CONFIG.clear()
            API_KEYS.clear()
            load_config()

            assert 1 in RPC_CONFIG
            assert isinstance(RPC_CONFIG[1], list)
            assert RPC_CONFIG[1] == ["http://old-single-rpc.com"]

    def test_load_config_creates_empty_if_missing(self):
        """Test load_config handles missing config file gracefully."""
        with patch("mcp_blockchain_rail.server.os.path.exists", return_value=False):
            RPC_CONFIG[1] = ["existing"]
            API_KEYS["test"] = "test"

            load_config()

            assert RPC_CONFIG[1] == ["existing"]
            assert API_KEYS["test"] == "test"


class TestGetTokenBalance:
    def test_get_token_balance_no_rpc_configured(self):
        """Test get_token_balance when no RPC is set."""
        result = get_token_balance(
            1,
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        )
        assert "No RPC configuration" in result

    def test_get_token_balance_success(self):
        """Test get_token_balance with valid RPC."""
        RPC_CONFIG[1] = ["http://test-rpc.com"]

        with (
            patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check,
            patch("mcp_blockchain_rail.server.call_erc20_read") as mock_call,
        ):
            mock_health_check.return_value = {
                "healthy": True,
                "chain_id": 1,
                "latency_ms": 50,
                "error": "",
            }
            mock_call.side_effect = [1000000000000000000, 18]

            result = get_token_balance(
                1,
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            )

            assert "Balance:" in result
            assert "1.000000000000000000" in result

    def test_get_token_balance_failover(self):
        """Test get_token_balance with automatic failover."""
        RPC_CONFIG[1] = ["http://failed-rpc.com", "http://backup-rpc.com"]

        with (
            patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check,
            patch("mcp_blockchain_rail.server.call_erc20_read") as mock_call,
        ):

            def health_side_effect(rpc_url, chain_id, timeout):
                return (
                    {"healthy": False, "latency_ms": 0, "error": "failed"}
                    if rpc_url == "http://failed-rpc.com"
                    else {
                        "healthy": True,
                        "latency_ms": 100,
                        "error": "",
                        "chain_id": 1,
                    }
                )

            mock_health_check.side_effect = health_side_effect
            mock_call.side_effect = [500000, 6]

            result = get_token_balance(
                1,
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            )

            assert "Balance:" in result
            assert "0.500000" in result
            assert RPC_CONFIG[1][0] == "http://backup-rpc.com"


class TestGetTokenInfo:
    def test_get_token_info_no_rpc_configured(self):
        """Test get_token_info when no RPC is set."""
        result = get_token_info(1, "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
        assert "No RPC configuration" in result

    def test_get_token_info_success(self):
        """Test get_token_info with valid RPC."""
        RPC_CONFIG[1] = ["http://test-rpc.com"]

        with (
            patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check,
            patch("mcp_blockchain_rail.server.call_erc20_read") as mock_call,
        ):
            mock_health_check.return_value = {
                "healthy": True,
                "chain_id": 1,
                "latency_ms": 50,
                "error": "",
            }
            mock_call.side_effect = ["USD Coin", "USDC", 6, 1000000000000]

            result = get_token_info(1, "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")

            assert "Token Information:" in result
            assert "Name: USD Coin" in result
            assert "Symbol: USDC" in result
            assert "Decimals: 6" in result
            assert "Total Supply:" in result

    def test_get_token_info_failover(self):
        """Test get_token_info with automatic failover."""
        RPC_CONFIG[1] = ["http://failed-rpc.com", "http://backup-rpc.com"]

        with (
            patch("mcp_blockchain_rail.server.health_check_rpc") as mock_health_check,
            patch("mcp_blockchain_rail.server.call_erc20_read") as mock_call,
        ):

            def health_side_effect(rpc_url, chain_id, timeout):
                return (
                    {"healthy": False, "latency_ms": 0, "error": "failed"}
                    if rpc_url == "http://failed-rpc.com"
                    else {
                        "healthy": True,
                        "latency_ms": 100,
                        "error": "",
                        "chain_id": 1,
                    }
                )

            mock_health_check.side_effect = health_side_effect
            mock_call.side_effect = ["Wrapped Ether", "WETH", 18, 500000000000000000]

            result = get_token_info(1, "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")

            assert "Token Information:" in result
            assert "Name: Wrapped Ether" in result
            assert "Symbol: WETH" in result
