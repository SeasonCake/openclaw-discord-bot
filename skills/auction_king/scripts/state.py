"""
Game state I/O。

state 保存为 state/<session_id>.json，每步调用 game.py 时 load → mutate → save。

支持两种模式（v3 引入）：
- quick：向下兼容的 v2 单轮暗标（7 轮、$2000 固定、lot_rounds=[3,6]）
- standard：v3 多轮竞价（4–5 件可变、$2000–$3000 随机、碾压阈值）

模式存在 state["config"]["mode"]。quick 模式的 state 和 v2 完全同构，
不包含 standard 模式特有字段（current_item_state / squash_thresholds 等）。
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_bidders import AI_BY_NAME, draft_opponents, init_ai_session_state
from items import Item, load_library, select_round_queue


STATE_DIR = Path(__file__).resolve().parent.parent / "state"
HUMAN_ID = "human"

# v3 常量（standard 模式用）
STANDARD_BUDGET_RANGE = (2000, 3000)
STANDARD_ITEMS_CHOICES = (4, 5)
SQUASH_THRESHOLDS = [1.8, 1.5, 1.2, None]
MIN_RAISE_RATIO = 1.05
MAX_SUB_ROUNDS_PER_ITEM = 4


def _state_path(session_id: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{session_id}.json"


def load_state(session_id: str) -> dict:
    p = _state_path(session_id)
    if not p.exists():
        raise FileNotFoundError(f"session not found: {session_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(session_id: str, state: dict) -> None:
    p = _state_path(session_id)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def session_exists(session_id: str) -> bool:
    return _state_path(session_id).exists()


def _init_current_item_state(item_id: str, participant_ids: list[str]) -> dict:
    """创建 standard 模式下某件物品的 sub_round 容器（sub_round=1 开始）。"""
    return {
        "item_id": item_id,
        "sub_round": 1,
        "active_participants": list(participant_ids),
        "withdrawn": [],
        "history": [],
        "current_bids": {},
        "current_max_bid": 0,
        "current_max_bidder": None,
    }


def _pick_standard_lot_rounds(max_rounds: int, rng: random.Random) -> list[int]:
    """
    standard 模式：4–5 件里随机放 1–2 个仓库。
    仓库不放第 1 轮（避免开局就被大杀器 push）。
    """
    n_lots = rng.choice([1, 2]) if max_rounds >= 4 else 1
    candidate_positions = list(range(2, max_rounds + 1))
    # 防御：候选位不够就减少 lot 数
    n_lots = min(n_lots, len(candidate_positions))
    return sorted(rng.sample(candidate_positions, n_lots))


def new_state(
    session_id: str,
    seed: Optional[int] = None,
    initial_budget: Optional[int] = None,
    max_rounds: Optional[int] = None,
    lot_rounds: Optional[list[int]] = None,
    n_ai: int = 3,
    mode: str = "quick",
) -> dict:
    """
    创建新 state 字典（不落盘，调用方决定何时 save）。

    mode:
      - "quick"（默认）：v2 向下兼容。initial_budget / max_rounds / lot_rounds 缺省
        分别为 2000 / 7 / [3, 6]。
      - "standard"（v3）：缺省时 initial_budget 随机 2000–3000、max_rounds 随机 4 或 5、
        lot_rounds 随机在第 2 轮之后塞 1–2 个仓库。config 里多出 squash_thresholds / 
        min_raise_ratio / max_sub_rounds_per_item；state 多出 current_item_state。

    显式传参始终优先于 mode 缺省。
    """
    if mode not in ("quick", "standard"):
        raise ValueError(f"unknown mode: {mode!r}. expected 'quick' or 'standard'.")

    if seed is None:
        seed = random.SystemRandom().randint(1, 10**9)
    rng = random.Random(seed)

    if mode == "quick":
        if initial_budget is None:
            initial_budget = 2000
        if max_rounds is None:
            max_rounds = 7
        if lot_rounds is None:
            lot_rounds = [3, 6]
    else:  # standard
        if initial_budget is None:
            initial_budget = rng.randint(*STANDARD_BUDGET_RANGE)
        if max_rounds is None:
            max_rounds = rng.choice(STANDARD_ITEMS_CHOICES)
        if lot_rounds is None:
            lot_rounds = _pick_standard_lot_rounds(max_rounds, rng)

    singles, lots = load_library()
    queue = select_round_queue(singles, lots, max_rounds, lot_rounds, rng)

    opponent_names = draft_opponents(seed, n=n_ai)

    players: dict[str, dict] = {
        HUMAN_ID: {
            "display": "你",
            "budget": initial_budget,
            "inventory": [],
            "is_human": True,
        }
    }
    for name in opponent_names:
        cls = AI_BY_NAME[name]
        players[name] = {
            "display": cls.display,
            "budget": initial_budget,
            "inventory": [],
            "is_human": False,
            "persona": cls.persona,
            "ai_state": init_ai_session_state(name, seed),
        }

    config: dict = {
        "mode": mode,
        "initial_budget": initial_budget,
        "max_rounds": max_rounds,
        "lot_rounds": lot_rounds,
        "time_limits": {"early": 60, "mid": 45, "late": 30},
    }
    if mode == "standard":
        config["squash_thresholds"] = list(SQUASH_THRESHOLDS)
        config["min_raise_ratio"] = MIN_RAISE_RATIO
        config["max_sub_rounds_per_item"] = MAX_SUB_ROUNDS_PER_ITEM

    state: dict = {
        "session_id": session_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "seed": seed,
        "config": config,
        "active_ais": opponent_names,
        "players": players,
        "items_queue": [it.id for it in queue],
        "items_done": [],
        "current_round": 1,
        "current_item": queue[0].id,
        "current_type": queue[0].type,
        "current_bids": {},
        "status": "awaiting_human_bid",
        "log": [
            f"{datetime.now():%Y-%m-%d %H:%M:%S} game started "
            f"(mode={mode}, seed={seed}, budget={initial_budget}, "
            f"rounds={max_rounds}, opponents={', '.join(opponent_names)})",
        ],
    }

    if mode == "standard":
        participant_ids = [HUMAN_ID] + opponent_names
        state["current_item_state"] = _init_current_item_state(
            item_id=queue[0].id,
            participant_ids=participant_ids,
        )

    return state


def append_log(state: dict, msg: str) -> None:
    state["log"].append(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}")
