"""
LLM 台词层测试。

策略：不真实调用网络。
- 用 monkeypatch 把 `_chat` / `is_enabled` 替换掉，测三种路径：
  1. LLM 关闭 → 各函数返回 None
  2. LLM 开启 + API 正常 → 返回清洗后的字符串
  3. LLM 开启 + API 失败 → 返回 None（调用方会 fallback）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import llm_narrator


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_opponents():
    return [
        {"name": "老周头", "display": "老周头", "persona": "北京琉璃厂老掌柜"},
        {"name": "Kai", "display": "Kai", "persona": "硅谷 VC"},
        {"name": "艺姐", "display": "艺姐", "persona": "景德镇鉴定师"},
    ]


@pytest.fixture
def sample_ranking():
    return [
        {"name": "human", "display": "你", "final_score": 2100, "profit": 100},
        {"name": "老周头", "display": "老周头", "final_score": 1980, "profit": -20},
        {"name": "Kai", "display": "Kai", "final_score": 1500, "profit": -500},
    ]


# ============================================================================
# is_enabled
# ============================================================================

def test_is_enabled_default_off(monkeypatch):
    monkeypatch.delenv("AUCTION_KING_USE_LLM", raising=False)
    assert llm_narrator.is_enabled() is False


@pytest.mark.parametrize("val,expected", [
    ("1", True),
    ("true", True),
    ("TRUE", True),
    ("yes", True),
    ("on", True),
    ("0", False),
    ("false", False),
    ("no", False),
    ("", False),
    ("  ", False),
])
def test_is_enabled_parses_env(monkeypatch, val, expected):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", val)
    assert llm_narrator.is_enabled() is expected


# ============================================================================
# fallback：LLM 关闭时所有生成函数返回 None
# ============================================================================

def test_intro_returns_none_when_disabled(monkeypatch, sample_opponents):
    monkeypatch.delenv("AUCTION_KING_USE_LLM", raising=False)
    assert llm_narrator.llm_intro(7, 2000, sample_opponents) is None


def test_round_line_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("AUCTION_KING_USE_LLM", raising=False)
    result = llm_narrator.llm_round_line(
        speaker="Kai",
        item_name="清代瓷碗",
        item_category="瓷器",
        round_num=1,
        total_rounds=7,
        speaker_bid=500,
        winner_display="你",
        winning_bid=600,
        is_winner=False,
    )
    assert result is None


def test_final_summary_returns_none_when_disabled(monkeypatch, sample_ranking):
    monkeypatch.delenv("AUCTION_KING_USE_LLM", raising=False)
    result = llm_narrator.llm_final_summary(sample_ranking, None, None)
    assert result is None


# ============================================================================
# 启用但 API 挂掉 → 应返回 None（不抛）
# ============================================================================

def test_intro_returns_none_on_api_failure(monkeypatch, sample_opponents):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", "1")
    monkeypatch.setattr(llm_narrator, "_chat", lambda *a, **kw: None)
    result = llm_narrator.llm_intro(7, 2000, sample_opponents)
    assert result is None


def test_round_line_returns_none_on_api_failure(monkeypatch):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", "1")
    monkeypatch.setattr(llm_narrator, "_chat", lambda *a, **kw: None)
    result = llm_narrator.llm_round_line(
        speaker="Kai", item_name="A", item_category="杂项",
        round_num=1, total_rounds=7,
        speaker_bid=100, winner_display="你", winning_bid=200,
        is_winner=False,
    )
    assert result is None


def test_final_summary_returns_none_on_api_failure(monkeypatch, sample_ranking):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", "1")
    monkeypatch.setattr(llm_narrator, "_chat", lambda *a, **kw: None)
    result = llm_narrator.llm_final_summary(sample_ranking, None, None)
    assert result is None


# ============================================================================
# 成功路径：mock _chat 返回字符串，验证被正确清洗
# ============================================================================

def test_intro_success(monkeypatch, sample_opponents):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", "1")
    monkeypatch.setattr(
        llm_narrator, "_chat",
        lambda *a, **kw: "诸位看官，今晚竞拍正式开始。",
    )
    result = llm_narrator.llm_intro(7, 2000, sample_opponents)
    assert result == "诸位看官，今晚竞拍正式开始。"


def test_round_line_strips_quotes(monkeypatch):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", "1")
    monkeypatch.setattr(
        llm_narrator, "_chat",
        lambda *a, **kw: '"这件东西归我了。"',
    )
    result = llm_narrator.llm_round_line(
        speaker="Kai", item_name="A", item_category="杂项",
        round_num=1, total_rounds=7,
        speaker_bid=100, winner_display="你", winning_bid=200,
        is_winner=False,
    )
    assert result == "这件东西归我了。"


def test_round_line_strips_chinese_quotes(monkeypatch):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", "1")
    monkeypatch.setattr(
        llm_narrator, "_chat",
        lambda *a, **kw: "「这件东西归我了。」",
    )
    result = llm_narrator.llm_round_line(
        speaker="Kai", item_name="A", item_category="杂项",
        round_num=1, total_rounds=7,
        speaker_bid=100, winner_display="你", winning_bid=200,
        is_winner=False,
    )
    assert result == "这件东西归我了。"


def test_round_line_truncates_long_output(monkeypatch):
    monkeypatch.setenv("AUCTION_KING_USE_LLM", "1")
    long_text = "这是一段非常非常长的台词" * 10
    monkeypatch.setattr(llm_narrator, "_chat", lambda *a, **kw: long_text)
    result = llm_narrator.llm_round_line(
        speaker="Kai", item_name="A", item_category="杂项",
        round_num=1, total_rounds=7,
        speaker_bid=100, winner_display="你", winning_bid=200,
        is_winner=False,
    )
    assert result is not None
    assert len(result) <= 61  # 60 + '…'
    assert result.endswith("…")


# ============================================================================
# _chat：key 缺失时直接 None，不触发网络
# ============================================================================

def test_chat_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = llm_narrator._chat([{"role": "user", "content": "hi"}])
    assert result is None


# ============================================================================
# persona_card：不存在的人也不抛
# ============================================================================

def test_persona_card_fallback():
    card = llm_narrator.persona_card("不存在的人")
    assert "不存在的人" in card


def test_persona_card_known():
    for name in ["老周头", "Kai", "艺姐", "阿鬼", "Miles"]:
        card = llm_narrator.persona_card(name)
        assert len(card) > 10
