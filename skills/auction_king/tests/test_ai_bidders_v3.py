"""
单元测试：v3 反应式决策层（decide_bid_v3 + compute_ai_bid_v3）。

覆盖：
- 基类默认行为（sub_round 1 走 bid_sealed）
- 5 人格在 sub_round 2+ 的反应曲线
- 归一化（None / 超预算 / 低于底价）
- 确定性（同 seed/round/sub_round 同结果）
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ai_bidders import (  # noqa: E402
    AhGui,
    BidContextV3,
    Kai,
    Miles,
    OldZhou,
    YiJie,
    _min_raise,
    _normalize_v3_bid,
    compute_ai_bid_v3,
)
from items import Item  # noqa: E402


# ---------- fixtures ----------

def make_item(category: str, est_mid: int = 700, base: int = 200) -> Item:
    lo, hi = est_mid - 200, est_mid + 200
    return Item(
        id="test_item",
        type="item",
        name=f"测试{category}",
        base_price=base,
        description="test",
        hints=[f"专家估价 ${lo}-${hi}"],
        category=category,
        true_value=est_mid,
    )


def v3ctx(
    *,
    item: Item,
    sub_round: int = 1,
    current_max_bid: int = 0,
    current_max_bidder=None,
    round_num: int = 1,
    total_rounds: int = 5,
    remaining: int = 2000,
    inventory: int = 0,
    min_raise_ratio: float = 1.05,
) -> BidContextV3:
    return BidContextV3(
        round_num=round_num,
        total_rounds=total_rounds,
        remaining_budget=remaining,
        inventory_count=inventory,
        item=item,
        sub_round=sub_round,
        current_max_bid=current_max_bid,
        current_max_bidder=current_max_bidder,
        min_raise_ratio=min_raise_ratio,
    )


def rng(seed: int = 0) -> random.Random:
    return random.Random(seed)


# ============================================================================
# 基础工具
# ============================================================================

def test_min_raise_sub_round_1_is_zero():
    item = make_item("玉器", est_mid=500)
    ctx = v3ctx(item=item, sub_round=1, current_max_bid=0)
    assert _min_raise(ctx) == 0


def test_min_raise_uses_ratio():
    item = make_item("玉器", est_mid=500)
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=500, min_raise_ratio=1.05)
    # 500 * 1.05 = 525, +1 = 526
    assert _min_raise(ctx) == 526


def test_normalize_none_returns_none():
    item = make_item("玉器")
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=500)
    assert _normalize_v3_bid(None, ctx) is None


def test_normalize_below_base_price_sub_round_1_returns_none():
    item = make_item("玉器", base=200)
    ctx = v3ctx(item=item, sub_round=1)
    assert _normalize_v3_bid(100, ctx) is None


def test_normalize_below_min_raise_sub_round_2_returns_none():
    item = make_item("玉器")
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=500)
    # min_raise = 526; 520 < 526 → None
    assert _normalize_v3_bid(520, ctx) is None


def test_normalize_truncates_to_budget():
    item = make_item("玉器", base=100)
    ctx = v3ctx(item=item, sub_round=1, remaining=800)
    assert _normalize_v3_bid(1500, ctx) == 800


# ============================================================================
# OldZhou：保守
# ============================================================================

def test_oldzhou_sub_round_1_falls_back_to_bid_sealed():
    bidder = OldZhou(rng=rng())
    item = make_item("玉器", est_mid=500)  # 非专长
    ctx = v3ctx(item=item, sub_round=1)
    bid = bidder.decide_bid_v3(ctx)
    # bid_sealed 打 7 折
    assert bid is not None and bid <= 360


def test_oldzhou_withdraws_when_bubble_above_ceiling():
    """current_max_bid = est * 1.2 → 超过 1.15 泡沫阈值，直接退。"""
    bidder = OldZhou(rng=rng())
    item = make_item("玉器", est_mid=500)
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=600)
    assert bidder.decide_bid_v3(ctx) is None


def test_oldzhou_follows_minimum_raise_when_safe():
    bidder = OldZhou(rng=rng())
    item = make_item("玉器", est_mid=500)
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=300)
    bid = bidder.decide_bid_v3(ctx)
    # min_raise = 316; 316 <= est * 0.90 = 450 → 跟
    assert bid == 316


def test_oldzhou_specialty_porcelain_extends_ceiling():
    """瓷器 ceiling 从 est*0.9 放宽到 est*0.95。"""
    bidder = OldZhou(rng=rng())
    item = make_item("瓷器", est_mid=500)
    # min_raise = 431 (410 * 1.05 + 1); est*0.9=450 非专长会退；est*0.95=475 专长能跟
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=451)
    bid = bidder.decide_bid_v3(ctx)
    assert bid is not None
    assert bid == 474  # 451 * 1.05 + 1 = 474.55 → 474


# ============================================================================
# Kai：FOMO
# ============================================================================

def test_kai_sub_round_1_falls_back_to_bid_sealed():
    bidder = Kai(rng=rng())
    item = make_item("书画", est_mid=500)
    ctx = v3ctx(item=item, sub_round=1)
    bid = bidder.decide_bid_v3(ctx)
    assert bid is not None and bid > 500  # Kai 激进加价


def test_kai_keeps_raising_when_affordable():
    bidder = Kai(rng=rng())
    item = make_item("玉器", est_mid=500)
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=600, remaining=2000)
    bid = bidder.decide_bid_v3(ctx)
    # 600 * 1.08 ~= 648 plus a bit of randomness
    assert bid is not None
    assert bid >= 648


def test_kai_withdraws_only_when_broke():
    bidder = Kai(rng=rng())
    item = make_item("玉器", est_mid=500)
    # 预算只剩 300，current_max 500，1.08 * 500 = 540 > 300 * 0.95 = 285 → 退
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=500, remaining=300)
    assert bidder.decide_bid_v3(ctx) is None


def test_kai_fomo_late_empty_inventory_spikes_raise():
    """空仓 + 末轮 → 用 1.15× 倍率而非 1.08×。"""
    bidder_normal = Kai(rng=rng(1))
    bidder_fomo = Kai(rng=rng(1))
    item = make_item("玉器", est_mid=500)
    ctx_normal = v3ctx(
        item=item, sub_round=2, current_max_bid=600,
        round_num=1, total_rounds=5, inventory=1,
    )
    ctx_fomo = v3ctx(
        item=item, sub_round=2, current_max_bid=600,
        round_num=5, total_rounds=5, inventory=0,  # 末轮空仓
    )
    bid_normal = bidder_normal.decide_bid_v3(ctx_normal)
    bid_fomo = bidder_fomo.decide_bid_v3(ctx_fomo)
    assert bid_fomo is not None and bid_normal is not None
    assert bid_fomo > bid_normal  # FOMO 明显加到更高


# ============================================================================
# YiJie：专长品类
# ============================================================================

def test_yijie_specialty_raises_up_to_115pct_of_estimate():
    bidder = YiJie(rng=rng())
    item = make_item("玉器", est_mid=500)  # 专长
    # min_raise = 526; est * 1.15 = 575 → 跟
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=500, inventory=0)
    assert bidder.decide_bid_v3(ctx) == 526


def test_yijie_specialty_withdraws_above_115pct():
    bidder = YiJie(rng=rng())
    item = make_item("书画", est_mid=500)  # 专长
    # current_max 600, min_raise = 631; est*1.15 = 575 → 超过 ceiling → 退
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=600, inventory=0)
    assert bidder.decide_bid_v3(ctx) is None


def test_yijie_non_specialty_caps_at_85pct():
    bidder = YiJie(rng=rng())
    item = make_item("钟表", est_mid=500)  # 非专长
    # est * 0.85 = 425; min_raise at current_max 420 = 442 > 425 → 退
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=420, inventory=0)
    assert bidder.decide_bid_v3(ctx) is None


def test_yijie_non_specialty_follows_only_cheap():
    bidder = YiJie(rng=rng())
    item = make_item("钟表", est_mid=500)
    # current_max 300 → min_raise 316; 316 < 425 → 跟
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=300, inventory=0)
    assert bidder.decide_bid_v3(ctx) == 316


# ============================================================================
# AhGui：陷阱 + 装输
# ============================================================================

def test_ahgui_feign_withdraws_on_sub_round_2():
    """flop_roll<0.15 → 稳定装输，sub_round 2 直接退。"""
    bidder = AhGui(rng=rng(), session_state={"trap_mode": "accurate", "flop_roll": 0.05})
    item = make_item("玉器", est_mid=500, base=150)
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=300)
    assert bidder.decide_bid_v3(ctx) is None


def test_ahgui_accurate_follows_when_below_trap_ceiling():
    bidder = AhGui(rng=rng(42), session_state={"trap_mode": "accurate", "flop_roll": 0.9})
    item = make_item("玉器", est_mid=500, base=150)
    # trap_est ≈ true_value * (1 ± 0.10)；current_max 350 → min_raise 368
    # ceiling = trap_est * 0.98 ~= ~460 → 368 < ceiling → 跟
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=350)
    bid = bidder.decide_bid_v3(ctx)
    assert bid is not None
    assert bid >= 368


def test_ahgui_wild_mode_may_chase_above_accurate_ceiling():
    """wild 模式 ceiling 更高（* 1.10），能追 accurate 模式退出的价位。"""
    item = make_item("玉器", est_mid=500, base=150)
    # trap_est ~ 500; accurate ceiling ≈ 490; wild ceiling ≈ 550
    bidder_a = AhGui(rng=rng(5), session_state={"trap_mode": "accurate", "flop_roll": 0.9})
    bidder_w = AhGui(rng=rng(5), session_state={"trap_mode": "wild", "flop_roll": 0.9})
    ctx = v3ctx(item=item, sub_round=2, current_max_bid=495)
    min_new = _min_raise(ctx)  # 520
    ba = bidder_a.decide_bid_v3(ctx)
    bw = bidder_w.decide_bid_v3(ctx)
    # accurate 因噪声可能退也可能跟；wild 更激进，至少不比 accurate 保守
    if ba is None:
        # 如果 accurate 退了，wild 要么跟（>= min_new）要么也退
        assert bw is None or bw >= min_new
    else:
        assert bw is None or bw >= ba


# ============================================================================
# Miles：狙击
# ============================================================================

def test_miles_withdraws_in_early_rounds():
    """round 1/2 in a 5-round game → 不在狙击窗口 → 退。"""
    bidder = Miles(rng=rng())
    item = make_item("杂项", est_mid=500)
    ctx = v3ctx(
        item=item, sub_round=2, current_max_bid=300,
        round_num=1, total_rounds=5,
    )
    assert bidder.decide_bid_v3(ctx) is None


def test_miles_snipes_in_last_two_rounds():
    """倒数 2 轮进入狙击窗口。"""
    bidder = Miles(rng=rng())
    item = make_item("杂项", est_mid=500, base=150)
    # total=5, round=4 (倒数第2) → snipe_window
    # est*1.4 (misc) = 700; min_raise at 500 = 526 < 700 → 跟
    ctx = v3ctx(
        item=item, sub_round=2, current_max_bid=500,
        round_num=4, total_rounds=5,
    )
    assert bidder.decide_bid_v3(ctx) == 526


def test_miles_misc_category_has_higher_ceiling():
    bidder_misc = Miles(rng=rng())
    bidder_art = Miles(rng=rng())
    item_misc = make_item("杂项", est_mid=500, base=150)
    item_art = make_item("玉器", est_mid=500, base=150)
    # current_max = 580 → min_raise = 610
    # misc ceiling = 700 → 跟；art ceiling = 600 → 退
    ctx_misc = v3ctx(
        item=item_misc, sub_round=2, current_max_bid=580,
        round_num=5, total_rounds=5,
    )
    ctx_art = v3ctx(
        item=item_art, sub_round=2, current_max_bid=580,
        round_num=5, total_rounds=5,
    )
    assert bidder_misc.decide_bid_v3(ctx_misc) == 610
    assert bidder_art.decide_bid_v3(ctx_art) is None


# ============================================================================
# compute_ai_bid_v3 外部入口
# ============================================================================

def test_compute_v3_returns_none_for_withdraw():
    item = make_item("书画", est_mid=500)
    ctx = v3ctx(
        item=item, sub_round=2, current_max_bid=1000,
        round_num=1, total_rounds=5,
    )
    # YiJie 书画专长但 min_raise 1051 > 575 → 退
    result = compute_ai_bid_v3("艺姐", ctx, game_seed=42, ai_session_state={})
    assert result is None


def test_compute_v3_returns_int_for_raise():
    item = make_item("玉器", est_mid=500, base=150)
    ctx = v3ctx(
        item=item, sub_round=2, current_max_bid=300,
        round_num=1, total_rounds=5,
    )
    result = compute_ai_bid_v3("艺姐", ctx, game_seed=42, ai_session_state={})
    assert isinstance(result, int)
    assert result >= _min_raise(ctx)


def test_compute_v3_deterministic_same_seed():
    item = make_item("书画", est_mid=500, base=150)
    ctx = v3ctx(
        item=item, sub_round=1,
        round_num=3, total_rounds=5,
        remaining=2000, inventory=1,
    )
    r1 = compute_ai_bid_v3("Kai", ctx, game_seed=123, ai_session_state={})
    r2 = compute_ai_bid_v3("Kai", ctx, game_seed=123, ai_session_state={})
    assert r1 == r2


def test_compute_v3_never_exceeds_budget():
    item = make_item("书画", est_mid=500, base=150)
    ctx = v3ctx(
        item=item, sub_round=2, current_max_bid=1500,
        round_num=5, total_rounds=5,
        remaining=1600, inventory=0,
    )
    # Kai 在末轮空仓会狂冲；但归一化必须截断
    result = compute_ai_bid_v3("Kai", ctx, game_seed=7, ai_session_state={})
    if result is not None:
        assert result <= 1600


def test_compute_v3_ahgui_session_state_routes_correctly():
    """AhGui 的 session_state 应该影响决策（trap_mode / flop_roll）。"""
    item = make_item("玉器", est_mid=500, base=150)
    ctx = v3ctx(
        item=item, sub_round=2, current_max_bid=300,
        round_num=2, total_rounds=5,
    )
    # 稳定装输
    feign = compute_ai_bid_v3(
        "阿鬼", ctx, game_seed=1,
        ai_session_state={"trap_mode": "accurate", "flop_roll": 0.01},
    )
    # 不装输
    real = compute_ai_bid_v3(
        "阿鬼", ctx, game_seed=1,
        ai_session_state={"trap_mode": "accurate", "flop_roll": 0.9},
    )
    assert feign is None
    assert real is not None


@pytest.mark.parametrize("name", ["老周头", "Kai", "艺姐", "阿鬼", "Miles"])
def test_compute_v3_all_personas_handle_sub_round_1(name):
    """所有人格在 sub_round 1 都能产出合法出价（不崩）。"""
    item = make_item("玉器", est_mid=500, base=150)
    ctx = v3ctx(
        item=item, sub_round=1,
        round_num=1, total_rounds=5,
    )
    state = {}
    if name == "阿鬼":
        state = {"trap_mode": "accurate", "flop_roll": 0.5}
    result = compute_ai_bid_v3(name, ctx, game_seed=42, ai_session_state=state)
    # 结果要么 None，要么是合法的 int
    assert result is None or (isinstance(result, int) and result >= item.base_price)
