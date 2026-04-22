"""
Game state I/O。

state 保存为 state/<session_id>.json，每步调用 game.py 时 load → mutate → save。
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


def new_state(
    session_id: str,
    seed: Optional[int] = None,
    initial_budget: int = 2000,
    max_rounds: int = 7,
    lot_rounds: Optional[list[int]] = None,
    n_ai: int = 3,
) -> dict:
    """创建新 state 字典（不落盘，调用方决定何时 save）。"""
    if seed is None:
        seed = random.SystemRandom().randint(1, 10**9)
    lot_rounds = lot_rounds or [3, 6]

    rng = random.Random(seed)
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

    state = {
        "session_id": session_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "seed": seed,
        "config": {
            "initial_budget": initial_budget,
            "max_rounds": max_rounds,
            "lot_rounds": lot_rounds,
            "time_limits": {"early": 60, "mid": 45, "late": 30},
        },
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
            f"{datetime.now():%Y-%m-%d %H:%M:%S} game started (seed={seed}, opponents={', '.join(opponent_names)})",
        ],
    }
    return state


def append_log(state: dict, msg: str) -> None:
    state["log"].append(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}")
