from __future__ import annotations

from collections import Counter

from recon.models import ACTIVE, CLOSED, SUSPENDED
from recon.synthetic import INJECTION_PLAN, generate_datasets
from recon.values import parse_int


def test_clean_summary_balance_equation_holds_for_every_account(datasets):
    clean, _ = datasets
    for row in clean.summary:
        assert row["opening_balance"] + row["deposit_amount"] - row["withdrawal_amount"] == row["closing_balance"]


def test_answer_file_matches_injection_plan(datasets):
    _, injected = datasets
    per_rule = Counter(rule for rule, _ in {(a["expected_rule"], a["error_id"]) for a in injected.answer})
    assert dict(per_rule) == INJECTION_PLAN
    assert sum(INJECTION_PLAN.values()) == 81


def test_clean_data_shape(datasets):
    clean, _ = datasets
    status = Counter(a.status for a in clean.accounts)
    assert status == {ACTIVE: 185, CLOSED: 10, SUSPENDED: 5}
    assert 4900 <= len(clean.transactions) <= 5100
    assert len({t["txn_id"] for t in clean.transactions}) == len(clean.transactions)
    suspended = {a.account_no for a in clean.accounts if a.status == SUSPENDED}
    assert all(t["direction"] == "D" for t in clean.transactions if t["account_no"] in suspended)


def test_clean_data_contains_boundary_cases(datasets):
    clean, _ = datasets
    times = {t["txn_dt"][11:] for t in clean.transactions}
    assert {"00:00:00", "23:59:59"} <= times
    assert any(parse_int(t["amount"]) >= 1_000_000_000 for t in clean.transactions)
    assert any("," in t["amount"] for t in clean.transactions)
    zero_txn = [r for r in clean.summary if r["deposit_count"] == 0 and r["withdrawal_count"] == 0]
    assert len(zero_txn) >= 3
    assert any(a.open_date == clean.base_date for a in clean.accounts)
    assert any(a.close_date == clean.base_date for a in clean.accounts)


def test_same_seed_same_data_and_different_seed_different_data():
    first_clean, first_injected = generate_datasets(seed=1)
    second_clean, second_injected = generate_datasets(seed=1)
    other_clean, _ = generate_datasets(seed=2)
    assert first_clean.transactions == second_clean.transactions
    assert first_injected.transactions == second_injected.transactions
    assert first_injected.answer == second_injected.answer
    assert first_clean.transactions != other_clean.transactions


def test_other_seeds_also_evaluate_cleanly(workspace):
    # 시드에 기대 우연히 통과한 것이 아닌지 다른 시드로도 확인한다.
    import pandas as pd

    from recon.evaluation import evaluate
    from recon.pipeline import run_pipeline

    for seed in (7, 2026):
        clean, injected = generate_datasets(seed=seed)
        clean_result = run_pipeline(clean.files(), clean.base_date, repository=workspace["repo"], data_dir=workspace["data_dir"])
        assert clean_result.validation.issues.empty
        result = run_pipeline(injected.files(), injected.base_date, repository=workspace["repo"], data_dir=workspace["data_dir"])
        ev = evaluate(result.validation.issues, pd.DataFrame(injected.answer))
        assert ev.passed, (seed, ev.missed, ev.false_positives)
