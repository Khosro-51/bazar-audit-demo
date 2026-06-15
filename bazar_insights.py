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
from bazar_metrics import _r_series


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

# ── Tunable thresholds (centralized — audit B3 / cross-cutting rec #4) ──────────
# Severity cutoffs live here, not scattered as magic numbers inside the insights.
SESSION_TOXIC_HIGH_R   = -0.50   # worst-session avg PnL (in R) → HIGH; scale-invariant
                                 # (≈ the legacy -$60 at 1R≈$120; chosen to keep the
                                 #  HIGH bar as strict as before, just size-independent)
SESSION_TOXIC_HIGH_USD = -60.0   # dollar fallback when R is unavailable (not scale-invariant)
DD_THRESHOLD_PCT       = 3.0     # equity drawdown depth (%) that counts as "in drawdown"
DD_OVERSIZE_RATIO_MIN  = 1.2     # dd/normal position-size ratio to report at all
DD_OVERSIZE_RATIO_HIGH = 1.5     # ratio at/above which the finding is HIGH
POST_LOSS_FAST_GAP_MIN = 60      # "fast re-entry" window after a loss, in minutes


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


def _perm_p_dd_oversize(normal_lots, dd_lots, n_perm: int = N_PERM, seed: int = 0):
    """Permutation p-value for "position size is larger in drawdown" (audit RA-1).

    Null: lot size is unrelated to drawdown state. The dd count is held fixed and
    the drawdown/normal labels are shuffled across the pooled lot sizes; we recompute
    mean(dd)/mean(rest) each time. p = P(shuffled ratio >= observed ratio). This puts
    DRAWDOWN_RECOVERY_SIZING on the same evidence footing as the session/symbol/cliff
    findings instead of a bare ratio threshold."""
    rng = np.random.default_rng(seed)
    normal = np.asarray(normal_lots, dtype=float)
    dd     = np.asarray(dd_lots, dtype=float)
    allv = np.concatenate([normal, dd])
    n_dd = len(dd)

    def ratio(d, r):
        mr = r.mean()
        return (d.mean() / mr) if mr > 0 else 0.0

    obs = ratio(dd, normal)
    idx = np.arange(len(allv))
    cnt = 0
    for _ in range(n_perm):
        rng.shuffle(idx)
        if ratio(allv[idx[:n_dd]], allv[idx[n_dd:]]) >= obs:
            cnt += 1
    return (cnt + 1) / (n_perm + 1)


def _binom_p_le(k: int, n: int, p0: float) -> float:
    """P(X <= k) برای X~Binom(n, p0) — دقیق، بدون scipy."""
    from math import comb
    p0 = min(max(p0, 1e-9), 1 - 1e-9)
    return sum(comb(n, i) * (p0 ** i) * ((1 - p0) ** (n - i)) for i in range(0, k + 1))


def _significance_series(df: pd.DataFrame, mode: str):
    """Series for the one-sample edge z-test, chosen by DATA, not schema (audit A4/B2).

    Uses the R series of the engine's mode (full OR computed) when it carries enough
    real points, else falls back to dollar pnl. This makes full-mode and
    computed-mode traders judged by the SAME rule (B2), and prevents an all-NaN or
    near-empty pnl_R column from bypassing the guard (A4)."""
    r = _r_series(df, mode)
    if r is not None:
        r = r.dropna()
        if len(r) > 10:
            return r
    return df['pnl'].dropna()


def _post_loss_indices(opens, closes, pnls, fast_gap_min: int = POST_LOSS_FAST_GAP_MIN):
    """Post-loss trade indices (audit A7).

    A trade i is "post-loss" if the most-recently-COMPLETED prior trade — the one
    with the latest close_time at/before trade i's open_time — was a loss. This is
    found by close_time, not by open_time order, so it is correct under overlapping
    positions, and the returned gap is always >= 0. Returns (post_loss_idx,
    fast_idx) as positional indices into the open_time-ordered arrays."""
    closes = np.asarray(closes)
    opens  = np.asarray(opens)
    pnls   = np.asarray(pnls, dtype=float)
    close_order   = np.argsort(closes, kind='stable')
    closes_sorted = closes[close_order]
    post, fast = [], []
    for i in range(len(opens)):
        oi = opens[i]
        k = int(np.searchsorted(closes_sorted, oi, side='right'))  # # closed at/before oi
        prev = None
        for j in range(k - 1, -1, -1):
            cand = int(close_order[j])
            if cand != i:
                prev = cand
                break
        if prev is None:
            continue
        if pnls[prev] < 0:
            post.append(i)
            gap = (oi - closes[prev]) / np.timedelta64(1, 'm')  # minutes, >= 0 by construction
            if gap <= fast_gap_min:
                fast.append(i)
    return post, fast


def _drawdown_buckets(balance, lots, threshold_pct: float = DD_THRESHOLD_PCT):
    """Split position sizes into normal vs in-drawdown buckets (audit E3).

    Uses a running high-water mark from the first row and classifies EVERY trade
    into exactly one bucket by its decision-time drawdown depth — no trade is
    silently dropped (the old in_dd state machine dropped the first recovery trade).
    Returns (normal_sizes, dd_sizes)."""
    balance = np.asarray(balance, dtype=float)
    lots    = np.asarray(lots, dtype=float)
    # RA-4: drop rows with NaN balance or lot so a single bad/missing value can't
    # poison the running peak (Python max propagates NaN) or the size means.
    valid = ~(np.isnan(balance) | np.isnan(lots))
    balance = balance[valid]
    lots    = lots[valid]
    normal_s, dd_s = [], []
    peak = balance[0] if len(balance) else 0.0
    for i in range(len(balance)):
        b = balance[i]
        peak = max(peak, b)
        dd_pct = (peak - b) / peak * 100 if peak > 0 else 0.0
        (dd_s if dd_pct > threshold_pct else normal_s).append(lots[i])
    return normal_s, dd_s


def _decided_counts(pnl):
    """(wins, decided) where decided = wins + losses (scratches pnl==0 excluded).
    Single engine-wide win-rate basis (audit RA-2) — matches compute_core_metrics."""
    arr = np.asarray(pnl, dtype=float)
    wins = int((arr > 0).sum())
    return wins, wins + int((arr < 0).sum())


def _decided_win_rate(pnl) -> float:
    """Win rate over DECIDED trades: wins / (wins + losses), 0.0 if none (RA-2)."""
    wins, dec = _decided_counts(pnl)
    return (wins / dec) if dec > 0 else 0.0


def _two_prop_p_less(w1: int, n1: int, w2: int, n2: int) -> float:
    """One-sided p-value for H1: p1 < p2 via a two-proportion z-test (no scipy).

    A2 fix: the post-loss reference rate is *estimated* from the non-post-loss
    complement, not known a priori. A one-sample binomial against that estimate
    as if it were exact understates the variance and inflates significance. The
    two-proportion test accounts for sampling error in both groups, which keeps
    the false-finding rate at its nominal level on noise.
    """
    from math import erf, sqrt
    if n1 == 0 or n2 == 0:
        return 1.0
    p1 = w1 / n1
    p2 = w2 / n2
    p  = (w1 + w2) / (n1 + n2)
    se = (p * (1 - p) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return 0.5 * (1 + erf(z / sqrt(2)))   # Phi(z): small when p1 is well below p2


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
        # B2 fix: judge the edge from the R series of the engine's mode (full OR
        # computed) via _significance_series, not the raw pnl_R column — so a
        # computed-mode trader can also reach the significant MEDIUM verdict, not
        # only the LOW observation. Same rule for full and computed.
        _sig_edge = False
        _edge_series = _significance_series(df, metrics["r_mode"])
        if len(_edge_series) > 10 and _edge_series.std(ddof=1) > 0:
            _se = _edge_series.std(ddof=1) / (len(_edge_series) ** 0.5)
            _sig_edge = (float(_edge_series.mean()) / _se) < -2.0
        if not _sig_edge:
            return Insight(
                insight_id="EDGE_BELOW_BREAKEVEN",
                severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=n,
                metric_snapshot={"win_rate": wr, "breakeven_win_rate": round(bwr, 4),
                                 "profit_factor": pf, "expectancy_R": exp_R,
                                 "gap_to_breakeven_pct": round(gap * 100, 1),
                                 "observation": True},
                message="Your strategy is marginally below breakeven in this sample; the gap is within noise range. Verify edge after costs and keep logging.",
                recommended_action="Research action (next 30 trades): Log exact spread and commission per trade. Calculate net PnL after costs. Re-check edge after 30 more trades before any structural strategy change.",
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
    # A4 fix (now via the shared _significance_series helper): gate on DATA, not the
    # presence of a pnl_R column. An all-NaN/near-empty pnl_R column no longer slips
    # past the guard, and computed-mode uses its R series like full mode (B2).
    _sig_sys = True
    _sig_series = _significance_series(df, metrics["r_mode"])
    if len(_sig_series) > 10 and _sig_series.std(ddof=1) > 0:
        _se = _sig_series.std(ddof=1) / (len(_sig_series) ** 0.5)
        _sig_sys = (float(_sig_series.mean()) / _se) < -2.0
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
        wr      = _decided_win_rate(grp['pnl'])   # RA-2: decided basis
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
        # B3 fix: prefer a scale-invariant R cutoff for HIGH (the worst session's
        # average loss in R) so the verdict doesn't depend on account/lot size;
        # fall back to the dollar cutoff only when R is unavailable.
        _rser = _r_series(df, metrics.get("r_mode", "pnl_only"))
        if _rser is not None:
            _seg_r = _rser[(df['session'] == worst['session']).to_numpy()].dropna()
            _is_high = len(_seg_r) > 0 and float(_seg_r.mean()) < SESSION_TOXIC_HIGH_R
        else:
            _is_high = worst["avg_pnl"] < SESSION_TOXIC_HIGH_USD
        sev  = _sev("HIGH") if _is_high else _sev("MEDIUM")
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
        recommended_action="Research action (next 30 trades): Tag this session separately on each trade. Do not increase size or risk. Re-check significance after 30 more trades — evidence triples around 300 total.",
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
    # D3 fix: ALWAYS derive the per-day trade index from open_time, deterministically,
    # instead of trusting a supplied column. Two uploads that differ only by the
    # presence (or upstream computation) of trade_index_in_day must produce the same
    # cliff result (live == backtest). Day boundary = the calendar date of open_time
    # in whatever timezone the data carries. (Limitation: a broker/session rollover
    # boundary is not modeled — see audit D3 note.)
    df = df.copy()
    df['_date'] = df['open_time'].dt.date
    _derived = df.groupby('_date').cumcount() + 1
    _supplied = df[col] if col in df.columns else None
    _overrode = False
    if _supplied is not None:
        try:
            _overrode = not np.array_equal(
                pd.to_numeric(_supplied, errors='coerce').to_numpy(), _derived.to_numpy())
        except Exception:
            _overrode = True
    df[col] = _derived

    results = []
    for idx in sorted(df[col].unique()):
        grp = df[df[col] == idx]
        # RA-2: decided basis — need >=5 DECIDED trades at this position; win rate
        # and the pooled weight `n` both exclude scratches (pnl==0).
        n_dec = int((grp['pnl'] != 0).sum())
        if n_dec < 5:
            continue
        results.append({"index": int(idx), "win_rate": _decided_win_rate(grp['pnl']), "n": n_dec})

    if len(results) < 3:
        return None

    # A6 fix: report the split the permutation statistic actually tests — the
    # argmax-drop split across ALL cut points (_perm_p_cliff's stat is the maximum
    # drop), not merely the FIRST split to cross 0.15. Same unweighted per-index
    # rates and same buckets as the test, so the reported cut point == the tested
    # cut point. (The 0.15 trigger set is unchanged: argmax > 0.15 iff some split
    # crosses 0.15.)
    rates = [r["win_rate"] for r in results]
    cliff_i = None
    best_drop = 0.0
    for i in range(1, len(results)):
        d = np.mean(rates[:i]) - np.mean(rates[i:])
        if d > best_drop:
            best_drop, cliff_i = d, i

    if cliff_i is None or best_drop <= 0.15:
        return None
    cliff = results[cliff_i]["index"]

    # A5 fix: detect the split on the unweighted per-index series (kept consistent
    # with the permutation statistic), but DISPLAY the real trade-weighted (pooled)
    # win rates over the buckets before/after the split. An unweighted average of
    # per-index win rates is not the win rate the trader would actually compute.
    def _pooled_wr(buckets):
        tot = sum(b["n"] for b in buckets)
        return (sum(b["n"] * b["win_rate"] for b in buckets) / tot) if tot else 0.0
    bwr = _pooled_wr(results[:cliff_i])
    awr = _pooled_wr(results[cliff_i:])
    drop = round((bwr - awr) * 100, 1)
    # Phase 2 (v2.0): جایگشت روی پرچم برد/باخت — finding فقط با شواهد
    # RA-2: permute over DECIDED trades only (scratches excluded), so the test sits
    # on the same basis as the displayed pooled win rates.
    _dec_mask = (df['pnl'] != 0).to_numpy()
    _wins = (df['pnl'] > 0).to_numpy()[_dec_mask].astype(float)
    _idx  = df[col].to_numpy()[_dec_mask]
    p_val, _ = _perm_p_cliff(_wins, _idx, seed=_data_seed(df, 13))
    if p_val >= ALPHA_FINDING:
        return Insight(
            insight_id="TRADE_COUNT_CLIFF",
            severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=len(df),
            metric_snapshot={"cliff_at_trade": cliff, "before_wr": round(bwr,4),
                             "after_wr": round(awr,4), "drop_pct": drop,
                             "p_value": round(p_val,4), "observation": True,
                             "derived_trade_index": True,
                             "trade_index_overrode_supplied": _overrode},
            message=(f"Win rate appears to drop after trade #{cliff} each day, but evidence is "
                     f"not yet sufficient (p={p_val:.2f}). Log more trades."),
            recommended_action="Research action (next 30 days): Log trade sequence number (1st, 2nd, 3rd…) per session in your journal. No structural change yet. Re-check after 30 more trading days.",
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
                         "drop_pct": drop, "p_value": round(p_val,4), "observation": False,
                         "derived_trade_index": True,
                         "trade_index_overrode_supplied": _overrode},
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

    # A7 fix (see _post_loss_indices): "previous" trade is the most-recently-CLOSED
    # one, not the prior by open_time — overlap-safe, and gaps are always >= 0.
    post_loss_idx, fast_idx = _post_loss_indices(
        df['open_time'].to_numpy(), df['close_time'].to_numpy(), df['pnl'].to_numpy())

    if len(post_loss_idx) < 15:
        return None

    pl   = df.iloc[post_loss_idx]
    # RA-2: decided basis (wins / wins+losses) everywhere — same basis as the global
    # win_rate and breakeven_wr; scratch trades (pnl==0) are excluded from rates and
    # from the two-proportion denominators.
    pl_wins, pl_dec = _decided_counts(pl['pnl'])
    pl_wr = (pl_wins / pl_dec) if pl_dec > 0 else 0.0
    # A2 fix: the reference is the NON-post-loss complement, not the overall win
    # rate. The overall rate contains the post-loss trades being tested, which
    # pulls the baseline toward pl_wr — understating the drop and biasing the
    # test toward non-significance (lost power).
    _pl_set = set(post_loss_idx)
    non_pl  = df.iloc[[i for i in range(len(df)) if i not in _pl_set]]
    _wins_ref, _n_ref = _decided_counts(non_pl['pnl'])   # _n_ref = decided count
    ref_wr  = (_wins_ref / _n_ref) if _n_ref > 0 else baseline_wr
    wr_drop = ref_wr - pl_wr

    has_fast = len(fast_idx) >= 5
    fast_wr = fast_drop = None
    fast_wins = fast_dec = 0
    if has_fast:
        ft = df.iloc[fast_idx]
        fast_wins, fast_dec = _decided_counts(ft['pnl'])
        fast_wr   = (fast_wins / fast_dec) if fast_dec > 0 else 0.0
        fast_drop = ref_wr - fast_wr   # A2 fix: vs non-post-loss complement

    def _fast_sig():
        if not has_fast or fast_dec == 0:
            return 1.0
        # A2 fix: fast trades vs the (disjoint) non-post-loss complement
        return _two_prop_p_less(fast_wins, fast_dec, _wins_ref, _n_ref)

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

    # Phase 2: گیت — بردهای post-loss در برابر مکمل non-post-loss (A2 fix: two-proportion)
    # RA-2: decided-basis counts on both sides.
    if _two_prop_p_less(pl_wins, pl_dec, _wins_ref, _n_ref) >= ALPHA_FINDING:
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
        f"{round(ref_wr*100,1)}٪ به {round(pl_wr*100,1)}٪ افت می‌کند "
        f"({round(wr_drop*100,1)} امتیاز).{fast_line}"
    )

    return Insight(
        insight_id="POST_LOSS_DECAY",
        severity=sev, confidence=_conf("HIGH") if len(post_loss_idx) >= 30 else _conf("MEDIUM"),
        sample_size=len(post_loss_idx),
        metric_snapshot={"baseline_wr": round(ref_wr,4), "overall_wr": round(baseline_wr,4),
                         "post_loss_wr": round(pl_wr,4),
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
    if 'balance_before' not in df.columns or 'lot_or_size' not in df.columns or len(df) < 20:
        return None

    # A1 fix: classify the drawdown state from the balance BEFORE each trade
    # (the equity reading at the moment the size was chosen), not balance_after.
    # Using balance_after lets a large losing trade push equity below peak and
    # thereby classify its own outcome as "drawdown" — outcome leakage that
    # manufactures the very oversizing-in-drawdown pattern this insight reports.
    # E3 fix (see _drawdown_buckets): running high-water mark from the first row;
    # every trade classified into exactly one bucket (no dropped recovery trade).
    normal_s, dd_s = _drawdown_buckets(
        df['balance_before'].values, df['lot_or_size'].values, DD_THRESHOLD_PCT)

    if len(dd_s) < 5 or len(normal_s) < 5:
        return None

    ratio = np.mean(dd_s) / np.mean(normal_s) if np.mean(normal_s) > 0 else 1.0
    if ratio < DD_OVERSIZE_RATIO_MIN:
        return None

    # RA-1 fix: gate with a permutation test, like every other behavioral finding,
    # instead of emitting a finding on a bare ratio threshold. Null = lot size is
    # unrelated to drawdown state. Below significance → LOW observation, not a finding.
    p_val = _perm_p_dd_oversize(normal_s, dd_s, seed=_data_seed(df, 23))
    significant = p_val < ALPHA_FINDING
    snapshot = {"size_ratio": round(ratio, 2),
                "avg_normal_lot": round(float(np.mean(normal_s)), 3),
                "avg_dd_lot": round(float(np.mean(dd_s)), 3),
                "n_dd": len(dd_s), "n_normal": len(normal_s),
                "p_value": round(p_val, 4), "observation": not significant}

    if not significant:
        return Insight(
            insight_id="DRAWDOWN_RECOVERY_SIZING",
            severity=_sev("LOW"), confidence=_conf("LOW"), sample_size=len(dd_s),
            metric_snapshot=snapshot,
            message=(f"Position size looks larger ({ratio:.1f}x) during drawdowns in this data, "
                     f"but the difference isn't statistically clear yet (p={p_val:.2f}). Log more trades."),
            recommended_action="Research action (next 30 trades): tag each trade's position size and account state. Don't change sizing yet — re-check after more data.",
            title_fa="مشاهده: احتمال بزرگ‌تر شدن سایز در drawdown",
            body_fa=(f"در داده فعلی سایز معاملات در دوره‌های drawdown حدود {ratio:.1f}x بزرگ‌تر دیده می‌شود، "
                     f"اما اختلاف هنوز از نظر آماری قطعی نیست (p={p_val:.2f}). با داده بیشتر دوباره بررسی می‌شود."),
        )

    sev = _sev("HIGH") if ratio >= DD_OVERSIZE_RATIO_HIGH else _sev("MEDIUM")

    body_fa = (
        f"در دوره‌های drawdown بیش از {int(DD_THRESHOLD_PCT)}٪، میانگین سایز معاملات شما "  # RA-6: tracks DD_THRESHOLD_PCT
        f"{ratio:.1f}x بزرگتر از حالت عادی است (p={p_val:.3f}). "
        f"این الگو معمولاً drawdown را عمیق‌تر می‌کند."
    )

    return Insight(
        insight_id="DRAWDOWN_RECOVERY_SIZING",
        severity=sev, confidence=_conf("MEDIUM"), sample_size=len(dd_s),
        metric_snapshot=snapshot,
        message=f"Position size increases {ratio:.1f}x during drawdown periods (p={p_val:.3f}).",
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
            "win_rate":  round(_decided_win_rate(grp['pnl']), 4),  # RA-2: decided basis
            "avg_pnl":   round(grp['pnl'].mean(), 2),
            "total_pnl": round(grp['pnl'].sum(), 2),
        })

    toxic = [r for r in results if r["avg_pnl"] < 0]
    if not toxic: return None

    # A3 fix: the permutation test (_perm_p_worst_group) tests the worst group by
    # MEAN pnl, so the reported symbol must also be the worst-by-mean — otherwise
    # the displayed p-value can belong to a different symbol than the one shown
    # (a high-volume symbol can have the worst total while a smaller one drives the
    # p-value). This matches how SESSION_TOXICITY already selects its worst segment.
    worst = min(toxic, key=lambda x: x["avg_pnl"])
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
        recommended_action="Research action (next 30 trades): Keep trading this symbol but tag it in your log. Record setup type per trade. Do not increase size. Re-check p-value after 30 more trades.",
        title_fa=f"مشاهده: {worst['symbol']} ضعیف دیده می‌شود",
        body_fa=(
            f"در داده فعلی، {worst['symbol']} ({worst['trades']} معامله، "
            f"مجموع {worst['total_pnl']:.2f}$) ضعیف دیده شده، اما شواهد برای حکم قطعی "
            f"کافی نیست (p={p_val:.2f}). با ثبت معاملات بیشتر، قدرت قضاوت بهتر می‌شود."
        ),
    )
