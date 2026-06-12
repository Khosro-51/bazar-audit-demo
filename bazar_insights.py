"""
Bazar Audit — Insight Library (v2.0 — Phase 2: statistical honesty)
هر insight یک تابع مستقل است که Insight | None برمی‌گرداند.

v2.0:
- finding (MEDIUM/HIGH) فقط با شواهد آماری (permutation / binomial / z)
- observation (LOW) وقتی الگو دیده می‌شود ولی شواهد کافی نیست
- تست دائمی Monte Carlo در pytest: نرخ finding کاذب روی نویز < 10٪
"""
import pandas as pd
import numpy as np
from bazar_schema import Insight, Severity, Confidence


# ── helpers ──────────────────────────────────────────────────────────────────

def _sev(s: str) -> Severity:
    return Severity[s]

def _conf(s: str) -> Confidence:
    return Confidence[s]


def _seg_conf(n: int) -> Confidence:
    """Patch 2 (v1.2): گارد confidence برای سگمنت‌های کوچک."""
    if n < 20:
        return Confidence["LOW"]
    if n < 50:
        return Confidence["MEDIUM"]
    return Confidence["HIGH"]


# ── Phase 2 (v2.0): آزمون‌های آماری — finding فقط با شواهد، وگرنه observation ──
ALPHA_FINDING = 0.015   # سطح معناداری هر آزمون؛ اجتماع FP چند آزمون < 10٪ می‌ماند
N_PERM = 300


def _data_seed(df: pd.DataFrame, salt: int = 0) -> int:
    """seed قطعی ولی وابسته به داده — جایگشت‌ها بین دیتاست‌ها همبسته نمی‌شوند."""
    s = int(abs(float(df['pnl'].sum())) * 100) % 1000003
    return (len(df) * 1000003 + s + salt) % (2**31)


def _perm_p_worst_group(df: pd.DataFrame, col: str, n_perm: int = N_PERM,
                        min_n: int = 5, seed: int = 0):
    """p-value جایگشتی برای «بدترین گروه» — تصحیح خودکار selection-of-worst."""
    rng = np.random.default_rng(seed)
    pnl = df['pnl'].to_numpy(dtype=float)
    labels = df[col].to_numpy()
    groups = pd.unique(labels)

    def stat(lbl):
        best = None
        for g in groups:
            m = lbl == g
            if m.sum() >= min_n:
                mu = pnl[m].mean()
                if best is None or mu < best:
                    best = mu
        return best if best is not None else 0.0

    s_obs = stat(labels)
    lab = labels.copy()
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(lab)
        if stat(lab) <= s_obs:
            cnt += 1
    return (cnt + 1) / (n_perm + 1)


def _perm_p_cliff(win_flags, day_index, n_perm: int = N_PERM,
                  min_n: int = 5, seed: int = 0):
    """p-value جایگشتی برای cliff: stat = بیشینه افت WR روی همه نقاط برش."""
    rng = np.random.default_rng(seed)
    wins = np.asarray(win_flags, dtype=float)
    idx = np.asarray(day_index)
    uniq = np.sort(np.unique(idx))

    def stat(w):
        rates = []
        for u in uniq:
            m = idx == u
            if m.sum() >= min_n:
                rates.append(w[m].mean())
        if len(rates) < 3:
            return 0.0
        best = 0.0
        for i in range(1, len(rates)):
            d = np.mean(rates[:i]) - np.mean(rates[i:])
            if d > best:
                best = d
        return best

    s_obs = stat(wins)
    w = wins.copy()
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(w)
        if stat(w) >= s_obs:
            cnt += 1
    return (cnt + 1) / (n_perm + 1), s_obs


def _binom_p_le(k: int, n: int, p0: float) -> float:
    """P(X <= k) برای X~Binom(n, p0) — دقیق، بدون scipy."""
    from math import comb
    p0 = min(max(p0, 1e-9), 1 - 1e-9)
    return sum(comb(n, i) * (p0 ** i) * ((1 - p0) ** (n - i)) for i in range(0, k + 1))


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


# ── 1. SYSTEMIC UNDERPERFORMANCE + EDGE_BELOW_BREAKEVEN ─────────────────────

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
        # Patch 1 (v1.2): حالت مرزی — کمی زیر سر-به-سر، نه شکست ساختاری
        neg_exp = (exp_R < 0) if exp_R is not None else (metrics["expectancy_dollar"] < 0)
        soft = (n >= 50 and pf < 1.0 and neg_exp and wr < bwr
                and pf >= 0.80 and (exp_R is None or exp_R > -0.10))
        if not soft:
            return None
        # Phase 2 (v2.0): آیا منفی‌بودن expectancy از نویز جدا می‌شود؟ (z-test ساده)
        _sig_edge = False
        if exp_R is not None and 'pnl_R' in df.columns:
            _r = df['pnl_R'].dropna()
            if len(_r) > 10 and _r.std(ddof=1) > 0:
                _se = _r.std(ddof=1) / (len(_r) ** 0.5)
                _sig_edge = (exp_R / _se) < -2.0
        if not _sig_edge:
            return Insight(
                insight_id="EDGE_BELOW_BREAKEVEN",
                severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=n,
                metric_snapshot={"win_rate": wr, "breakeven_win_rate": round(bwr, 4),
                                 "profit_factor": pf, "expectancy_R": exp_R,
                                 "gap_to_breakeven_pct": round(gap * 100, 1),
                                 "observation": True},
                message="Your strategy is marginally below breakeven in this sample; the gap is within noise range. Verify edge after costs and keep logging.",
                recommended_action="Track costs (spread/commission) and collect more trades before structural changes.",
                title_fa="مشاهده: کمی زیر سطح سر‌به‌سر",
                body_fa=(f"استراتژی شما در این نمونه کمی زیر سر‌به‌سر است "
                         f"(WR {round(wr*100,1)}٪، حد لازم {round(bwr*100,1)}٪، PF {pf})، "
                         f"اما فاصله در محدوده نویز است. هزینه‌ها را بررسی کن و داده بیشتر ثبت کن."),
            )
        body_fa = (
            f"استراتژی شما فعلاً کمی زیر سطح سر‌به‌سر است "
            f"(Win Rate {round(wr*100,1)}٪، حد لازم {round(bwr*100,1)}٪، PF {pf}). "
            f"قبل از بهینه‌سازی فیلترهای جزئی، باید بررسی شود که هسته اصلی استراتژی "
            f"بعد از هزینه‌ها edge کافی دارد یا نه."
        )
        return Insight(
            insight_id="EDGE_BELOW_BREAKEVEN",
            severity=_sev("MEDIUM"), confidence=_conf("MEDIUM"), sample_size=n,
            metric_snapshot={"win_rate": wr, "breakeven_win_rate": round(bwr, 4),
                             "profit_factor": pf, "expectancy_R": exp_R,
                             "gap_to_breakeven_pct": round(gap * 100, 1),
                             "observation": False},
            message="Your strategy is currently slightly below breakeven. Before optimizing individual filters, verify whether the core strategy has enough edge after costs.",
            recommended_action="Verify core edge after costs (spread/commission) before tuning sessions or symbols.",
            title_fa="کمی زیر سطح سر‌به‌سر",
            body_fa=body_fa,
        )

    # Phase 2 (v2.0): HIGH فقط با شواهد — expectancy باید معنادار زیر صفر باشد
    _sig_sys = True
    if 'pnl_R' in df.columns:
        _r = df['pnl_R'].dropna()
        if len(_r) > 10 and _r.std(ddof=1) > 0:
            _se = _r.std(ddof=1) / (len(_r) ** 0.5)
            _sig_sys = (float(_r.mean()) / _se) < -2.0
    else:
        _p = df['pnl'].dropna()
        if len(_p) > 10 and _p.std(ddof=1) > 0:
            _se = _p.std(ddof=1) / (len(_p) ** 0.5)
            _sig_sys = (float(_p.mean()) / _se) < -2.0
    if not _sig_sys:
        return None  # gap بزرگ ولی در محدوده نویز — سکوت بهتر از حکم کاذب

    gap = round((bwr - wr) * 100, 1)
    conf = _conf("HIGH") if n >= 80 else _conf("MEDIUM")

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
            "observation": False,
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
    # Patch 3 (v1.2): counterfactual به جای impact_pct ناپایدار
    rest = df[df['session'] != worst['session']]
    rest_gp = rest[rest['pnl'] > 0]['pnl'].sum()
    rest_gl = abs(rest[rest['pnl'] < 0]['pnl'].sum())
    pf_without = round(rest_gp / rest_gl, 3) if rest_gl > 0 else None
    counterfactual = {
        "current_pf": metrics["profit_factor"],
        "pf_without_segment": pf_without,
        "current_net_pnl": round(df['pnl'].sum(), 2),
        "net_pnl_without_segment": round(rest['pnl'].sum(), 2),
    }

    # Phase 2 (v2.0): finding فقط با شواهد جایگشتی؛ وگرنه observation
    p_val = _perm_p_worst_group(df, 'session', seed=_data_seed(df, 1))
    significant = p_val < ALPHA_FINDING

    snapshot = {"worst_session": worst, "all_sessions": results,
                "counterfactual": counterfactual,
                "p_value": round(p_val, 4), "observation": not significant}

    if significant:
        sev  = _sev("HIGH") if worst["avg_pnl"] < -60 else _sev("MEDIUM")
        conf = _seg_conf(worst["trades"])
        body_fa = (
            f"در سشن {worst['session']} با {worst['trades']} معامله، "
            f"Win Rate شما {round(worst['win_rate']*100,1)}٪ و "
            f"میانگین PnL {worst['avg_pnl']:.2f}$ است (p={p_val:.3f}). "
            f"بدون این سشن، Profit Factor از {counterfactual['current_pf']} به "
            f"{pf_without if pf_without is not None else '—'} و نتیجه خالص از "
            f"{counterfactual['current_net_pnl']}$ به {counterfactual['net_pnl_without_segment']}$ می‌رسید."
        )
        return Insight(
            insight_id="SESSION_TOXICITY",
            severity=sev, confidence=conf, sample_size=worst["trades"],
            metric_snapshot=snapshot,
            message=f"Session '{worst['session']}' is consistently unprofitable for you (p={p_val:.3f}).",
            recommended_action=f"Avoid or reduce trading during '{worst['session']}' session.",
            title_fa=f"سشن {worst['session']} برای شما مضر است",
            body_fa=body_fa,
        )

    # observation: سگمنت منفی ولی شواهد ناکافی
    return Insight(
        insight_id="SESSION_TOXICITY",
        severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=worst["trades"],
        metric_snapshot=snapshot,
        message=(f"Session '{worst['session']}' looks weak in this data, but evidence is "
                 f"not yet sufficient for a firm conclusion (p={p_val:.2f}). Log more trades."),
        recommended_action="No firm action yet — keep logging trades in this session; judgment power roughly triples around 300 trades.",
        title_fa=f"مشاهده: سشن {worst['session']} ضعیف دیده می‌شود",
        body_fa=(
            f"در داده فعلی، سشن {worst['session']} ({worst['trades']} معامله، "
            f"میانگین {worst['avg_pnl']:.2f}$) ضعیف دیده شده، اما شواهد برای حکم قطعی "
            f"کافی نیست (p={p_val:.2f}). با ثبت معاملات بیشتر، قدرت قضاوت به‌مراتب بهتر می‌شود."
        ),
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
    # Phase 2 (v2.0): جایگشت روی پرچم برد/باخت — finding فقط با شواهد
    _wins = (df['pnl'] > 0).to_numpy()
    _idx  = df[col].to_numpy()
    p_val, _ = _perm_p_cliff(_wins, _idx, seed=_data_seed(df, 13))
    if p_val >= ALPHA_FINDING:
        return Insight(
            insight_id="TRADE_COUNT_CLIFF",
            severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=len(df),
            metric_snapshot={"cliff_at_trade": cliff, "before_wr": round(bwr,4),
                             "after_wr": round(awr,4), "drop_pct": drop,
                             "p_value": round(p_val,4), "observation": True},
            message=(f"Win rate appears to drop after trade #{cliff} each day, but evidence is "
                     f"not yet sufficient (p={p_val:.2f}). Log more trades."),
            recommended_action="No firm action yet — keep logging; re-check after more trading days.",
            title_fa=f"مشاهده: افت بعد از معامله {cliff}ام دیده می‌شود",
            body_fa=(f"در داده فعلی بعد از معامله {cliff}ام روز افت Win Rate دیده شده "
                     f"({drop} امتیاز)، اما شواهد برای حکم قطعی کافی نیست (p={p_val:.2f})."),
        )
    conf = _conf("HIGH") if drop >= 25 else _conf("MEDIUM")

    body_fa = (
        f"قبل از معامله {cliff}ام روز، Win Rate شما {round(bwr*100,1)}٪ است. "
        f"از معامله {cliff}ام به بعد به {round(awr*100,1)}٪ می‌افتد ({drop} امتیاز، p={p_val:.3f}). "
        f"تا وقتی داده بیشتری ثابت نکرده معامله {cliff}ام سودآور است، "
        f"خودت را به {cliff-1} معامله در روز محدود کن."
    )

    return Insight(
        insight_id="TRADE_COUNT_CLIFF",
        severity=_sev("HIGH") if drop >= 25 else _sev("MEDIUM"),
        confidence=conf, sample_size=len(df),
        metric_snapshot={"cliff_at_trade": cliff, "before_wr": round(bwr,4), "after_wr": round(awr,4),
                         "drop_pct": drop, "p_value": round(p_val,4), "observation": False},
        message=f"Win rate drops sharply after trade #{cliff} each day (p={p_val:.3f}).",
        recommended_action=f"Limit yourself to {cliff-1} trade(s) per day until more data proves trade #{cliff} is profitable.",
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

    def _fast_sig():
        if not has_fast:
            return 1.0
        wins_fast = int((df.iloc[fast_idx]['pnl'] > 0).sum())
        return _binom_p_le(wins_fast, len(fast_idx), baseline_wr)

    # حالت ۱: baseline خیلی پایین → مشکل systemic است، post-loss معنادار نیست
    if baseline_wr < 0.25:
        if not has_fast or fast_drop is None or fast_drop < 0.05:
            return None
        if _fast_sig() >= ALPHA_FINDING:
            return None  # Phase 2: شواهد ناکافی — سکوت بهتر از ادعاست
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
                             "n_fast": len(fast_idx), "observation": False},
            message="Fast re-entry after losses worsens an already weak performance.",
            recommended_action="Implement a mandatory cooldown period after each loss.",
            title_fa="ورود سریع بعد از ضرر وضع را بدتر می‌کند",
            body_fa=body_fa,
        )

    # حالت ۲: wr_drop کم است اما fast_drop بالاست
    if wr_drop < 0.10 and has_fast and fast_drop is not None and fast_drop >= 0.15:
        if _fast_sig() >= ALPHA_FINDING:
            return None  # Phase 2: شواهد ناکافی
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
                             "fast_drop_pct": round(fast_drop*100,1), "n_fast": len(fast_idx),
                             "observation": False},
            message="Trades entered within 60 min of a loss have significantly lower win rate.",
            recommended_action="Add a 60-minute cooldown rule after any losing trade.",
            title_fa="ورود سریع بعد از ضرر عملکرد را خراب می‌کند",
            body_fa=body_fa,
        )

    # حالت ۳: decay کلی واقعی
    if wr_drop < 0.10:
        return None

    # Phase 2: گیت binomial — بردهای post-loss در برابر baseline
    _wins_pl = int((pl['pnl'] > 0).sum())
    if _binom_p_le(_wins_pl, len(post_loss_idx), baseline_wr) >= ALPHA_FINDING:
        return None  # شواهد ناکافی

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
                         "fast_wr": round(fast_wr*100,1) if fast_wr is not None else None,
                         "observation": False},
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
                         "avg_dd_lot": round(float(np.mean(dd_s)), 3),
                         "observation": False},
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

    # Phase 2 (v2.0): ratio بین 0.70 و 0.9 = observation (نویز محتمل)
    if ratio >= 0.70:
        return Insight(
            insight_id="PAYOFF_IMBALANCE",
            severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=len(df),
            metric_snapshot={"avg_win": round(avg_w,3), "avg_loss": round(avg_l,3),
                             "payoff_ratio": round(ratio,3), "unit": unit, "observation": True},
            message=(f"Average win ({avg_w:.2f}{unit}) is somewhat smaller than average loss "
                     f"({avg_l:.2f}{unit}); difference is small and may be noise."),
            recommended_action="No firm action yet — watch exits; re-check with more trades.",
            title_fa="مشاهده: نسبت سود/ضرر کمی نامتعادل است",
            body_fa=(f"میانگین سود {avg_w:.2f}{unit} و میانگین ضرر {avg_l:.2f}{unit} است "
                     f"(نسبت {ratio:.2f}). اختلاف کوچک است و ممکن است نویز باشد؛ با داده بیشتر دوباره بررسی می‌شود."),
        )

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
                         "payoff_ratio": round(ratio,3), "unit": unit, "observation": False},
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

    worst = min(toxic, key=lambda x: x["total_pnl"])
    # Patch 3 (v1.2): counterfactual به جای درصد ناپایدار
    rest = df[df['symbol'] != worst['symbol']]
    rest_gp = rest[rest['pnl'] > 0]['pnl'].sum()
    rest_gl = abs(rest[rest['pnl'] < 0]['pnl'].sum())
    pf_without = round(rest_gp / rest_gl, 3) if rest_gl > 0 else None
    counterfactual = {
        "current_pf": metrics["profit_factor"],
        "pf_without_segment": pf_without,
        "current_net_pnl": round(df['pnl'].sum(), 2),
        "net_pnl_without_segment": round(rest['pnl'].sum(), 2),
    }

    # Phase 2 (v2.0): finding فقط با شواهد جایگشتی؛ وگرنه observation
    p_val = _perm_p_worst_group(df, 'symbol', min_n=8, seed=_data_seed(df, 7))
    significant = p_val < ALPHA_FINDING

    snapshot = {"worst_symbol": worst, "all_symbols": results,
                "counterfactual": counterfactual,
                "p_value": round(p_val, 4), "observation": not significant}

    if significant:
        body_fa = (
            f"در این دیتاست، {worst['symbol']} ضعیف‌ترین نماد شماست: "
            f"{worst['trades']} معامله، Win Rate {round(worst['win_rate']*100,1)}٪، "
            f"مجموع {worst['total_pnl']:.2f}$ (p={p_val:.3f}). "
            f"تا تأیید بهبود با داده جدید، حجم/تعداد معاملاتش را کاهش بده."
        )
        return Insight(
            insight_id="SYMBOL_NO_EDGE",
            severity=_sev("MEDIUM"), confidence=_seg_conf(worst["trades"]),
            sample_size=worst["trades"],
            metric_snapshot=snapshot,
            message=f"{worst['symbol']} is currently your weakest symbol in this dataset (p={p_val:.3f}).",
            recommended_action=f"Pause or reduce {worst['symbol']} exposure until more data confirms improvement.",
            title_fa=f"{worst['symbol']} ضعیف‌ترین نماد شما در این دیتاست",
            body_fa=body_fa,
        )

    return Insight(
        insight_id="SYMBOL_NO_EDGE",
        severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=worst["trades"],
        metric_snapshot=snapshot,
        message=(f"{worst['symbol']} looks weak in this data, but evidence is not yet "
                 f"sufficient for a firm conclusion (p={p_val:.2f}). Log more trades."),
        recommended_action="No firm action yet — keep logging trades on this symbol before deciding.",
        title_fa=f"مشاهده: {worst['symbol']} ضعیف دیده می‌شود",
        body_fa=(
            f"در داده فعلی، {worst['symbol']} ({worst['trades']} معامله، "
            f"مجموع {worst['total_pnl']:.2f}$) ضعیف دیده شده، اما شواهد برای حکم قطعی "
            f"کافی نیست (p={p_val:.2f}). با ثبت معاملات بیشتر، قدرت قضاوت بهتر می‌شود."
        ),
    )
