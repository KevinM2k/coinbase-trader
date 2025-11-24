#!/usr/bin/env python3
"""
Coinbase Trailing Stop-Loss Trader
Monitors a trading pair and executes trailing stop-loss strategy
"""

import time
import yaml
import sys
from datetime import datetime
from coinbase.rest import RESTClient

class TrailingStopTrader:
    def __init__(self, config_path='config.yaml'):
        """Initialize the trader with configuration"""
        self.config = self.load_config(config_path)
        self.client = self.setup_client()

        # Trading parameters
        self.product_id = self.config['trading']['product_id']
        self.poll_interval = self.config['trading']['poll_interval']
        self.emergency_stop = float(self.config['trading']['emergency_stop_price'])

        # Trailing stop parameters
        trailing = self.config['trading']['trailing_stop']
        self.current_stop = float(trailing['initial_stop_price'])
        self.threshold_pct = float(trailing['threshold_percentage'])
        self.trail_pct = float(trailing['trail_percentage'])

        # State tracking
        self.highest_price_since_last_update = 0.0
        self.initial_price = None

        print("=" * 80)
        print("COINBASE TRAILING STOP-LOSS TRADER")
        print("=" * 80)
        print(f"Product: {self.product_id}")
        print(f"Emergency Stop: ${self.emergency_stop:.4f}")
        print(f"Initial Trailing Stop: ${self.current_stop:.4f}")
        print(f"Threshold for Stop Update: {self.threshold_pct}%")
        print(f"Trail Distance: {self.trail_pct}%")
        print(f"Poll Interval: {self.poll_interval}s")
        print(f"Mode: {'SANDBOX (Testing)' if self.config['api']['use_sandbox'] else 'PRODUCTION (Live Trading)'}")
        print("=" * 80)
        print()

    def load_config(self, config_path):
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"ERROR: Config file '{config_path}' not found!")
            print("Please copy config.yaml.example to config.yaml and add your credentials.")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML in config file: {e}")
            sys.exit(1)

    def setup_client(self):
        """Setup Coinbase REST client"""
        api_config = self.config['api']

        try:
            # Determine API URL based on sandbox setting
            if api_config['use_sandbox']:
                api_url = "https://api-public.sandbox.exchange.coinbase.com"
            else:
                api_url = "https://api.coinbase.com"

            client = RESTClient(
                api_key=api_config['key_name'],
                api_secret=api_config['private_key'],
                base_url=api_url
            )

            return client
        except Exception as e:
            print(f"ERROR: Failed to setup Coinbase client: {e}")
            sys.exit(1)

    def get_current_price(self):
        """Get current market price for the product"""
        try:
            ticker = self.client.get_product(self.product_id)
            price = float(ticker['price'])
            return price
        except Exception as e:
            print(f"ERROR: Failed to get price: {e}")
            return None

    def get_account_balance(self):
        """Get account balances"""
        try:
            accounts = self.client.get_accounts()
            return accounts
        except Exception as e:
            print(f"ERROR: Failed to get account balance: {e}")
            return None

    def execute_market_sell(self, reason):
        """Execute market sell order"""
        print("\n" + "!" * 80)
        print(f"EXECUTING MARKET SELL: {reason}")
        print("!" * 80)

        try:
            # Get available balance to sell
            accounts = self.get_account_balance()
            if not accounts:
                print("ERROR: Could not retrieve account balance")
                return False

            # Find the base currency balance (e.g., MON from MON-USDC)
            base_currency = self.product_id.split('-')[0]
            balance = 0

            for account in accounts.get('accounts', []):
                if account['currency'] == base_currency:
                    balance = float(account['available_balance']['value'])
                    break

            if balance <= 0:
                print(f"No {base_currency} balance to sell")
                return False

            print(f"Selling {balance} {base_currency}")

            # Place market sell order
            order = self.client.market_order_sell(
                client_order_id=f"stop-loss-{int(time.time())}",
                product_id=self.product_id,
                base_size=str(balance)
            )

            print(f"Order placed: {order}")
            print("!" * 80)
            return True

        except Exception as e:
            print(f"ERROR: Failed to execute sell order: {e}")
            return False

    def update_trailing_stop(self, current_price):
        """Update the trailing stop-loss based on price movement"""
        # Calculate new stop based on current price
        new_stop = current_price * (1 - self.trail_pct / 100)

        # Calculate how much price has increased since last stop update
        price_increase_pct = ((current_price - self.highest_price_since_last_update) /
                              self.highest_price_since_last_update * 100)

        # Update stop if price increased by threshold percentage
        if price_increase_pct >= self.threshold_pct:
            old_stop = self.current_stop
            self.current_stop = new_stop
            self.highest_price_since_last_update = current_price

            print(f"\n>>> STOP-LOSS UPDATED! Price increased by {price_increase_pct:.2f}%")
            print(f">>> Old Stop: ${old_stop:.4f} -> New Stop: ${self.current_stop:.4f}")
            print(f">>> Stop raised by ${self.current_stop - old_stop:.4f}\n")

        # Track highest price
        if current_price > self.highest_price_since_last_update:
            self.highest_price_since_last_update = current_price

    def format_timestamp(self):
        """Get formatted timestamp"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def run(self):
        """Main trading loop"""
        print(f"[{self.format_timestamp()}] Starting trader...\n")

        try:
            iteration = 0
            while True:
                iteration += 1
                current_price = self.get_current_price()

                if current_price is None:
                    print(f"[{self.format_timestamp()}] Skipping iteration due to price fetch error")
                    time.sleep(self.poll_interval)
                    continue

                # Set initial price and highest price tracking
                if self.initial_price is None:
                    self.initial_price = current_price
                    self.highest_price_since_last_update = current_price

                # Calculate price changes
                price_change = current_price - self.initial_price
                price_change_pct = (price_change / self.initial_price * 100)

                # Print current status
                print(f"[{self.format_timestamp()}] Poll #{iteration}")
                print(f"  Current Price: ${current_price:.4f} ({price_change_pct:+.2f}%)")
                print(f"  Trailing Stop: ${self.current_stop:.4f}")
                print(f"  Emergency Stop: ${self.emergency_stop:.4f}")
                print(f"  Distance to Trailing Stop: ${current_price - self.current_stop:.4f} ({((current_price - self.current_stop) / current_price * 100):.2f}%)")
                print(f"  Highest Price Since Last Update: ${self.highest_price_since_last_update:.4f}")

                # Check emergency stop-loss
                if current_price <= self.emergency_stop:
                    print(f"\n*** EMERGENCY STOP TRIGGERED! Price ${current_price:.4f} <= ${self.emergency_stop:.4f} ***")
                    if self.execute_market_sell("Emergency stop-loss triggered"):
                        print("\nTrading stopped. Emergency exit completed.")
                        break

                # Check trailing stop-loss
                if current_price <= self.current_stop:
                    print(f"\n*** TRAILING STOP TRIGGERED! Price ${current_price:.4f} <= ${self.current_stop:.4f} ***")
                    if self.execute_market_sell("Trailing stop-loss triggered"):
                        print("\nTrading stopped. Trailing stop exit completed.")
                        break

                # Update trailing stop if price increased enough
                self.update_trailing_stop(current_price)

                print()  # Blank line for readability

                # Wait before next poll
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n\nTrading stopped by user (Ctrl+C)")
            print(f"Final Price: ${current_price:.4f}")
            print(f"Final Trailing Stop: ${self.current_stop:.4f}")
        except Exception as e:
            print(f"\n\nERROR: Unexpected error in trading loop: {e}")
            import traceback
            traceback.print_exc()

def main():
    trader = TrailingStopTrader()
    trader.run()

if __name__ == "__main__":
    main()
