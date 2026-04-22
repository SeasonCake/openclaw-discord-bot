"""
v3 standard 模式的 sub_round 引擎。

所有函数都是 pure-ish：接收 state（dict），原地修改 + 返回 markdown 字符串。
game.py 负责 CLI 调度，本模块负责状态机。

核心状态字段（state["current_item_state"]）：
  - item_id: 当前件 id
  - sub_round: 1..4
  - active_participants: 尚未退出的参与者 name 列表
  - withdrawn: 已退出的 name 列表
  - history: 每 sub_round 的记录 [{sub_round, bids, max_bid, max_bidder}]
  - current_bids: 当前 sub_round 的新出价 {name: amount}
  - current_max_bid / current_max_bidder: 截至当前 sub_round 的领跑情报
"""

from __future__ import annotations

import random
from typing import Optional

from ai_bidders import BidContextV3, compute_ai_bid_v3
from items import Item, find_item, load_library
from state import HUMAN_ID, append_log


# ============================================================================
# 查找工具
# ============================================================================

def _current_item(state: dict) -> Item:
    singles, lots = load_library()
    return find_item(singles, lots, state["current_item"])


def _active_non_leaders(state: dict) -> list[str]:
    """当前 sub_round 需要做决策的参与者（排除领跑者 + 已退出）。"""
    cis = state["current_item_state"]
    leader = cis.get("current_max_bidder")
    return [
        p for p in cis["active_participants"]
        if p != leader  # leader 持位不动
    ]


def human_is_leading(state: dict) -> bool:
    return state["current_item_state"].get("current_max_bidder") == HUMAN_ID


def human_is_withdrawn(state: dict) -> bool:
    return HUMAN_ID in state["current_item_state"].get("withdrawn", [])


# ============================================================================
# sub_round 1：全员密封出价
# sub_round 2+：非领跑者反应（领跑者持位）
# ============================================================================

def collect_ai_bids(state: dict) -> dict[str, Optional[int]]:
    """
    对「应当出价的 AI」调用 compute_ai_bid_v3。
    sub_round 1：所有活跃 AI 都要出价。
    sub_round 2+：只有非领跑 + 未退出的 AI 要决策。

    返回 {ai_name: amount or None(=withdraw)}。不落 state。
    """
    cis = state["current_item_state"]
    item = _current_item(state)
    sub_round = cis["sub_round"]
    leader = cis.get("current_max_bidder")

    ai_decisions: dict[str, Optional[int]] = {}
    for ai in state["active_ais"]:
        if ai in cis["withdrawn"]:
            continue
        if sub_round > 1 and ai == leader:
            continue  # 领跑者持位
        p = state["players"][ai]
        ctx = BidContextV3(
            round_num=state["current_round"],
            total_rounds=state["config"]["max_rounds"],
            remaining_budget=p["budget"],
            inventory_count=len(p["inventory"]),
            item=item,
            sub_round=sub_round,
            current_max_bid=cis["current_max_bid"],
            current_max_bidder=leader,
            min_raise_ratio=state["config"].get("min_raise_ratio", 1.05),
        )
        ai_decisions[ai] = compute_ai_bid_v3(
            ai_name=ai,
            ctx=ctx,
            game_seed=state["seed"],
            ai_session_state=p.get("ai_state", {}),
        )
    return ai_decisions


def apply_sub_round_bids(
    state: dict,
    human_action: Optional[int],
    ai_decisions: dict[str, Optional[int]],
) -> None:
    """
    把本 sub_round 的所有出价 / 退出合并到 current_item_state。

    human_action: None 表示人类退出或持位（取决于是否领跑）；int 表示出价金额
    ai_decisions: compute_ai_bid_v3 的输出（None = 退出）

    执行后：
      - 新 withdraw 进 withdrawn，从 active_participants 移除
      - current_bids 记录本 sub_round 有效出价（含领跑者持位 bid）
      - 更新 current_max_bid / current_max_bidder
      - history 追加本 sub_round 完整快照（new_bids + pool）
    """
    cis = state["current_item_state"]
    sub_round = cis["sub_round"]
    leader_before = cis.get("current_max_bidder")
    prev_max_bid = cis.get("current_max_bid", 0)

    # 1. 收集本 sub_round 的新出价（含 withdraw）
    new_bids: dict[str, int] = {}
    newly_withdrawn: list[str] = []

    def _handle(name: str, amt: Optional[int]) -> None:
        if amt is None:
            newly_withdrawn.append(name)
        else:
            new_bids[name] = int(amt)

    if sub_round == 1 or (sub_round > 1 and leader_before != HUMAN_ID):
        # 人类在本 sub_round 需要决策
        if HUMAN_ID not in cis["withdrawn"]:
            _handle(HUMAN_ID, human_action)
    # sub_round 2+ 且人类领跑时，human_action 忽略（人类自动持位）

    for ai, amt in ai_decisions.items():
        _handle(ai, amt)

    # 2. 处理退出
    for name in newly_withdrawn:
        if name not in cis["withdrawn"]:
            cis["withdrawn"].append(name)
        if name in cis["active_participants"]:
            cis["active_participants"].remove(name)

    # 3. 合成本 sub_round 的「有效当前出价池」
    #    sub_round 2+：领跑者持位 = 把之前的 current_max_bid 带入
    pool: dict[str, int] = dict(new_bids)
    if (
        sub_round > 1
        and leader_before
        and leader_before not in cis["withdrawn"]
        and leader_before not in pool
        and prev_max_bid > 0
    ):
        pool[leader_before] = prev_max_bid

    # 4. 新领跑者
    if pool:
        max_amt = max(pool.values())
        tied = [p for p, a in pool.items() if a == max_amt]
        if len(tied) > 1:
            tiebreak_rng = random.Random(
                hash((state["seed"], state["current_round"], sub_round, "tie")) & 0xFFFFFFFF
            )
            new_leader = tiebreak_rng.choice(tied)
        else:
            new_leader = tied[0]
        cis["current_max_bid"] = int(max_amt)
        cis["current_max_bidder"] = new_leader
    # 池为空 → 保持原 max / leader

    cis["current_bids"] = new_bids  # 仅本 sub_round 新出价
    cis["history"].append({
        "sub_round": sub_round,
        "new_bids": dict(new_bids),
        "pool": dict(pool),  # 完整池含前领跑者持位 bid
        "withdrawn": list(newly_withdrawn),
        "prev_leader": leader_before,
        "prev_max_bid": prev_max_bid,
        "max_bid": cis["current_max_bid"],
        "max_bidder": cis["current_max_bidder"],
    })


# ============================================================================
# 结束条件
# ============================================================================

def check_item_end(state: dict) -> Optional[str]:
    """
    返回结束原因（或 None 表示继续）：
      - "squash": 碾压阈值达成
      - "final_sub_round": sub_round == max_sub_rounds_per_item
      - "all_others_withdrew": 除领跑者外全退出
      - "no_bids": 完全没人有效出价
    """
    cis = state["current_item_state"]
    cfg = state["config"]
    sub_round = cis["sub_round"]
    leader = cis.get("current_max_bidder")
    max_bid = cis.get("current_max_bid", 0)
    last = cis["history"][-1] if cis["history"] else None
    pool = dict(last["pool"]) if last else {}

    # 没人有效出价（sub_round 1 就没人出） → 流拍
    if leader is None or max_bid <= 0:
        all_empty = all(not h.get("pool") for h in cis["history"])
        if sub_round >= 1 and all_empty:
            return "no_bids"
        return None

    # 领跑者之外全退出
    remaining_others = [
        p for p in cis["active_participants"] if p != leader
    ]
    if not remaining_others:
        return "all_others_withdrew"

    # Squash 检查：max / second_highest >= threshold[sub_round-1]
    thresholds = cfg.get("squash_thresholds", [1.8, 1.5, 1.2, None])
    idx = sub_round - 1
    threshold = thresholds[idx] if idx < len(thresholds) else None
    if threshold is not None:
        others_amounts = [a for p, a in pool.items() if p != leader]
        if others_amounts:
            second = max(others_amounts)
            if second > 0 and max_bid / second >= threshold:
                return "squash"
        else:
            # 池里只有领跑一人 → 无人挑战 → 视作碾压
            return "squash"

    # 最后 sub_round 无条件结束
    max_sr = cfg.get("max_sub_rounds_per_item", 4)
    if sub_round >= max_sr:
        return "final_sub_round"

    return None


# ============================================================================
# 结算 + 推进
# ============================================================================

def finalize_item(state: dict, end_reason: str) -> dict:
    """
    结算当前件：扣预算、更新 inventory、写 items_done。
    返回 {"winner", "winning_bid", "item_id", "end_reason"}。
    """
    cis = state["current_item_state"]
    item = _current_item(state)
    leader = cis.get("current_max_bidder")
    winning_bid = cis.get("current_max_bid", 0) or 0

    if end_reason == "no_bids" or not leader or winning_bid <= 0:
        winner = None
        winning_bid = 0
    else:
        winner = leader
        state["players"][winner]["budget"] -= winning_bid
        state["players"][winner]["inventory"].append(item.id)

    # 汇总 bids：每人在本件出过的最高价（从 history 的 new_bids 聚合）
    aggregated_bids: dict[str, int] = {}
    for h in cis["history"]:
        for p, a in h["new_bids"].items():
            if a > 0:
                aggregated_bids[p] = max(aggregated_bids.get(p, 0), a)
    if leader and leader not in aggregated_bids and winning_bid > 0:
        aggregated_bids[leader] = winning_bid

    round_record = {
        "item_id": item.id,
        "type": item.type,
        "round": state["current_round"],
        "mode": "standard",
        "sub_rounds_played": cis["sub_round"],
        "end_reason": end_reason,
        "history": list(cis["history"]),
        "bids": aggregated_bids,
        "winner": winner,
        "winning_bid": winning_bid,
        "withdrawn": list(cis["withdrawn"]),
    }
    state["items_done"].append(round_record)
    append_log(
        state,
        f"round {state['current_round']} ({item.id}): "
        f"winner={winner or 'passed'}@${winning_bid} ({end_reason}, "
        f"sub_rounds={cis['sub_round']})",
    )
    return {
        "winner": winner,
        "winning_bid": winning_bid,
        "item_id": item.id,
        "end_reason": end_reason,
    }


def advance_to_next_item_or_end(state: dict) -> None:
    """件结算完毕后推进：要么换件并重建 current_item_state，要么终局。"""
    cfg = state["config"]
    if state["current_round"] >= cfg["max_rounds"]:
        state["status"] = "ended"
        state["current_item"] = None
        state["current_type"] = None
        state["current_bids"] = {}
        state.pop("current_item_state", None)
        return

    state["current_round"] += 1
    next_item_id = state["items_queue"][state["current_round"] - 1]
    singles, lots = load_library()
    next_item = find_item(singles, lots, next_item_id)
    state["current_item"] = next_item.id
    state["current_type"] = next_item.type
    state["current_bids"] = {}
    state["status"] = "awaiting_human_bid"

    participants = [HUMAN_ID] + list(state["active_ais"])
    state["current_item_state"] = {
        "item_id": next_item.id,
        "sub_round": 1,
        "active_participants": participants,
        "withdrawn": [],
        "history": [],
        "current_bids": {},
        "current_max_bid": 0,
        "current_max_bidder": None,
    }


def increment_sub_round(state: dict) -> None:
    """件未结束 → 进入下一 sub_round。清空 current_bids，保留 max/leader。"""
    cis = state["current_item_state"]
    cis["sub_round"] += 1
    cis["current_bids"] = {}
    # current_max_bid / current_max_bidder 保持不变（领跑持位）


# ============================================================================
# 展示层（MVP，无 LLM；Phase D 再加）
# ============================================================================

def format_sub_round_reveal(state: dict) -> str:
    """展示刚刚 resolve 完的 sub_round 结果。"""
    cis = state["current_item_state"]
    item = _current_item(state)
    players = state["players"]
    sub_round = cis["sub_round"]
    last = cis["history"][-1]
    leader = cis["current_max_bidder"]
    leader_disp = players[leader]["display"] if leader else "无"

    lines = [
        f"**Sub-round {sub_round} 揭晓**（{item.name}）",
        "",
    ]

    # 本 sub_round 新出价
    for name, amt in last["new_bids"].items():
        disp = players[name]["display"]
        tag = " 👑" if name == leader else ""
        lines.append(f"  · {disp}：${amt}{tag}")

    # 前领跑者（sub_round 2+）如果还在池中但没加价 → 持位
    prev_leader = last.get("prev_leader")
    if (
        prev_leader
        and prev_leader not in last["new_bids"]
        and prev_leader in last["pool"]
    ):
        disp = players[prev_leader]["display"]
        amt = last["pool"][prev_leader]
        tag = " 👑" if prev_leader == leader else ""
        lines.append(f"  · {disp}：${amt}（持位）{tag}")

    if last["withdrawn"]:
        withdrawn_disp = "、".join(players[n]["display"] for n in last["withdrawn"])
        lines.append(f"  · 退出：{withdrawn_disp}")

    lines.append("")
    # 次高信息（给玩家判断碾压距离）
    others = [a for p, a in last["pool"].items() if p != leader]
    if others:
        second = max(others)
        ratio = cis["current_max_bid"] / second if second > 0 else float("inf")
        lines.append(
            f"📣 当前领跑：**{leader_disp}** ${cis['current_max_bid']}"
            f"（次高 ${second}，领先 {ratio:.2f}×）"
        )
    else:
        lines.append(f"📣 当前领跑：**{leader_disp}** ${cis['current_max_bid']}")
    return "\n".join(lines)


def format_item_award(state: dict, result: dict) -> str:
    """件结算后的颁奖文案。"""
    item = _current_item(state) if state.get("current_item") else None
    # 结算后 current_item 可能已推进；用 result 里的 item_id 再查一次
    if result["item_id"]:
        singles, lots = load_library()
        item = find_item(singles, lots, result["item_id"])

    end_reason = result["end_reason"]
    reason_txt = {
        "squash": "**碾压达成**",
        "final_sub_round": "**末轮决胜**",
        "all_others_withdrew": "**其他人全退**",
        "no_bids": "**无人出价，流拍**",
    }.get(end_reason, end_reason)

    lines = [
        "─" * 32,
        f"🏆 **{item.name if item else result['item_id']} 成交！** {reason_txt}",
    ]
    if result["winner"]:
        disp = state["players"][result["winner"]]["display"]
        lines.append(f"   → {disp} 以 ${result['winning_bid']} 拿下")
        # 真实价值对比（如果已结算）
        if item is not None:
            true_val = item.effective_true_value
            delta = true_val - result["winning_bid"]
            sign = "+" if delta >= 0 else ""
            lines.append(
                f"   📊 真实价值 ${true_val}（净值 {sign}{delta}）"
            )
    else:
        lines.append("   → 流拍，无人获得")
    lines.append("─" * 32)
    return "\n".join(lines)


def format_sub_round_prompt(state: dict) -> str:
    """下一个 sub_round 的玩家提示（玩家需要决策时）。"""
    cis = state["current_item_state"]
    item = _current_item(state)
    sub_round = cis["sub_round"]
    total_sr = state["config"].get("max_sub_rounds_per_item", 4)
    players = state["players"]
    leader = cis.get("current_max_bidder")
    human = players[HUMAN_ID]

    lines = [
        "",
        f"📢 {item.name} — Sub-round {sub_round}/{total_sr}",
    ]
    if leader:
        leader_disp = players[leader]["display"]
        lines.append(
            f"   当前领跑：{leader_disp} ${cis['current_max_bid']}"
        )
        min_raise = int(cis["current_max_bid"] * state["config"].get("min_raise_ratio", 1.05)) + 1
        lines.append(f"   最低加价：**${min_raise}**（或 `withdraw` 退出）")
    else:
        lines.append(f"   首轮密封出价（底价 ${item.base_price}）")
    lines.append(f"   你的预算：${human['budget']}")
    return "\n".join(lines)


def format_new_item_header(state: dict) -> str:
    """件推进后的新件开场。"""
    item = _current_item(state)
    players = state["players"]
    human = players[HUMAN_ID]

    est_hint = item.hints[0] if item.hints else ""
    lines = [
        "",
        f"═══ 第 {state['current_round']}/{state['config']['max_rounds']} 件 ═══",
        f"📦 **{item.name}** ({item.display_category})",
        f"   底价 ${item.base_price}",
    ]
    if est_hint:
        lines.append(f"   💡 {est_hint}")
    lines.append(f"   你的预算：${human['budget']}")
    lines.append("")
    lines.append("首轮密封出价 — 出价格式：`bid --amount <金额>`")
    return "\n".join(lines)
