import sys
import os

# Add current directory to path so we can import server
sys.path.append(os.getcwd())

from mcp_blockchain_rail.server import (
    query_rpc_urls,
    set_rpc,
    check_native_balance,
)


def test_query_rpc_urls():
    print("Testing query_rpc_urls(1)...")
    urls = query_rpc_urls(1)
    if isinstance(urls, list) and len(urls) > 0:
        print(f"Success: Found {len(urls)} RPC URLs for Ethereum Mainnet.")
        print(f"Sample: {urls[0]}")
        return urls[0]
    else:
        print(f"Failed: {urls}")
        return None


def test_set_rpc(url):
    print(f"\nTesting set_rpc(1, '{url}')...")
    result = set_rpc(1, url)
    print(result)
    if "Success" in result:
        return True
    return False


def test_check_native_balance():
    # Vitalik's address
    address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    print(f"\nTesting check_native_balance(1, '{address}')...")
    balance = check_native_balance(1, address)
    print(f"Balance: {balance}")
    if "ETH" in balance:
        return True
    return False


def main():
    print("Starting verification...")

    # Test 1: Query RPCs
    rpc_urls = test_query_rpc_urls()

    # Since we implemented filtering for reliable RPCs, we should try to use one from the list
    # test_query_rpc_urls returns a single URL string or None
    if rpc_urls and isinstance(rpc_urls, str) and not rpc_urls.startswith("Error"):
        test_rpc = rpc_urls
        print(f"Selected reliable RPC from query: {test_rpc}")

        # Test 2: Set RPC
        if test_set_rpc(test_rpc):
            # Test 3: Check Balance
            test_check_native_balance()
        else:
            print("Set RPC failed with queried URL.")
    else:
        print(
            "Query failed to return valid RPCs, falling back to known good one for basic sanity check."
        )
        test_rpc = "https://eth.llamarpc.com"
        if test_set_rpc(test_rpc):
            test_check_native_balance()


if __name__ == "__main__":
    main()
