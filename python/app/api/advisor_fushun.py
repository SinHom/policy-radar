"""政策顾问 API - 抚顺市政策顾问（基于政府政策知识库的智能问答 Agent）。

与秦皇岛 advisor.py 完全独立：独立政策库检索（抚顺/辽宁/国家级）+ 独立 LLM prompt + 独立联网 query。
架构：RAG（政策库检索）+ 联网搜索补充 + LLM 结构化生成。
- 不再让模型凭空编造政策来源，每条红利必须挂真实政策库 ID 或联网 URL。
- 强制 JSON 输出（json_mode + chat_json），解析失败明文报错重试，不兜底假数据。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from typing import Optional

import httpx
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from sqlalchemy import Integer, func, or_, select
from sqlalchemy.orm import joinedload

from python.ai.llm_client import get_llm_client
from python.models import Policy, PolicySource
from python.models.base import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


# === 角色与系统提示词（通用版，无公司背景）===

ADVISOR_SYSTEM_PROMPT = """你是「抚顺市政策顾问」--一个基于政府政策知识库的智能问答 Agent。

你的职责：基于下方提供的【政策库检索结果】和【联网搜索结果】，针对用户描述的企业或项目情况，给出政策红利、项目风险和可行性判断。联网搜索结果来自真实检索，source 字段填网站名、source_url 填真实 URL、source_type 填"网"。

覆盖范围：抚顺市企业培育、科技创新、成果转化、数字化转型、人才引育等惠企政策，以及辽宁省、国家级相关政策。

铁律（违反即失败）：
1. 只用【政策库检索结果】和【联网搜索结果】里真实存在的政策。绝不能编造文号、编造来源、编造金额。
2. 每条红利的 source 必须填真实来源：政策库政策填发文单位（如"辽宁省科技厅"），联网结果填网站名。source_type 填 "库" 或 "网"。
3. 若该红利对应政策库中的政策，policy_id 必须填【政策库检索结果】里给出的真实 ID；联网结果 policy_id 填 null，source_url 填真实 URL。
4. 找不到真实依据就少写或不写，绝不凑数、绝不编造。
5. match_level 1-5 表示与用户项目的匹配度，5 最高。
6. 风险要真实指出，合规/资金/市场/运营/审批任一维度有风险就写，不回避。level 填"高"/"中"/"低"。
7. content 和 action 支持简短 markdown（换行、加粗、列表），但不要写大段废话。

只返回一个合法 JSON 对象，不要输出 JSON 以外的任何文字、不要用 markdown 围栏包裹。格式严格如下：
{
  "feasibility_score": 78,
  "verdict": "一句话总判断，点明值不值得投入",
  "bonuses": [
    {
      "policy_name": "政策名称",
      "source": "发文单位+文号 或 联网网站名",
      "source_type": "库",
      "policy_id": 123,
      "source_url": null,
      "priority": "立即",
      "match_level": 4,
      "content": "核心支持内容",
      "action": "建议行动"
    }
  ],
  "risks": [
    {
      "risk_type": "风险类型",
      "level": "高",
      "description": "具体表现",
      "suggestion": "应对建议"
    }
  ]
}
"""


# === 关键词抽取（轻量中文分词，无外部依赖）===

_STOPWORDS = {
    "的", "了", "是", "在", "我", "想", "做", "有", "和", "与", "及", "或", "等",
    "中", "上", "下", "不", "没", "要", "可以", "能", "会", "对", "给", "为", "以",
    "于", "这", "那", "也", "都", "就", "还", "把", "被", "让", "其", "之", "而",
    "一个", "一些", "什么", "怎么", "哪些", "情况", "项目", "相关", "了解", "知道",
    "帮忙", "帮我", "看看", "一下", "需要", "应该", "可能", "这个", "那个",
    "我在", "我想", "我要", "我有", "我做", "我想做", "我在抚顺",
}

# 惠企/科技领域高频有效词，优先保留
_DOMAIN_HINTS = {
    "高新技术企业", "高企", "专精特新", "小巨人", "科技型", "研发", "创新", "成果转化",
    "石化大学", "产学研", "中试", "技术合同", "数字化转型", "智能制造", "工业互联网",
    "企业培育", "梯度培育", "人才引育", "人才安居", "贷款贴息", "服务券",
    "补贴", "专项资金", "贷款", "税收", "减免", "奖补", "申报", "立项", "资质",
}


def _extract_keywords(text: str) -> list[str]:
    """从 scenario 抽取检索关键词。

    领域词全词扫描优先（in 匹配，长词优先），避免 re.findall 的贪婪 {2,6}
    把「高新技术企业」拆进「抚顺高新」导致 DOMAIN_HINTS 匹配不上。
    """
    text_str = text or ""
    seen: set[str] = set()
    ordered: list[str] = []
    # 1. 领域词全词扫描（长词优先）
    for hint in sorted(_DOMAIN_HINTS, key=len, reverse=True):
        if hint in text_str and hint not in seen:
            seen.add(hint)
            ordered.append(hint)
    # 2. 补其他有效中文段（2-4 字，去停用词）
    for w in re.findall(r"[一-龥]{2,4}", text_str):
        if w in seen or w in _STOPWORDS or len(w) < 2:
            continue
        seen.add(w)
        ordered.append(w)
        if len(ordered) >= 8:
            break
    return ordered


# === 政策库 RAG 检索 ===

def _keyword_filter(keywords: list[str]):
    """构造关键词 OR 条件（命中 title / summary_text / raw_content）。"""
    conds = []
    for kw in keywords:
        if not kw:
            continue
        like = f"%{kw}%"
        conds.append(Policy.title.like(like))
        conds.append(Policy.summary_text.like(like))
        conds.append(Policy.raw_content.like(like))
    return or_(*conds) if conds else None


async def _search_policies(scenario: str, limit: int = 10) -> list[Policy]:
    """按地区（抚顺/辽宁/国家级）+ 关键词检索政策库 top N。

    关键词命中不足时，fallback 到纯地区最新政策（让模型自己挑相关性）。

    注：不强制 summary_text 非空--很多政策只抓了 raw_content 还没做摘要，
    用 raw_content 兜底检索，避免 references 全空、点击无原文可看。
    """
    keywords = _extract_keywords(scenario)
    region_cond = or_(
        PolicySource.region.like("%抚顺%"),
        PolicySource.region.like("%辽宁%"),
        PolicySource.category == "国家级",
    )
    # 有正文即可（摘要或原文，二选一）
    has_text = or_(
        Policy.summary_text.isnot(None),
        func.length(Policy.raw_content) > 100,
    )

    async with get_session() as session:
        # 第一轮：地区 + 关键词
        stmt = (
            select(Policy)
            .options(joinedload(Policy.source))
            .join(PolicySource, Policy.source_id == PolicySource.id)
            .where(has_text)
            .where(region_cond)
        )
        kf = _keyword_filter(keywords)
        if kf is not None:
            stmt = stmt.where(kf)
        # title 命中关键词越多越相关，优先于纯发布时间（避免泛词如"改造"的最新无关政策压过精准词）
        title_score = None
        for kw in keywords:
            if kw:
                bit = Policy.title.like(f"%{kw}%").cast(Integer)
                title_score = bit if title_score is None else title_score + bit
        if title_score is not None:
            stmt = stmt.order_by(title_score.desc(), Policy.published_at.desc().nulls_last(), Policy.id.desc())
        else:
            stmt = stmt.order_by(Policy.published_at.desc().nulls_last(), Policy.id.desc())
        stmt = stmt.limit(limit)
        policies = list((await session.execute(stmt)).scalars().all())

        if len(policies) >= 3:
            return policies

        # 第二轮 fallback：纯地区最新有正文的（跨关键词）
        stmt2 = (
            select(Policy)
            .options(joinedload(Policy.source))
            .join(PolicySource, Policy.source_id == PolicySource.id)
            .where(has_text)
            .where(region_cond)
            .order_by(
                Policy.published_at.desc().nulls_last(),
                Policy.id.desc(),
            )
            .limit(limit)
        )
        fallback = list((await session.execute(stmt2)).scalars().all())
        # 合并去重
        seen_ids = {p.id for p in policies}
        for p in fallback:
            if p.id not in seen_ids:
                policies.append(p)
                seen_ids.add(p.id)
            if len(policies) >= limit:
                break
        return policies


def _format_policy_context(policies: list[Policy]) -> tuple[str, dict[int, dict]]:
    """把检索到的政策格式化成 prompt 上下文，同时返回 id->meta 映射供后端校验/补全。"""
    if not policies:
        return "（本次未检索到相关本地政策，请主要依赖联网结果与通用判断，并在 source 中诚实标注。）", {}
    lines = []
    meta: dict[int, dict] = {}
    for i, p in enumerate(policies, 1):
        src = p.source
        source_name = ""
        if src:
            parts = []
            if src.department:
                parts.append(src.department)
            if src.region:
                parts.append(src.region)
            if not parts and src.name:
                parts.append(src.name)
            source_name = "".join(parts) if parts else (src.name or "")
        summary = (p.summary_text or "").strip()
        if not summary and p.raw_content:
            # 没摘要时用原文前 300 字兜底（去 HTML 标签的粗清洗）
            raw = re.sub(r"<[^>]+>", " ", p.raw_content)
            summary = re.sub(r"\s+", " ", raw).strip()[:300]
        if len(summary) > 300:
            summary = summary[:300] + "…"
        lines.append(
            f"[{i}] ID={p.id} | {source_name or '未知来源'} | 《{p.title}》\n"
            f"摘要：{summary}\n"
            f"原文：/policy-radar/markdown/{p.id}"
        )
        meta[p.id] = {
            "policy_id": p.id,
            "title": p.title,
            "source_name": source_name or (src.name if src else ""),
            "url": p.url,
            "region": src.region if src else None,
            "published_at": p.published_at.isoformat() if p.published_at else None,
        }
    return "\n\n".join(lines), meta


# === 联网搜索（MiniMax 官方 Web Search API：/v1/coding_plan/search）===

async def _web_search(query: str, max_results: int = 5) -> list[dict]:
    """联网搜索。失败静默降级（返回空列表），不阻塞主流程。

    用 MiniMax 官方 Web Search API（/v1/coding_plan/search，参数 q），
    复用现有 MINIMAX_API_KEY + base_url，返回真实政策新闻结果。
    （duckduckgo 在大陆服务器返回垃圾，tinyfish 服务器未安装，均弃用。）
    """
    try:
        client = await get_llm_client()
    except Exception as e:
        logger.warning("get_llm_client for web search failed: %s", e)
        return []

    # base_url 形如 https://api.minimaxi.com/v1，搜索端点是 /v1/coding_plan/search
    base = (client.base_url or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/v1/coding_plan/search"

    async with httpx.AsyncClient(timeout=20) as hc:
        try:
            r = await hc.post(url, json={"q": query},
                headers={"Authorization": f"Bearer {client.api_key}", "Content-Type": "application/json"})
            if r.status_code != 200:
                logger.warning("minimax search %d: %s", r.status_code, r.text[:200])
                return []
            data = r.json()
        except Exception as e:
            logger.warning("minimax search failed: %s", e)
            return []

    organic = data.get("organic") or []
    out: list[dict] = []
    for item in organic[:max_results]:
        link = item.get("link") or ""
        site_name = ""
        if link and "/" in link:
            try:
                site_name = link.split("/")[2]
            except IndexError:
                pass
        out.append({
            "title": (item.get("title") or "")[:120],
            "url": link,
            "snippet": (item.get("snippet") or "")[:200],
            "site_name": site_name,
        })
    return out


def _format_web_context(web_results: list[dict]) -> str:
    if not web_results:
        return "（本次联网未返回结果或 tinyfish 不可用。）"
    lines = []
    for i, r in enumerate(web_results, 1):
        site = r.get("site_name") or ""
        lines.append(
            f"[网{i}] {site} | {r['title']}\n"
            f"摘要：{r['snippet']}\n"
            f"链接：{r['url']}"
        )
    return "\n\n".join(lines)


# === 请求/响应模型 ===

class AdvisorAnalyzeRequest(BaseModel):
    scenario: str
    use_web: bool = True  # 是否启用联网搜索


class PolicyBonus(BaseModel):
    policy_name: str
    source: str
    source_type: str = "库"           # "库" / "网"
    policy_id: Optional[int] = None
    source_url: Optional[str] = None
    priority: str = "中期"             # 立即 / 中期 / 长期
    match_level: int = 3              # 1-5
    content: str
    action: str


class ProjectRisk(BaseModel):
    risk_type: str
    level: str = "中"                 # 高 / 中 / 低
    description: str
    suggestion: str


class PolicyReference(BaseModel):
    policy_id: int
    title: str
    source_name: str
    url: str
    region: Optional[str] = None
    published_at: Optional[str] = None


class AdvisorAnalyzeResponse(BaseModel):
    feasibility_score: int = 0
    verdict: str = ""
    bonuses: list[PolicyBonus] = []
    risks: list[ProjectRisk] = []
    references: list[PolicyReference] = []
    searched_online: bool = False
    policy_count: int = 0


# === 端点 ===

@router.post("/advisor-fushun/analyze", response_model=AdvisorAnalyzeResponse)
async def analyze_scenario(req: AdvisorAnalyzeRequest):
    """抚顺市政策顾问：RAG 政策库 + 联网搜索 + LLM 结构化分析（独立于秦皇岛 /advisor/analyze）。"""
    if not req.scenario or len(req.scenario.strip()) < 10:
        raise HTTPException(status_code=400, detail="项目描述至少需要 10 个字")

    scenario = req.scenario.strip()

    # 1. RAG 政策库检索
    try:
        policies = await _search_policies(scenario, limit=10)
    except Exception as e:
        logger.exception("policy search failed: %s", e)
        policies = []
    policy_context, policy_meta = _format_policy_context(policies)

    # 2. 联网搜索（duckduckgo，显式调用把结果喂给 LLM 当上下文）
    #    注：M3 的 plugins web_search 在 /v1/chat/completions 端点不生效（实测模型自称未联网），
    #    改回后端自己搜，结果作为 prompt 上下文传入，LLM 据此生成带真实 source_url 的网类红利。
    web_results: list[dict] = []
    searched_online = False
    if req.use_web:
        try:
            kws = _extract_keywords(scenario)[:4]
            web_query = "抚顺 企业 政策 " + " ".join(kws) if kws else "抚顺 惠企 政策 2026"
            web_results = await _web_search(web_query, max_results=5)
            searched_online = bool(web_results)
        except Exception as e:
            logger.warning("web search failed: %s", e)
            web_results = []
    web_context = _format_web_context(web_results)

    # 3. 组装 user prompt
    user_prompt = f"""## 政策库检索结果（抚顺/辽宁/国家级，与项目相关）
{policy_context}

## 联网搜索结果（最新动态，已为真实检索）
{web_context}

## 用户项目情况
{scenario}

---

请基于上述真实政策与联网结果分析。每条红利必须能对应到上面的【政策库检索结果】(填真实 policy_id)或【联网搜索结果】(填真实 source_url、source 填网站名)。找不到真实依据的红利不要写。
"""

    # 4. 调 LLM（强制 JSON，失败重试 1 次）
    #    不再用 plugins web_search -- 该参数在 /v1/chat/completions 端点不生效，
    #    联网由上面 _web_search 显式完成并塞入 prompt 上下文。
    client = await get_llm_client()
    data: dict = {}
    last_err: Optional[Exception] = None
    valid_policy_ids = set(policy_meta.keys())
    for attempt in range(2):
        try:
            text = await client.chat(
                system=ADVISOR_SYSTEM_PROMPT,
                user=user_prompt,
                json_mode=True,
                max_tokens=3000,  # 联网结果让输出更长（含网类红利），给足空间防 JSON 截断触发重试
                purpose="advisor_analyze",
            )
            data = _parse_advisor_json(text)
            if isinstance(data, dict):
                break
        except Exception as e:
            last_err = e
            logger.warning("LLM JSON attempt %d failed: %s", attempt + 1, e)
    else:
        raise HTTPException(status_code=500, detail=f"AI 分析失败（多次重试仍无法解析）: {last_err}")

    # 5. 清洗 + 校验 policy_id
    bonuses = _clean_bonuses(data.get("bonuses", []), valid_policy_ids)
    risks = _clean_risks(data.get("risks", []))
    verdict = _clean_verdict(data.get("verdict", ""))
    score = _coerce_score(data.get("feasibility_score"))

    # 6. references 后端用检索到的政策生成（不依赖模型）
    references = [
        PolicyReference(
            policy_id=m["policy_id"],
            title=m["title"],
            source_name=m["source_name"],
            url=m["url"],
            region=m["region"],
            published_at=m["published_at"],
        )
        for m in policy_meta.values()
    ]

    return AdvisorAnalyzeResponse(
        feasibility_score=score,
        verdict=verdict,
        bonuses=bonuses,
        risks=risks,
        references=references,
        searched_online=searched_online,
        policy_count=len(policies),
    )


# === 清洗函数 ===

# advisor JSON 固定起始 key（SYSTEM_PROMPT 规定），用于跳过 M3 reasoning 思考链前缀
_ADVISOR_JSON_START = '{"feasibility_score"'


def _parse_advisor_json(text: str) -> dict:
    """从 LLM 输出提取 advisor JSON。

    M3 开 web_search 插件后会把 reasoning 思考链（英文叙述）混入 content，
    通用 _safe_parse_json 的「首个 {」定位会被思考链里的 { 字符带偏。
    这里用已知起始 key {"feasibility_score" 定位真正 JSON 起点。
    """
    if not text:
        raise ValueError("Empty LLM response")
    s = text.strip()
    # 剥 ```json 围栏
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if m:
        s = m.group(1)
    # 优先从已知起始 key 定位（跳过思考链前缀里的 { 字符）
    idx = s.find(_ADVISOR_JSON_START)
    if idx == -1:
        # fallback：宽松找首个 {（无思考链的常规输出）
        idx = s.find("{")
    last = s.rfind("}")
    if idx != -1 and last > idx:
        s = s[idx : last + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"advisor JSON not valid: {e}; raw head: {text[:300]}")


# 提示词泄露 / 思考草稿 / JSON 字段名泄露的脏字符串特征
_BAD_FRAGMENTS = (
    "Let me draft", "Let me write", "Risks:", "Bonuses:", "verdict", "feasibility_score",
    "policy_name", "source_type", "match_level", "risk_type", "description", "suggestion",
    "我需要", "让我写", "让我", "最终回复", "响应应当", "合法JSON", "JSON对象",
    "JSON格式", "LLM生成", "llm生成", "系统提示", "你只能", "绝对不要",
    "no additional text", "only output JSON", "json_object", "```",
)


def _is_dirty(s: str) -> bool:
    if not s:
        return False
    s_low = s.lower()
    # JSON 字段名行特征：以 "xxx": 开头
    if re.match(r'^\s*"[a-z_]+"[：:]', s_low):
        return True
    return any(bad.lower() in s_low for bad in _BAD_FRAGMENTS)


def _clean_bonuses(raw_bonuses: list, valid_policy_ids: set[int]) -> list[PolicyBonus]:
    out: list[PolicyBonus] = []
    for b in raw_bonuses:
        if not isinstance(b, dict):
            continue
        name = (b.get("policy_name") or "").strip()
        if not name or _is_dirty(name):
            continue
        source = (b.get("source") or "").strip()
        if _is_dirty(source):
            source = ""
        # 校验 policy_id：必须在检索到的真实集合里，否则置空
        pid = b.get("policy_id")
        if pid is not None:
            try:
                pid = int(pid)
                if pid not in valid_policy_ids:
                    pid = None
            except (TypeError, ValueError):
                pid = None
        source_type = (b.get("source_type") or "").strip()
        if source_type not in ("库", "网"):
            source_type = "库" if pid else "网"
        source_url = (b.get("source_url") or "").strip() or None
        priority = (b.get("priority") or "").strip()
        if priority not in ("立即", "中期", "长期"):
            priority = "中期"
        try:
            match_level = max(1, min(5, int(b.get("match_level", 3))))
        except (TypeError, ValueError):
            match_level = 3
        content = (b.get("content") or "").strip()
        action = (b.get("action") or "").strip()
        if not content:
            continue
        out.append(PolicyBonus(
            policy_name=name,
            source=source or "未知来源",
            source_type=source_type,
            policy_id=pid,
            source_url=source_url,
            priority=priority,
            match_level=match_level,
            content=content,
            action=action,
        ))
    return out


def _clean_risks(raw_risks: list) -> list[ProjectRisk]:
    out: list[ProjectRisk] = []
    for r in raw_risks:
        if not isinstance(r, dict):
            continue
        risk_type = (r.get("risk_type") or "").strip()
        if not risk_type or _is_dirty(risk_type):
            risk_type = "风险识别"
        level = (r.get("level") or "").strip()
        if level not in ("高", "中", "低"):
            level = "中"
        description = (r.get("description") or "").strip()
        suggestion = (r.get("suggestion") or "").strip()
        if _is_dirty(description):
            # 字段名泄露行整条跳过
            continue
        if not description:
            continue
        out.append(ProjectRisk(
            risk_type=risk_type,
            level=level,
            description=description,
            suggestion=suggestion or "建议进一步评估后制定应对方案",
        ))
    return out


def _clean_verdict(raw: str) -> str:
    v = (raw or "").strip()
    if not v or _is_dirty(v):
        return "（见上方政策红利与风险分析）"
    # 截断过长总判断
    if len(v) > 300:
        v = v[:300] + "…"
    return v


def _coerce_score(raw) -> int:
    try:
        s = int(raw)
        return max(0, min(100, s))
    except (TypeError, ValueError):
        return 0
