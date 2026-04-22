"""
单元测试：v3 mode 分叉与 state schema。

覆盖：
- quick 模式向下兼容（默认 budget/rounds/lot_rounds 与 v2 一致）
- standard 模式随机化范围（budget 2000-3000、rounds 4/5、lot_rounds 不在第 1 轮）
- standard 模式 config 独有字段（squash_thresholds 等）
- standard 模式 current_item_state 结构
- seed 可复现
- 显式参数覆盖 mode 默认值
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from state import (  # noqa: E402
    HUMAN_ID,
    MAX_SUB_ROUNDS_PER_ITEM,
    MIN_RAISE_RATIO,
    SQUASH_THRESHOLDS,
    STANDARD_BUDGET_RANGE,
    STANDARD_ITEMS_CHOICES,
    new_state,
)


# ---------- quick 模式向下兼容 ----------

def test_quick_mode_is_default():
    st = new_state("t_quick_default", seed=1)
    assert st["config"]["mode"] == "quick"


def test_quick_mode_legacy_defaults_unchanged():
    st = new_state("t_quick_legacy", seed=42)
    assert st["config"]["initial_budget"] == 2000
    assert st["config"]["max_rounds"] == 7
    assert st["config"]["lot_rounds"] == [3, 6]


def test_quick_mode_has_no_standard_fields():
    st = new_state("t_quick_clean", seed=42, mode="quick")
    assert "current_item_state" not in st
    assert "squash_thresholds" not in st["config"]
    assert "min_raise_ratio" not in st["config"]
    assert "max_sub_rounds_per_item" not in st["config"]


def test_quick_mode_same_seed_reproducible():
    a = new_state("t_quick_a", seed=777)
    b = new_state("t_quick_b", seed=777)
    # session_id / started_at 不同，其余应完全一致
    keys_that_may_differ = {"session_id", "started_at", "log"}
    for k in a:
        if k in keys_that_may_differ:
            continue
        assert a[k] == b[k], f"key {k} diverged under same seed"


# ---------- standard 模式 ----------

def test_standard_mode_sets_mode_field():
    st = new_state("t_std_mode", seed=1, mode="standard")
    assert st["config"]["mode"] == "standard"


@pytest.mark.parametrize("seed", [1, 17, 42, 100, 2026])
def test_standard_mode_budget_in_range(seed):
    st = new_state(f"t_std_budget_{seed}", seed=seed, mode="standard")
    lo, hi = STANDARD_BUDGET_RANGE
    assert lo <= st["config"]["initial_budget"] <= hi


@pytest.mark.parametrize("seed", [1, 17, 42, 100, 2026])
def test_standard_mode_rounds_in_choices(seed):
    st = new_state(f"t_std_rounds_{seed}", seed=seed, mode="standard")
    assert st["config"]["max_rounds"] in STANDARD_ITEMS_CHOICES


@pytest.mark.parametrize("seed", [1, 17, 42, 100, 2026, 9999])
def test_standard_mode_lot_rounds_valid(seed):
    st = new_state(f"t_std_lot_{seed}", seed=seed, mode="standard")
    max_rounds = st["config"]["max_rounds"]
    lot_rounds = st["config"]["lot_rounds"]
    assert 1 <= len(lot_rounds) <= 2
    for r in lot_rounds:
        assert 2 <= r <= max_rounds, f"lot at round {r} invalid for max_rounds={max_rounds}"
    assert len(set(lot_rounds)) == len(lot_rounds), "duplicate lot round"


def test_standard_mode_config_extras_present():
    st = new_state("t_std_extras", seed=1, mode="standard")
    assert st["config"]["squash_thresholds"] == SQUASH_THRESHOLDS
    assert st["config"]["min_raise_ratio"] == MIN_RAISE_RATIO
    assert st["config"]["max_sub_rounds_per_item"] == MAX_SUB_ROUNDS_PER_ITEM


def test_standard_mode_current_item_state_shape():
    st = new_state("t_std_cis", seed=1, mode="standard")
    cis = st["current_item_state"]
    assert cis["item_id"] == st["current_item"]
    assert cis["sub_round"] == 1
    assert HUMAN_ID in cis["active_participants"]
    for ai in st["active_ais"]:
        assert ai in cis["active_participants"]
    assert cis["withdrawn"] == []
    assert cis["history"] == []
    assert cis["current_bids"] == {}
    assert cis["current_max_bid"] == 0
    assert cis["current_max_bidder"] is None


def test_standard_mode_same_seed_reproducible():
    a = new_state("t_std_a", seed=12345, mode="standard")
    b = new_state("t_std_b", seed=12345, mode="standard")
    assert a["config"]["initial_budget"] == b["config"]["initial_budget"]
    assert a["config"]["max_rounds"] == b["config"]["max_rounds"]
    assert a["config"]["lot_rounds"] == b["config"]["lot_rounds"]
    assert a["items_queue"] == b["items_queue"]
    assert a["active_ais"] == b["active_ais"]


# ---------- 显式参数覆盖 ----------

def test_explicit_budget_overrides_standard_default():
    st = new_state("t_std_ovr_budget", seed=1, mode="standard", initial_budget=2500)
    assert st["config"]["initial_budget"] == 2500


def test_explicit_rounds_overrides_standard_default():
    st = new_state("t_std_ovr_rounds", seed=1, mode="standard", max_rounds=4, lot_rounds=[2])
    assert st["config"]["max_rounds"] == 4
    assert st["config"]["lot_rounds"] == [2]
    assert len(st["items_queue"]) == 4


def test_explicit_lot_rounds_override():
    st = new_state(
        "t_std_ovr_lot",
        seed=1,
        mode="standard",
        max_rounds=5,
        lot_rounds=[2, 4],
    )
    assert st["config"]["lot_rounds"] == [2, 4]


# ---------- 异常 ----------

def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown mode"):
        new_state("t_bad_mode", seed=1, mode="insane")


# ---------- 通用字段（两种模式都要有）----------

@pytest.mark.parametrize("mode", ["quick", "standard"])
def test_both_modes_have_core_fields(mode):
    st = new_state(f"t_core_{mode}", seed=1, mode=mode)
    for k in (
        "session_id", "seed", "config", "active_ais", "players",
        "items_queue", "items_done", "current_round", "current_item",
        "current_type", "current_bids", "status", "log",
    ):
        assert k in st, f"missing core field: {k} (mode={mode})"
    assert st["status"] == "awaiting_human_bid"
    assert st["current_round"] == 1
    assert st["current_item"] == st["items_queue"][0]
