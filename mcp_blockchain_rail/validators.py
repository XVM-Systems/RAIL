"""Input validation and sanitization utilities."""

import base64
import re

from web3 import Web3

from mcp_blockchain_rail.exceptions import ConfigError, EncryptionError


def validate_address(address: str, param_name: str = "address") -> str:
    """Validate and return checksum address.

    Args:
        address: Ethereum address to validate.
        param_name: Parameter name for error messages.

    Returns:
        Checksummed address.

    Raises:
        ConfigError: If address is invalid.
    """
    try:
        return Web3.to_checksum_address(address)
    except ValueError as e:
        raise ConfigError(
            f"Invalid {param_name}: {mask_address(address)}",
            ConfigError.ERR_INVALID_ADDRESS,
            hint="Address must be a valid 0x-prefixed hex string of 40 characters",
        ) from e


def validate_chain_id(chain_id: int) -> int:
    """Validate chain ID is positive integer.

    Args:
        chain_id: Chain ID to validate.

    Returns:
        Validated chain ID.

    Raises:
        ConfigError: If chain ID is invalid.
    """
    if not isinstance(chain_id, int) or chain_id <= 0:
        raise ConfigError(
            f"Invalid chain ID: {chain_id}",
            ConfigError.ERR_INVALID_CHAIN_ID,
            hint="Chain ID must be a positive integer",
        )
    return chain_id


def validate_rpc_url(url: str) -> str:
    """Validate RPC URL format.

    Args:
        url: RPC URL to validate.

    Returns:
        Validated URL.

    Raises:
        ConfigError: If URL is invalid.
    """
    if not re.match(r"^https?://[^\s/]+$", url):
        raise ConfigError(
            f"Invalid RPC URL: {mask_url(url)}",
            ConfigError.ERR_INVALID_URL,
            hint="URL must start with http:// or https://",
        )
    return url


def validate_private_key(private_key: str, encrypted: bool) -> str:
    """Validate private key format.

    Args:
        private_key: Private key to validate.
        encrypted: Whether the key should be encrypted.

    Returns:
        Validated private key.

    Raises:
        EncryptionError: If key format is invalid.
    """
    if encrypted:
        try:
            base64.b64decode(private_key)
        except Exception as e:
            raise EncryptionError(
                "Invalid encrypted private key format",
                EncryptionError.ERR_INVALID_KEY,
                hint="Encrypted key must be base64-encoded",
            ) from e
    else:
        raise EncryptionError(
            "Plain text private keys are not allowed",
            EncryptionError.ERR_PLAIN_TEXT_KEY,
            hint="Private keys must be encrypted. Use setup_encryption()",
        )
    return private_key


def mask_address(address: str) -> str:
    """Mask address for display in errors.

    Args:
        address: Address to mask.

    Returns:
        Masked address.
    """
    if len(address) < 10:
        return "***"
    return f"{address[:6]}...{address[-4:]}"


def mask_url(url: str) -> str:
    """Mask URL for display in errors.

    Args:
        url: URL to mask.

    Returns:
        Masked URL.
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        netloc = parsed.netloc
        if len(netloc) > 10:
            netloc = f"{netloc[:4]}...{netloc[-4:]}"
        return f"{parsed.scheme}://{netloc}{parsed.path}"
    except Exception:
        return "***"
