"""
台词生成（v3.4：template + 可选 LLM 层）。

- 默认走模板，100% 可预测、可离线跑。
- 当 env `AUCTION_KING_USE_LLM=1` 时，开场/揭晓/终局三处优先用 DeepSeek 生成，失败自动回退模板。
"""

from __future__ import annotations

import random

import llm_narrator

# ============================================================================
# 每个角色的台词池（按情境分）
# ============================================================================

LINES_WIN = {
    "老周头": [
        "嘿，这物件还是老夫懂行。",
        "年轻人啊，老夫给你们示范一下什么叫'一眼货'。",
        "这价我拿得值，有便宜必须占。",
    ],
    "Kai":    [
        "Let's go! 这 deal 不拿回家对不起我的 FOMO。",
        "All in 才是 playmaker 的姿态。",
        "Classic undervalued asset，我 bet right 了。",
        "Moat 建立，下一轮继续扩张版图。",
        "老子就是喜欢这种 asymmetric upside。",
        "嘿嘿，这波 IRR 稳了。",
    ],
    "艺姐":   [
        "……（轻轻点头，没说话）",
        "这价刚好，不亏。",
        "行里人都知道该出多少。",
    ],
    "阿鬼":   [
        "这一件，气场对了，老夫收了。",
        "诸位不必抢，我心里有数。",
        "嘿嘿，等的就是这一件。",
    ],
    "Miles":  [
        "EV positive，入。",
        "Finally a mispriced asset.",
        "Numbers checked out. Acquired.",
    ],
}

LINES_NEAR_MISS = {
    "老周头": [
        "唉，差了几块钱，算了算了。",
        "年纪大了反应慢。",
    ],
    "Kai":    [
        "差一点啊！should have pushed harder.",
        "下一轮绝对不能再被抢！",
        "Damn，timing off by a hair，下轮见。",
        "没关系，这是 long game，别盯着一单 loss。",
    ],
    "艺姐":   [
        "……",
        "预算该留着，没事。",
    ],
    "阿鬼":   [
        "嘿嘿，不着急，这才第几轮？",
    ],
    "Miles":  [
        "Edge too thin. Pass.",
    ],
}

LINES_YIJIE_SNARK = [
    "Kai 又在交学费。",
    "老周头这波看走眼了。",
    "阿鬼的戏份不错。",
    "Miles 还在装睡。",
    "有人出价真是无理取闹。",
]

LINES_AHGUI_TRAP_SUCCESS = [
    "嗯……还是算了吧。",
    "想想，这件留给别人也挺好。",
    "气氛到了，价也上了，老夫撤。",
]

LINES_AHGUI_TRAP_SELF_BURN = [
    "嘁……这批货没看透。",
    "失算了，老夫今日不在状态。",
]

INTRO_TEMPLATE = """🏛️ **竞拍之夜开始！**

📋 规则：{max_rounds} 轮暗标拍卖（v2 阶段 3.2a 简化版，仓库轮也走暗标），初始预算 ${budget}。
🎭 本局对手（从 5 人池随机抽 3）：

{opponents}

终局按 "剩余预算 + 所持物品真实价值" 比高下。
第 1 轮马上开始…"""

ROUND_HEADER_ITEM = """【第 {round_num}/{total}} 轮 · 单件】

🏺 **{name}**
品类：{category} | 底价 ${base_price}

📌 线索
{hints}

⏱️ 请在 {time_limit} 秒内出价（`python game.py bid --session {session} --amount <金额>`）"""

ROUND_HEADER_LOT = """【第 {round_num}/{total}} 轮 · 仓库 🎁（3.2a 暂按暗标处理）】

📦 **{name}**
{description}
底价 ${base_price}

📌 线索
{hints}

👀 可见物品：
{visibles}

⏱️ 请在 {time_limit} 秒内出价（`python game.py bid --session {session} --amount <金额>`）"""


# ============================================================================
# 台词选择
# ============================================================================

def pick_round_speaker(
    winner: str,
    second_bidder: str | None,
    active_ais: list[str],
    is_human_winner: bool,
    rng: random.Random,
) -> tuple[str, str]:
    """
    决定本轮谁说话 + 说什么。返回 (speaker_name, line)。
    speaker_name == "" 表示本轮无人发言。

    优先级：
    0. **Kai 话痨机制**：只要 Kai 出场在 top-2（中标或差一点），必说话。
    1. 中标 AI 炫耀（70%）
    2. 差点中标的 AI 遗憾（额外 18%）
    3. 艺姐毒舌旁观（额外 7%）
    4. 静默（~5%）
    """
    # ---- Kai 话痨专属规则（最高优先级）----
    if winner == "Kai":
        return "Kai", rng.choice(LINES_WIN.get("Kai", ["Kai：……"]))
    if second_bidder == "Kai" and "Kai" in active_ais:
        return "Kai", rng.choice(LINES_NEAR_MISS.get("Kai", ["Kai：……"]))

    roll = rng.random()

    if not is_human_winner and winner and roll < 0.70:
        lines = LINES_WIN.get(winner, [f"{winner}：……"])
        return winner, rng.choice(lines)

    if second_bidder and second_bidder in active_ais and second_bidder != winner and roll < 0.88:
        lines = LINES_NEAR_MISS.get(second_bidder, [f"{second_bidder}：……"])
        return second_bidder, rng.choice(lines)

    if "艺姐" in active_ais and "艺姐" != winner and roll < 0.95:
        return "艺姐", rng.choice(LINES_YIJIE_SNARK)

    return "", ""


def build_intro(max_rounds: int, budget: int, opponents: list[dict]) -> str:
    lines = []
    for o in opponents:
        lines.append(f"  · **{o['display']}** — {o['persona']}")
    base = INTRO_TEMPLATE.format(
        max_rounds=max_rounds,
        budget=budget,
        opponents="\n".join(lines),
    ).replace("{total}}", f"{max_rounds}")  # no-op, kept for safety

    llm_text = llm_narrator.llm_intro(max_rounds, budget, opponents)
    if llm_text:
        return f"{base}\n\n🎙️ 主持人：\n> {llm_text}"
    return base


def enhance_line_with_llm(
    speaker: str,
    fallback_line: str,
    item,
    round_num: int,
    total_rounds: int,
    speaker_bid: int,
    winner: str,
    winning_bid: int,
    players: dict,
) -> str:
    """
    给 pick_round_speaker 已经选好的 (speaker, fallback_line) 加 LLM 润色。
    任何情况失败都返回 fallback_line。
    """
    if not speaker or not fallback_line:
        return fallback_line
    if not llm_narrator.is_enabled():
        return fallback_line
    winner_display = players.get(winner, {}).get("display", winner)
    llm_line = llm_narrator.llm_round_line(
        speaker=speaker,
        item_name=item.name,
        item_category=getattr(item, "display_category", item.category or "杂项"),
        round_num=round_num,
        total_rounds=total_rounds,
        speaker_bid=speaker_bid,
        winner_display=winner_display,
        winning_bid=winning_bid,
        is_winner=(speaker == winner),
    )
    return llm_line or fallback_line


def format_hints(hints: list[str]) -> str:
    return "\n".join(f"  · {h}" for h in hints)


def format_visibles(items_inside: list) -> str:
    visibles = [c for c in items_inside if c.visible]
    hidden_count = len([c for c in items_inside if not c.visible])
    lines = [f"  · {c.name}（{c.category}）{('—' + c.note) if c.note else ''}" for c in visibles]
    if hidden_count > 0:
        lines.append(f"  · ……还有 **{hidden_count} 件** 隐藏物品")
    return "\n".join(lines)


def build_round_header(item, round_num: int, total: int, time_limit: int, session_id: str) -> str:
    if item.type == "lot":
        return ROUND_HEADER_LOT.replace("{total}}", str(total)).format(
            round_num=round_num,
            name=item.name,
            description=item.description,
            base_price=item.base_price,
            hints=format_hints(item.hints),
            visibles=format_visibles(item.items_inside or []),
            time_limit=time_limit,
            session=session_id,
        )
    return ROUND_HEADER_ITEM.replace("{total}}", str(total)).format(
        round_num=round_num,
        name=item.name,
        category=item.category,
        base_price=item.base_price,
        hints=format_hints(item.hints),
        time_limit=time_limit,
        session=session_id,
    )


def build_reveal(
    round_num: int,
    total_rounds: int,
    item,
    bids: dict[str, int],
    winner: str,
    winning_bid: int,
    players: dict[str, dict],
    speaker: str,
    line: str,
) -> str:
    """揭晓本轮结果的 Markdown。"""
    sorted_bids = sorted(bids.items(), key=lambda kv: kv[1], reverse=True)
    bid_lines = []
    for bidder, amount in sorted_bids:
        mark = " 🏆" if bidder == winner else ""
        display = players[bidder]["display"]
        bid_lines.append(f"  · {display:<8} ${amount}{mark}")

    out = [
        f"📢 揭晓第 {round_num}/{total_rounds} 轮出价：",
        *bid_lines,
        "",
    ]

    if winner:
        winner_display = players[winner]["display"]
        out.append(f"🏆 **{winner_display}** 以 ${winning_bid} 拿下【{item.name}】。")
    else:
        out.append(f"⚠️ 无人出价达到底价，【{item.name}】流拍。")

    if speaker:
        speaker_display = players.get(speaker, {}).get("display", speaker)
        out.append(f"")
        out.append(f"💬 {speaker_display}：「{line}」")

    out.append("")
    budgets = " | ".join(
        f"{p['display']} ${p['budget']}" for pid, p in players.items()
    )
    out.append(f"💰 预算剩余：{budgets}")

    if round_num < total_rounds:
        out.append(f"\n第 {round_num + 1}/{total_rounds} 轮即将开始。")
    else:
        out.append("\n🎲 全部 {n} 轮结束，运行 `scoreboard` 查看最终排名。".format(n=total_rounds))

    return "\n".join(out)
