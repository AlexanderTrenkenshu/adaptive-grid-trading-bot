"""
Main entry point for the Adaptive Grid Trading Bot.

This script initializes the bot, loads configuration, and starts the trading engine.
"""

import asyncio
import argparse
import json
import signal
from pathlib import Path
from typing import Optional

from utils.logger import setup_logger, log_system_event, EventType


class TradingBot:
    """Main trading bot coordinator."""

    def __init__(self, config_path: str):
        """
        Initialize the trading bot.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.logger = setup_logger(
            log_level=self.config.get("logging", {}).get("level", "INFO"),
            log_dir=self.config.get("logging", {}).get("log_dir", "logs"),
            log_format=self.config.get("logging", {}).get("format", "json"),
            service_name="adaptive-grid-bot"
        )
        self.running = False

    def _load_config(self) -> dict:
        """Load configuration from JSON file."""
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(config_file, 'r') as f:
            return json.load(f)

    async def start(self):
        """Start the trading bot."""
        self.running = True
        log_system_event(
            self.logger,
            EventType.STARTUP,
            "Trading bot starting",
            config_path=self.config_path,
            testnet=self.config.get("exchange", {}).get("testnet", True),
            market_type=self.config.get("exchange", {}).get("market_type", "futures")
        )

        try:
            # Main bot loop (placeholder for now)
            self.logger.info("Bot initialized successfully (Day 1 skeleton)")
            self.logger.info("Waiting for components to be implemented...")

            # Keep running until shutdown signal
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(
                "critical_error",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Gracefully shutdown the bot."""
        if not self.running:
            return

        self.running = False
        log_system_event(
            self.logger,
            EventType.SHUTDOWN,
            "Trading bot shutting down gracefully"
        )

        # Placeholder for cleanup tasks:
        # - Close all positions
        # - Cancel all open orders
        # - Disconnect WebSocket
        # - Save state to database

        self.logger.info("Shutdown complete")

    def handle_signal(self, signum, frame):
        """Handle shutdown signals (Ctrl+C)."""
        self.logger.warning("shutdown_signal_received", signal=signum)
        asyncio.create_task(self.shutdown())


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Adaptive Multi-System Grid Trading Bot"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.json",
        help="Path to configuration file"
    )
    args = parser.parse_args()

    # Create and start bot
    bot = TradingBot(args.config)

    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(bot.shutdown()))
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(bot.shutdown()))

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
