"""ERC-20 ABI helper module"""

from .erc20_abi import ERC20_ABI as ERC20_ABI
from .erc20_abi import call_erc20_read as call_erc20_read

__all__ = ["ERC20_ABI", "call_erc20_read"]
