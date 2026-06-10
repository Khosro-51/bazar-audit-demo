# Bazar Audit Engine v1

**Bazar does not provide buy/sell signals or financial advice.**  
**It analyzes trading performance, risk behavior, and strategy structure.**

## What is Bazar?
Bazar is an advanced trading audit engine that goes beyond traditional statistics. Instead of just showing you a generic "win rate" or "profit factor", Bazar digs into the exact structural and behavioral reasons why you are making or losing money. It reads your trading history and extracts actionable insights, helping you understand the real drivers of your performance.

## What it is NOT
- It is **not** a signal provider.
- It is **not** a trading bot.
- It is **not** a simple statistical dashboard.

## Why is it different?
Traditional platforms show you what happened. Bazar tells you *why* it happened and *what to do about it*.
For example, instead of just showing a low win rate, Bazar might tell you:
> "Your win rate drops sharply after the 3rd trade of the day. Stop trading after your 2nd trade."

## What does the Demo show?
The Public Demo runs in a read-only state. You can analyze three synthesized profiles to see how Bazar thinks:
1. **Good Trader:** A stable trading profile. Bazar verifies the health and recommends collecting more data.
2. **Average Trader:** A trader with typical behavioral leaks, such as session toxicity and fast re-entry after losses.
3. **Problem Trader:** A trader whose core strategy is structurally below breakeven, identifying that behavior optimization cannot fix a mathematically flawed edge.

## How to Run

### Local Execution
1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the Streamlit application:
   ```bash
   streamlit run streamlit_app.py
   ```
4. Open the provided local URL (usually http://localhost:8501) in your browser.

### Streamlit Community Cloud
You can deploy this repository directly on Streamlit Community Cloud. Select `streamlit_app.py` as your entrypoint. The `requirements.txt` will automatically install dependencies.

## Repository Structure
```
bazar-audit-demo/
│
├── streamlit_app.py         # The web UI and entry point
├── bazar_schema.py          # Data models and insight definitions
├── bazar_metrics.py         # Core statistical calculations
├── bazar_insights.py        # Library of analytical functions
├── bazar_audit_engine.py    # The main processing engine
├── requirements.txt         # Minimal dependencies (streamlit, pandas, numpy)
├── README.md                # This file
│
├── sample_data/             # Frozen datasets for the Public Demo
│   ├── bazar_sample_good_trader.csv
│   ├── bazar_sample_average_trader.csv
│   └── bazar_sample_behavior_problem_trader.csv
│
└── tests/                   # Acceptance criteria tests
    └── test_all.py
```
