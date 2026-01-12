"""Custom exception hierarchy for RAIL."""

# ruff: noqa: N818 - Base exception class ending with "Exception" is acceptable for base class


class RAILException(Exception):
    """Base exception for all RAIL errors."""

    def __init__(self, message: str, code: int, hint: str | None = None):
        self.message = message
        self.code = code
        self.hint = hint
        super().__init__(self.message)


class RPCError(RAILException):
    """RPC connection/validation errors."""

    ERR_UNREACHABLE = 1001
    ERR_WRONG_CHAIN = 1002
    ERR_ALL_FAILED = 1003
    ERR_TIMEOUT = 1004


class ConfigError(RAILException):
    """Configuration errors."""

    ERR_MISSING_FILE = 2001
    ERR_INVALID_SCHEMA = 2002
    ERR_MIGRATION_FAILED = 2003
    ERR_INVALID_ADDRESS = 2004
    ERR_INVALID_CHAIN_ID = 2005
    ERR_INVALID_URL = 2006
    ERR_ENCRYPTION_REQUIRED = 2007


class TokenError(RAILException):
    """Token/contract interaction errors."""

    ERR_INVALID_ADDRESS = 3001
    ERR_INVALID_DECIMALS = 3002
    ERR_CALL_FAILED = 3003
    ERR_INSUFFICIENT_ALLOWANCE = 3004


class TransactionError(RAILException):
    """Transaction-related errors."""

    ERR_INSUFFICIENT_FUNDS = 4001
    ERR_NONCE_MISMATCH = 4002
    ERR_GAS_ESTIMATION_FAILED = 4003
    ERR_TRANSACTION_FAILED = 4004


class EncryptionError(RAILException):
    """Encryption/decryption errors."""

    ERR_INVALID_KEY = 5001
    ERR_DECRYPTION_FAILED = 5002
    ERR_ENCRYPTION_FAILED = 5003
    ERR_PLAIN_TEXT_KEY = 5004
