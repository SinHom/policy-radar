# Policy-radar — Hermes memory 归档

> 2026-08-15 从 Hermes memory 归档，项目后续不再开发。

- WeKnora: `policies` 表 `raw_content`（图片 VLM caption 后转 HTML）
- 外部 KB 抓取端点: `/policy-radar/markdown/{id}`，输出带 YAML frontmatter 的 md
- 后端 RAG: `advisor.py`
- KB 配置: 需配齐 embedding model + summary model + chunking
