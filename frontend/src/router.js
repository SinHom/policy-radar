import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Subscriptions from './views/Subscriptions.vue'
import Policies from './views/Policies.vue'
import Sources from './views/Sources.vue'
import PushLogs from './views/PushLogs.vue'
import LLMConfig from './views/LLMConfig.vue'
import AuditLogs from './views/AuditLogs.vue'
import Login from './views/Login.vue'
import api from './api.js'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login, meta: { public: true } },
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/subscriptions', name: 'subscriptions', component: Subscriptions },
    { path: '/policies', name: 'policies', component: Policies },
    { path: '/sources', name: 'sources', component: Sources },
    { path: '/push-logs', name: 'push-logs', component: PushLogs },
    { path: '/llm-config', name: 'llm-config', component: LLMConfig },
    { path: '/audit-logs', name: 'audit-logs', component: AuditLogs },
  ],
})

// 路由守卫:非 public 路由必须已登录(否则跳登录页)
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  try {
    await api.get('/auth/me')
    return true
  } catch {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})