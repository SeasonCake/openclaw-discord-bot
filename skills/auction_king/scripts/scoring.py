"""
终局积分榜计算。
"""

from __future__ import annotations

from items import Item, find_item, load_library


def compute_final_scores(state: dict) -> dict:
    """
    返回：{
      "ranking": [{name, display, final_score, profit, budget, items: [...]}, ...],
      "true_values": {item_id: true_value},
      "best_roi": (name, item_id, profit) or None,
      "worst_loss": (name, item_id, profit) or None,
    }
    """
    singles, lots = load_library()
    lib_by_id = {it.id: it for it in singles + lots}

    rows = []
    best_roi = None
    worst_loss = None

    done_by_item = {d["item_id"]: d for d in state["items_done"]}

    for pid, p in state["players"].items():
        item_rows = []
        for item_id in p["inventory"]:
            it = lib_by_id[item_id]
            true_val = it.effective_true_value
            done = done_by_item.get(item_id)
            winning_bid = done["winning_bid"] if done else 0
            profit = true_val - winning_bid
            item_rows.append({
                "item_id": item_id,
                "name": it.name,
                "true_value": true_val,
                "winning_bid": winning_bid,
                "profit": profit,
            })

            if best_roi is None or profit > best_roi[2]:
                best_roi = (pid, item_id, profit)
            if worst_loss is None or profit < worst_loss[2]:
                worst_loss = (pid, item_id, profit)

        total_item_value = sum(r["true_value"] for r in item_rows)
        final_score = p["budget"] + total_item_value
        profit = final_score - state["config"]["initial_budget"]

        rows.append({
            "name": pid,
            "display": p["display"],
            "budget": p["budget"],
            "items": item_rows,
            "final_score": final_score,
            "profit": profit,
        })

    rows.sort(key=lambda r: r["final_score"], reverse=True)

    return {
        "ranking": rows,
        "best_roi": best_roi,
        "worst_loss": worst_loss,
    }


def format_scoreboard(scores: dict, state: dict) -> str:
    """Markdown 积分榜。"""
    lines = ["🏛️ **拍卖结束！**", "", "📊 真实价值复盘："]
    for d in state["items_done"]:
        item_id = d["item_id"]
        singles, lots = load_library()
        lib_by_id = {it.id: it for it in singles + lots}
        it = lib_by_id[item_id]
        true_val = it.effective_true_value
        winner_display = state["players"][d["winner"]]["display"] if d["winner"] else "流拍"
        if d["winner"]:
            profit = true_val - d["winning_bid"]
            sign = "+" if profit >= 0 else ""
            lines.append(
                f"  {d['round']}. {it.name:<14} 真值 ${true_val} → {winner_display} ${d['winning_bid']} ({sign}${profit})"
            )
        else:
            lines.append(f"  {d['round']}. {it.name:<14} 真值 ${true_val} → 流拍")

    lines.append("")
    lines.append("🏆 **最终排名**")
    medals = ["🥇", "🥈", "🥉", "4️⃣"]
    for i, r in enumerate(scores["ranking"]):
        medal = medals[i] if i < len(medals) else " "
        sign = "+" if r["profit"] >= 0 else ""
        lines.append(
            f"  {medal} {r['display']:<8} ${r['final_score']}  ({sign}${r['profit']})"
        )

    if scores["best_roi"]:
        pid, item_id, profit = scores["best_roi"]
        if profit > 0:
            singles, lots = load_library()
            lib_by_id = {it.id: it for it in singles + lots}
            item_name = lib_by_id[item_id].name
            lines.append("")
            lines.append(
                f"🎯 最佳 ROI：{state['players'][pid]['display']} 的【{item_name}】 +${profit}"
            )
    if scores["worst_loss"]:
        pid, item_id, profit = scores["worst_loss"]
        if profit < 0:
            singles, lots = load_library()
            lib_by_id = {it.id: it for it in singles + lots}
            item_name = lib_by_id[item_id].name
            lines.append(
                f"😱 最惨接盘：{state['players'][pid]['display']} 的【{item_name}】 ${profit}"
            )

    return "\n".join(lines)
