# 监控（Prometheus + Grafana）

## 启动

```bash
docker compose up -d prometheus grafana
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000（admin/admin，自动登录）

## 已有指标

`/metrics` 端点暴露：

| 指标 | 类型 | 说明 |
|------|------|------|
| `policy_radar_policies_total` | gauge | 政策总数 |
| `policy_radar_policies_summarized` | gauge | 已摘要数 |
| `policy_radar_policies_crawled_7d` | counter | 近 7 天新爬取 |
| `policy_radar_companies_total` | gauge | 企业总数 |
| `policy_radar_subscriptions_total` | gauge | 订阅总数 |
| `policy_radar_subscriptions_enabled` | gauge | 启用订阅 |
| `policy_radar_matches_total` | gauge | 匹配总数 |
| `policy_radar_matches_pushed` | gauge | 已推送匹配 |
| `policy_radar_push_total_24h` | counter | 24h 推送数 |
| `policy_radar_push_success_24h` | counter | 24h 推送成功 |
| `policy_radar_push_success_rate_24h` | gauge | 24h 推送成功率 |
| `policy_radar_dead_letters_unresolved` | gauge | 未解决死信 |
| `policy_radar_dead_letters_resolved` | gauge | 已解决死信 |

## 预置 Dashboard

`monitoring/grafana-dashboard.json` 包含 7 个 panel：
- 4 个 stat（Policies/Companies/Subs/Matches 总数）
- 1 个 24h 推送成功率曲线
- 1 个死信数曲线
- 1 个 7d 爬取量曲线

打开 Grafana → Dashboards → Browse → "Policy Radar Overview"。
