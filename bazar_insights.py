"""
Bazar Audit — Insight Library
هر insight یک تابع مستقل است که Insight | None برمی‌گرداند.
"""
import pandas as pd
import numpy as np
from bazar_schema import Insight, Severity, Confidence


# ── helpers ──────────────────────────────────────────────────────────────────

def _sev(s: str) -> Severity:
    return Severity[s]

def _conf(s: str) -> Confidence:
    return Confidence[s]


# ── 0. SAMPLE SIZE GUARD ─────────────────────────────────────────────────────

def insight_sample_size(df: pd.DataFrame):
    n = len(df)
    if n < 30:
        return False, Insight(
            insight_id="SAMPLE_SIZE_INSUFFICIENT",
            severity=_sev("HIGH"), confidence=_conf("HIGH"), sample_size=n,
            metric_snapshot={"trades": n, "minimum_required": 30},
            message="Not enough trades for reliable analysis.",
            recommended_action="Continue logging trades. Minimum 30 required; 100+ recommended.",
            title_fa="داده کافی نیست",
            body_fa=f"فقط {n} معامله آپلود شده. برای تحلیل پایه حداقل ۳۰ معامله لازم است.",
        )
    if n < 100:
        return True, Insight(
            insight_id="SAMPLE_SIZE_LIMITED",
            severity=_sev("LOW"), confidence=_conf("MEDIUM"), sample_size=n,
            metric_snapshot={"trades": n, "recommended": 100},
            message=f"Analysis is possible but limited with {n} trades.",
            recommended_action="Continue logging to reach 100+ trades for deeper insights.",
            title_fa="داده محدود",
            body_fa=f"{n} معامله موجود است. برای نتایج قابل اطمینان ۱۰۰+ معامله توصیه می‌شود.",
        )
    return True, None


# ── 1. SYSTEMIC UNDERPERFORMANCE ─────────────────────────────────────────────

def insight_systemic(df: pd.DataFrame, metrics: dict):
    n   = metrics["n"]
    wr  = metrics["win_rate"]
    pf  = metrics["profit_factor"]
    bwr = metrics["breakeven_wr"]
    exp_R = metrics.get("expectancy_R")

    if n < 30:
        return None
    gap = bwr - wr
    if gap < 0.15 and pf >= 0.50:
        return None

    gap = round((bwr - wr) * 100, 1)
    conf = _conf("HIGH") if n >= 80 else _conf("MEDIUM")

    exp_line = ""
    if exp_R is not None:
        exp_line = f", expectancy {exp_R:.2f}R"

    body_fa = (
        f"Win Rate شما {round(wr*100,1)}٪ است. "
        f"برای breakeven با این میانگین سود/ضرر، حداقل {round(bwr*100,1)}٪ لازم است "
        f"({gap} امتیاز فاصله). Profit Factor: {pf}. "
        f"این یک مشکل سیستمیک در استراتژی است، نه صرفاً رفتار احساسی."
    )

    return Insight(
        insight_id="SYSTEMIC_UNDERPERFORMANCE",
        severity=_sev("HIGH"), confidence=conf, sample_size=n,
        metric_snapshot={
            "win_rate": wr,
            "breakeven_win_rate": round(bwr, 4),
            "profit_factor": pf,
            "expectancy_R": exp_R,
            "gap_to_breakeven_pct": gap,
        },
        message="Current strategy performance is structurally below breakeven.",
        recommended_action="Review core entry/exit logic before optimizing behavioral rules.",
        title_fa="مشکل سیستمیک در استراتژی",
        body_fa=body_fa,
    )


# ── 2. SESSION TOXICITY ───────────────────────────────────────────────────────

def insight_session_toxicity(df: pd.DataFrame, metrics: dict):
    results = []
    for ses, grp in df.groupby('session'):
        if len(grp) < 5:
            continue
        wr      = (grp['pnl'] > 0).mean()
        avg_pnl = grp['pnl'].mean()
        results.append({"session": ses, "trades": len(grp),
                         "win_rate": round(wr, 4), "avg_pnl": round(avg_pnl, 2)})

    toxic = [r for r in results if r["avg_pnl"] < 0]
    if not toxic:
        return None

    worst = min(toxic, key=lambda x: x["avg_pnl"])
    ses_pnl   = df[df['session'] == worst['session']]['pnl'].sum()
    total_pnl = df['pnl'].sum()
    impact_pct = round(abs(ses_pnl / total_pnl * 100), 1) if total_pnl != 0 else 0

    sev  = _sev("HIGH") if worst["avg_pnl"] < -60 else _sev("MEDIUM")
    conf = _conf("HIGH") if worst["trades"] >= 15 else _conf("MEDIUM")

    body_fa = (
        f"در سشن {worst['session']} با {worst['trades']} معامله، "
        f"Win Rate شما {round(worst['win_rate']*100,1)}٪ و "
        f"میانگین PnL {worst['avg_pnl']:.2f}$ است. "
        f"حذف این سشن می‌تواند نتیجه کلی را تا {impact_pct}٪ بهبود دهد."
    )

    return Insight(
        insight_id="SESSION_TOXICITY",
        severity=sev, confidence=conf, sample_size=worst["trades"],
        metric_snapshot={"worst_session": worst, "all_sessions": results, "impact_pct": impact_pct},
        message=f"Session '{worst['session']}' is consistently unprofitable for you.",
        recommended_action=f"Avoid or reduce trading during '{worst['session']}' session.",
        title_fa=f"سشن {worst['session']} برای شما مضر است",
        body_fa=body_fa,
    )


# ── 3. TRADE COUNT CLIFF ──────────────────────────────────────────────────────

def insight_trade_count_cliff(df: pd.DataFrame, metrics: dict):
    col = 'trade_index_in_day'
    if col not in df.columns:
        df = df.copy()
        df['_date'] = df['open_time'].dt.date
        df[col] = df.groupby('_date').cumcount() + 1

    results = []
    for idx in sorted(df[col].unique()):
        grp = df[df[col] == idx]
        if len(grp) < 5:
            continue
        results.append({"index": int(idx), "win_rate": (grp['pnl'] > 0).mean(), "n": len(grp)})

    if len(results) < 3:
        return None

    cliff = None
    bwr = awr = 0.0
    for i in range(1, len(results)):
        before = np.mean([r["win_rate"] for r in results[:i]])
        after  = np.mean([r["win_rate"] for r in results[i:]])
        if before - after > 0.15:
            cliff = results[i]["index"]
            bwr, awr = before, after
            break

    if cliff is None:
        return None

    drop = round((bwr - awr) * 100, 1)
    conf = _conf("HIGH") if drop >= 25 else _conf("MEDIUM")

    body_fa = (
        f"قبل از معامله {cliff}ام روز، Win Rate شما {round(bwr*100,1)}٪ است. "
        f"از معامله {cliff}ام به بعد به {round(awr*100,1)}٪ می‌افتد ({drop} امتیاز). "
        f"توقف بعد از معامله {cliff-1}ام در هر روز توصیه می‌شود."
    )

    return Insight(
        insight_id="TRADE_COUNT_CLIFF",
        severity=_sev("HIGH") if drop >= 25 else _sev("MEDIUM"),
        confidence=conf, sample_size=len(df),
        metric_snapshot={"cliff_at_trade": cliff, "before_wr": round(bwr,4), "after_wr": round(awr,4), "drop_pct": drop},
        message=f"Win rate drops sharply after trade #{cliff} each day.",
        recommended_action=f"Set a hard stop after {cliff-1} trades per day.",
        title_fa=f"بعد از معامله {cliff}ام کیفیت افت می‌کند",
        body_fa=body_fa,
    )


# ── 4. POST-LOSS DECAY v2 ─────────────────────────────────────────────────────

def insight_post_loss_decay(df: pd.DataFrame, metrics: dict):
    if len(df) < 30:
        return None

    baseline_wr  = metrics["win_rate"]
    baseline_exp = metrics["expectancy_dollar"]

    post_loss_idx, fast_idx = [], []
    for i in range(1, len(df)):
        if df.iloc[i-1]['pnl'] < 0:
            post_loss_idx.append(i)
            gap = (df.iloc[i]['open_time'] - df.iloc[i-1]['close_time']).total_seconds() / 60
            if gap <= 60:
                fast_idx.append(i)

    if len(post_loss_idx) < 15:
        return None

    pl   = df.iloc[post_loss_idx]
    pl_wr = (pl['pnl'] > 0).mean()
    wr_drop = baseline_wr - pl_wr

    has_fast = len(fast_idx) >= 5
    fast_wr = fast_drop = None
    if has_fast:
        ft = df.iloc[fast_idx]
        fast_wr   = (ft['pnl'] > 0).mean()
        fast_drop = baseline_wr - fast_wr

    # حالت ۱: baseline خیلی پایین → مشکل systemic است، post-loss معنادار نیست
    if baseline_wr < 0.25:
        if not has_fast or fast_drop is None or fast_drop < 0.05:
            return None
        body_fa = (
            f"Win Rate کلی شما {round(baseline_wr*100,1)}٪ است. "
            f"در {len(fast_idx)} معامله ظرف ۶۰ دقیقه بعد از ضرر، "
            f"به {round(fast_wr*100,1)}٪ می‌افتد. "  # type: ignore
            f"مشکل اصلی سیستمیک است، اما ورود سریع آن را تشدید می‌کند."
        )
        return Insight(
            insight_id="POST_LOSS_FAST_REENTRY",
            severity=_sev("MEDIUM"), confidence=_conf("MEDIUM"), sample_size=len(fast_idx),
            metric_snapshot={"baseline_wr": round(baseline_wr,4), "fast_wr": round(fast_wr,4),  # type: ignore
                             "n_fast": len(fast_idx)},
            message="Fast re-entry after losses worsens an already weak performance.",
            recommended_action="Implement a mandatory cooldown period after each loss.",
            title_fa="ورود سریع بعد از ضرر وضع را بدتر می‌کند",
            body_fa=body_fa,
        )

    # حالت ۲: wr_drop کم است اما fast_drop بالاست
    if wr_drop < 0.10 and has_fast and fast_drop is not None and fast_drop >= 0.15:
        sev = _sev("HIGH") if fast_drop >= 0.25 else _sev("MEDIUM")
        body_fa = (
            f"Win Rate کلی شما {round(baseline_wr*100,1)}٪ است. "
            f"در {len(fast_idx)} معامله ظرف ۶۰ دقیقه بعد از ضرر، "
            f"به {round(fast_wr*100,1)}٪ می‌افتد. "  # type: ignore
            f"مشکل شما revenge speed است، نه decay کلی."
        )
        return Insight(
            insight_id="POST_LOSS_FAST_REENTRY",
            severity=sev, confidence=_conf("MEDIUM"), sample_size=len(fast_idx),
            metric_snapshot={"baseline_wr": round(baseline_wr,4), "fast_wr": round(fast_wr,4),  # type: ignore
                             "fast_drop_pct": round(fast_drop*100,1), "n_fast": len(fast_idx)},
            message="Trades entered within 60 min of a loss have significantly lower win rate.",
            recommended_action="Add a 60-minute cooldown rule after any losing trade.",
            title_fa="ورود سریع بعد از ضرر عملکرد را خراب می‌کند",
            body_fa=body_fa,
        )

    # حالت ۳: decay کلی واقعی
    if wr_drop < 0.10:
        return None

    sev = _sev("HIGH") if wr_drop >= 0.20 else _sev("MEDIUM")
    if has_fast and fast_drop is not None and fast_drop >= 0.25:
        sev = _sev("HIGH")

    fast_line = ""
    if has_fast and fast_wr is not None:
        fast_is_primary = fast_drop is not None and fast_drop > wr_drop * 1.3
        if fast_is_primary:
            fast_line = (f" معاملات ظرف ۶۰ دقیقه ({len(fast_idx)} مورد) "
                         f"با WR {round(fast_wr*100,1)}٪ عامل اصلی هستند.")
        else:
            fast_line = (f" حتی با فاصله بیشتر هم decay ادامه دارد. "
                         f"fast re-entry ({len(fast_idx)} مورد) مشکل را تشدید می‌کند.")

    body_fa = (
        f"در {len(post_loss_idx)} معامله بعد از ضرر، Win Rate از "
        f"{round(baseline_wr*100,1)}٪ به {round(pl_wr*100,1)}٪ افت می‌کند "
        f"({round(wr_drop*100,1)} امتیاز).{fast_line}"
    )

    return Insight(
        insight_id="POST_LOSS_DECAY",
        severity=sev, confidence=_conf("HIGH") if len(post_loss_idx) >= 30 else _conf("MEDIUM"),
        sample_size=len(post_loss_idx),
        metric_snapshot={"baseline_wr": round(baseline_wr,4), "post_loss_wr": round(pl_wr,4),
                         "wr_drop_pct": round(wr_drop*100,1), "n_post_loss": len(post_loss_idx),
                         "n_fast_reentry": len(fast_idx),
                         "fast_wr": round(fast_wr*100,1) if fast_wr is not None else None},
        message=f"Win rate drops {round(wr_drop*100,1)}pp after losing trades.",
        recommended_action="Implement a structured review process before re-entering after a loss.",
        title_fa="کیفیت معاملات بعد از ضرر افت می‌کند",
        body_fa=body_fa,
    )


# ── 5. DRAWDOWN RECOVERY ──────────────────────────────────────────────────────

def insight_drawdown_recovery(df: pd.DataFrame, metrics: dict):
    if 'balance_after' not in df.columns or 'lot_or_size' not in df.columns or len(df) < 20:
        return None

    balance = df['balance_after'].values
    peak = balance[0]
    in_dd = False
    normal_s, dd_s = [], []

    for i, b in enumerate(balance):
        dd_pct = (peak - b) / peak * 100 if peak > 0 else 0
        lot    = df.iloc[i]['lot_or_size']
        if dd_pct > 3:
            in_dd = True; dd_s.append(lot)
        else:
            if not in_dd: normal_s.append(lot)
            peak = max(peak, b); in_dd = False

    if len(dd_s) < 5 or len(normal_s) < 5:
        return None

    ratio = np.mean(dd_s) / np.mean(normal_s) if np.mean(normal_s) > 0 else 1.0
    if ratio < 1.2:
        return None

    sev = _sev("HIGH") if ratio >= 1.5 else _sev("MEDIUM")

    body_fa = (
        f"در دوره‌های drawdown بیش از ۳٪، میانگین سایز معاملات شما "
        f"{ratio:.1f}x بزرگتر از حالت عادی است. "
        f"این الگو معمولاً drawdown را عمیق‌تر می‌کند."
    )

    return Insight(
        insight_id="DRAWDOWN_RECOVERY_SIZING",
        severity=sev, confidence=_conf("MEDIUM"), sample_size=len(dd_s),
        metric_snapshot={"size_ratio": round(ratio, 2),
                         "avg_normal_lot": round(float(np.mean(normal_s)), 3),
                         "avg_dd_lot": round(float(np.mean(dd_s)), 3)},
        message=f"Position size increases {ratio:.1f}x during drawdown periods.",
        recommended_action="Fix position size to a consistent risk % regardless of account state.",
        title_fa="در drawdown سایز را بزرگ می‌کنید",
        body_fa=body_fa,
    )


# ── 6. PAYOFF IMBALANCE ───────────────────────────────────────────────────────

def insight_payoff_imbalance(df: pd.DataFrame, metrics: dict):
    # v1.1: اگر متریک‌های R موجود باشند (full یا computed) از R استفاده کن
    if metrics.get("avg_win_R") is not None:
        avg_w = metrics["avg_win_R"]  or 0
        avg_l = abs(metrics["avg_loss_R"] or 0)
        unit  = "R"
    else:
        avg_w = metrics["avg_win_dollar"]
        avg_l = abs(metrics["avg_loss_dollar"])
        unit  = "$"

    if avg_l == 0: return None
    ratio = avg_w / avg_l
    if ratio >= 0.90: return None

    wins   = df[df['pnl'] > 0]
    losses = df[df['pnl'] < 0]
    if len(wins) < 5 or len(losses) < 5: return None

    sev = _sev("HIGH") if ratio < 0.60 else _sev("MEDIUM")

    body_fa = (
        f"میانگین سود شما {avg_w:.2f}{unit} و میانگین ضرر {avg_l:.2f}{unit} است. "
        f"نسبت فعلی {ratio:.2f} است. "
        f"احتمالاً Winner ها را زود می‌بندید یا Loser ها را نگه می‌دارید."
    )

    return Insight(
        insight_id="PAYOFF_IMBALANCE",
        severity=sev, confidence=_conf("HIGH"), sample_size=len(df),
        metric_snapshot={"avg_win": round(avg_w,3), "avg_loss": round(avg_l,3),
                         "payoff_ratio": round(ratio,3), "unit": unit},
        message=f"Average win ({avg_w:.2f}{unit}) is smaller than average loss ({avg_l:.2f}{unit}).",
        recommended_action="Review exit strategy. Let winners run; cut losers faster.",
        title_fa="Winner ها را زود می‌بندید",
        body_fa=body_fa,
    )


# ── 7. SYMBOL EDGE ────────────────────────────────────────────────────────────

def insight_symbol_edge(df: pd.DataFrame, metrics: dict):
    results = []
    for sym, grp in df.groupby('symbol'):
        if len(grp) < 8: continue
        results.append({
            "symbol":    sym,
            "trades":    len(grp),
            "win_rate":  round((grp['pnl'] > 0).mean(), 4),
            "avg_pnl":   round(grp['pnl'].mean(), 2),
            "total_pnl": round(grp['pnl'].sum(), 2),
        })

    toxic = [r for r in results if r["avg_pnl"] < 0]
    if not toxic: return None

    worst     = min(toxic, key=lambda x: x["total_pnl"])
    total_pnl = df['pnl'].sum()
    pct = round(abs(worst["total_pnl"] / total_pnl * 100), 1) if total_pnl < 0 else 0

    body_fa = (
        f"روی {worst['symbol']} در {worst['trades']} معامله، "
        f"Win Rate {round(worst['win_rate']*100,1)}٪ و مجموع ضرر {abs(worst['total_pnl']):.2f}$ است. "
        f"این نماد {pct}٪ از کل ضرر شما را ساخته. در این نماد edge ندارید."
    )

    return Insight(
        insight_id="SYMBOL_NO_EDGE",
        severity=_sev("MEDIUM"), confidence=_conf("HIGH") if worst["trades"] >= 20 else _conf("MEDIUM"),
        sample_size=worst["trades"],
        metric_snapshot={"worst_symbol": worst, "all_symbols": results, "loss_contribution_pct": pct},
        message=f"No statistical edge on {worst['symbol']}.",
        recommended_action=f"Remove {worst['symbol']} from your trading plan or paper-trade it first.",
        title_fa=f"در {worst['symbol']} edge ندارید",
        body_fa=body_fa,
    )
