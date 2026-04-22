"""
AI 对手池 + 出价公式。

5 个人格：老周头 / Kai / 艺姐 / 阿鬼 / Miles
所有公式严格对应 GAME_DESIGN.md §5。

设计约束：
- 出价逻辑零 LLM 调用（deterministic）
- 随机性由调用方提供的 random.Random 注入，保证可复现
- 阿鬼的 trap_accuracy_mode 在开局时 roll 一次存 state，所有后续局中调用用同一个
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from typing import Optional

from items import Item


# ============================================================================
# 估值：从 hints 解析
# ============================================================================

_RE_RANGE = re.compile(r"\$?\s*(\d+)\s*[-–~到]\s*\$?\s*(\d+)")
_RE_AMOUNT = re.compile(r"\$\s*(\d+)")


def estimate_from_hints(item: Item) -> float:
    """从 hints 提取估值 est。优先级：区间中值 > 单价 > 底价兜底。"""
    for h in item.hints:
        m = _RE_RANGE.search(h)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            return (lo + hi) / 2
    for h in item.hints:
        m = _RE_AMOUNT.search(h)
        if m:
            return float(m.group(1))
    return item.base_price * 2.5


# ============================================================================
# Bidder 基类 + 上下文
# ============================================================================

@dataclass
class BidContext:
    """传给 bid_sealed 的运行时上下文，避免 arg 爆炸。"""
    round_num: int
    total_rounds: int
    remaining_budget: int
    inventory_count: int  # 已持物品数


class Bidder:
    """AI 对手基类。子类覆盖 bid_sealed。"""
    name: str = "base"
    display: str = "Base"
    persona: str = ""

    # 定义子类用的几类状态字段（默认为空，由 init_session_state 填）
    @classmethod
    def init_session_state(cls, rng: random.Random) -> dict:
        """每局开始时 roll 一次，存入 players[name].ai_state。"""
        return {}

    def __init__(self, rng: random.Random, session_state: Optional[dict] = None):
        self.rng = rng
        self.session_state = session_state or {}

    def estimate(self, item: Item) -> float:
        return estimate_from_hints(item)

    def bid_sealed(self, item: Item, ctx: BidContext) -> int:
        raise NotImplementedError

    def _cap(self, bid: float, item: Item, budget: int) -> int:
        """统一收尾：低于底价 → 0；超过预算 → 截断；转 int。"""
        if bid < item.base_price:
            return 0
        return int(min(bid, budget))


# ============================================================================
# 角色 1：老周头（保守派）
# ============================================================================

class OldZhou(Bidder):
    name = "老周头"
    display = "老周头"
    persona = "福建古董行老江湖，40 年经验"

    def bid_sealed(self, item: Item, ctx: BidContext) -> int:
        est = self.estimate(item)
        bid = est * 0.70

        if item.category == "瓷器" or item.display_category.startswith("仓库(瓷器)"):
            bid *= 1.10
        if ctx.remaining_budget < 600:
            bid *= 0.8
        if ctx.round_num >= 6 and ctx.remaining_budget > 1000:
            bid = max(bid, est * 0.85)

        return self._cap(bid, item, ctx.remaining_budget)


# ============================================================================
# 角色 2：Kai（激进派）
# ============================================================================

class Kai(Bidder):
    name = "Kai"
    display = "Kai"
    persona = "硅谷回国创投人，FOMO 严重"

    def bid_sealed(self, item: Item, ctx: BidContext) -> int:
        est = self.estimate(item)
        bid = est * 1.05 + self.rng.randint(0, 50)

        if ctx.round_num <= 2:
            bid *= 1.15
        if item.category in ("书画", "钟表"):
            bid *= 1.08
        if ctx.round_num >= 5 and ctx.inventory_count == 0:
            bid *= 1.30

        bid = min(bid, ctx.remaining_budget * 0.95)
        return self._cap(bid, item, ctx.remaining_budget)


# ============================================================================
# 角色 3：艺姐（套利派）
# ============================================================================

class YiJie(Bidder):
    name = "艺姐"
    display = "艺姐"
    persona = "前苏富比行内人，冷静精准"

    def bid_sealed(self, item: Item, ctx: BidContext) -> int:
        est = self.estimate(item)
        bid = est * 0.88 + self.rng.gauss(0, 15)

        is_specialty = item.category in ("玉器", "书画")
        if is_specialty:
            bid = est * 1.05
        elif item.category in ("钟表", "珠宝"):
            bid = est * 0.70

        # 艺姐按"预计中标 3 件"规划预算。专长品类放宽 50%。
        target_wins_remaining = max(1, 3 - ctx.inventory_count)
        per_target = ctx.remaining_budget / target_wins_remaining
        soft_cap = per_target * (1.5 if is_specialty else 1.1)
        bid = min(bid, soft_cap)

        return self._cap(bid, item, ctx.remaining_budget)


# ============================================================================
# 角色 4：阿鬼（陷阱派）
# ============================================================================

class AhGui(Bidder):
    name = "阿鬼"
    display = "阿鬼"
    persona = "江湖收藏局局长，专设陷阱"

    @classmethod
    def init_session_state(cls, rng: random.Random) -> dict:
        # 80% 情报准 / 20% 情报歪
        mode = "accurate" if rng.random() < 0.80 else "wild"
        return {"trap_mode": mode, "flop_roll": rng.random()}

    def _trap_estimate(self, item: Item) -> float:
        true_val = item.effective_true_value
        mode = self.session_state.get("trap_mode", "accurate")
        if mode == "accurate":
            noise = self.rng.uniform(-0.10, 0.10)
        else:
            # wild：真值的 50% ~ 180% 随机
            noise = self.rng.uniform(-0.50, 0.80)
        return true_val * (1 + noise)

    def bid_sealed(self, item: Item, ctx: BidContext) -> int:
        # 15% 概率本轮装输
        if self.rng.random() < 0.15:
            est = self.estimate(item)
            bid = est * 0.55
        else:
            trap_est = self._trap_estimate(item)
            bid = trap_est * 0.92

        return self._cap(bid, item, ctx.remaining_budget)


# ============================================================================
# 角色 5：Miles（狙击派）
# ============================================================================

class Miles(Bidder):
    name = "Miles"
    display = "Miles"
    persona = "前华尔街量化交易员，延迟启动"

    def bid_sealed(self, item: Item, ctx: BidContext) -> int:
        est = self.estimate(item)

        if ctx.round_num <= 3:
            bid = item.base_price + self.rng.randint(0, 30)
        elif ctx.round_num <= 5:
            bid = est * 0.85
        else:  # round 6-7 狙击期
            bid = est * 1.15
            if item.category == "杂项" or item.display_category.startswith("仓库(杂项)"):
                bid *= 1.20

        return self._cap(bid, item, ctx.remaining_budget)


# ============================================================================
# 注册表 + 工厂
# ============================================================================

AI_POOL: list[type[Bidder]] = [OldZhou, Kai, YiJie, AhGui, Miles]
AI_BY_NAME: dict[str, type[Bidder]] = {cls.name: cls for cls in AI_POOL}


def draft_opponents(seed: int, n: int = 3) -> list[str]:
    """从 5 AI 池中随机抽 n 个，返回 name 列表。"""
    rng = random.Random(seed)
    return [cls.name for cls in rng.sample(AI_POOL, n)]


def init_ai_session_state(ai_name: str, seed: int) -> dict:
    """开局调用一次，返回该 AI 在本 session 的固定 state（如阿鬼的 trap mode）。"""
    cls = AI_BY_NAME[ai_name]
    rng = random.Random(hash((seed, ai_name, "init")) & 0xFFFFFFFF)
    return cls.init_session_state(rng)


def _round_rng(base_seed: int, ai_name: str, round_num: int) -> random.Random:
    """每回合每个 AI 的随机源：确定性 + 隔离。"""
    key = f"{base_seed}:{ai_name}:r{round_num}"
    digest = hashlib.md5(key.encode()).hexdigest()
    return random.Random(int(digest[:8], 16))


def compute_ai_bid(
    ai_name: str,
    item: Item,
    ctx: BidContext,
    game_seed: int,
    ai_session_state: dict,
) -> int:
    """外部入口：给定 AI name + 上下文 → 出价金额。"""
    cls = AI_BY_NAME[ai_name]
    rng = _round_rng(game_seed, ai_name, ctx.round_num)
    bidder = cls(rng=rng, session_state=ai_session_state)
    return bidder.bid_sealed(item, ctx)
