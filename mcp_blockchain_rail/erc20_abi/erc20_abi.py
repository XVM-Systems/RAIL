"""ERC-20 ABI Constants"""

from typing import Any

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def call_erc20_read(
    rpc_url: str, token_address: str, function_name: str, *args: Any
) -> Any:
    """Call a read-only function on an ERC-20 contract.

    Args:
        rpc_url: The RPC URL to use.
        token_address: The ERC-20 token contract address.
        function_name: The function name to call (e.g., 'balanceOf', 'totalSupply').
        *args: Arguments to pass to the function.

    Returns:
        The result of the function call.

    Raises:
        Exception: If the RPC call fails.
    """
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
    checksum_address = Web3.to_checksum_address(token_address)
    contract = w3.eth.contract(address=checksum_address, abi=ERC20_ABI)
    return contract.functions[function_name](*args).call()
