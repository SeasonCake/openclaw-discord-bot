"""
LLM 台词层（v3.4）。

设计原则：
- DeepSeek 为可选增强，任何失败（key 缺失/网络/超时/解析）都 fallback 到 template。
- 启用开关：env var AUCTION_KING_USE_LLM=1。默认关。
- 预算：一局 ~1500-2500 tokens = ~¥0.002，便宜到可以忽略。
- 仅用 stdlib urllib.request，不引入新依赖。

调用点（只有 3 个）：
- llm_intro()          开局主持人开场白（1 次/局）
- llm_round_line()     每轮揭晓时角色的一句话（7 次/局）
- llm_final_summary()  终局主持人总结（1 次/局）
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 10  # 秒


def is_enabled() -> bool:
    v = os.environ.get("AUCTION_KING_USE_LLM", "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _get_api_key() -> Optional[str]:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip() or None


PERSONA_CARDS: dict[str, str] = {
    "老周头": (
        "老周头，72 岁，北京琉璃厂老掌柜三代传人。说话带京片子，常自称『老夫』。"
        "口头禅：『这东西我眼毒』『别跟我谈价，跟规矩谈』。"
        "性格保守、重品相、讨厌当冤大头。"
    ),
    "Kai": (
        "Kai，34 岁，硅谷回国连续创业者，中英文夹杂的互联网黑话大师。"
        "把拍卖当 venture bet，崇尚 All in、FOMO 体质、赢了骄傲输了嘴硬。"
        "口头禅：All in、moat、playmaker、undervalued、EV positive。"
    ),
    "艺姐": (
        "艺姐，38 岁，景德镇世家出身，瓷器+玉器双栖鉴定师。"
        "话少、毒舌、点评一针见血。精于本行，其他品类不屑出价。"
        "发言通常短、带冷笑气质、偶尔一个省略号就够了。"
    ),
    "阿鬼": (
        "阿鬼，45 岁，江湖收藏圈的情报贩子，信息比物件更赚钱。"
        "说话慢条斯理、爱说『嘿嘿』、擅长埋伏笔。表面客气心狠手辣。"
        "经常在别人出价时嘴上唱衰实际上心里门儿清。"
    ),
    "Miles": (
        "Miles，31 岁，美籍华裔，前华尔街高频交易员，现职业收藏家。"
        "英文为主偶尔中文。说话精炼到像电报：EV positive / Pass / Edge too thin。"
        "前期装睡养预算，后期突然出手。没有无效发言。"
    ),
}


def persona_card(name: str) -> str:
    return PERSONA_CARDS.get(name, f"{name}，一位拍卖会常客。")


def _chat(
    messages: list[dict],
    max_tokens: int = 200,
    temperature: float = 0.9,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """向 DeepSeek 发一次 chat completion。成功返 content，任何异常返 None。"""
    api_key = _get_api_key()
    if not api_key:
        return None

    model = os.environ.get("AUCTION_KING_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        return content.strip() or None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, IndexError):
        return None
    except Exception:
        return None


def _strip_wrapping_quotes(text: str) -> str:
    """去掉成对的首尾引号（ASCII/中式/书名号）。"""
    pairs = [
        ('"', '"'),
        ("'", "'"),
        ("\u201C", "\u201D"),
        ("\u2018", "\u2019"),
        ("\u300C", "\u300D"),
        ("\u300E", "\u300F"),
        ("\u300A", "\u300B"),
    ]
    for lo, hi in pairs:
        if text.startswith(lo) and text.endswith(hi) and len(text) >= 2:
            return text[1:-1].strip()
    return text


def _sanitize_line(text: str, max_len: int = 60) -> str:
    """清理 LLM 输出：去前缀/换行/过长。"""
    if not text:
        return ""
    text = text.strip()
    text = _strip_wrapping_quotes(text)
    for prefix in ["台词：", "台词:", "回答：", "回答:", ":", "：", "— ", "- "]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    text = text.replace("\n", " ").replace("\r", " ")
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def llm_intro(max_rounds: int, budget: int, opponents: list[dict]) -> Optional[str]:
    """开场白（80-150 字）。失败返 None。"""
    if not is_enabled():
        return None

    opp_cards = "\n".join(
        f"- {o['display']}：{persona_card(o['name'])}"
        for o in opponents
    )
    system = (
        "你是民国时期上海滩一家老牌拍卖行的主持人，风格老派、带点江湖气、会吆喝。"
        "今晚主持一场暗标拍卖会。你的台词只用中文，要有画面感。"
    )
    user = (
        f"今晚总共 {max_rounds} 轮，每人初始预算 ${budget}。\n"
        f"今晚的 3 位常客：\n{opp_cards}\n\n"
        "请写一段 80-150 字的开场白，营造氛围，可以点名调侃每位常客一句。"
        "直接返回开场白正文，不要任何前缀、引号、解释。"
    )
    out = _chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=300,
        temperature=0.95,
    )
    return out.strip() if out else None


def llm_round_line(
    speaker: str,
    item_name: str,
    item_category: str,
    round_num: int,
    total_rounds: int,
    speaker_bid: int,
    winner_display: str,
    winning_bid: int,
    is_winner: bool,
) -> Optional[str]:
    """某角色一句话（<= 40 字）。失败返 None。"""
    if not is_enabled():
        return None
    card = persona_card(speaker)

    status = (
        f"你刚刚以 ${speaker_bid} 拿下了这件。"
        if is_winner
        else f"你出 ${speaker_bid}，但最终被 {winner_display} 以 ${winning_bid} 抢走。"
    )
    system = (
        "你在扮演一位参加上海滩拍卖会的角色，以下是你的人设：\n"
        f"{card}\n\n"
        "请严格按照该人设的口吻发言。"
    )
    user = (
        f"现在是第 {round_num}/{total_rounds} 轮。拍品：【{item_name}】（品类：{item_category}）。\n"
        f"{status}\n\n"
        "请用你的口吻说一句话（20-35 字），展现此刻的心情。"
        "直接返回台词原文，不要引号、前缀、解释、对话标签。"
    )
    out = _chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=100,
        temperature=1.0,
    )
    return _sanitize_line(out, max_len=60) if out else None


def llm_final_summary(ranking: list[dict], best_roi, worst_loss) -> Optional[str]:
    """终局主持人总结（80-150 字）。失败返 None。"""
    if not is_enabled():
        return None

    rank_lines = []
    medals = ["第 1 名", "第 2 名", "第 3 名", "第 4 名"]
    for i, r in enumerate(ranking):
        sign = "+" if r["profit"] >= 0 else ""
        # 把玩家的 display "你" 替换成明确的第三人称，避免 LLM 把它当主持人自称
        display = "那位人类玩家" if r["display"] == "你" else r["display"]
        rank_lines.append(
            f"{medals[i] if i < len(medals) else str(i+1)+'.'} {display} "
            f"资产 ${r['final_score']}（{sign}${r['profit']}）"
        )
    rank_text = "\n".join(rank_lines)

    extras = []
    if best_roi and best_roi[2] > 0:
        extras.append(f"最赚的一笔 +${best_roi[2]}")
    if worst_loss and worst_loss[2] < 0:
        extras.append(f"最冤的接盘 ${worst_loss[2]}")
    extras_text = ("\n\n附注：" + "；".join(extras)) if extras else ""

    system = (
        "你是今晚上海滩拍卖会的主持人，老派京沪腔、带江湖气、点评毒辣但不失分寸。"
        "注意：排名中所有人都是参赛者，没有一个是你本人；请用第三人称点评他们。"
    )
    user = (
        f"拍卖会结束了，最终排名：\n{rank_text}{extras_text}\n\n"
        "请写 80-150 字的结局感言，用主持人身份点评前几名的风格和特点，"
        "调侃一下『那位人类玩家』或垫底的那位。**全程第三人称**，不要自述。"
        "直接返回正文，不要前缀、标题、解释。"
    )
    out = _chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=300,
        temperature=0.9,
    )
    return out.strip() if out else None
