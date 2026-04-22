"""
auction_king 主 CLI。

Subcommands:
  start       开局
  status      看当前状态
  bid         玩家出价（自动推进 AI 出价 + 揭晓 + 转下一轮）
  advance     强制推进（视玩家未出价为 $0）
  scoreboard  终局排名
  simulate    自动模拟 N 局，输出平衡统计

所有命令都输出 Markdown 到 stdout，方便 skill 转发。
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_bidders import BidContext, compute_ai_bid
from items import Item, find_item, load_library
from narration import (
    build_intro,
    build_reveal,
    build_round_header,
    enhance_line_with_llm,
    pick_round_speaker,
)
from scoring import compute_final_scores, format_scoreboard
from state import (
    HUMAN_ID,
    append_log,
    load_state,
    new_state,
    save_state,
    session_exists,
)
from standard_engine import (
    advance_to_next_item_or_end,
    apply_sub_round_bids,
    check_item_end,
    collect_ai_bids,
    finalize_item,
    format_item_award,
    format_new_item_header,
    format_sub_round_prompt,
    format_sub_round_reveal,
    human_is_leading,
    human_is_withdrawn,
    increment_sub_round,
)


# ============================================================================
# 工具
# ============================================================================

def _time_limit_for(round_num: int, config: dict) -> int:
    tl = config.get("time_limits", {"early": 60, "mid": 45, "late": 30})
    if round_num <= 2:
        return tl["early"]
    if round_num <= 5:
        return tl["mid"]
    return tl["late"]


def _get_current_item(state: dict) -> Item:
    singles, lots = load_library()
    return find_item(singles, lots, state["current_item"])


def _resolve_round(state: dict) -> str:
    """
    在收齐所有出价后：
    - 确定赢家（并列随机）
    - 扣预算、更新 inventory
    - 推入 items_done
    - 前移到下一轮 or ended
    返回本轮揭晓 markdown。
    """
    item = _get_current_item(state)
    bids = dict(state["current_bids"])

    valid_bids = {p: b for p, b in bids.items() if b >= item.base_price}
    if not valid_bids:
        winner = None
        winning_bid = 0
    else:
        max_bid = max(valid_bids.values())
        tied = [p for p, b in valid_bids.items() if b == max_bid]
        rng = random.Random(hash((state["seed"], state["current_round"], "tie")) & 0xFFFFFFFF)
        winner = rng.choice(tied) if len(tied) > 1 else tied[0]
        winning_bid = max_bid

    second_bidder = None
    if valid_bids and winner:
        rest = {p: b for p, b in valid_bids.items() if p != winner}
        if rest:
            second_bidder = max(rest.items(), key=lambda kv: kv[1])[0]

    if winner:
        state["players"][winner]["budget"] -= winning_bid
        state["players"][winner]["inventory"].append(item.id)

    speaker_rng = random.Random(hash((state["seed"], state["current_round"], "speaker")) & 0xFFFFFFFF)
    speaker, line = pick_round_speaker(
        winner=winner or "",
        second_bidder=second_bidder,
        active_ais=state["active_ais"],
        is_human_winner=(winner == HUMAN_ID),
        rng=speaker_rng,
    )

    if speaker and line:
        speaker_bid = bids.get(speaker, 0)
        line = enhance_line_with_llm(
            speaker=speaker,
            fallback_line=line,
            item=item,
            round_num=state["current_round"],
            total_rounds=state["config"]["max_rounds"],
            speaker_bid=speaker_bid,
            winner=winner or "",
            winning_bid=winning_bid,
            players=state["players"],
        )

    round_record = {
        "item_id": item.id,
        "type": item.type,
        "round": state["current_round"],
        "bids": bids,
        "winner": winner,
        "winning_bid": winning_bid,
        "narration": f"{speaker}:{line}" if speaker else "",
    }
    state["items_done"].append(round_record)
    append_log(
        state,
        f"round {state['current_round']}: {item.id} → winner={winner or 'passed'}@${winning_bid}",
    )

    reveal_md = build_reveal(
        round_num=state["current_round"],
        total_rounds=state["config"]["max_rounds"],
        item=item,
        bids=bids,
        winner=winner or "",
        winning_bid=winning_bid,
        players=state["players"],
        speaker=speaker,
        line=line,
    )

    if state["current_round"] >= state["config"]["max_rounds"]:
        state["status"] = "ended"
        state["current_item"] = None
        state["current_type"] = None
    else:
        state["current_round"] += 1
        next_item_id = state["items_queue"][state["current_round"] - 1]
        next_item = find_item(*load_library(), next_item_id)
        state["current_item"] = next_item.id
        state["current_type"] = next_item.type
        state["status"] = "awaiting_human_bid"
    state["current_bids"] = {}

    return reveal_md


def _compute_all_ai_bids(state: dict) -> None:
    """在 state['current_bids'] 填充所有 AI 的出价（幂等）。"""
    item = _get_current_item(state)
    for ai_name in state["active_ais"]:
        if ai_name in state["current_bids"]:
            continue
        p = state["players"][ai_name]
        ctx = BidContext(
            round_num=state["current_round"],
            total_rounds=state["config"]["max_rounds"],
            remaining_budget=p["budget"],
            inventory_count=len(p["inventory"]),
        )
        bid = compute_ai_bid(
            ai_name=ai_name,
            item=item,
            ctx=ctx,
            game_seed=state["seed"],
            ai_session_state=p.get("ai_state", {}),
        )
        state["current_bids"][ai_name] = bid


def _next_round_header(state: dict, session_id: str) -> str:
    item = _get_current_item(state)
    return build_round_header(
        item=item,
        round_num=state["current_round"],
        total=state["config"]["max_rounds"],
        time_limit=_time_limit_for(state["current_round"], state["config"]),
        session_id=session_id,
    )


# ============================================================================
# Subcommand 实现
# ============================================================================

def cmd_start(args: argparse.Namespace) -> str:
    if session_exists(args.session) and not args.force:
        return (
            f"⚠️ session `{args.session}` 已存在。加 `--force` 覆盖，"
            "或换一个 session id。"
        )

    state = new_state(
        session_id=args.session,
        seed=args.seed,
        initial_budget=args.budget,
        max_rounds=args.rounds,
        mode=args.mode,
    )
    save_state(args.session, state)

    opponents = [
        {**state["players"][n], "name": n} for n in state["active_ais"]
    ]
    intro = build_intro(
        max_rounds=state["config"]["max_rounds"],
        budget=state["config"]["initial_budget"],
        opponents=opponents,
    )

    if _is_standard_mode(state):
        mode_blurb = (
            f"🎯 模式：**standard (v3)** — 每件最多 {state['config']['max_sub_rounds_per_item']} "
            f"轮竞价，碾压阈值 {'/'.join(str(t) for t in state['config']['squash_thresholds'] if t)}。"
        )
        header = format_new_item_header(state)
        return f"{intro}\n\n{mode_blurb}\n{header}"

    header = _next_round_header(state, args.session)
    return f"{intro}\n\n{header}"


def _is_standard_mode(state: dict) -> bool:
    return state.get("config", {}).get("mode") == "standard"


def cmd_status(args: argparse.Namespace) -> str:
    state = load_state(args.session)
    if state["status"] == "ended":
        return (
            "🏁 本局已结束。\n"
            f"运行 `python game.py scoreboard --session {args.session}` 查看排名。"
        )
    if _is_standard_mode(state):
        header = format_sub_round_prompt(state)
    else:
        header = _next_round_header(state, args.session)
    budgets = " | ".join(
        f"{p['display']} ${p['budget']}" for p in state["players"].values()
    )
    return f"{header}\n\n💰 当前预算：{budgets}"


# ============================================================================
# cmd_bid 分流
# ============================================================================

def cmd_bid(args: argparse.Namespace) -> str:
    state = load_state(args.session)
    if _is_standard_mode(state):
        return _cmd_bid_standard(state, args)
    return _cmd_bid_quick(state, args)


def _cmd_bid_quick(state: dict, args: argparse.Namespace) -> str:
    """v2 单轮密封路径（quick 模式），逐字节保留原行为。"""
    if state["status"] != "awaiting_human_bid":
        return f"⚠️ 当前状态是 `{state['status']}`，不能出价。"

    human = state["players"][HUMAN_ID]
    if args.amount < 0:
        return "⚠️ 出价必须 ≥ 0。"
    if args.amount > human["budget"]:
        return f"⚠️ 出价 ${args.amount} 超过你的预算 ${human['budget']}。"

    state["current_bids"][HUMAN_ID] = int(args.amount)
    _compute_all_ai_bids(state)
    reveal = _resolve_round(state)
    save_state(args.session, state)

    out = [reveal]
    if state["status"] == "awaiting_human_bid":
        out.append("")
        out.append(_next_round_header(state, args.session))
    elif state["status"] == "ended":
        scores = compute_final_scores(state)
        out.append("")
        out.append(format_scoreboard(scores, state))
    return "\n".join(out)


def _cmd_bid_standard(state: dict, args: argparse.Namespace) -> str:
    """v3 多轮竞价路径。人类出价后级联跑 sub_round 直到需要再次输入或件结束。"""
    if state["status"] != "awaiting_human_bid":
        return f"⚠️ 当前状态是 `{state['status']}`，不能出价。"

    human = state["players"][HUMAN_ID]
    cis = state["current_item_state"]
    sub_round = cis["sub_round"]

    if human_is_withdrawn(state):
        return "⚠️ 你已退出当前件，等待件结束。用 `advance` 让本件跑完。"
    if sub_round > 1 and human_is_leading(state):
        return (
            "⚠️ 你当前正在领跑（自己不能加价给自己）。\n"
            "   用 `advance --session ...` 让 AI 反应，或 `withdraw` 放弃位置。"
        )

    # 校验出价
    if args.amount < 0:
        return "⚠️ 出价必须 ≥ 0。"
    if args.amount > human["budget"]:
        return f"⚠️ 出价 ${args.amount} 超过你的预算 ${human['budget']}。"

    if sub_round == 1:
        item = _get_current_item(state)
        if args.amount > 0 and args.amount < item.base_price:
            return f"⚠️ Sub-round 1 出价需 ≥ 底价 ${item.base_price}（或出 0 弃拍）。"
        human_action = int(args.amount) if args.amount > 0 else None
    else:
        min_raise = int(cis["current_max_bid"] * state["config"].get("min_raise_ratio", 1.05)) + 1
        if args.amount < min_raise:
            return (
                f"⚠️ 最低加价 ${min_raise}（当前领跑 ${cis['current_max_bid']} × "
                f"{state['config'].get('min_raise_ratio', 1.05)} + 1）。"
                "或用 `withdraw` 退出。"
            )
        human_action = int(args.amount)

    return _v3_process_and_cascade(state, args, human_action)


def _v3_process_and_cascade(
    state: dict,
    args: argparse.Namespace,
    first_human_action: Optional[int],
) -> str:
    """
    执行人类动作 → 收 AI 反应 → 结算 sub_round → 判断件结束 →
    继续 cascade 直到需要人类再次输入 / 件结束 / 整局结束。
    """
    out: list[str] = []
    human_action: Optional[int] = first_human_action

    while True:
        cis = state["current_item_state"]
        ai_decisions = collect_ai_bids(state)
        apply_sub_round_bids(state, human_action, ai_decisions)
        out.append(format_sub_round_reveal(state))

        end_reason = check_item_end(state)
        if end_reason:
            result = finalize_item(state, end_reason)
            out.append("")
            out.append(format_item_award(state, result))
            advance_to_next_item_or_end(state)
            if state["status"] == "ended":
                scores = compute_final_scores(state)
                out.append("")
                out.append(format_scoreboard(scores, state))
                break
            out.append(format_new_item_header(state))
            break

        increment_sub_round(state)

        if human_is_leading(state):
            human_action = None  # 人类领跑，自动持位，继续级联
            out.append("")
            out.append("（你在领跑，AI 继续反应…）")
            continue
        if human_is_withdrawn(state):
            human_action = None  # 已退出，让 AI 之间互拼到结束
            out.append("")
            out.append("（你已退出，AI 继续…）")
            continue

        out.append("")
        out.append(format_sub_round_prompt(state))
        break

    save_state(args.session, state)
    return "\n".join(out)


# ============================================================================
# cmd_advance 分流
# ============================================================================

def cmd_advance(args: argparse.Namespace) -> str:
    state = load_state(args.session)
    if _is_standard_mode(state):
        return _cmd_advance_standard(state, args)
    return _cmd_advance_quick(state, args)


def _cmd_advance_quick(state: dict, args: argparse.Namespace) -> str:
    """quick 模式：玩家未出价时强制推进（视为 $0）。"""
    if state["status"] != "awaiting_human_bid":
        return f"⚠️ 当前状态 `{state['status']}`，不能推进。"

    if HUMAN_ID not in state["current_bids"]:
        state["current_bids"][HUMAN_ID] = 0
    _compute_all_ai_bids(state)
    reveal = _resolve_round(state)
    save_state(args.session, state)

    out = [reveal]
    if state["status"] == "awaiting_human_bid":
        out.append("")
        out.append(_next_round_header(state, args.session))
    elif state["status"] == "ended":
        scores = compute_final_scores(state)
        out.append("")
        out.append(format_scoreboard(scores, state))
    return "\n".join(out)


def _cmd_advance_standard(state: dict, args: argparse.Namespace) -> str:
    """
    standard 模式的 advance 语义：
      - sub_round 1 且人类未出价 → 视为 0（弃拍）
      - sub_round 2+ 人类领跑 → 合法「持位」
      - sub_round 2+ 人类非领跑且未退出 → 等同 withdraw
      - 已退出 → 让 AI 跑完本件
    """
    if state["status"] != "awaiting_human_bid":
        return f"⚠️ 当前状态 `{state['status']}`，不能推进。"

    cis = state["current_item_state"]
    sub_round = cis["sub_round"]

    if human_is_withdrawn(state):
        human_action: Optional[int] = None
    elif sub_round == 1:
        human_action = None  # 弃拍 sub_round 1
    elif human_is_leading(state):
        human_action = None  # 自动持位
    else:
        human_action = None  # 等同退出

    return _v3_process_and_cascade(state, args, human_action)


# ============================================================================
# cmd_withdraw（standard 专有）
# ============================================================================

def cmd_withdraw(args: argparse.Namespace) -> str:
    state = load_state(args.session)
    if not _is_standard_mode(state):
        return "⚠️ `withdraw` 仅支持 standard 模式（quick 模式直接出 $0 弃拍）。"
    if state["status"] != "awaiting_human_bid":
        return f"⚠️ 当前状态 `{state['status']}`，不能退出。"
    if human_is_withdrawn(state):
        return "⚠️ 你已退出当前件。"
    if human_is_leading(state):
        return (
            "⚠️ 你在领跑，主动退出会让次高者接位。确认？\n"
            "   如果确认，请再发一次 `withdraw --confirm`（TODO：v3.1）"
        )
    # 标准流程：human_action=None 进入级联
    return _v3_process_and_cascade(state, args, None)


def cmd_scoreboard(args: argparse.Namespace) -> str:
    state = load_state(args.session)
    if state["status"] != "ended":
        return (
            f"⚠️ 本局还未结束（当前第 {state['current_round']}/{state['config']['max_rounds']} 轮）。"
        )
    scores = compute_final_scores(state)
    return format_scoreboard(scores, state)


# ============================================================================
# simulate：自动模拟 N 局
# ============================================================================

def _simulate_human_bid(item: Item, ctx: BidContext, strategy: str, rng: random.Random) -> int:
    """模拟"玩家"策略，用于 simulate 命令。"""
    est = 0
    # 复用 ai_bidders.estimate_from_hints
    from ai_bidders import estimate_from_hints
    est = estimate_from_hints(item)

    if strategy == "random":
        bid = est * rng.uniform(0.5, 1.2)
    elif strategy == "conservative":
        bid = est * 0.75
    elif strategy == "aggressive":
        bid = est * 1.10
    else:  # auto / balanced
        bid = est * 0.90

    if bid < item.base_price:
        return 0
    return int(min(bid, ctx.remaining_budget))


def cmd_simulate(args: argparse.Namespace) -> str:
    """自动玩 N 局，输出统计。不写 state 文件。"""
    results_by_ai: dict[str, list[int]] = {}
    human_scores: list[int] = []
    winners: list[str] = []
    trap_success_count = 0
    ahgui_played = 0

    base_seed = args.seed if args.seed is not None else random.randint(1, 10**6)

    for game_idx in range(args.n_games):
        game_seed = base_seed + game_idx
        session_id = f"sim_{game_idx}"

        state = new_state(
            session_id=session_id,
            seed=game_seed,
            initial_budget=args.budget,
            max_rounds=args.rounds,
        )

        human_strategy = args.human_strategy
        sim_rng = random.Random(game_seed * 31 + 7)

        while state["status"] != "ended":
            item = _get_current_item(state)
            ctx = BidContext(
                round_num=state["current_round"],
                total_rounds=state["config"]["max_rounds"],
                remaining_budget=state["players"][HUMAN_ID]["budget"],
                inventory_count=len(state["players"][HUMAN_ID]["inventory"]),
            )
            human_bid = _simulate_human_bid(item, ctx, human_strategy, sim_rng)
            state["current_bids"][HUMAN_ID] = human_bid
            _compute_all_ai_bids(state)
            _resolve_round(state)

        scores = compute_final_scores(state)
        ranking = scores["ranking"]
        winner_pid = ranking[0]["name"]
        winners.append(winner_pid)

        for r in ranking:
            results_by_ai.setdefault(r["name"], []).append(r["final_score"])
        human_scores.append(
            next(r["final_score"] for r in ranking if r["name"] == HUMAN_ID)
        )

        if "阿鬼" in state["active_ais"]:
            ahgui_played += 1
            for d in state["items_done"]:
                if d["winner"] != "阿鬼" and d["winner"] is not None:
                    if "阿鬼" in d["bids"]:
                        ahgui_bid = d["bids"]["阿鬼"]
                        winning_bid = d["winning_bid"]
                        singles, lots = load_library()
                        lib_by_id = {it.id: it for it in singles + lots}
                        true_val = lib_by_id[d["item_id"]].effective_true_value
                        if (
                            ahgui_bid > 0
                            and ahgui_bid < winning_bid
                            and winning_bid > true_val
                        ):
                            trap_success_count += 1
                            break

    lines = [
        f"🎲 Simulate {args.n_games} games (strategy={args.human_strategy}, base_seed={base_seed})",
        "",
        "| 玩家     | 出场次数 | 平均分 | 中位分 | 胜率 |",
        "|----------|----------|--------|--------|------|",
    ]
    win_counts = {name: winners.count(name) for name in set(winners)}
    all_names = ["human"] + ["老周头", "Kai", "艺姐", "阿鬼", "Miles"]
    for name in all_names:
        scores_list = results_by_ai.get(name, [])
        if not scores_list:
            continue
        mean = statistics.mean(scores_list)
        median = statistics.median(scores_list)
        wins = win_counts.get(name, 0)
        lines.append(
            f"| {name:<8} | {len(scores_list):>8} | {mean:>6.0f} | {median:>6.0f} | {wins}/{args.n_games} |"
        )

    lines.append("")
    lines.append(f"阿鬼登场 {ahgui_played} 局，陷阱疑似触发 {trap_success_count} 次。")
    return "\n".join(lines)


# ============================================================================
# Arg parser
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="auction_king CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="开一局新游戏")
    p_start.add_argument("--session", required=True)
    p_start.add_argument("--seed", type=int, default=None)
    p_start.add_argument(
        "--mode",
        choices=["quick", "standard"],
        default="quick",
        help="quick=v2 单轮暗标（默认），standard=v3 多轮竞价",
    )
    p_start.add_argument(
        "--budget",
        type=int,
        default=None,
        help="初始预算；留空时 quick=2000，standard=随机 2000-3000",
    )
    p_start.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="件数；留空时 quick=7，standard=随机 4 或 5",
    )
    p_start.add_argument("--force", action="store_true", help="覆盖已存在 session")

    p_status = sub.add_parser("status", help="查看当前轮状态")
    p_status.add_argument("--session", required=True)

    p_bid = sub.add_parser("bid", help="玩家出价并推进本轮")
    p_bid.add_argument("--session", required=True)
    p_bid.add_argument("--amount", type=int, required=True)

    p_adv = sub.add_parser("advance", help="玩家超时，强推本轮（quick=视为$0；standard=持位/退出）")
    p_adv.add_argument("--session", required=True)

    p_wd = sub.add_parser("withdraw", help="主动退出当前件（standard 模式专有）")
    p_wd.add_argument("--session", required=True)

    p_sb = sub.add_parser("scoreboard", help="终局排名")
    p_sb.add_argument("--session", required=True)

    p_sim = sub.add_parser("simulate", help="自动模拟 N 局")
    p_sim.add_argument("--n-games", type=int, default=100)
    p_sim.add_argument(
        "--human-strategy",
        choices=["random", "conservative", "aggressive", "auto"],
        default="auto",
    )
    p_sim.add_argument("--seed", type=int, default=None)
    p_sim.add_argument("--budget", type=int, default=2000)
    p_sim.add_argument("--rounds", type=int, default=7)

    args = parser.parse_args()

    handlers = {
        "start": cmd_start,
        "status": cmd_status,
        "bid": cmd_bid,
        "advance": cmd_advance,
        "withdraw": cmd_withdraw,
        "scoreboard": cmd_scoreboard,
        "simulate": cmd_simulate,
    }
    out = handlers[args.cmd](args)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
