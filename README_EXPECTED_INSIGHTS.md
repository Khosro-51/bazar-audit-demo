# Bazar Audit Test Datasets

These three CSV files are synthetic but realistic test datasets for Bazar Audit v1.

## Dataset 1: bazar_sample_good_trader.csv
Expected insight profile:
- Sample size guard: PASS
- Session Toxicity: weak or none
- Trade Count Cliff: mild or none
- Post-Loss Performance Decay: low
- Drawdown Recovery Behavior: low
- Payoff Imbalance: generally healthy

## Dataset 2: bazar_sample_average_trader.csv
Expected insight profile:
- Sample size guard: PASS
- Session Toxicity: Asia likely weak/toxic
- Trade Count Cliff: mild after 3rd or 4th trade
- Symbol Edge Test: GBPJPY likely weak
- Payoff Imbalance: moderate issue

## Dataset 3: bazar_sample_behavior_problem_trader.csv
Expected insight profile:
- Sample size guard: PASS
- Session Toxicity: Asia toxic
- Trade Count Cliff: strong after 3rd trade
- Post-Loss Performance Decay: strong
- Drawdown Recovery Behavior: strong
- Payoff Imbalance: strong
- Time In Trade asymmetry: likely visible

## Important MVP R Policy
Bazar Audit should use three-tier R handling:
1. pnl_R exists -> use reported R, but validate against pnl / initial_risk_amount when possible.
2. pnl_R missing but initial_sl / entry / size / risk metadata exists -> compute R.
3. neither exists -> run PnL-only analysis and disable R-based insights with a clear limitation warning.
