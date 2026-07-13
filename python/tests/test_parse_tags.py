"""测试 parse_tags 边界：确保 JSON string/object 等非 array 输入安全降级为 []。

背景：parse_tags(json.loads(raw)) 可能返回 str/dict（当 src.tags 存的是
JSON string 或 object 而非 array），与 classify_tags 结果拼接时会 TypeError，
导致 RSS/article/markdown 端点 500。本测试锁定防护层。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from python.app.api.policy_radar import parse_tags


def test_none_returns_empty():
    assert parse_tags(None) == []


def test_empty_list_returns_empty():
    assert parse_tags([]) == []


def test_list_passthrough():
    assert parse_tags(["文旅_政策"]) == ["文旅_政策"]


def test_json_array_string():
    assert parse_tags('["国家级","文旅_政策"]') == ["国家级", "文旅_政策"]


def test_json_string_degrades_to_empty():
    """JSON string（非 array）修复后安全降级为 []。"""
    assert parse_tags('"国家级"') == []


def test_json_object_degrades_to_empty():
    """JSON object（非 array）修复后安全降级为 []。"""
    assert parse_tags('{"k":"v"}') == []


def test_invalid_json_returns_empty():
    assert parse_tags("not json") == []


def test_empty_string_returns_empty():
    assert parse_tags("") == []
