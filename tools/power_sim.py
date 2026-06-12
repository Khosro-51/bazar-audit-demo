"""
Phase 2 — Step 0: Statistical power simulation for SESSION_TOXICITY / SYMBOL_NO_EDGE.
Permutation test (corrects for worst-of-K selection). Effects injected in R units.

اجرا:  python tools/power_sim.py session 100
       python tools/power_sim.py symbol 100
"""
import json, sys
import numpy as np

def perm_test_worst_group(pnl, labels, groups, n_perm=400, min_n=5, rng=None):
    """stat = min over groups (>=min_n) of mean pnl. p = P(stat_null <= stat_obs)."""
    rng = rng or np.random.default_rng()
    def stat(lbl):
        best = None
        worst_g = None
        for g in groups:
            m = lbl == g
            cnt = m.sum()
            if cnt >= min_n:
                mu = pnl[m].mean()
                if best is None or mu < best:
                    best = mu; worst_g = g
        return (best if best is not None else 0.0), worst_g
    s_obs, g_obs = stat(labels)
    cnt = 0
    lab = labels.copy()
    for _ in range(n_perm):
        rng.shuffle(lab)
        s, _ = stat(lab)
        if s <= s_obs:
            cnt += 1
    p = (cnt + 1) / (n_perm + 1)
    return p, g_obs

def make_trader(rng, n, shares, effect_R, toxic_idx, k):
    labels = rng.choice(k, size=n, p=shares)
    pnl = rng.normal(0.0, 1.0, size=n)
    pnl[labels == toxic_idx] += effect_R
    return pnl, labels

def run_config(kind, n, effect, sims, n_perm, seed):
    rng = np.random.default_rng(seed)
    if kind == "session":
        k = 4; shares = np.array([0.15, 0.40, 0.30, 0.15]); toxic = 0  # Asia 15%
    else:  # symbol
        k = 5; shares = np.ones(5) / 5; toxic = 0                     # 20% share
    groups = np.arange(k)
    detected = 0; detected_right = 0
    for _ in range(sims):
        pnl, labels = make_trader(rng, n, shares, effect, toxic, k)
        p, g = perm_test_worst_group(pnl, labels, groups, n_perm=n_perm, rng=rng)
        if p < 0.05:
            detected += 1
            if g == toxic:
                detected_right += 1
    return {"kind": kind, "n": n, "effect_R": effect,
            "trigger_rate": round(detected / sims, 3),
            "correct_target_rate": round(detected_right / sims, 3)}

if __name__ == "__main__":
    kind = sys.argv[1]; n = int(sys.argv[2])
    out = []
    for eff in [0.0, -0.3, -0.5, -0.8]:
        out.append(run_config(kind, n, eff, sims=150, n_perm=300, seed=42 + n))
    print(json.dumps(out))
