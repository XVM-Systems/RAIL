API_KEYS: dict[str, str] = {}

load_config()

from mcp_blockchain_rail.erc20_abi import ERC20_ABI, call_erc20_read

mcp = FastMCP("mcp-blockchain-rail")


if __name__ == "__main__":
    main()
