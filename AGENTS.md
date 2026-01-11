# RAIL - OpenCode Development Guide

## Project Overview
RAIL is an MCP (Model Context Protocol) Server for EVM blockchain interactions. It provides standardized tools for AI/LLM systems to interact with EVM-compatible blockchains through a unified interface.

## Project Structure
```
RAIL/
├── mcp_blockchain_rail/
│   ├── __init__.py
│   └── server.py          # Main MCP server implementation
├── tests/
│   ├── __init__.py
│   ├── conftest.py        # pytest fixtures
│   ├── test_server.py     # Tests for MCP tools
│   └── test_verify_rpc.py # Tests for RPC verification
├── pyproject.toml         # Project configuration and dependencies
├── test_server.py         # Legacy verification script for tools
├── AGENTS.md              # This development guide
└── README.md              # Project documentation
```

## Tech Stack
- **Language**: Python 3.10+
- **Core Dependencies**:
  - `mcp` - Model Context Protocol framework (FastMCP)
  - `web3` - Ethereum Web3.py for blockchain interactions
  - `requests` - HTTP client for API calls
- **Package Manager**: uv
- **Build System**: hatchling
- **Testing & Quality**:
  - `pytest` - Test framework
  - `pytest-cov` - Code coverage reporting
  - `mypy` - Static type checking
  - `ruff` - Linting and formatting

## Key Components

### MCP Tools (in `server.py`)
1. `set_rpc(chain_id, rpc_url)` - Configure and validate RPC endpoints
2. `query_rpc_urls(chain_id)` - Find reliable public RPCs from ChainList
3. `check_native_balance(chain_id, address)` - Query ETH balance
4. `set_api_key(provider, key)` - Configure explorer API keys
5. `get_source_code(chain_id, contract_address)` - Fetch verified contract code

### Important Patterns
- **RPC Validation**: All RPCs are verified for connectivity and chain ID matching before use
- **Caching**: ChainList data is cached locally for 1 hour (`chain_cache.json`)
- **Parallel Verification**: RPCs are verified concurrently using ThreadPoolExecutor
- **Fallback Strategy**: Source code fetch tries Sourcify first, then Etherscan

## Development Workflow

### Running Tests
```bash
# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run tests with coverage report
uv run pytest --cov=mcp_blockchain_rail --cov-report=html

# Run specific test file
uv run pytest tests/test_server.py

# Run specific test
uv run pytest tests/test_server.py::TestSetRpc::test_set_rpc_success
```

### Starting the MCP Server
```bash
# Using uv
uv run mcp-blockchain-rail

# Or directly
python -m mcp_blockchain_rail.server
```

### Installing Dependencies
```bash
uv sync

# Install dev dependencies (testing, linting, type checking)
uv sync --extra dev
```

### Linting & Type Checking
```bash
# Run linter
uv run ruff check

# Auto-fix linting issues
uv run ruff check --fix

# Format code
uv run ruff format

# Run type checker
uv run mypy mcp_blockchain_rail/

# Run all quality checks together
uv run ruff check && uv run mypy mcp_blockchain_rail/
```

## Code Conventions

### MCP Tool Structure
```python
@mcp.tool()
def tool_name(param1: type, param2: type) -> str:
    """
    Tool description explaining what it does.
    
    Args:
        param1: Description of parameter
        param2: Description of parameter
    """
    # Implementation
    return result
```

### Error Handling
- All tools should catch exceptions and return descriptive error messages
- Error messages should start with `"Error: "` for consistent parsing
- Validate inputs before making network calls

### RPC Configuration
- RPC URLs are stored in the global `RPC_CONFIG` dictionary keyed by chain_id
- Always validate RPCs before storing them using `verify_rpc()`
- Use Web3 HTTPProvider with timeout configuration

## Known Limitations & Areas for Improvement

### Current Limitations
1. **State Management**: RPC_CONFIG and API_KEYS are in-memory only (lost on restart)
2. **Error Handling**: Some error cases could be more specific
3. **Configuration**: Hard-coded values (CACHE_DURATION, timeouts)
4. **Logging**: No structured logging system

### Potential Improvements
1. **Persistence**: Save RPC configs and API keys to disk (encrypted)
2. **Expanded Functionality**:
   - ERC-20 token balance queries
   - Transaction sending
   - Contract interaction (read/write functions)
   - Gas price estimation
   - Block information queries
   - Transaction receipt queries
3. **Performance**:
   - Connection pooling for RPC endpoints
   - Longer cache duration with TTL-based invalidation
4. **Reliability**:
   - Automatic RPC failover when configured RPC goes down
   - Health checks for stored RPCs
5. **Developer Experience**:
    - Configuration file support (YAML/TOML)
    - CLI for managing RPCs and API keys

## External APIs Used

### ChainList
- **URL**: https://chainid.network/chains.json
- **Purpose**: Discover public RPC endpoints for EVM chains
- **Caching**: 1 hour local cache

### Sourcify
- **Base URL**: https://sourcify.dev/server
- **Purpose**: Fetch verified contract source code
- **Advantage**: No API key required, multi-chain support

### Etherscan API
- **Base URL**: https://api.etherscan.io/v2/api
- **Purpose**: Fallback for contract source code
- **Requirement**: API key needed

## Adding New Tools

When adding new MCP tools:

1. Follow the existing `@mcp.tool()` decorator pattern
2. Use descriptive docstrings with Args sections
3. Return string responses for consistency
4. Validate inputs before making network calls
5. Handle all exceptions gracefully
6. Return error messages with `"Error: "` prefix
7. Use existing global configs (RPC_CONFIG, API_KEYS) where appropriate
8. Add test cases to the `tests/` directory

## Chain Support

The server is chain-agnostic and works with any EVM-compatible chain. Test chains include:
- Ethereum Mainnet (Chain ID: 1)
- Add test cases for other chains as needed (Polygon, Arbitrum, Optimism, etc.)

## Security Considerations

1. **API Keys**: Never commit API keys to the repository
2. **RPC URLs**: Validate RPCs before using them (checks chain ID and connectivity)
3. **User Input**: Always validate and checksum addresses using `Web3.to_checksum_address()`
4. **Timeouts**: Use appropriate timeouts on all network requests
5. **Error Messages**: Don't expose sensitive information in error messages
