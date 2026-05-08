"""Permanent regression: fuzz + Singapore-archetype sweep.

Captures the property-based fuzzer + 10 SG archetypes as pytest tests so
regressions surface in CI rather than requiring a manual fuzz run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from stress_test.fuzzer import run as fuzz_run
from stress_test.sg_archetypes import ARCHETYPES, run_one


def test_fuzz_normal_500_runs_clean():
    rep = fuzz_run(n=500, base_seed=1, mode="normal")
    assert not rep.failures, (
        f"{len(rep.failures)} fuzz failures across {rep.runs} runs:\n"
        + "\n".join(f"  seed {f.seed} {f.invariant}: {f.detail}" for f in rep.failures[:10])
    )


def test_fuzz_pathological_300_runs_clean():
    rep = fuzz_run(n=300, base_seed=5000, mode="patho")
    assert not rep.failures, (
        f"{len(rep.failures)} patho failures:\n"
        + "\n".join(f"  seed {f.seed} {f.invariant}: {f.detail}" for f in rep.failures[:10])
    )


@pytest.mark.parametrize("aid,name,builder", ARCHETYPES, ids=[a[0] for a in ARCHETYPES])
def test_sg_archetype_clean(aid, name, builder):
    r = run_one(aid, name, builder)
    assert r.error is None, f"{aid} crashed: {r.error}"
    assert not r.notes, f"{aid} has invariant violations: {r.notes}"
    assert r.n_breakpoints >= 1
    assert r.n_tranches >= 1
