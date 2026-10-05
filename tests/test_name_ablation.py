"""Section 27.4 - mandatory counterparty-name ablation test (30% / 60% / 100% masking)."""

from __future__ import annotations

import pytest

from builders import business, make_request
from se_income_engine.contracts.enums import AnalysisStatus
from se_income_engine.pipeline.analyse import run_analysis_pipeline
from test_unit_spec import strip_names

LEVELS = (0.0, 0.3, 0.6, 1.0)


@pytest.fixture(scope="module")
def ablation():
    out = {}
    for level in LEVELS:
        ctx = run_analysis_pipeline(make_request(strip_names(business(), level).build()))
        out[level] = ctx
    return out


def test_engine_degrades_gracefully_under_name_masking(ablation, capsys):
    base = ablation[0.0]
    base_uwi = float(base.decision.underwriting_income_monthly)
    rows = []
    for level, ctx in ablation.items():
        assert ctx.decision.status in (AnalysisStatus.SUCCESS, AnalysisStatus.REFER_LOW_CONFIDENCE)
        sbci = float(ctx.sbci.sbci_monthly)
        uwi = float(ctx.decision.underwriting_income_monthly or 0)
        rows.append((level, sbci, uwi, ctx.uncertainty.confidence,
                     float(ctx.uncertainty.unresolved_outflow_allowance)))
        assert sbci > 0, "no collapse"
        assert abs(sbci - float(base.sbci.sbci_monthly)) / float(base.sbci.sbci_monthly) < 0.35
        assert uwi <= base_uwi * 1.02, "losing evidence must never raise the policy-selected income"
    with capsys.disabled():
        print("\nmask  SBCI      UWI       confidence  unresolved_outflow_allowance")
        for level, sbci, uwi, conf, allowance in rows:
            print(f"{level:>4.0%}  {sbci:>8,.0f}  {uwi:>8,.0f}  {conf:>10.3f}  {allowance:>12,.0f}")


def test_unresolved_allowance_grows_with_masking(ablation):
    allowances = [float(ablation[level].uncertainty.unresolved_outflow_allowance) for level in LEVELS]
    assert allowances[-1] > allowances[0]
    assert all(b >= a * 0.9 for a, b in zip(allowances, allowances[1:]))
