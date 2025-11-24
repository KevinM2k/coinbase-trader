# Coinbase Trailing Stop-Loss Trader

A Python bot that monitors cryptocurrency prices on Coinbase and executes a trailing stop-loss strategy to protect your investment while maximizing gains.

## Features

- **Trailing Stop-Loss**: Automatically follows price increases and locks in profits
- **Emergency Stop-Loss**: Hard floor protection - sells immediately if price crashes
- **Pre-Market Waiting**: Polls for new trading pairs before they go live
- **User Approval**: Asks for confirmation before starting to trade
- **Dry Run Mode**: Test the bot without executing real orders
- **Real-Time Monitoring**: Displays current price, stops, and updates every poll
- **Detailed Logging**: See exactly what the bot is doing at all times

## How It Works

1. **Emergency Stop**: Set an absolute minimum price. If the coin drops to this level, sell everything immediately.

2. **Trailing Stop**: Follows the price upward. When the price increases by your threshold percentage (e.g., 5%), the stop-loss moves up to stay a certain percentage (e.g., 5%) below the current price.

3. **Example**:
   - You buy at $0.025
   - Initial trailing stop: $0.022 (12% below entry)
   - Emergency stop: $0.020 (20% below entry)
   - Price rises to $0.030 (+20%) → Trailing stop moves to $0.0285
   - Price drops to $0.0285 → Bot sells and locks in your profit
   - If price ever crashes to $0.020 → Bot sells immediately (emergency)

## Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd coinbase-trader
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your settings**
   ```bash
   cp config.yaml.example config.yaml
   ```
   
   Edit `config.yaml` and add:
   - Your Coinbase API credentials (key name and private key)
   - Trading pair (e.g., `MON-USDC`)
   - Emergency stop price
   - Initial trailing stop price
   - Threshold and trail percentages
   - Set `dry_run: true` for testing, `false` for live trading

## Configuration

### API Credentials

Get your Coinbase API keys from [Coinbase Developer Portal](https://portal.cdp.coinbase.com/):
- Create a new API key
- Copy the **key name** and **private key**
- Ensure it has trading permissions

### Trading Parameters

```yaml
trading:
  dry_run: true  # Set to false for live trading
  product_id: "MON-USDC"
  poll_interval: 5  # Check price every 5 seconds
  
  emergency_stop_price: 0.020  # Absolute floor - sell if price hits this
  
  trailing_stop:
    threshold_percentage: 3.0  # Price must increase 3% to update stop
    trail_percentage: 10.0  # Keep stop 10% below current price
```

**Note:** The `initial_stop_price` is no longer needed - it's auto-calculated as `opening_price * (1 - trail_percentage / 100)`.

### Example Configuration

If MON opens at $0.035:
- **Emergency Stop**: $0.020 (protects against crash)
- **Initial Trailing Stop**: Auto-calculated at $0.0315 (10% below $0.035)
- **Threshold**: 3% (updates stop when price gains 3%)
- **Trail**: 10% (keeps stop 10% below current price)

**Note:** The initial trailing stop is automatically calculated based on the opening price and your trail percentage. You don't need to set it manually!

## Usage

### Activate Virtual Environment
```bash
source venv/bin/activate
```

### Run the Bot
```bash
python main.py
```

You can also specify a custom config file:
```bash
python main.py --config config.test.yaml
```

### Pre-Market Launch

If you run the bot before a trading pair is available (e.g., before 2pm launch):
1. The bot will poll every X seconds waiting for the pair
2. Once available, it displays the initial price and your settings
3. You must type `START` to begin trading
4. The bot places stop-loss orders on Coinbase and begins monitoring

### How Stop-Loss Orders Work

**The bot places REAL stop-loss orders on Coinbase:**
- **Emergency Stop**: Placed once at startup, never changes
- **Trailing Stop**: Updated as price rises to lock in profits

**Key Benefits:**
- ✓ Orders are visible in Coinbase UI
- ✓ Orders execute even if bot crashes or internet drops
- ✓ No need to keep bot running 24/7 for protection
- ✓ Can manually manage orders in Coinbase if needed

**When price increases by your threshold (e.g., 3%):**
1. Bot cancels old trailing stop order
2. Bot places new trailing stop order at higher price
3. You're protected with updated stops on Coinbase

### During Trading

The bot displays:
```
[2025-11-24 14:05:23] Poll #42
  Current Price: $0.0285 (+14.00%)
  Trailing Stop: $0.0271
  Emergency Stop: $0.0200
  Distance to Trailing Stop: $0.0014 (4.91%)
  Highest Price Since Last Update: $0.0285
```

When the trailing stop updates, you'll see:
```
>>> STOP-LOSS UPDATE TRIGGERED! Price increased by 5.12%
>>> Old Stop: $0.0271 -> New Stop: $0.0285
>>> Stop raised by $0.0014

✓ New trailing stop active at $0.0285
```

### Stop the Bot

Press `Ctrl+C` to stop the bot safely. 

**Important:** Your stop-loss orders remain active on Coinbase even after the bot stops! You can:
- Let them stay active for continued protection
- Cancel them manually in Coinbase UI if you want to remove protection

## Dry Run vs Live Trading

### Dry Run Mode (`dry_run: true`)
- Monitors real prices
- Simulates placing orders (doesn't actually create them on Coinbase)
- Perfect for testing your configuration
- No risk to your funds
- No orders visible in Coinbase UI

### Live Trading Mode (`dry_run: false`)
- Places real stop-loss orders on Coinbase
- Orders are visible in Coinbase UI
- Orders will execute and sell your coins when triggered
- **USE WITH CAUTION**

**Always test with dry run first!**

## Safety Features

- **Approval Required**: Bot asks for confirmation before trading
- **Dry Run Mode**: Test without risk
- **Emergency Stop**: Absolute floor protection
- **Real-Time Display**: Always see what the bot is doing
- **Error Handling**: Continues on temporary errors, exits gracefully

## Important Notes

⚠️ **Risk Warning**: Cryptocurrency trading involves significant risk. This bot:
- Cannot guarantee profits
- May sell during temporary dips
- Requires stable internet connection
- Should be monitored during use

⚠️ **API Security**: 
- Never commit `config.yaml` (it's in `.gitignore`)
- Keep your API keys secure
- Use API keys with only necessary permissions

⚠️ **Testing**:
- Always test with `dry_run: true` first
- Start with small amounts
- Monitor the first few hours closely

## Troubleshooting

### "Module not found" errors
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### "Config file not found"
```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your settings
```

### "Product not supported"
The trading pair isn't available yet. The bot will wait and check periodically.

### API Authentication Errors
- Verify your API key name and private key
- Ensure the key has trading permissions
- Check if the key is active in Coinbase

## File Structure

```
coinbase-trader/
├── main.py                # Main bot script
├── config.yaml            # Your configuration (not committed)
├── config.yaml.example    # Example configuration
├── config.test.yaml       # Test configuration for BTC-USD
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── .gitignore            # Excludes config.yaml and venv
```

## License

MIT License - Use at your own risk

## Support

For issues or questions, open an issue on GitHub.

---

**Disclaimer**: This software is provided as-is. Trading cryptocurrencies carries risk. The authors are not responsible for any financial losses.
