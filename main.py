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
    def __init__(self, config_path="config.yaml", auto_start=False):
        """Initialize the trader with configuration"""
        self.config = self.load_config(config_path)
        self.client = self.setup_client()

        # Trading parameters
        self.product_id = self.config["trading"]["product_id"]
        self.poll_interval = self.config["trading"]["poll_interval"]
        self.dry_run = self.config["trading"].get("dry_run", False)
        self.auto_start = auto_start

        # Trailing stop parameters
        trailing = self.config["trading"]["trailing_stop"]
        self.threshold_pct = float(trailing["threshold_percentage"])
        self.trail_pct = float(trailing["trail_percentage"])

        # State tracking (calculated from opening price)
        self.current_stop = None  # Will be set based on opening price
        self.highest_price_since_last_update = 0.0
        self.initial_price = None
        self.trailing_order_id = None
        self.quote_increment = None  # Will be fetched from product info

        print("=" * 80)
        print("COINBASE TRAILING STOP-LOSS TRADER")
        print("=" * 80)
        print(f"Product: {self.product_id}")
        print(f"Trailing Stop: Auto-calculated ({self.trail_pct}% below opening price)")
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
            response = self.client.get_product(self.product_id)
            price = float(response.price)

            # Get quote_increment if not already fetched
            if self.quote_increment is None and hasattr(response, "quote_increment"):
                self.quote_increment = float(response.quote_increment)
                print(f"✓ Detected price increment: ${self.quote_increment}")

            return price
        except Exception as e:
            print(f"ERROR: Failed to get price: {e}")
            return None

    def get_account_balance(self):
        """Get account balance for base currency"""
        try:
            response = self.client.get_accounts()
            base_currency = self.product_id.split("-")[0]

            for account in response.accounts:
                if account.currency == base_currency:
                    balance = float(account.available_balance["value"])
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

            # Round prices to the product's quote_increment
            # Default to 0.00001 if not yet fetched (5 decimal places for MON)
            increment = self.quote_increment if self.quote_increment else 0.00001

            # Round to nearest increment
            stop_price_rounded = round(stop_price / increment) * increment
            limit_price_rounded = round((stop_price * 0.995) / increment) * increment

            # Format to proper decimal places to avoid floating point errors
            decimal_places = (
                5 if increment == 0.00001 else (2 if increment == 0.01 else 4)
            )
            limit_price = f"{limit_price_rounded:.{decimal_places}f}"
            stop_price_str = f"{stop_price_rounded:.{decimal_places}f}"

            # Round base_size to the product's base_increment
            base_inc = getattr(self, "base_increment", None) or 1.0
            balance_rounded = round(balance / base_inc) * base_inc

            # Format base_size with appropriate decimal places
            if base_inc >= 1.0:
                base_size = str(int(balance_rounded))
            else:
                base_decimals = (
                    len(str(base_inc).rstrip("0").split(".")[-1])
                    if "." in str(base_inc)
                    else 0
                )
                base_size = f"{balance_rounded:.{base_decimals}f}"

            if self.dry_run:
                print(f"\n[DRY RUN] Would place {order_type} stop-loss order:")
                print(f"  Stop Price: ${stop_price_rounded:.2f}")
                print(f"  Limit Price: ${limit_price_rounded:.2f}")
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

            # Extract order_id from response
            # Convert to dict to access nested fields
            order_dict = order.to_dict() if hasattr(order, "to_dict") else order

            if order_dict.get("success") and "success_response" in order_dict:
                order_id = order_dict["success_response"].get("order_id")
                if order_id:
                    print(f"\n✓ Placed {order_type} stop-loss order on Coinbase")
                    print(f"  Order ID: {order_id}")
                    print(f"  Stop Price: ${stop_price_rounded:.2f}")
                    print(f"  Limit Price: ${limit_price_rounded:.2f}")
                    print(f"  Size: {base_size} {self.product_id.split('-')[0]}")
                    return order_id

            print(f"ERROR: Failed to place order")
            print(f"Response: {order_dict}")
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
                # Wait for balance to be released from hold
                time.sleep(2)

            print("Placing new trailing stop order...")

            # Retry up to 3 times if balance is still on hold
            max_retries = 3
            for attempt in range(max_retries):
                self.trailing_order_id = self.place_stop_loss_order(
                    self.current_stop, "trailing"
                )

                if self.trailing_order_id:
                    print(f"✓ New trailing stop active at ${self.current_stop:.4f}\n")
                    break
                elif attempt < max_retries - 1:
                    print(
                        f"⚠ Balance still on hold, retrying in 2 seconds... (attempt {attempt + 2}/{max_retries})"
                    )
                    time.sleep(2)
                else:
                    print(
                        "ERROR: Failed to place new trailing stop order after retries!\n"
                    )
                    print(
                        "⚠ Your position is NOT protected! Check Coinbase UI immediately!"
                    )

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
                response = self.client.get_product(self.product_id)
                price = float(response.price)

                # Get quote_increment for price precision
                if hasattr(response, "quote_increment"):
                    self.quote_increment = float(response.quote_increment)
                    print(f"✓ Detected price increment: ${self.quote_increment}")
                else:
                    self.quote_increment = 0.01  # Default to 2 decimals
                    print(f"⚠ Could not detect price increment, defaulting to $0.01")

                # If we got a price, the market is live!
                # Calculate trailing stop based on opening price
                calculated_trailing = price * (1 - self.trail_pct / 100)

                print("\n" + "=" * 80)
                print(f"🚀 {self.product_id} IS NOW LIVE!")
                print("=" * 80)
                print(f"Opening Price: ${price:.4f}")
                print(
                    f"Trailing Stop: ${calculated_trailing:.4f} ({self.trail_pct}% below opening)"
                )
                print(f"Threshold for Updates: {self.threshold_pct}%")
                print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE TRADING'}")
                print("=" * 80)

                # Ask for approval or auto-start
                if self.auto_start:
                    print("\n✓ Auto-start enabled, beginning trading immediately...\n")
                    self.current_stop = (
                        calculated_trailing  # Set the initial trailing stop
                    )
                    return price
                else:
                    print("\n⚠️  REVIEW THE SETTINGS ABOVE CAREFULLY ⚠️\n")
                    response = input("Type 'START' to begin trading: ").strip().upper()

                    if response == "START":
                        print("\n✓ Starting trading bot...\n")
                        self.current_stop = (
                            calculated_trailing  # Set the initial trailing stop
                        )
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

        # Place initial trailing stop order
        print("\n" + "=" * 80)
        print("PLACING TRAILING STOP-LOSS ORDER ON COINBASE")
        print("=" * 80)

        print(f"\nPlacing Trailing Stop-Loss at ${self.current_stop:.4f}...")
        self.trailing_order_id = self.place_stop_loss_order(
            self.current_stop, "trailing"
        )

        if not self.trailing_order_id:
            print("\nERROR: Failed to place trailing stop! Exiting for safety.")
            sys.exit(1)

        print("\n" + "=" * 80)
        print("✓ TRAILING STOP-LOSS ORDER ACTIVE ON COINBASE")
        print("=" * 80)
        print("\nYour stop-loss order is now visible in the Coinbase UI.")
        print("It will execute automatically even if this bot stops running.")
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
                print(
                    f"  Distance to Stop: ${current_price - self.current_stop:.4f} ({((current_price - self.current_stop) / current_price * 100):.2f}%)"
                )
                print(
                    f"  Highest Price Since Last Update: ${self.highest_price_since_last_update:.4f}"
                )

                # Calculate and show next update trigger
                next_update_price = self.highest_price_since_last_update * (
                    1 + self.threshold_pct / 100
                )
                pct_to_next_update = (
                    (next_update_price - current_price) / current_price
                ) * 100
                print(
                    f"  Next Update At: ${next_update_price:.5f} ({pct_to_next_update:+.2f}% from here)"
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
            print("\n⚠️  STOP-LOSS ORDER IS STILL ACTIVE ON COINBASE")
            print("Go to Coinbase UI to cancel it if you want to disable protection.\n")
        except Exception as e:
            print(f"\n\nERROR: Unexpected error in trading loop: {e}")
            import traceback

            traceback.print_exc()
            print("\n⚠️  STOP-LOSS ORDER MAY STILL BE ACTIVE ON COINBASE")
            print("Check Coinbase UI and cancel manually if needed.\n")


def main():
    parser = argparse.ArgumentParser(description="Coinbase Trailing Stop-Loss Trader")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Skip manual START confirmation and begin trading automatically when market opens",
    )
    args = parser.parse_args()

    trader = TrailingStopTrader(config_path=args.config, auto_start=args.auto_start)
    trader.run()


if __name__ == "__main__":
    main()
