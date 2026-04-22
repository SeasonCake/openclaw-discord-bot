"""
单元测试：standard_engine 的 sub_round 状态机。

覆盖：
- 各 sub_round 碾压阈值
- 持位 / 退出合并
- 流拍 / 全退 边界
- advance_to_next_item_or_end 转件 + 终局
- CLI dispatch：cmd_bid / cmd_withdraw 在 standard 模式的分支
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from standard_engine import (  # noqa: E402
    advance_to_next_item_or_end,
    apply_sub_round_bids,
    check_item_end,
    finalize_item,
    human_is_leading,
    increment_sub_round,
)
from state import HUMAN_ID, new_state  # noqa: E402


# ---------- fixtures ----------

def std_state(seed: int = 42, **kwargs) -> dict:
    """创建 standard 模式 state，便于测试 mutations。"""
    defaults = dict(max_rounds=4, lot_rounds=[4], initial_budget=2000)
    defaults.update(kwargs)
    return new_state(f"t_{seed}", seed=seed, mode="standard", **defaults)


# ============================================================================
# check_item_end：碾压阈值
# ============================================================================

def test_squash_sub_round_1_at_1_8x():
    """sub_round 1：max / second >= 1.8 → squash。"""
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["history"] = [{
        "sub_round": 1,
        "new_bids": {"human": 1800, "老周头": 500, "Miles": 100},
        "pool": {"human": 1800, "老周头": 500, "Miles": 100},
        "withdrawn": [],
        "prev_leader": None,
        "prev_max_bid": 0,
        "max_bid": 1800,
        "max_bidder": "human",
    }]
    cis["current_max_bid"] = 1800
    cis["current_max_bidder"] = "human"
    assert check_item_end(st) == "squash"


def test_no_squash_sub_round_1_below_1_8x():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["history"] = [{
        "sub_round": 1,
        "new_bids": {"human": 1000, "老周头": 700},
        "pool": {"human": 1000, "老周头": 700},
        "withdrawn": [],
        "prev_leader": None,
        "prev_max_bid": 0,
        "max_bid": 1000,
        "max_bidder": "human",
    }]
    cis["current_max_bid"] = 1000
    cis["current_max_bidder"] = "human"
    # 1000 / 700 = 1.43 < 1.8 → 继续
    assert check_item_end(st) is None


def test_squash_sub_round_2_at_1_5x():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["sub_round"] = 2
    cis["history"] = [
        {
            "sub_round": 1, "new_bids": {}, "pool": {}, "withdrawn": [],
            "prev_leader": None, "prev_max_bid": 0,
            "max_bid": 500, "max_bidder": "老周头",
        },
        {
            "sub_round": 2,
            "new_bids": {"human": 800},
            "pool": {"human": 800, "老周头": 500},
            "withdrawn": [],
            "prev_leader": "老周头",
            "prev_max_bid": 500,
            "max_bid": 800,
            "max_bidder": "human",
        },
    ]
    cis["current_max_bid"] = 800
    cis["current_max_bidder"] = "human"
    # 800 / 500 = 1.6 >= 1.5 → squash
    assert check_item_end(st) == "squash"


def test_no_squash_sub_round_2_below_1_5x():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["sub_round"] = 2
    cis["history"] = [
        {
            "sub_round": 1, "new_bids": {}, "pool": {}, "withdrawn": [],
            "prev_leader": None, "prev_max_bid": 0,
            "max_bid": 761, "max_bidder": "艺姐",
        },
        {
            "sub_round": 2,
            "new_bids": {"human": 900},
            "pool": {"human": 900, "艺姐": 761},
            "withdrawn": [],
            "prev_leader": "艺姐",
            "prev_max_bid": 761,
            "max_bid": 900,
            "max_bidder": "human",
        },
    ]
    cis["current_max_bid"] = 900
    cis["current_max_bidder"] = "human"
    # 900 / 761 = 1.18 < 1.5 → 继续（这是真实 bug 案例）
    assert check_item_end(st) is None


def test_final_sub_round_4_always_ends():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["sub_round"] = 4
    cis["history"] = [{
        "sub_round": 4,
        "new_bids": {"human": 1000, "老周头": 950},
        "pool": {"human": 1000, "老周头": 950},
        "withdrawn": [],
        "prev_leader": None,
        "prev_max_bid": 0,
        "max_bid": 1000,
        "max_bidder": "human",
    }]
    cis["current_max_bid"] = 1000
    cis["current_max_bidder"] = "human"
    # 1000 / 950 = 1.05 < 1.2，但 sub_round 4 无条件结束
    assert check_item_end(st) == "final_sub_round"


def test_all_others_withdrew_ends_item():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["sub_round"] = 2
    cis["active_participants"] = ["human"]  # 只剩人类
    cis["withdrawn"] = [n for n in st["active_ais"]]
    cis["current_max_bid"] = 500
    cis["current_max_bidder"] = "human"
    cis["history"] = [{
        "sub_round": 1,
        "new_bids": {"human": 500},
        "pool": {"human": 500},
        "withdrawn": [],
        "prev_leader": None,
        "prev_max_bid": 0,
        "max_bid": 500,
        "max_bidder": "human",
    }]
    assert check_item_end(st) == "all_others_withdrew"


def test_no_bids_passes_item():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["sub_round"] = 1
    cis["history"] = [{
        "sub_round": 1,
        "new_bids": {},
        "pool": {},
        "withdrawn": list(cis["active_participants"]),
        "prev_leader": None,
        "prev_max_bid": 0,
        "max_bid": 0,
        "max_bidder": None,
    }]
    cis["current_max_bid"] = 0
    cis["current_max_bidder"] = None
    assert check_item_end(st) == "no_bids"


# ============================================================================
# apply_sub_round_bids：持位 + 退出合并
# ============================================================================

def test_apply_sub_round_1_all_players_bid():
    st = std_state(seed=1)
    ai_decisions = {"老周头": 400, "Miles": 200, "艺姐": 600}
    apply_sub_round_bids(st, human_action=500, ai_decisions=ai_decisions)

    cis = st["current_item_state"]
    assert cis["current_max_bid"] == 600
    assert cis["current_max_bidder"] == "艺姐"
    assert cis["withdrawn"] == []
    assert len(cis["history"]) == 1
    assert cis["history"][0]["new_bids"]["human"] == 500


def test_apply_sub_round_2_leader_holds():
    """sub_round 2：前领跑者持位，新领跑者由 pool 决定。"""
    st = std_state(seed=1)
    cis = st["current_item_state"]
    # 模拟 sub_round 1 之后：艺姐领跑 $600
    cis["current_max_bid"] = 600
    cis["current_max_bidder"] = "艺姐"
    cis["sub_round"] = 2
    cis["history"].append({
        "sub_round": 1, "new_bids": {}, "pool": {}, "withdrawn": [],
        "prev_leader": None, "prev_max_bid": 0,
        "max_bid": 600, "max_bidder": "艺姐",
    })

    # human 出 700，其他 AI 退
    apply_sub_round_bids(st, human_action=700, ai_decisions={"老周头": None, "Miles": None})

    assert cis["current_max_bid"] == 700
    assert cis["current_max_bidder"] == "human"
    # 艺姐持位入池
    last = cis["history"][-1]
    assert last["pool"]["艺姐"] == 600
    assert last["pool"]["human"] == 700
    assert "老周头" in cis["withdrawn"]
    assert "Miles" in cis["withdrawn"]


def test_apply_withdrawn_ai_removed_from_active():
    st = std_state(seed=1)
    apply_sub_round_bids(st, human_action=500, ai_decisions={"老周头": None, "Miles": 200, "艺姐": 400})
    cis = st["current_item_state"]
    assert "老周头" in cis["withdrawn"]
    assert "老周头" not in cis["active_participants"]
    assert "Miles" in cis["active_participants"]


def test_apply_human_none_withdraws_when_not_leading():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["current_max_bid"] = 500
    cis["current_max_bidder"] = "艺姐"
    cis["sub_round"] = 2
    cis["history"].append({
        "sub_round": 1, "new_bids": {}, "pool": {}, "withdrawn": [],
        "prev_leader": None, "prev_max_bid": 0,
        "max_bid": 500, "max_bidder": "艺姐",
    })
    apply_sub_round_bids(st, human_action=None, ai_decisions={"老周头": None, "Miles": None})
    assert HUMAN_ID in cis["withdrawn"]


def test_apply_human_leading_auto_holds():
    """sub_round 2 人类领跑：human_action 被忽略，人类不会进 withdrawn。"""
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["current_max_bid"] = 500
    cis["current_max_bidder"] = HUMAN_ID
    cis["sub_round"] = 2
    cis["history"].append({
        "sub_round": 1, "new_bids": {}, "pool": {}, "withdrawn": [],
        "prev_leader": None, "prev_max_bid": 0,
        "max_bid": 500, "max_bidder": HUMAN_ID,
    })
    apply_sub_round_bids(st, human_action=None, ai_decisions={"老周头": None, "Miles": None, "艺姐": None})
    assert HUMAN_ID not in cis["withdrawn"]
    # 领跑者持位 $500 仍然是最高
    assert cis["current_max_bidder"] == HUMAN_ID
    assert cis["current_max_bid"] == 500


# ============================================================================
# finalize_item：扣预算 + inventory
# ============================================================================

def test_finalize_deducts_budget_and_adds_inventory():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    initial_budget = st["players"]["human"]["budget"]
    item_id = cis["item_id"]

    cis["current_max_bid"] = 800
    cis["current_max_bidder"] = "human"
    cis["history"].append({
        "sub_round": 1,
        "new_bids": {"human": 800},
        "pool": {"human": 800},
        "withdrawn": [],
        "prev_leader": None,
        "prev_max_bid": 0,
        "max_bid": 800,
        "max_bidder": "human",
    })

    result = finalize_item(st, "squash")

    assert result["winner"] == "human"
    assert result["winning_bid"] == 800
    assert st["players"]["human"]["budget"] == initial_budget - 800
    assert item_id in st["players"]["human"]["inventory"]
    assert len(st["items_done"]) == 1
    assert st["items_done"][0]["end_reason"] == "squash"


def test_finalize_no_bids_leaves_budgets_unchanged():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["current_max_bid"] = 0
    cis["current_max_bidder"] = None
    cis["history"].append({
        "sub_round": 1, "new_bids": {}, "pool": {}, "withdrawn": [],
        "prev_leader": None, "prev_max_bid": 0,
        "max_bid": 0, "max_bidder": None,
    })

    budgets_before = {k: p["budget"] for k, p in st["players"].items()}
    result = finalize_item(st, "no_bids")

    assert result["winner"] is None
    assert result["winning_bid"] == 0
    for k, p in st["players"].items():
        assert p["budget"] == budgets_before[k]


# ============================================================================
# advance_to_next_item_or_end
# ============================================================================

def test_advance_to_next_item():
    st = std_state(seed=1, max_rounds=4, lot_rounds=[4])
    # 假装 item 1 已结算
    st["current_round"] = 1
    st["items_done"].append({"item_id": st["items_queue"][0]})

    advance_to_next_item_or_end(st)

    assert st["current_round"] == 2
    assert st["current_item"] == st["items_queue"][1]
    assert st["status"] == "awaiting_human_bid"
    assert "current_item_state" in st
    assert st["current_item_state"]["sub_round"] == 1
    assert st["current_item_state"]["current_max_bid"] == 0


def test_advance_last_item_ends_game():
    st = std_state(seed=1, max_rounds=4)
    st["current_round"] = 4
    advance_to_next_item_or_end(st)

    assert st["status"] == "ended"
    assert st["current_item"] is None
    assert "current_item_state" not in st


def test_increment_sub_round_preserves_leader():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["current_max_bid"] = 500
    cis["current_max_bidder"] = "艺姐"
    cis["sub_round"] = 1
    cis["current_bids"] = {"human": 300}

    increment_sub_round(st)

    assert cis["sub_round"] == 2
    assert cis["current_max_bid"] == 500  # 持位
    assert cis["current_max_bidder"] == "艺姐"
    assert cis["current_bids"] == {}  # 清空


# ============================================================================
# 辅助判断
# ============================================================================

def test_human_is_leading():
    st = std_state(seed=1)
    cis = st["current_item_state"]
    cis["current_max_bidder"] = HUMAN_ID
    assert human_is_leading(st) is True
    cis["current_max_bidder"] = "艺姐"
    assert human_is_leading(st) is False


# ============================================================================
# 真实 bug 回归：sub_round 2 YiJie 持位 $761 不被漏掉
# ============================================================================

def test_regression_held_leader_counted_in_squash_check():
    """
    真实案例：sub_round 1 艺姐 $761 领跑，sub_round 2 人类 $900 raise。
    pool = {人类: 900, 艺姐: 761}，900/761 = 1.18 < 1.5 → 应继续。
    之前 bug：history 只存 new_bids={人类:900}，二查者为空 → 误判为 squash。
    """
    st = std_state(seed=42, max_rounds=4)
    cis = st["current_item_state"]

    # sub_round 1：模拟艺姐胜
    apply_sub_round_bids(
        st, human_action=500,
        ai_decisions={"老周头": 507, "Miles": 205, "艺姐": 761},
    )
    assert cis["current_max_bidder"] == "艺姐"
    assert check_item_end(st) is None  # 1.50× not ≥ 1.8×

    increment_sub_round(st)

    # sub_round 2：人类 900 raise，其他 AI 退出
    apply_sub_round_bids(
        st, human_action=900,
        ai_decisions={"老周头": None, "Miles": None},  # 艺姐不在 ai_decisions（领跑者持位）
    )
    assert cis["current_max_bidder"] == "human"
    assert cis["current_max_bid"] == 900
    # pool 必须含艺姐的 $761
    last = cis["history"][-1]
    assert last["pool"]["艺姐"] == 761
    # 900/761 = 1.18 < 1.5 → 不应 squash
    assert check_item_end(st) is None
