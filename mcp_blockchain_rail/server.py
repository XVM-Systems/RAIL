from typing import Dict, List
import random
import requests
import concurrent.futures
from mcp.server.fastmcp import FastMCP
from web3 import Web3

import json
import os
import time

mcp = FastMCP("mcp-blockchain-rail")

RPC_CONFIG: Dict[int, str] = {}

CHAIN_LIST_URL = "https://chainid.network/chains.json"
CACHE_FILE = "chain_cache.json"
CACHE_DURATION = 3600


def verify_rpc(rpc_url: str, chain_id: int, timeout: int = 3) -> bool:
    """Helper to verify if an RPC is reachable, on the correct chain, and can read state."""
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        if not w3.is_connected():
            return False

        if w3.eth.chain_id != chain_id:
            return False

        # Verify basic state read
        w3.eth.get_balance("0x0000000000000000000000000000000000000000")

        return True
    except Exception:
        return False


@mcp.tool()
def set_rpc(chain_id: int, rpc_url: str) -> str:
    """
    Set the RPC URL for a specific chain ID.
    Validates the RPC URL by checking if it's accessible and matches the chain ID.

    Args:
        chain_id: The chain ID to set the RPC for.
        rpc_url: The RPC URL to use.
    """
    try:
        if verify_rpc(rpc_url, chain_id, timeout=10):
            RPC_CONFIG[chain_id] = rpc_url
            return f"Success: RPC URL for chain ID {chain_id} set to {rpc_url}"
        else:
            return f"Error: RPC URL {rpc_url} is unreachable or belongs to a different chain ID."
    except Exception as e:
        return f"Error validating RPC: {str(e)}"


@mcp.tool()
def query_rpc_urls(chain_id: int) -> List[str]:
    """
    Query and return RELIABLE public RPC URLs for a given chain ID from ChainList.
    Performs active verification to ensure the RPCs are reachable.
    Caches the chain list for 1 hour in a local file.

    Args:
        chain_id: The chain ID to search for.
    """
    try:
        chains = None
        current_time = time.time()

        # Try to load from cache
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    cache_data = json.load(f)
                    if current_time - cache_data.get("timestamp", 0) < CACHE_DURATION:
                        chains = cache_data.get("data")
            except Exception:
                pass

        if not chains:
            response = requests.get(CHAIN_LIST_URL, timeout=10)
            response.raise_for_status()
            chains = response.json()

            # Write to cache
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
                    # Filter out non-http RPCs and those with API keys placeholder
                    if rpc.startswith("http") and "${" not in rpc:
                        candidates.append(rpc)

        # Limit candidates to check to avoid taking forever if there are many
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
            return ["Error: No reliable RPC URLs found for this chain ID."]

        return reliable_rpcs
    except Exception as e:
        return [f"Error fetching RPC URLs: {str(e)}"]


@mcp.tool()
def check_native_balance(chain_id: int, address: str) -> str:
    """
    Check the native token balance of an address on a specific chain.
    Requires an RPC URL to be set for the chain ID using set_rpc first.

    Args:
        chain_id: The chain ID of the network.
        address: The address to check balance for.
    """
    rpc_url = RPC_CONFIG.get(chain_id)
    if not rpc_url:
        return f"Error: No RPC URL configured for chain ID {chain_id}. Please use set_rpc({chain_id}, 'YOUR_RPC_URL') first."

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        if not w3.is_connected():
            return "Error: Could not connect to configured RPC URL. It may have gone offline."

        # Ensure checksum address
        try:
            checksum_address = Web3.to_checksum_address(address)
        except ValueError:
            return f"Error: Invalid address format '{address}'"

        balance_wei = w3.eth.get_balance(checksum_address)
        balance_eth = w3.from_wei(balance_wei, "ether")

        return f"{balance_eth} ETH"
    except Exception as e:
        return f"Error fetching balance from {rpc_url}: {str(e)}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
