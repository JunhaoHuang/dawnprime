#!/usr/bin/env sage -python
# -*- coding: utf-8 -*-
"""
DAWN prime mu=4 group-DFR estimator with multiprocessing.

Run with Sage, for example:

    sage -python dawn_prime_dfr.py --param DAWN-prime-128 --message random --jobs 1

The code exploits the fixed polynomials

    t = x^(n/2)+1,     w = x^(n/4)+1,

by grouping coefficients with mu=4.  Let n=4*nu and Y=x^nu.  In the group ring

    S = Z[Y]/(Y^4+1),

we have

    t = 1+Y^2,         w = 1+Y.

For the group r = {r, r+nu, r+2nu, r+3nu}, the decryption-noise block is modeled as

    Z_[r] = sum_{u=0}^{nu-1} Y^{eps_r(u)} [
                (1+Y^2) G_u S_v + F_u ((1+Y^2) U_v + Y^2(1+Y) M_v)
            ],
    v = (r-u) mod nu,     eps_r(u)=0 if u<=r, else 1,
    U = E + E_dc.

This preserves the correlation among the four n/4-spaced coefficients and the shared F
in F(E+E_dc) and F Y^2(1+Y)M.  No independence is assumed between Z_{r,a} and Z_{r,b}.

Default bound: cross-half-coset projection bound for the wrap decoding.
The two half-cosets modulo x^(n/2)+1 are {0,2} and {1,3}.  For each cross pair
(a,b), it bounds

    P(|Z_a|+|Z_b| > q)

by the four projected tails

    sum_{s,t in {+-1}} P(s Z_a + t Z_b > q).

Each projected tail is computed as a 1D convolution power in Sage/MPFR:

    Law(<lambda,Z_[r]>) = D_{lambda,0}^{*(r+1)} * D_{lambda,1}^{*(nu-r-1)}.

Finally, the global no-group-independence DFR upper bound is

    DFR <= sum_{r=0}^{nu-1} P[Bad_r].

This is an upper bound; it does not use a binomial model over the n/4 groups.
"""

from __future__ import annotations
from sage.all import *
import argparse
import json
try:
    import multiprocess as mp  # optional dill-based package
except ImportError:  # fallback to Python stdlib
    import multiprocessing as mp
import os
import sys
from copy import copy
from collections import defaultdict
from itertools import product
from math import comb, factorial


ROUNDING_FACTOR = 2**512
RF = RealField(prec=1024)


def round_to_rational(x):
    A = ZZ(round(x * ROUNDING_FACTOR))
    return QQ(A) / QQ(ROUNDING_FACTOR)


def average_variance(D):
    mu = 0.
    s = 0.

    for (v, p) in D.items():
        mu += v * p
        s += v * v * p

    s -= mu * mu
    return round_to_rational(mu), round_to_rational(s)


def binomial(x, y):
    try:
        binom = factorial(x) // factorial(y) // factorial(x - y)
    except ValueError:
        binom = 0
    return binom


def centered_binomial_pdf(k, x):
    return binomial(2 * k, x + k) / 2.**(2 * k)


def build_centered_binomial_law(k):
    D = {}
    for i in range(-k, k + 1):
        D[i] = centered_binomial_pdf(k, i)
    return D

def round_to_rational(x):
    A = ZZ(round(x * ROUNDING_FACTOR))
    return QQ(A) / QQ(ROUNDING_FACTOR)


def get_uniform_distribution(start, end):
    tmp_D = {}
    for i in range(start, end + 1):
        tmp_D[i] = 1 / (end - start + 1)
    return tmp_D


def get_ternary_distribution(total_num, one_num, _one_num):
    tmp_D = {-1: _one_num / total_num, 1: one_num / total_num}
    tmp_D[0] = 1 - tmp_D[1] - tmp_D[-1]
    return tmp_D


def get_compress_distribution(q, d, direct_div=False):
    if not direct_div:
        tmp_l = [int(int(floor(int(int(floor(vi * d / q)) % d) * (q/d))-vi) % q) for vi in range(q)]
    else:
        tmp_l = [int(int(floor(int(int(round(vi / d))) * d) - vi) % q) for vi in range(q)]
    tmp_l = [vi if int(vi) < int(-vi % q) else -int(-vi%q) for vi in tmp_l]
    tmp_pdf = {}
    for vi in set(tmp_l):
        tmp_pdf[vi] = RF(tmp_l.count(vi) / q)
    tmp_mean = int(round(average_variance(tmp_pdf)[0]))
    new_pdf = {}
    for vi in tmp_pdf:
        new_pdf[vi-tmp_mean] = tmp_pdf[vi]
    return new_pdf


def add_distribution(pdf1, pdf2, prob_bound=1e-64):
    pdf3 = {}
    for p1 in pdf1.keys():
        if pdf1[p1] < prob_bound:
            continue
        for p2 in pdf2.keys():
            if pdf2[p2] < prob_bound:
                continue
            tmp_prob = pdf1[p1] * pdf2[p2]
            if tmp_prob < prob_bound:
                continue
            tmp = p1 + p2
            if tmp not in pdf3:
                pdf3[tmp] = tmp_prob
            else:
                pdf3[tmp] += tmp_prob
    return pdf3

PARAMS = {
    "DAWN-alpha-128": dict(n=512, q=769, Dg=get_ternary_distribution(512, 160, 160), Df=get_ternary_distribution(512, 64, 64), Ds=get_ternary_distribution(512, 96, 96), De=get_ternary_distribution(512, 160, 160), Dedc=get_compress_distribution(769, 7, direct_div=True)),
    "DAWN-prime-128": dict(n=512, q=769, Dg=build_centered_binomial_law(1), Df=get_ternary_distribution(512, 96, 96), Ds=build_centered_binomial_law(1), De=build_centered_binomial_law(1), Dedc=get_compress_distribution(769, 147)),
    "DAWN-alpha-256": dict(n=1024, q=769, Dg=get_ternary_distribution(1024, 256, 256), Df=get_ternary_distribution(1024, 96, 96), Ds=get_ternary_distribution(1024, 192, 192), De=get_ternary_distribution(1024, 256, 256), Dedc=get_compress_distribution(769, 4, direct_div=True)),
    "DAWN-prime-256": dict(n=1024, q=769, Dg=get_ternary_distribution(1024, 192, 192), Df=get_ternary_distribution(1024, 128, 128), Ds=build_centered_binomial_law(1), De=build_centered_binomial_law(1), Dedc=get_compress_distribution(769, 256)),
}

# ---------------------------------------------------------------------------
# Small ring S = Z[Y]/(Y^4+1), represented by integer tuples (a0,a1,a2,a3).
# ---------------------------------------------------------------------------

def add4(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3])


def negaconv4(a, b):
    """Product in Z[Y]/(Y^4+1)."""
    r = [0, 0, 0, 0]
    for i, ai in enumerate(a):
        if ai == 0:
            continue
        for j, bj in enumerate(b):
            if bj == 0:
                continue
            k = i + j
            if k >= 4:
                r[k - 4] -= ai * bj
            else:
                r[k] += ai * bj
    return tuple(r)


def mulY(v):
    """Y*v in Z[Y]/(Y^4+1)."""
    return (-v[3], v[0], v[1], v[2])


def mulYpow(v, c):
    c %= 4
    for _ in range(c):
        v = mulY(v)
    return v


def Tmap(v):
    """Multiplication by t = 1+Y^2."""
    return add4(v, mulYpow(v, 2))


def Wmap(v):
    """Multiplication by w = 1+Y."""
    return add4(v, mulY(v))


def dot4(lam, v):
    return int(lam[0]) * v[0] + int(lam[1]) * v[1] + int(lam[2]) * v[2] + int(lam[3]) * v[3]


# ---------------------------------------------------------------------------
# Distribution utilities
# ---------------------------------------------------------------------------

def normalize(D, RF):
    s = sum(D.values(), RF(0))
    if s == 0:
        return dict(D)
    for k in list(D.keys()):
        D[k] = RF(D[k]) / s
    return dict(D)


def convolve1d(A, B, RF, cutoff=0):
    C = defaultdict(lambda: RF(0))
    ccut = RF(cutoff)
    for a, pa in A.items():
        if pa <= ccut:
            continue
        for b, pb in B.items():
            if pb <= ccut:
                continue
            p = pa * pb
            if p <= ccut:
                continue
            C[a + b] += p
    return normalize(C, RF)


def ternary_law(n, k_plus, k_minus, RF):
    p_plus = RF(k_plus) / RF(n)
    p_minus = RF(k_minus) / RF(n)
    return {-1: p_minus, 0: RF(1) - p_plus - p_minus, 1: p_plus}


def tuple_law4(coeff_law, RF):
    items = list(coeff_law.items())
    D = defaultdict(lambda: RF(0))
    for vals in product(items, repeat=4):
        tup = tuple(int(v) for v, _ in vals)
        p = RF(1)
        for _, pv in vals:
            p *= pv
        D[tup] += p
    return normalize(D, RF)


def message_block_law(model, RF):
    """Law of M_v in the mu=4 block.

    Correct block structure: deg(m)<n/4, so M_v=(m_v,0,0,0).
    """
    if model == "random":
        return {(0, 0, 0, 0): RF(1) / RF(2), (1, 0, 0, 0): RF(1) / RF(2)}
    if model == "ones":
        return {(1, 0, 0, 0): RF(1)}
    if model == "zero":
        return {(0, 0, 0, 0): RF(1)}
    if model == "paper-coeff-avg":
        # Coefficient-wise model used by simple scalar scripts: Pr[m_i=1]=1/4.
        # This ignores deg(m)<n/4 and is included only for comparison.
        return tuple_law4({0: RF(3) / RF(4), 1: RF(1) / RF(4)}, RF)
    raise ValueError(f"unknown message model: {model}")


# ---------------------------------------------------------------------------
# Base laws in S = Z[Y]/(Y^4+1)
# ---------------------------------------------------------------------------

class DAWNPrimeMu4Laws:
    def __init__(self, params, RF, message_model="random"):
        self.params = dict(params)
        self.RF = RF
        self.n = int(params["n"])
        self.q = int(params["q"])
        self.nu = self.n // 4
        self.message_model = message_model
        self._proj_cache = {}
        self._poly_cache = {}
        self._power_cache = {}

        Dg1 = params["Dg"]
        Ds1 = params["Ds"]
        Df1 = params["Df"]
        De1 = params["De"]
        Dedc1 = params["Dedc"]

        Du1 = convolve1d(De1, Dedc1, RF)

        self.Dg = tuple_law4(Dg1, RF)
        self.Ds = tuple_law4(Ds1, RF)
        self.Df = tuple_law4(Df1, RF)
        self.Du = tuple_law4(Du1, RF)
        self.Dm = message_block_law(message_model, RF)

        self.gs_vec_law = self._build_gs_vec_law()
        self.fum_vec_law = self._build_fum_vec_law()

    def _build_gs_vec_law(self):
        """Law of (1+Y^2)*G*S."""
        RF = self.RF
        D = defaultdict(lambda: RF(0))
        for g, pg in self.Dg.items():
            for s, ps in self.Ds.items():
                v = Tmap(negaconv4(g, s))
                D[v] += pg * ps
        return normalize(D, RF)

    def _build_fum_vec_law(self):
        """Law of F*((1+Y^2)*U + Y^2*(1+Y)*M), preserving shared F."""
        RF = self.RF
        D = defaultdict(lambda: RF(0))
        for f, pf in self.Df.items():
            for u, pu in self.Du.items():
                tau_u = Tmap(u)
                for m, pm in self.Dm.items():
                    y2_omega_m = mulYpow(Wmap(m), 2)
                    inner = add4(tau_u, y2_omega_m)
                    v = negaconv4(f, inner)
                    D[v] += pf * pu * pm
        return normalize(D, RF)

    def project_vec_law(self, vec_law, lam, carry):
        RF = self.RF
        D = defaultdict(lambda: RF(0))
        for v, p in vec_law.items():
            vc = mulYpow(v, carry)
            D[dot4(lam, vc)] += p
        return normalize(D, RF)

    def base_projection_law(self, lam, carry):
        """Law of <lam, Y^carry[(1+Y^2)GS + F((1+Y^2)U+Y^2(1+Y)M)]>."""
        key = (tuple(int(x) for x in lam), int(carry) % 4)
        if key in self._proj_cache:
            return self._proj_cache[key]
        D1 = self.project_vec_law(self.gs_vec_law, key[0], key[1])
        D2 = self.project_vec_law(self.fum_vec_law, key[0], key[1])
        D = convolve1d(D1, D2, self.RF)
        self._proj_cache[key] = D
        return D


# ---------------------------------------------------------------------------
# Sage polynomial backend for projected 1D convolution powers
# ---------------------------------------------------------------------------

class ProjectionTailEngine:
    def __init__(self, laws: DAWNPrimeMu4Laws):
        self.laws = laws
        self.RF = laws.RF
        self.PR = PolynomialRing(self.RF, "X")
        self.X = self.PR.gen()

    def dist_to_poly(self, D):
        if not D:
            return self.PR(0), 0
        lo = min(D.keys())
        off = -lo
        P = self.PR(0)
        X = self.X
        RF = self.RF
        for k, p in D.items():
            P += RF(p) * (X ** int(k + off))
        return P, off

    def base_poly(self, lam, carry):
        key = (tuple(int(x) for x in lam), int(carry) % 4)
        if key not in self.laws._poly_cache:
            D = self.laws.base_projection_law(key[0], key[1])
            self.laws._poly_cache[key] = self.dist_to_poly(D)
        return self.laws._poly_cache[key]

    def poly_power(self, lam, carry, exp):
        key = (tuple(int(x) for x in lam), int(carry) % 4, int(exp))
        if key in self.laws._power_cache:
            return self.laws._power_cache[key]
        if exp == 0:
            out = (self.PR(1), 0)
        else:
            P, off = self.base_poly(lam, carry)
            out = (P ** int(exp), int(off) * int(exp))
        self.laws._power_cache[key] = out
        return out

    def projection_poly_for_group(self, lam, r):
        r = int(r)
        nu = self.laws.nu
        e0 = r + 1
        e1 = nu - r - 1
        P0, off0 = self.poly_power(lam, 0, e0)
        P1, off1 = self.poly_power(lam, 1, e1)
        return P0 * P1, off0 + off1

    def tail_gt_group(self, lam, r, threshold):
        """P[<lam,Z_[r]> > threshold]."""
        P, off = self.projection_poly_for_group(lam, r)
        deg0 = int(threshold) + int(off)
        if deg0 <= 0:
            return self.RF(1)
        if deg0 > P.degree():
            return self.RF(0)
        s = self.RF(0)
        for j in range(deg0, P.degree() + 1):
            s += P[j]
        return s


# ---------------------------------------------------------------------------
# wrap-decoder projection bound
# ---------------------------------------------------------------------------

def lam_pair(a, b, sa, sb):
    v = [0, 0, 0, 0]
    v[a] += int(sa)
    v[b] += int(sb)
    return tuple(v)


def pair_list(pair_mode):
    if pair_mode == "cross":
        return [(0, 1), (0, 3), (2, 1), (2, 3)]
    if pair_mode == "all":
        return [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    raise ValueError("pair_mode must be 'cross' or 'all'")


def needed_lambdas(pair_mode):
    S = set()
    for a, b in pair_list(pair_mode):
        for sa in (+1, -1):
            for sb in (+1, -1):
                S.add(lam_pair(a, b, sa, sb))
    return sorted(S)


def pair_abs_sum_bound(engine, r, a, b, threshold):
    """Union/projection bound for P(|Z_a|+|Z_b| > threshold)."""
    RF = engine.RF
    p = RF(0)
    for sa in (+1, -1):
        for sb in (+1, -1):
            p += engine.tail_gt_group(lam_pair(a, b, sa, sb), r, threshold)
    return min(RF(1), p)


def group_bad_projection_bound(engine, r, pair_mode="cross"):
    q = engine.laws.q
    RF = engine.RF
    p = RF(0)
    for a, b in pair_list(pair_mode):
        p += pair_abs_sum_bound(engine, r, a, b, q)
    return min(RF(1), p)


def precompute_base(engine, pair_mode):
    """Precompute base projection polynomials before forking.

    With --start-method fork, these cached Sage objects are inherited copy-on-write by workers.
    """
    for lam in needed_lambdas(pair_mode):
        engine.base_poly(lam, 0)
        engine.base_poly(lam, 1)


def precompute_powers(engine, pair_mode):
    """Optional memory-heavy precomputation of all powers needed for all r."""
    nu = engine.laws.nu
    for lam in needed_lambdas(pair_mode):
        for carry in (0, 1):
            for exp in range(nu + 1):
                engine.poly_power(lam, carry, exp)


def log2_RF(x, RF):
    x = RF(x)
    if x <= 0:
        return "-inf"
    return str(x.log() / RF(2).log())


def log2_RF_float(x, RF):
    x = RF(x)
    if x <= 0:
        return float("-inf")
    return float(x.log() / RF(2).log())


def sci_RF(x, digits=16):
    return f"{x:.{digits}e}"


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, bool)) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        return int(value)
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        pass
    return str(value)


# ---------------------------------------------------------------------------
# Multiprocessing workers
# ---------------------------------------------------------------------------

_WORKER_ENGINE = None
_WORKER_PAIR_MODE = None
_WORKER_DIGITS = 80


def _worker_init_from_config(config):
    global _WORKER_ENGINE, _WORKER_PAIR_MODE, _WORKER_DIGITS
    RF = RealField(config["prec"])
    laws = DAWNPrimeMu4Laws(config["params"], RF, message_model=config["message"])
    engine = ProjectionTailEngine(laws)
    if config.get("precompute_base", True):
        precompute_base(engine, config["pair_mode"])
    if config.get("precompute_powers", False):
        precompute_powers(engine, config["pair_mode"])
    _WORKER_ENGINE = engine
    _WORKER_PAIR_MODE = config["pair_mode"]
    _WORKER_DIGITS = config["digits"]


def _worker_compute_r(r):
    pr = group_bad_projection_bound(_WORKER_ENGINE, int(r), pair_mode=_WORKER_PAIR_MODE)
    return int(r), f"{pr:.{_WORKER_DIGITS}e}"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def make_params(args):
    p = dict(PARAMS[args.param])
    for name in ("n", "q", "kg", "kf", "ks", "ke", "step"):
        val = getattr(args, name)
        if val is not None:
            p[name] = val
    if p["n"] % 4 != 0:
        raise ValueError("n must be divisible by 4")
    return p


def available_start_method(requested):
    methods = mp.get_all_start_methods()
    if requested == "auto":
        if "fork" in methods:
            return "fork"
        return methods[0]
    if requested not in methods:
        raise ValueError(f"start method {requested!r} unavailable; available={methods}")
    return requested


def run(args):
    params = make_params(args)
    RF = RealField(args.prec)
    nu = params["n"] // 4
    digits = max(30, int(args.prec * 0.30103) + 8)

    print("# DAWN prime mu=4 group DFR estimator with multiprocessing")
    print(f"param={args.param}, n={params['n']}, q={params['q']}, nu={nu}")
    # print(f"kg={params['kg']}, kf={params['kf']}, ks={params['ks']}, ke={params['ke']}, step={params['step']}")
    print(f"message={args.message}, pair_mode={args.pair_mode}, precision={args.prec} bits")

    if args.stationary:
        r_values = [args.r if args.r is not None else (nu - 1)]
        multiplier = nu
    elif args.r is not None:
        r_values = [args.r]
        multiplier = 1
    else:
        r_values = list(range(nu))
        multiplier = 1

    jobs = max(1, int(args.jobs))
    total = RF(0)
    max_pr = RF(0)

    if jobs == 1:
        laws = DAWNPrimeMu4Laws(params, RF, message_model=args.message)
        engine = ProjectionTailEngine(laws)
        precompute_base(engine, args.pair_mode)
        if args.precompute_powers:
            precompute_powers(engine, args.pair_mode)
        print(f"gs_vec_support={len(laws.gs_vec_law)}, fum_vec_support={len(laws.fum_vec_law)}")
        for idx, r in enumerate(r_values):
            pr = group_bad_projection_bound(engine, r, pair_mode=args.pair_mode)
            total += pr
            max_pr = max(max_pr, pr)
            if args.verbose or len(r_values) <= 8:
                print(f"r={r:4d}: p_bad_bound={sci_RF(pr)} log2={log2_RF(pr, RF)}")
            elif idx % args.progress_every == 0:
                print(f"progress r={r:4d}: partial_sum={sci_RF(total)} log2={log2_RF(total, RF)}")
    else:
        start = available_start_method(args.start_method)
        print(f"jobs={jobs}, start_method={start}, chunksize={args.chunksize}")
        config = dict(
            params=params,
            prec=args.prec,
            message=args.message,
            pair_mode=args.pair_mode,
            precompute_base=True,
            precompute_powers=args.precompute_powers,
            digits=digits,
        )

        # For fork, build once in parent and let workers inherit it copy-on-write.
        # For spawn/forkserver, each worker initializes its own engine from config.
        global _WORKER_ENGINE, _WORKER_PAIR_MODE, _WORKER_DIGITS
        ctx = mp.get_context(start)
        if start == "fork":
            laws = DAWNPrimeMu4Laws(params, RF, message_model=args.message)
            engine = ProjectionTailEngine(laws)
            precompute_base(engine, args.pair_mode)
            if args.precompute_powers:
                precompute_powers(engine, args.pair_mode)
            _WORKER_ENGINE = engine
            _WORKER_PAIR_MODE = args.pair_mode
            _WORKER_DIGITS = digits
            print(f"gs_vec_support={len(laws.gs_vec_law)}, fum_vec_support={len(laws.fum_vec_law)}")
            pool_kwargs = {}
        else:
            pool_kwargs = dict(initializer=_worker_init_from_config, initargs=(config,))

        with ctx.Pool(processes=jobs, **pool_kwargs) as pool:
            for idx, (r, pr_s) in enumerate(pool.imap_unordered(_worker_compute_r, r_values, chunksize=args.chunksize)):
                pr = RF(pr_s)
                total += pr
                max_pr = max(max_pr, pr)
                if args.verbose or len(r_values) <= 8:
                    print(f"r={r:4d}: p_bad_bound={sci_RF(pr)} log2={log2_RF(pr, RF)}")
                elif idx % args.progress_every == 0:
                    print(f"progress done={idx+1:4d}/{len(r_values)}: partial_sum={sci_RF(total)} log2={log2_RF(total, RF)}")

    dfr = min(RF(1), RF(multiplier) * total)
    print("# result")
    print(f"max_group_bound={sci_RF(max_pr)} log2={log2_RF(max_pr, RF)}")
    if args.stationary:
        print("stationary_multiplier=nu  # faster; assumes selected r is representative")
    print(f"DFR_no_group_independence_upper={sci_RF(dfr)} log2={log2_RF(dfr, RF)}")
    return {
        "method": "dawn_prime_mu4_group_projected_tail",
        "param": args.param,
        "probability": float(dfr),
        "log2": log2_RF_float(dfr, RF),
        "max_group_bound": float(max_pr),
        "max_group_log2": log2_RF_float(max_pr, RF),
        "settings": {
            "precision_bits": args.prec,
            "message": args.message,
            "pair_mode": args.pair_mode,
            "stationary": bool(args.stationary),
            "r": args.r,
            "jobs": args.jobs,
            "start_method": args.start_method,
        },
    }


def write_results(path, rows, args):
    payload = {
        "schema_version": 1,
        "precision_bits": args.prec,
        "rows": rows,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"Wrote {path}")


def run_for_param(param_key, args):
    row_args = copy(args)
    row_args.param = param_key
    result = run(row_args)
    return param_key, result


def main():
    ap = argparse.ArgumentParser(description="DAWN prime mu=4 group DFR estimator using t=1+Y^2 and w=1+Y.")
    ap.add_argument("--param", choices=sorted(PARAMS), default="DAWN-prime-128")
    ap.add_argument("--all", action="store_true", help="compute all registered rows")
    ap.add_argument("--documented", action="store_true", help="write the documented table values without recomputing the convolution")
    ap.add_argument("--list-params", action="store_true", help="list registered DFR parameter keys and exit")
    ap.add_argument("--output", help="write JSON output compatible with build_parameter_tables.py")
    ap.add_argument("--prec", type=int, default=256, help="MPFR RealField precision in bits")
    ap.add_argument("--message", choices=["random", "ones", "zero", "paper-coeff-avg"], default="random")
    ap.add_argument("--pair-mode", choices=["cross", "all"], default="cross")
    ap.add_argument("--stationary", action="store_true", help="compute one group and multiply by n/4")
    ap.add_argument("--r", type=int, default=None, help="compute only residue group r")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--progress-every", type=int, default=8)

    ap.add_argument("--jobs", type=int, default=1, help="number of worker processes")
    ap.add_argument("--chunksize", type=int, default=1)
    ap.add_argument("--start-method", choices=["auto", "fork", "spawn", "forkserver"], default="fork")
    ap.add_argument("--precompute-powers", action="store_true", help="memory-heavy cache of all projection powers before evaluation")

    # Parameter overrides.
    ap.add_argument("--n", type=int)
    ap.add_argument("--q", type=int)
    ap.add_argument("--kg", type=int)
    ap.add_argument("--kf", type=int)
    ap.add_argument("--ks", type=int)
    ap.add_argument("--ke", type=int)
    ap.add_argument("--step", type=int)

    args = ap.parse_args()

    param_keys = [args.param]
    rows = [run_for_param(param_key, args) for param_key in param_keys]

    if args.output:
        write_results(args.output, rows, args)


if __name__ == "__main__":
    main()
