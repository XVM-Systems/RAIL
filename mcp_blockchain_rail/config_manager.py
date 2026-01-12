"""Configuration management with YAML and environment variable support."""

import json
import os
from typing import Any

import yaml


class ConfigManager:
    """Configuration manager for RAIL."""

    DEFAULT_CONFIG = {
        "rpc": {"max_backups": 2, "default_timeout": 5, "health_check_interval": 300},
        "cache": {"duration": 3600, "file": "chain_cache.json", "metadata_ttl": 86400},
        "api": {
            "chain_list_url": "https://chainid.network/chains.json",
            "sourcify_url": "https://sourcify.dev/server",
            "etherscan_url": "https://api.etherscan.io/v2/api",
        },
        "encryption": {"enabled": False, "algorithm": "Fernet"},
        "logging": {
            "level": "INFO",
            "file": None,
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
        "testnets": {
            "goerli_rpc": None,
            "sepolia_rpc": None,
            "anvil_rpc": "http://127.0.0.1:8545",
            "hardhat_rpc": "http://127.0.0.1:8545",
        },
    }

    def __init__(self, config_path: str | None = None):
        """Initialize configuration manager.

        Args:
            config_path: Path to config file (uses default or env var).
        """
        self.config_path: str = config_path or os.getenv(  # type: ignore[assignment]
            "RAIL_CONFIG_PATH", "rail_config.yaml"
        )
        self.config: dict[str, Any] = self.DEFAULT_CONFIG.copy()  # type: ignore[assignment]

    def load(self) -> None:
        """Load configuration from YAML file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    loaded_config = yaml.safe_load(f)

                if loaded_config:
                    self.config.update(loaded_config)

                self._apply_env_overrides()
            except Exception as e:
                from mcp_blockchain_rail.logging_config import get_logger

                logger = get_logger(__name__)
                logger.warning(f"Failed to load config: {e}")
        else:
            from mcp_blockchain_rail.logging_config import get_logger

            logger = get_logger(__name__)
            logger.info("Config file not found, using defaults")

    def save(self) -> None:
        """Save configuration to YAML file."""
        try:
            with open(self.config_path, "w") as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            from mcp_blockchain_rail.logging_config import get_logger

            logger = get_logger(__name__)
            logger.error(f"Failed to save config: {e}")

    def get(self, *keys: str) -> Any:
        """Get configuration value using dot notation.

        Args:
            *keys: Nested keys (e.g., "rpc", "max_backups").

        Returns:
            Configuration value or None if not found.
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def set(self, *keys: str, value: Any) -> None:
        """Set configuration value using dot notation.

        Args:
            *keys: Nested keys (e.g., "rpc", "max_backups").
            value: Value to set.
        """
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]

        config[keys[-1]] = value

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides.

        Environment variables:
            RAIL_CACHE_DURATION
            RAIL_RPC_TIMEOUT
            RAIL_LOG_LEVEL
            RAIL_LOG_FILE
            RAIL_ENCRYPTION_KEY
            RAIL_CONFIG_PATH (handled in __init__)
        """
        env_mappings = {
            "RAIL_CACHE_DURATION": ("cache", "duration", int),
            "RAIL_RPC_TIMEOUT": ("rpc", "default_timeout", int),
            "RAIL_LOG_LEVEL": ("logging", "level", str),
            "RAIL_LOG_FILE": ("logging", "file", str),
        }

        for env_var, (section, key, type_converter) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                if section not in self.config:
                    self.config[section] = {}

                converted_value = type_converter(value)
                self.config[section][key] = converted_value

    def validate(self) -> list[str]:
        """Validate configuration schema.

        Returns:
            List of validation errors (empty if valid).
        """
        errors = []

        cache_duration = self.get("cache", "duration")
        if not isinstance(cache_duration, int) or cache_duration < 0:
            errors.append("cache.duration must be a positive integer")

        max_backups = self.get("rpc", "max_backups")
        if not isinstance(max_backups, int) or max_backups < 0:
            errors.append("rpc.max_backups must be a positive integer")

        rpc_timeout = self.get("rpc", "default_timeout")
        if not isinstance(rpc_timeout, int) or rpc_timeout < 0:
            errors.append("rpc.default_timeout must be a positive integer")

        return errors

    def migrate_from_json(self, json_path: str) -> bool:
        """Migrate legacy JSON config to YAML.

        Args:
            json_path: Path to legacy JSON config file.

        Returns:
            True if migration succeeded, False otherwise.
        """
        if not os.path.exists(json_path):
            return False

        try:
            with open(json_path) as f:
                json_data = json.load(f)

            migrated_data = {
                "rpcs": json_data.get("rpcs", {}),
                "api_keys": json_data.get("api_keys", {}),
                "encryption": {"enabled": False},
            }

            if json_data.get("rpcs"):
                self.config["rpcs"] = migrated_data["rpcs"]
            if json_data.get("api_keys"):
                self.config["api_keys"] = migrated_data["api_keys"]

            self.save()
            return True
        except Exception:
            return False


# Global config manager instance
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """Get global config manager instance.

    Returns:
        ConfigManager instance.
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager
