"""测试标题标签分类器 classify_tags。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from python.crawlers.tagger import classify_tags


def test_planning_tag():
    """十五五/十四五/十三五规划类应命中 文旅_规划。"""
    assert "文旅_规划" in classify_tags("文化和旅游部关于印发旅游强国建设十五五规划的通知")
    assert "文旅_规划" in classify_tags("十四五文化和旅游发展规划")


def test_application_tag():
    """申报窗口/资金申报类应命中 文旅_申报。"""
    tags = classify_tags("关于申报2026年度国家文化和旅游科技创新研发项目的通知")
    assert "文旅_申报" in tags
    tags = classify_tags("文化和旅游部办公厅关于开展人工智能+文化和旅游应用试点申报的通知")
    assert "文旅_申报" in tags


def test_wenwu_tag():
    """文物相关应命中 文旅_文物。"""
    assert "文旅_文物" in classify_tags("国家文物局关于革命文物保护工程技术导则的通知")


def test_multiple_tags():
    """一条政策可同时命中多个标签（规划+政策文件）。"""
    tags = classify_tags("关于印发十四五文化和旅游发展规划的通知")
    assert "文旅_规划" in tags
    assert "政策文件" in tags  # 含"规划"也含"通知"，但规划优先；至少多标签可叠加


def test_generic_notice():
    """普通通知命中 通知，不含文旅专属。"""
    tags = classify_tags("关于开展某某工作的通知")
    assert "通知" in tags


def test_empty_and_unknown():
    """空标题或无命中返回 新闻动态 或空。"""
    assert isinstance(classify_tags(""), list)
    tags = classify_tags("某某动态报道")
    assert "新闻动态" in tags or tags == []


def test_returns_list():
    """返回值必须是 list[str]，去重。"""
    tags = classify_tags("关于申报十四五文旅规划的通知")
    assert isinstance(tags, list)
    assert len(tags) == len(set(tags))  # 无重复


def test_rss_item_merges_title_tags():
    """RSS item 的 tags 应同时含源级标签和标题级标签，去重保序。"""
    from python.crawlers.tagger import classify_tags
    # 模拟一条标题级标签
    src_tags = ["国家级"]
    title = "文化和旅游部关于印发旅游强国建设十五五规划的通知"
    merged = list(dict.fromkeys(src_tags + classify_tags(title)))  # 去重保序
    assert "国家级" in merged          # 源级保留
    assert "文旅_规划" in merged        # 标题级加入
    assert "政策文件" in merged or "通知" in merged
    # 去重：源级与标题级重叠时不重复
    overlap = list(dict.fromkeys(["通知"] + classify_tags(title)))
    assert overlap.count("通知") == 1


def test_title_tag_filterable_when_not_in_source():
    """标题级标签（如 文旅_规划）不在源级 tags 时，merged tags 仍含它，
    使得 ?tag=文旅_规划 可过滤到该政策（过滤在 item 构建后于 Python 层）。"""
    from python.crawlers.tagger import classify_tags
    src_tags = ["国家级"]  # 源级不含 文旅_规划
    title = "关于印发十四五文化和旅游发展规划的通知"
    merged = list(dict.fromkeys(src_tags + classify_tags(title)))
    assert "文旅_规划" in merged
    assert "文旅_规划" not in src_tags  # 确认它来自标题级
