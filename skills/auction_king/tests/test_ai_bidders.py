"""
单元测试：5 AI 出价公式的边界行为。

这些测试防止未来改动 AI 公式时意外破坏人格一致性。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from ai_bidders import (
    AhGui,
    BidContext,
    Kai,
    Miles,
    OldZhou,
    YiJie,
    estimate_from_hints,
)
from items import Item


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------

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


def ctx(round_num=1, remaining=2000, inventory=0, total=7) -> BidContext:
    return BidContext(
        round_num=round_num,
        total_rounds=total,
        remaining_budget=remaining,
        inventory_count=inventory,
    )


def rng(seed: int = 0) -> random.Random:
    return random.Random(seed)


# ----------------------------------------------------------------------------
# Hints 解析
# ----------------------------------------------------------------------------

def test_estimate_from_range():
    item = make_item("瓷器", est_mid=500)
    assert estimate_from_hints(item) == 500


def test_estimate_from_single_amount():
    item = Item(
        id="x", type="item", name="x", base_price=100,
        description="", hints=["同类成交 $400"], category="瓷器", true_value=400,
    )
    assert estimate_from_hints(item) == 400


def test_estimate_fallback_to_base():
    item = Item(
        id="x", type="item", name="x", base_price=100,
        description="", hints=["无价格线索"], category="瓷器", true_value=400,
    )
    assert estimate_from_hints(item) == 250  # base * 2.5


# ----------------------------------------------------------------------------
# 老周头
# ----------------------------------------------------------------------------

def test_oldzhou_bids_below_estimate():
    bidder = OldZhou(rng=rng())
    item = make_item("玉器", est_mid=500)  # 非专长
    bid = bidder.bid_sealed(item, ctx())
    assert bid <= 500 * 0.72  # 打七折 + 极小误差


def test_oldzhou_porcelain_bonus():
    bidder_a = OldZhou(rng=rng())
    item_porcelain = make_item("瓷器", est_mid=500)
    bid_porcelain = bidder_a.bid_sealed(item_porcelain, ctx())

    bidder_b = OldZhou(rng=rng())
    item_jade = make_item("玉器", est_mid=500)
    bid_jade = bidder_b.bid_sealed(item_jade, ctx())

    assert bid_porcelain > bid_jade  # 瓷器 +10%


def test_oldzhou_returns_zero_if_below_base():
    bidder = OldZhou(rng=rng())
    item = Item(
        id="x", type="item", name="x", base_price=600,
        description="", hints=["专家估价 $400-$600"], category="玉器", true_value=500,
    )
    assert bidder.bid_sealed(item, ctx()) == 0  # 打七折后远低于底价


# ----------------------------------------------------------------------------
# Kai
# ----------------------------------------------------------------------------

def test_kai_bids_above_estimate_early():
    bidder = Kai(rng=rng(42))
    item = make_item("瓷器", est_mid=500)
    bid = bidder.bid_sealed(item, ctx(round_num=1))
    assert bid > 500  # 早期溢价


def test_kai_fomo_when_empty_late():
    # round 6, 0 inventory → FOMO * 1.30
    bidder = Kai(rng=rng(1))
    item = make_item("瓷器", est_mid=500)
    normal = Kai(rng=rng(1)).bid_sealed(item, ctx(round_num=4, inventory=1))
    fomo = bidder.bid_sealed(item, ctx(round_num=6, inventory=0))
    assert fomo > normal


def test_kai_capped_by_budget():
    bidder = Kai(rng=rng())
    item = make_item("瓷器", est_mid=500)
    bid = bidder.bid_sealed(item, ctx(remaining=300))
    assert bid <= 300


# ----------------------------------------------------------------------------
# 艺姐
# ----------------------------------------------------------------------------

def test_yijie_specialty_bids_higher():
    item_jade = make_item("玉器", est_mid=500)
    item_watch = make_item("钟表", est_mid=500)
    b1 = YiJie(rng=rng(1)).bid_sealed(item_jade, ctx())
    b2 = YiJie(rng=rng(1)).bid_sealed(item_watch, ctx())
    assert b1 > b2


def test_yijie_budget_management():
    # 中后期预算已花大半，不能再孤注一掷
    item = make_item("玉器", est_mid=500)
    rich = YiJie(rng=rng()).bid_sealed(item, ctx(round_num=5, remaining=1800, inventory=0))
    poor = YiJie(rng=rng()).bid_sealed(item, ctx(round_num=5, remaining=300, inventory=2))
    assert rich > poor


# ----------------------------------------------------------------------------
# 阿鬼
# ----------------------------------------------------------------------------

def test_ahgui_accurate_mode_close_to_true_value():
    # 当 trap_mode=accurate，出价应在 true_value × [0.75, 1.02] 之间
    item = make_item("瓷器", est_mid=500)
    item.true_value = 500
    close_bids = []
    for i in range(30):
        bidder = AhGui(rng=rng(i), session_state={"trap_mode": "accurate", "flop_roll": 0.5})
        b = bidder.bid_sealed(item, ctx())
        if b > 0:  # 过滤 15% 装输
            close_bids.append(b)
    # 平均值应接近 true_value × 0.92
    avg = sum(close_bids) / len(close_bids)
    assert 400 <= avg <= 560


def test_ahgui_wild_mode_noisy():
    item = make_item("瓷器", est_mid=500)
    item.true_value = 500
    bids = []
    for i in range(30):
        bidder = AhGui(rng=rng(i), session_state={"trap_mode": "wild", "flop_roll": 0.5})
        bids.append(bidder.bid_sealed(item, ctx()))
    # wild 模式方差应该更大
    span = max(bids) - min(bids)
    assert span > 150


# ----------------------------------------------------------------------------
# Miles
# ----------------------------------------------------------------------------

def test_miles_sleeps_early():
    item = make_item("瓷器", est_mid=500)
    early = Miles(rng=rng(1)).bid_sealed(item, ctx(round_num=1))
    late = Miles(rng=rng(1)).bid_sealed(item, ctx(round_num=7))
    assert late > early * 2


def test_miles_misc_boost_late():
    item_misc = make_item("杂项", est_mid=500)
    item_porcelain = make_item("瓷器", est_mid=500)
    b_misc = Miles(rng=rng(1)).bid_sealed(item_misc, ctx(round_num=7))
    b_porc = Miles(rng=rng(1)).bid_sealed(item_porcelain, ctx(round_num=7))
    assert b_misc > b_porc  # 杂项 +20%
