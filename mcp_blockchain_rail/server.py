import concurrent.futures
import json
import os
import random
import time

import requests
from mcp.server.fastmcp import FastMCP
from web3 import Web3

from mcp_blockchain_rail.config_manager import get_config_manager
from mcp_blockchain_rail.erc20_abi import call_erc20_read
from mcp_blockchain_rail.exceptions import (
    ConfigError,
)
from mcp_blockchain_rail.logging_config import (
    get_logger,
    log_with_context,
    setup_logging,
)
from mcp_blockchain_rail.validators import (
    mask_address,
    mask_url,
    validate_address,
    validate_chain_id,
    validate_rpc_url,
)

config_manager = get_config_manager()
logger = get_logger(__name__)
setup_logging(
    level=config_manager.get("logging", "level"),
    log_file=config_manager.get("logging", "file"),
)

mcp = FastMCP("mcp-blockchain-rail")

RPC_CONFIG: dict[int, list[str]] = {}
MAX_BACKUPS = config_manager.get("rpc", "max_backups")

CHAIN_LIST_URL = config_manager.get("api", "chain_list_url")
CACHE_FILE = config_manager.get("cache", "file")
CACHE_DURATION = config_manager.get("cache", "duration")


def health_check_rpc(rpc_url: str, chain_id: int, timeout: int = 5) -> dict:
    """Check RPC health and return detailed status.

    Args:
        rpc_url: The RPC URL to check.
        chain_id: The expected chain ID.
        timeout: Timeout in seconds.

    Returns:
        dict with keys: healthy (bool), chain_id (int),
        latency_ms (int), error (str)
    """
    try:
        start_time = time.time()
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        if not w3.is_connected():
            log_with_context(
                logger,
                logging.WARNING,
                "RPC not connected",
                {"rpc_url": mask_url(rpc_url)},
            )
            return {
                "healthy": False,
                "chain_id": None,
                "latency_ms": 0,
                "error": "Not connected",
            }

        if w3.eth.chain_id != chain_id:
            log_with_context(
                logger,
                logging.WARNING,
                "RPC wrong chain ID",
                {
                    "rpc_url": mask_url(rpc_url),
                    "expected": chain_id,
                    "actual": w3.eth.chain_id,
                },
            )
            return {
                "healthy": False,
                "chain_id": w3.eth.chain_id,
                "latency_ms": 0,
                "error": f"Wrong chain ID (expected {chain_id})",
            }

        w3.eth.get_balance(
            Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
        )
        latency_ms = int((time.time() - start_time) * 1000)

        log_with_context(
            logger,
            logging.INFO,
            "RPC health check passed",
            {
                "rpc_url": mask_url(rpc_url),
                "latency_ms": latency_ms,
            },
        )

        return {
            "healthy": True,
            "chain_id": chain_id,
            "latency_ms": latency_ms,
            "error": "",
        }
    except Exception as e:
        log_with_context(
            logger,
            logging.ERROR,
            "RPC health check failed",
            {
                "rpc_url": mask_url(rpc_url),
                "error": str(e),
            },
        )
        return {
            "healthy": False,
            "chain_id": None,
            "latency_ms": 0,
            "error": str(e),
        }


def load_config() -> None:
    """Load RPC configs and API keys from config file."""
    try:
        config_file = config_manager.config_path
        if os.path.exists(config_file):
            logger.info(f"Loading config from {config_file}")
            config_manager.load()

            rpcs = config_manager.get("rpcs") or {}
            for chain_id_str, rpc_value in rpcs.items():
                chain_id = int(chain_id_str)
                if isinstance(rpc_value, str):
                    RPC_CONFIG[chain_id] = [rpc_value]
                elif isinstance(rpc_value, list):
                    RPC_CONFIG[chain_id] = rpc_value

            api_keys = config_manager.get("api_keys") or {}
            API_KEYS.update(api_keys)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")


def save_config() -> None:
    """Save RPC configs and API keys to config file."""
    try:
        rpcs_as_strings = {str(k): v for k, v in RPC_CONFIG.items()}
        config_data = {"rpcs": rpcs_as_strings, "api_keys": API_KEYS}

        with open(config_manager.config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        logger.info("Configuration saved")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def get_working_rpc(chain_id: int) -> str:
    """Get a working RPC for a chain with automatic failover.

    Tries primary RPC first, then backups in order. Promotes working
    backup to primary position on success. Logs failover events.

    Args:
        chain_id: The chain ID to get a working RPC for.

    Returns:
        str: A working RPC URL.

    Raises:
        ValueError: If no RPCs configured or all RPCs fail.
    """
    validate_chain_id(chain_id)

    if chain_id not in RPC_CONFIG:
        raise ValueError(f"No RPC configuration for chain ID {chain_id}")

    rpcs = RPC_CONFIG[chain_id]
    failed_rpcs: list[str] = []

    for i, rpc_url in enumerate(rpcs):
        if rpc_url in failed_rpcs:
            continue

        result = health_check_rpc(rpc_url, chain_id, timeout=5)

        if result["healthy"]:
            if i > 0:
                log_with_context(
                    logger,
                    logging.INFO,
                    "Failover: Using backup RPC",
                    {
                        "chain_id": chain_id,
                        "old_rpc": mask_url(rpcs[0]),
                        "new_rpc": mask_url(rpc_url),
                        "index": i,
                    },
                )

            if i > 0:
                RPC_CONFIG[chain_id] = [rpc_url] + [
                    r for r in rpcs if r not in [rpc_url] + failed_rpcs
                ]
                save_config()

            return rpc_url

        failed_rpcs.append(rpc_url)

    error_list = ", ".join([mask_url(r) for r in failed_rpcs[:3]])
    raise ValueError(
        f"All RPCs failed for chain {chain_id}. "
        f"Tried: {error_list}{'...' if len(failed_rpcs) > 3 else ''}"
    )


def verify_rpc(rpc_url: str, chain_id: int, timeout: int = 3) -> bool:
    """Helper to verify if an RPC is reachable, on correct chain, and
    can read state.
    """
    try:
        validate_rpc_url(rpc_url)

        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        if not w3.is_connected():
            return False

        if w3.eth.chain_id != chain_id:
            return False

        w3.eth.get_balance(
            Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
        )

        return True
    except Exception:
        return False


@mcp.tool()
def set_rpc(chain_id: int, rpc_url: str) -> str:
    """
    Set the primary RPC URL for a specific chain ID.
    Validates the RPC URL by checking if it's accessible and matches the chain ID.
    If chain already exists, new RPC becomes primary and old ones become backups.

    Args:
        chain_id: The chain ID to set the RPC for.
        rpc_url: The RPC URL to use.
    """
    try:
        validate_chain_id(chain_id)
        validate_rpc_url(rpc_url)

        if verify_rpc(rpc_url, chain_id, timeout=10):
            if chain_id in RPC_CONFIG:
                existing_rpcs = RPC_CONFIG[chain_id]
                new_config = [rpc_url] + existing_rpcs
                RPC_CONFIG[chain_id] = new_config[: MAX_BACKUPS + 1]
            else:
                RPC_CONFIG[chain_id] = [rpc_url]
            save_config()

            log_with_context(
                logger,
                logging.INFO,
                "RPC set for chain",
                {
                    "chain_id": chain_id,
                    "rpc_url": mask_url(rpc_url),
                    "config_count": len(RPC_CONFIG[chain_id]),
                },
            )

            return f"Success: RPC URL for chain ID {chain_id} set to {rpc_url}"
        else:
            error_msg = (
                f"Error: RPC URL {mask_url(rpc_url)} is unreachable or belongs to a "
                "different chain ID."
            )
            log_with_context(
                logger,
                logging.ERROR,
                error_msg,
                {"rpc_url": mask_url(rpc_url), "chain_id": chain_id},
            )
            return error_msg
    except (ConfigError, ValueError) as e:
        log_with_context(
            logger,
            logging.ERROR,
            "set_rpc failed",
            {"chain_id": chain_id, "error": str(e)},
        )
        return str(e)
    except Exception as e:
        log_with_context(
            logger,
            logging.ERROR,
            "Unexpected error in set_rpc",
            {"chain_id": chain_id, "error": str(e)},
        )
        return f"Error validating RPC: {str(e)}"


@mcp.tool()
def query_rpc_urls(chain_id: int) -> list[str]:
    """
    Query and return RELIABLE public RPC URLs for a given chain ID from ChainList.
    Performs active verification to ensure the RPCs are reachable.
    Caches the chain list for 1 hour in a local file.

    Args:
        chain_id: The chain ID to search for.
    """
    try:
        validate_chain_id(chain_id)

        chains = None
        current_time = time.time()

        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE) as f:
                    cache_data = json.load(f)
                    if current_time - cache_data.get("timestamp", 0) < CACHE_DURATION:
                        chains = cache_data.get("data")
            except Exception:
                pass

        if not chains:
            response = requests.get(CHAIN_LIST_URL, timeout=10)
            response.raise_for_status()
            chains = response.json()

            try:
                with open(CACHE_FILE, "w") as f:
                    json.dump({"timestamp": current_time, "data": chains}, f)
            except Exception:
                pass

        candidates = []
        for chain in chains:
            if chain.get("chainId") == chain_id:
                rpcs = chain.get("rpc", [])
                random.shuffle(rpcs)
                for rpc in rpcs:
                    if rpc.startswith("http") and "${" not in rpc:
                        candidates.append(rpc)

        candidates = candidates[:10]
        reliable_rpcs = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {
                executor.submit(verify_rpc, url, chain_id): url for url in candidates
            }
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    is_valid = future.result()
                    if is_valid:
                        reliable_rpcs.append(url)
                except Exception:
                    pass

        if not reliable_rpcs:
            error_msg = "Error: No reliable RPC URLs found for this chain ID."
            log_with_context(
                logger,
                logging.WARNING,
                error_msg,
                {"chain_id": chain_id, "candidates": len(candidates)},
            )
            return [error_msg]

        log_with_context(
            logger,
            logging.INFO,
            "Found reliable RPCs",
            {"chain_id": chain_id, "count": len(reliable_rpcs)},
        )

        return reliable_rpcs
    except Exception as e:
        error_msg = f"Error fetching RPC URLs: {str(e)}"
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {"chain_id": chain_id},
        )
        return [error_msg]


@mcp.tool()
def check_native_balance(chain_id: int, address: str) -> str:
    """
    Check the native token balance of an address on a specific chain.
    Requires an RPC URL to be set for the chain ID using set_rpc first.

    Args:
        chain_id: The chain ID of the network.
        address: The address to check balance for.
    """
    try:
        validate_chain_id(chain_id)

        try:
            checksum_address = validate_address(address, param_name="address")
        except ConfigError as e:
            log_with_context(
                logger,
                logging.ERROR,
                "Invalid address",
                {"address": address, "error": e.message},
            )
            return e.message

        try:
            rpc_url = get_working_rpc(chain_id)
        except ValueError as e:
            log_with_context(
                logger,
                logging.ERROR,
                "No RPC configuration",
                {"chain_id": chain_id},
            )
            return str(e)

        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            error_msg = (
                "Error: Could not connect to configured RPC URL. "
                "It may have gone offline."
            )
            log_with_context(
                logger,
                logging.ERROR,
                error_msg,
                {"rpc_url": mask_url(rpc_url), "chain_id": chain_id},
            )
            return error_msg

        balance_wei = w3.eth.get_balance(checksum_address)
        balance_eth = w3.from_wei(balance_wei, "ether")

        log_with_context(
            logger,
            logging.INFO,
            "Balance checked",
            {
                "chain_id": chain_id,
                "address": mask_address(address),
                "balance": balance_eth,
            },
        )

        return f"{balance_eth} ETH"
    except Exception as e:
        error_msg = f"Error fetching balance from {mask_url(rpc_url)}: {str(e)}"
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {
                "chain_id": chain_id,
                "address": address,
            },
        )
        return error_msg


API_KEYS: dict[str, str] = {}

load_config()


@mcp.tool()
def set_api_key(provider: str, key: str) -> str:
    """
    Set an API key for a specific provider (e.g., 'etherscan').

    Args:
        provider: The name of the service (e.g., 'etherscan').
        key: The API key.
    """
    provider_lower = provider.lower()
    API_KEYS[provider_lower] = key
    save_config()

    log_with_context(
        logger,
        logging.INFO,
        "API key set",
        {"provider": provider},
    )

    return f"Success: API key set for {provider}"


@mcp.tool()
def delete_rpc(chain_id: int) -> str:
    """
    Delete the RPC configuration for a specific chain ID.

    Args:
        chain_id: The chain ID to remove the RPC configuration for.
    """
    validate_chain_id(chain_id)

    if chain_id in RPC_CONFIG:
        del RPC_CONFIG[chain_id]
        save_config()

        log_with_context(
            logger,
            logging.INFO,
            "RPC configuration deleted",
            {"chain_id": chain_id},
        )

        return f"Success: RPC configuration for chain ID {chain_id} deleted."

    error_msg = f"Error: No RPC configuration found for chain ID {chain_id}."
    log_with_context(
        logger,
        logging.WARNING,
        error_msg,
        {"chain_id": chain_id},
    )
    return error_msg


@mcp.tool()
def delete_api_key(provider: str) -> str:
    """
    Delete the API key configuration for a specific provider.

    Args:
        provider: The name of the service (e.g., 'etherscan').
    """
    provider_key = provider.lower()
    if provider_key in API_KEYS:
        del API_KEYS[provider_key]
        save_config()

        log_with_context(
            logger,
            logging.INFO,
            "API key deleted",
            {"provider": provider},
        )

        return f"Success: API key for {provider} deleted."

    error_msg = f"Error: No API key found for {provider}."
    log_with_context(
        logger,
        logging.WARNING,
        error_msg,
        {"provider": provider},
    )
    return error_msg


@mcp.tool()
def list_configs() -> str:
    """
    List all saved RPC configurations and API keys.
    API keys are masked for security.
    """
    lines = []
    lines.append("=== RPC Configuration ===")
    if RPC_CONFIG:
        for chain_id, rpc_list in RPC_CONFIG.items():
            primary = rpc_list[0] if rpc_list else "None"
            backups = (
                ", ".join([mask_url(r) for r in rpc_list[1:]])
                if len(rpc_list) > 1
                else "None"
            )
            lines.append(f"  Chain {chain_id}:")
            lines.append(f"    Primary: {mask_url(primary)}")
            if backups != "None":
                lines.append(f"    Backups: {backups}")
    else:
        lines.append("  No RPCs configured.")

    lines.append("\n=== API Keys ===")
    if API_KEYS:
        for provider, key in API_KEYS.items():
            masked_key = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
            lines.append(f"  {provider}: {masked_key}")
    else:
        lines.append("  No API keys configured.")

    log_with_context(
        logger,
        logging.INFO,
        "Configuration listed",
        {"rpc_count": len(RPC_CONFIG), "api_key_count": len(API_KEYS)},
    )

    return "\n".join(lines)


@mcp.tool()
def check_rpc_health(chain_id: int) -> str:
    """
    Check the health status of all configured RPCs for a chain.

    Args:
        chain_id: The chain ID to check RPC health for.
    """
    validate_chain_id(chain_id)

    if chain_id not in RPC_CONFIG:
        return f"Error: No RPC configuration for chain ID {chain_id}."

    rpcs = RPC_CONFIG[chain_id]
    lines = [f"=== RPC Health for Chain {chain_id} ==="]

    for i, rpc_url in enumerate(rpcs):
        role = "Primary" if i == 0 else f"Backup {i}"
        result = health_check_rpc(rpc_url, chain_id, timeout=5)

        if result["healthy"]:
            status = (
                f"✓ Healthy (latency: {result['latency_ms']}ms, "
                f"chain_id: {result['chain_id']})"
            )
        else:
            status = f"✗ Unhealthy (error: {result['error']})"

        lines.append(f"  [{role}] {mask_url(rpc_url)}")
        lines.append(f"    Status: {status}")

    return "\n".join(lines)


@mcp.tool()
def set_backup_rpc(chain_id: int, rpc_url: str) -> str:
    """
    Add a backup RPC URL for a specific chain ID.
    Validates the RPC URL before adding.

    Args:
        chain_id: The chain ID to add the backup RPC for.
        rpc_url: The backup RPC URL to add.
    """
    validate_chain_id(chain_id)

    if chain_id not in RPC_CONFIG:
        return (
            f"Error: No primary RPC configured for chain ID {chain_id}. "
            f"Use set_rpc({chain_id}, 'PRIMARY_RPC_URL') first."
        )

    if verify_rpc(rpc_url, chain_id, timeout=10):
        existing_rpcs = RPC_CONFIG[chain_id]
        if rpc_url in existing_rpcs:
            return f"Error: RPC URL {mask_url(rpc_url)} already configured for chain {chain_id}."

        new_config = existing_rpcs + [rpc_url]
        RPC_CONFIG[chain_id] = new_config[: MAX_BACKUPS + 1]
        save_config()

        log_with_context(
            logger,
            logging.INFO,
            "Backup RPC added",
            {
                "chain_id": chain_id,
                "config_count": len(RPC_CONFIG[chain_id]),
            },
        )

        return (
            f"Success: Backup RPC added for chain {chain_id}. "
            f"Total RPCs: {len(RPC_CONFIG[chain_id])}"
        )
    else:
        error_msg = (
            f"Error: RPC URL {mask_url(rpc_url)} is unreachable or belongs to a "
            "different chain ID."
        )
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {"chain_id": chain_id},
        )
        return error_msg


@mcp.tool()
def rotate_rpc(chain_id: int) -> str:
    """
    Rotate to the next backup RPC for a chain.
    Cycles current primary to the end of the backup list.

    Args:
        chain_id: The chain ID to rotate RPCs for.
    """
    validate_chain_id(chain_id)

    if chain_id not in RPC_CONFIG:
        return f"Error: No RPC configuration for chain ID {chain_id}."

    rpcs = RPC_CONFIG[chain_id]
    if len(rpcs) <= 1:
        return f"Error: No backup RPCs to rotate to for chain {chain_id}."

    new_config = rpcs[1:] + [rpcs[0]]
    RPC_CONFIG[chain_id] = new_config
    save_config()
    new_primary = new_config[0]

    log_with_context(
        logger,
        logging.INFO,
        "RPC rotated",
        {"chain_id": chain_id, "new_primary": mask_url(new_primary)},
    )

    return f"Success: Rotated to new primary RPC for chain {chain_id}: {new_primary}"


@mcp.tool()
def get_source_code(chain_id: int, contract_address: str) -> str:
    """
    Get the source code of a verified contract.
    First tries Sourcify, then falls back to Etherscan.

    Args:
        chain_id: The chain ID of the network.
        contract_address: The address of the contract.
    """
    try:
        validate_chain_id(chain_id)

        sourcify_base_url = config_manager.get("api", "sourcify_url")

        checksum_address = validate_address(
            contract_address, param_name="contract_address"
        )

        try:
            url = f"{sourcify_base_url}/files/{chain_id}/{checksum_address}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                files = response.json()
                result = []
                for file in files:
                    path = file.get("path", "unknown_path")
                    content = file.get("content", "")
                    result.append(f"// File: {path}\n{content}")

                log_with_context(
                    logger,
                    logging.INFO,
                    "Source code fetched from Sourcify",
                    {
                        "chain_id": chain_id,
                        "contract_address": mask_address(contract_address),
                    },
                )

                return "\n\n".join(result)
        except Exception:
            pass

        api_key = API_KEYS.get("etherscan")

        if api_key:
            try:
                etherscan_url = config_manager.get("api", "etherscan_url")
                etherscan_url = f"{etherscan_url}?chainid={chain_id}&module=contract&action=getsourcecode&address={checksum_address}&apikey={api_key}"
                response = requests.get(etherscan_url, timeout=10)
                data = response.json()

                if data.get("status") == "1" and data.get("result"):
                    result_data = data["result"][0]
                    source_code = result_data["SourceCode"]

                    if source_code.startswith("{{"):
                        try:
                            sources = json.loads(source_code[1:-1])
                            return f"{json.dumps(sources, indent=2)}"
                        except Exception:
                            pass

                    log_with_context(
                        logger,
                        logging.INFO,
                        "Source code fetched from Etherscan",
                        {
                            "chain_id": chain_id,
                            "contract_address": mask_address(contract_address),
                        },
                    )

                    return f"{source_code}"

                error_msg = (
                    f"Error: Contract not verified on Etherscan "
                    f"(Status: {data.get('message')})"
                )
                log_with_context(
                    logger,
                    logging.WARNING,
                    error_msg,
                    {
                        "chain_id": chain_id,
                        "contract_address": mask_address(contract_address),
                    },
                )
                return error_msg
            except Exception as e:
                error_msg = f"Error fetching from Etherscan: {str(e)}"
                log_with_context(
                    logger,
                    logging.ERROR,
                    error_msg,
                    {
                        "chain_id": chain_id,
                        "contract_address": mask_address(contract_address),
                    },
                )
                return error_msg

        error_msg = (
            f"Error: Contract not found on Sourcify for chain ID {chain_id} and "
            f"address {mask_address(contract_address)}. Etherscan fallback failed "
            f"(missing API key or contract not found)."
        )
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {"chain_id": chain_id, "contract_address": mask_address(contract_address)},
        )
        return error_msg
    except ConfigError as e:
        log_with_context(
            logger,
            logging.ERROR,
            "Error in get_source_code",
            {"error": e.message, "code": e.code},
        )
        return e.message
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {"chain_id": chain_id, "contract_address": mask_address(contract_address)},
        )
        return error_msg


@mcp.tool()
def get_token_balance(chain_id: int, token_address: str, wallet_address: str) -> str:
    """
    Query the ERC-20 token balance of a wallet address.
    Uses automatic RPC failover if the primary RPC is down.

    Args:
        chain_id: The chain ID of the network.
        token_address: The address of the ERC-20 token contract.
        wallet_address: The address to check the token balance for.
    """
    try:
        validate_chain_id(chain_id)

        try:
            checksum_token = validate_address(token_address, param_name="token_address")
            checksum_wallet = validate_address(
                wallet_address, param_name="wallet_address"
            )
        except ConfigError as e:
            log_with_context(
                logger,
                logging.ERROR,
                "Invalid address",
                {"error": e.message},
            )
            return e.message

        try:
            rpc_url = get_working_rpc(chain_id)
        except ValueError as e:
            log_with_context(
                logger,
                logging.ERROR,
                "No RPC configuration",
                {"chain_id": chain_id},
            )
            return str(e)

        balance = call_erc20_read(rpc_url, checksum_token, "balanceOf", checksum_wallet)
        decimals = call_erc20_read(rpc_url, checksum_token, "decimals")

        if decimals == 0:
            formatted_balance = str(balance)
        else:
            divisor = 10**decimals
            formatted_balance = f"{balance / divisor:.{decimals}f}"

        log_with_context(
            logger,
            logging.INFO,
            "Token balance queried",
            {
                "chain_id": chain_id,
                "token_address": mask_address(token_address),
                "wallet_address": mask_address(wallet_address),
                "balance": formatted_balance,
            },
        )

        return f"Balance: {formatted_balance} tokens (raw: {balance})"
    except Exception as e:
        error_msg = f"Error fetching token balance: {str(e)}"
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {
                "chain_id": chain_id,
                "token_address": mask_address(token_address),
                "wallet_address": mask_address(wallet_address),
            },
        )
        return error_msg


@mcp.tool()
def get_token_info(chain_id: int, token_address: str) -> str:
    """
    Get metadata for an ERC-20 token (name, symbol, decimals, total supply).
    Uses automatic RPC failover if the primary RPC is down.

    Args:
        chain_id: The chain ID of the network.
        token_address: The address of the ERC-20 token contract.
    """
    try:
        validate_chain_id(chain_id)

        try:
            checksum_address = validate_address(
                token_address, param_name="token_address"
            )
        except ConfigError as e:
            log_with_context(
                logger,
                logging.ERROR,
                "Invalid address",
                {"error": e.message},
            )
            return e.message

        try:
            rpc_url = get_working_rpc(chain_id)
        except ValueError as e:
            log_with_context(
                logger,
                logging.ERROR,
                "No RPC configuration",
                {"chain_id": chain_id},
            )
            return str(e)

        name = call_erc20_read(rpc_url, checksum_address, "name")
        symbol = call_erc20_read(rpc_url, checksum_address, "symbol")
        decimals = call_erc20_read(rpc_url, checksum_address, "decimals")
        total_supply = call_erc20_read(rpc_url, checksum_address, "totalSupply")

        if decimals == 0:
            formatted_supply = str(total_supply)
        else:
            divisor = 10**decimals
            formatted_supply = f"{total_supply / divisor:.{decimals}f}"

        log_with_context(
            logger,
            logging.INFO,
            "Token info queried",
            {
                "chain_id": chain_id,
                "token_address": mask_address(token_address),
                "name": name,
                "symbol": symbol,
            },
        )

        return (
            f"Token Information:\n"
            f"  Name: {name}\n"
            f"  Symbol: {symbol}\n"
            f"  Decimals: {decimals}\n"
            f"  Total Supply: {formatted_supply}"
        )
    except Exception as e:
        error_msg = f"Error fetching token info: {str(e)}"
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {"chain_id": chain_id, "token_address": mask_address(token_address)},
        )
        return error_msg


@mcp.tool()
def setup_encryption(password: str | None = None) -> str:
    """
    Setup encryption for API keys. Mandatory for all keys.

    Args:
        password: Encryption password. If not provided, prompts interactively.

    Returns:
        Success message or error.
    """
    import os

    from mcp_blockchain_rail.crypto import EncryptionManager

    if not password:
        password = os.getenv("RAIL_ENCRYPTION_KEY")

    if not password:
        import getpass

        password = getpass.getpass("Enter encryption password: ")

    if not password:
        return "Error: Encryption password required. Use --password or RAIL_ENCRYPTION_KEY env var."

    try:
        config_manager = get_config_manager()
        encryption_manager = EncryptionManager.from_password(password)

        api_keys = API_KEYS.copy()
        encrypted_keys = {}

        for provider, key in api_keys.items():
            encrypted_key = encryption_manager.encrypt(key)
            encrypted_keys[provider] = encrypted_key

        config_manager.set("encryption", "enabled", True)
        config_manager.set("encryption", "salt", encryption_manager.get_salt_base64())
        config_manager.set("api_keys", encrypted_keys)
        config_manager.save()

        log_with_context(
            logger,
            logging.INFO,
            "Encryption enabled",
            {"keys_count": len(encrypted_keys)},
        )

        return f"Success: Encryption enabled. All {len(encrypted_keys)} API key(s) encrypted."
    except Exception as e:
        error_msg = f"Error setting up encryption: {str(e)}"
        log_with_context(
            logger,
            logging.ERROR,
            error_msg,
            {"error": str(e)},
        )
        return error_msg


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
