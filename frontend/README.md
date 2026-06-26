# Policy Radar Admin (Vue 3 + Vite)

管理后台前端，对接 FastAPI 8000 端口。

## 开发

```bash
cd frontend
npm install
npm run dev
# 浏览器打开 http://localhost:5173
# Vite proxy 自动转发 /api /health /metrics /version 到 8000
```

## 生产 build

```bash
npm run build
# 产物在 dist/ 目录
# 可用 Nginx / FastAPI StaticFiles 托管
```

## 路由

- `/` Dashboard（漏斗 + 企业概览）
- `/subscriptions` 订阅管理（启停/删除）
- `/policies` 政策库（搜索/爬取触发）
- `/sources` 政策源
- `/push-logs` 推送历史
