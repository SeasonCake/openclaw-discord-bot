"""
Item / Lot data classes and loader.

拍品库 data/items.json → Python 对象。每局开始时从这里随机抽序列。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class LotChild:
    """仓库内的单个物品（v1 只记录信息，计分时汇总 true_value）"""
    name: str
    category: str
    true_value: int
    visible: bool
    note: Optional[str]


@dataclass
class Item:
    """单件拍品 / 仓库组通用数据类。type 字段区分。"""
    id: str
    type: str  # "item" | "lot"
    name: str
    base_price: int
    description: str
    hints: list[str]
    image: Optional[str] = None
    # 单件专属
    category: Optional[str] = None
    true_value: Optional[int] = None
    # 仓库专属
    items_inside: Optional[list[LotChild]] = None
    true_total: Optional[int] = None

    @property
    def effective_true_value(self) -> int:
        """scoring 和 AI 估值用。单件返回 true_value，仓库返回 true_total。"""
        if self.type == "lot":
            return int(self.true_total or 0)
        return int(self.true_value or 0)

    @property
    def display_category(self) -> str:
        if self.type == "lot":
            # 仓库没有单一品类，返回主导品类（可见物品中 value 最高的）
            visibles = [c for c in (self.items_inside or []) if c.visible]
            if visibles:
                top = max(visibles, key=lambda c: c.true_value)
                return f"仓库({top.category})"
            return "仓库(综合)"
        return self.category or "杂项"


def _parse_child(d: dict) -> LotChild:
    return LotChild(
        name=d["name"],
        category=d["category"],
        true_value=int(d["true_value"]),
        visible=bool(d["visible"]),
        note=d.get("note"),
    )


def _parse_item(d: dict) -> Item:
    children = None
    if d.get("type") == "lot" and d.get("items_inside"):
        children = [_parse_child(c) for c in d["items_inside"]]
    return Item(
        id=d["id"],
        type=d["type"],
        name=d["name"],
        base_price=int(d["base_price"]),
        description=d.get("description", ""),
        hints=list(d.get("hints", [])),
        image=d.get("image"),
        category=d.get("category"),
        true_value=d.get("true_value"),
        items_inside=children,
        true_total=d.get("true_total"),
    )


def load_library(path: Optional[Path] = None) -> tuple[list[Item], list[Item]]:
    """加载整个拍品库。返回 (singles, lots)。"""
    path = path or (DATA_DIR / "items.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    singles = [_parse_item(d) for d in raw.get("items", [])]
    lots = [_parse_item(d) for d in raw.get("lots", [])]
    return singles, lots


def select_round_queue(
    singles: list[Item],
    lots: list[Item],
    max_rounds: int,
    lot_rounds: list[int],
    rng: random.Random,
) -> list[Item]:
    """
    构造本局 max_rounds 件拍品的出场序列。
    lot_rounds 里指定哪几轮放仓库（1-indexed），其余为单件。
    """
    n_lots = len(lot_rounds)
    n_singles = max_rounds - n_lots

    if n_singles > len(singles):
        raise ValueError(f"need {n_singles} single items, library has {len(singles)}")
    if n_lots > len(lots):
        raise ValueError(f"need {n_lots} lots, library has {len(lots)}")

    chosen_singles = rng.sample(singles, n_singles)
    chosen_lots = rng.sample(lots, n_lots)

    queue: list[Item] = []
    single_iter = iter(chosen_singles)
    lot_iter = iter(chosen_lots)

    for r in range(1, max_rounds + 1):
        if r in lot_rounds:
            queue.append(next(lot_iter))
        else:
            queue.append(next(single_iter))

    return queue


def find_item(library_singles: list[Item], library_lots: list[Item], item_id: str) -> Item:
    for it in library_singles + library_lots:
        if it.id == item_id:
            return it
    raise KeyError(f"item not found: {item_id}")
