#!/usr/bin/env python3
"""
Coinbase Trailing Stop-Loss Trader
Places and manages stop-loss orders on Coinbase exchange
"""

import argparse
import sys
import time
from datetime import datetime

import yaml
from coinbase.rest import RESTClient


class TrailingStopTrader:
    def __init__(self, config_path="config.yaml"):
        """Initialize the trader with configuration"""
        self.config = self.load_config(config_path)
        self.client = self.setup_client()

        # Trading parameters
        self.product_id = self.config["trading"]["product_id"]
        self.poll_interval = self.config["trading"]["poll_interval"]
        self.emergency_stop = float(self.config["trading"]["emergency_stop_price"])
        self.dry_run = self.config["trading"].get("dry_run", False)

        # Trailing stop parameters
        trailing = self.config["trading"]["trailing_stop"]
        self.current_stop = float(trailing["initial_stop_price"])
        self.threshold_pct = float(trailing["threshold_percentage"])
        self.trail_pct = float(trailing["trail_percentage"])

        # State tracking
        self.highest_price_since_last_update = 0.0
        self.initial_price = None
        self.emergency_order_id = None
        self.trailing_order_id = None

        print("=" * 80)
        print("COINBASE TRAILING STOP-LOSS TRADER")
        print("=" * 80)
        print(f"Product: {self.product_id}")
        print(f"Emergency Stop: ${self.emergency_stop:.4f}")
        print(f"Initial Trailing Stop: ${self.current_stop:.4f}")
        print(f"Threshold for Stop Update: {self.threshold_pct}%")
        print(f"Trail Distance: {self.trail_pct}%")
        print(f"Poll Interval: {self.poll_interval}s")
        print(
            f"Mode: {'DRY RUN (Simulated - No Real Orders)' if self.dry_run else 'LIVE TRADING (Real Orders)'}"
        )
        print("=" * 80)
        print()

    def load_config(self, config_path):
        """Load configuration from YAML file"""
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"ERROR: Config file '{config_path}' not found!")
            print(
                "Please copy config.yaml.example to config.yaml and add your credentials."
            )
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML in config file: {e}")
            sys.exit(1)

    def setup_client(self):
        """Setup Coinbase REST client"""
        api_config = self.config["api"]

        try:
            client = RESTClient(
                api_key=api_config["key_name"], api_secret=api_config["private_key"]
            )

            return client
        except Exception as e:
            print(f"ERROR: Failed to setup Coinbase client: {e}")
            sys.exit(1)

    def get_current_price(self):
        """Get current market price for the product"""
        try:
            ticker = self.client.get_product(self.product_id)
            price = float(ticker["price"])
            return price
        except Exception as e:
            print(f"ERROR: Failed to get price: {e}")
            return None

    def get_account_balance(self):
        """Get account balance for base currency"""
        try:
            accounts = self.client.get_accounts()
            base_currency = self.product_id.split("-")[0]

            for account in accounts.get("accounts", []):
                if account["currency"] == base_currency:
                    balance = float(account["available_balance"]["value"])
                    return balance

            return 0.0
        except Exception as e:
            print(f"ERROR: Failed to get account balance: {e}")
            return 0.0

    def cancel_order(self, order_id):
        """Cancel an existing order"""
        if self.dry_run:
            print(f"[DRY RUN] Would cancel order: {order_id}")
            return True

        try:
            result = self.client.cancel_orders([order_id])
            print(f"✓ Cancelled order: {order_id}")
            return True
        except Exception as e:
            print(f"ERROR: Failed to cancel order {order_id}: {e}")
            return False

    def place_stop_loss_order(self, stop_price, order_type="trailing"):
        """Place a stop-loss sell order on Coinbase"""
        try:
            balance = self.get_account_balance()

            if balance <= 0:
                base_currency = self.product_id.split("-")[0]
                print(f"ERROR: No {base_currency} balance available to protect")
                return None

            # Use stop price as both trigger and limit (small buffer for execution)
            limit_price = str(stop_price * 0.995)  # 0.5% below stop for safety
            stop_price_str = str(stop_price)
            base_size = str(balance)

            if self.dry_run:
                print(f"\n[DRY RUN] Would place {order_type} stop-loss order:")
                print(f"  Stop Price: ${stop_price:.4f}")
                print(f"  Limit Price: ${float(limit_price):.4f}")
                print(f"  Size: {base_size} {self.product_id.split('-')[0]}")
                return f"dry_run_{order_type}_{int(time.time())}"

            # Place stop-limit order (GTC - Good 'Til Canceled)
            order = self.client.stop_limit_order_gtc_sell(
                client_order_id=f"{order_type}_stop_{int(time.time())}",
                product_id=self.product_id,
                base_size=base_size,
                limit_price=limit_price,
                stop_price=stop_price_str,
                stop_direction="STOP_DIRECTION_STOP_DOWN",
            )

            order_id = order.get("success_response", {}).get("order_id")

            if order_id:
                print(f"\n✓ Placed {order_type} stop-loss order on Coinbase")
                print(f"  Order ID: {order_id}")
                print(f"  Stop Price: ${stop_price:.4f}")
                print(f"  Size: {base_size} {self.product_id.split('-')[0]}")
                return order_id
            else:
                print(f"ERROR: Failed to place order: {order}")
                return None

        except Exception as e:
            print(f"ERROR: Failed to place stop-loss order: {e}")
            import traceback

            traceback.print_exc()
            return None

    def update_trailing_stop(self, current_price):
        """Update the trailing stop-loss order based on price movement"""
        # Calculate new stop based on current price
        new_stop = current_price * (1 - self.trail_pct / 100)

        # Calculate how much price has increased since last stop update
        if self.highest_price_since_last_update > 0:
            price_increase_pct = (
                (current_price - self.highest_price_since_last_update)
                / self.highest_price_since_last_update
                * 100
            )
        else:
            price_increase_pct = 0

        # Update stop if price increased by threshold percentage
        if price_increase_pct >= self.threshold_pct:
            old_stop = self.current_stop
            self.current_stop = new_stop
            self.highest_price_since_last_update = current_price

            print(f"\n{'=' * 80}")
            print(
                f">>> STOP-LOSS UPDATE TRIGGERED! Price increased by {price_increase_pct:.2f}%"
            )
            print(
                f">>> Old Stop: ${old_stop:.4f} -> New Stop: ${self.current_stop:.4f}"
            )
            print(f">>> Stop raised by ${self.current_stop - old_stop:.4f}")
            print(f"{'=' * 80}\n")

            # Cancel old trailing stop and place new one
            if self.trailing_order_id:
                print("Canceling old trailing stop order...")
                self.cancel_order(self.trailing_order_id)

            print("Placing new trailing stop order...")
            self.trailing_order_id = self.place_stop_loss_order(
                self.current_stop, "trailing"
            )

            if self.trailing_order_id:
                print(f"✓ New trailing stop active at ${self.current_stop:.4f}\n")
            else:
                print("ERROR: Failed to place new trailing stop order!\n")

        # Track highest price
        if current_price > self.highest_price_since_last_update:
            self.highest_price_since_last_update = current_price

    def format_timestamp(self):
        """Get formatted timestamp"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def wait_for_market(self):
        """Wait for the trading pair to become available"""
        print(
            f"[{self.format_timestamp()}] Waiting for {self.product_id} to become available..."
        )
        print(f"Checking every {self.poll_interval} seconds...\n")

        while True:
            try:
                ticker = self.client.get_product(self.product_id)
                price = float(ticker["price"])

                # If we got a price, the market is live!
                print("\n" + "=" * 80)
                print(f"🚀 {self.product_id} IS NOW LIVE!")
                print("=" * 80)
                print(f"Initial Price: ${price:.4f}")
                print(f"Emergency Stop: ${self.emergency_stop:.4f}")
                print(f"Initial Trailing Stop: ${self.current_stop:.4f}")
                print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE TRADING'}")
                print("=" * 80)
                print("\n⚠️  REVIEW THE SETTINGS ABOVE CAREFULLY ⚠️\n")

                # Ask for approval
                response = input("Type 'START' to begin trading: ").strip().upper()

                if response == "START":
                    print("\n✓ Starting trading bot...\n")
                    return price
                else:
                    print("\nTrading cancelled by user.")
                    sys.exit(0)

            except Exception as e:
                # Market not available yet, keep waiting
                print(
                    f"[{self.format_timestamp()}] {self.product_id} not available yet, waiting..."
                )
                time.sleep(self.poll_interval)

    def run(self):
        """Main trading loop"""
        print(f"[{self.format_timestamp()}] Starting trader...\n")

        # Wait for market to open and get user approval
        initial_price = self.wait_for_market()
        self.initial_price = initial_price
        self.highest_price_since_last_update = initial_price

        # Place initial stop-loss orders
        print("\n" + "=" * 80)
        print("PLACING INITIAL STOP-LOSS ORDERS ON COINBASE")
        print("=" * 80)

        # Place emergency stop
        print(f"\n1. Placing Emergency Stop-Loss at ${self.emergency_stop:.4f}...")
        self.emergency_order_id = self.place_stop_loss_order(
            self.emergency_stop, "emergency"
        )

        if not self.emergency_order_id:
            print("\nERROR: Failed to place emergency stop! Exiting for safety.")
            sys.exit(1)

        # Place initial trailing stop
        print(f"\n2. Placing Initial Trailing Stop-Loss at ${self.current_stop:.4f}...")
        self.trailing_order_id = self.place_stop_loss_order(
            self.current_stop, "trailing"
        )

        if not self.trailing_order_id:
            print("\nERROR: Failed to place trailing stop! Exiting for safety.")
            if self.emergency_order_id:
                print("Cleaning up emergency stop...")
                self.cancel_order(self.emergency_order_id)
            sys.exit(1)

        print("\n" + "=" * 80)
        print("✓ ALL STOP-LOSS ORDERS ACTIVE ON COINBASE")
        print("=" * 80)
        print("\nYour stop-loss orders are now visible in the Coinbase UI.")
        print("They will execute automatically even if this bot stops running.")
        print("\nMonitoring price to update trailing stop as market rises...\n")

        try:
            iteration = 0
            while True:
                iteration += 1
                current_price = self.get_current_price()

                if current_price is None:
                    print(
                        f"[{self.format_timestamp()}] Skipping iteration due to price fetch error"
                    )
                    time.sleep(self.poll_interval)
                    continue

                # Calculate price changes
                price_change = current_price - self.initial_price
                price_change_pct = price_change / self.initial_price * 100

                # Print current status
                print(f"[{self.format_timestamp()}] Poll #{iteration}")
                print(
                    f"  Current Price: ${current_price:.4f} ({price_change_pct:+.2f}%)"
                )
                print(f"  Trailing Stop: ${self.current_stop:.4f}")
                print(f"  Emergency Stop: ${self.emergency_stop:.4f}")
                print(
                    f"  Distance to Trailing Stop: ${current_price - self.current_stop:.4f} ({((current_price - self.current_stop) / current_price * 100):.2f}%)"
                )
                print(
                    f"  Highest Price Since Last Update: ${self.highest_price_since_last_update:.4f}"
                )

                # Check if stops were triggered (orders would be filled/canceled)
                # In a production system, you'd check order status here

                # Update trailing stop if price increased enough
                self.update_trailing_stop(current_price)

                print()  # Blank line for readability

                # Wait before next poll
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n\nTrading stopped by user (Ctrl+C)")
            print(f"Final Price: ${current_price:.4f}")
            print(f"Final Trailing Stop: ${self.current_stop:.4f}")
            print("\n⚠️  STOP-LOSS ORDERS ARE STILL ACTIVE ON COINBASE")
            print(
                "Go to Coinbase UI to cancel them if you want to disable protection.\n"
            )
        except Exception as e:
            print(f"\n\nERROR: Unexpected error in trading loop: {e}")
            import traceback

            traceback.print_exc()
            print("\n⚠️  STOP-LOSS ORDERS MAY STILL BE ACTIVE ON COINBASE")
            print("Check Coinbase UI and cancel manually if needed.\n")


def main():
    parser = argparse.ArgumentParser(description="Coinbase Trailing Stop-Loss Trader")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    args = parser.parse_args()

    trader = TrailingStopTrader(config_path=args.config)
    trader.run()


if __name__ == "__main__":
    main()
