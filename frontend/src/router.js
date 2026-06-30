import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Subscriptions from './views/Subscriptions.vue'
import Policies from './views/Policies.vue'
import Sources from './views/Sources.vue'
import PushLogs from './views/PushLogs.vue'
import LLMConfig from './views/LLMConfig.vue'
import AuditLogs from './views/AuditLogs.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/subscriptions', name: 'subscriptions', component: Subscriptions },
    { path: '/policies', name: 'policies', component: Policies },
    { path: '/sources', name: 'sources', component: Sources },
    { path: '/push-logs', name: 'push-logs', component: PushLogs },
    { path: '/llm-config', name: 'llm-config', component: LLMConfig },
    { path: '/audit-logs', name: 'audit-logs', component: AuditLogs },
  ],
})
