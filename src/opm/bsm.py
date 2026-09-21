"""Black-Scholes-Merton call valuation, used by both Backsolve and ESOP.

Standard European-call BSM. Continuous dividend yield supported. All inputs
in consistent units (S, K in same currency; T in years; sigma, r, q
annualised). Returns the option's value at issue.

Used internally by `src/opm/backsolve.py` to value each waterfall tranche
as a call on total equity value with strike = breakpoint.
"""

from __future__ import annotations

import math


_SQRT_2 = math.sqrt(2.0)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf. No scipy required, deterministic."""
    return 0.5 * (1.0 + math.erf(x / _SQRT_2))


def bsm_call_value(
    S: float,
    K: float,
    T: float,
    sigma: float,
    r: float,
    q: float = 0.0,
) -> float:
    """European call on a continuous-dividend underlying.

    S: spot (total equity value)
    K: strike (waterfall breakpoint)
    T: time to liquidity in years
    sigma: annualised volatility (e.g. 0.55 for 55%)
    r: continuously-compounded risk-free rate (annualised)
    q: continuous dividend yield (default 0)
    """
    if T <= 0:
        return max(S - K, 0.0)
    if S <= 0:
        return 0.0
    if K <= 0:
        return S * math.exp(-q * T)  # zero-strike → discounted spot
    if sigma <= 0:
        forward = S * math.exp((r - q) * T)
        intrinsic = max(forward - K, 0.0)
        return intrinsic * math.exp(-r * T)

    sigma_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
