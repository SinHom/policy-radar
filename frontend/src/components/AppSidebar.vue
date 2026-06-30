<script setup>
import { RouterLink } from 'vue-router'

const tabs = [
  { name: 'dashboard',     label: '概览',     icon: '📊' },
  { name: 'subscriptions', label: '订阅',     icon: '📋' },
  { name: 'policies',      label: '政策库',   icon: '📜' },
  { name: 'sources',       label: '政策源',   icon: '🕷️' },
  { name: 'push-logs',     label: '推送历史', icon: '📤' },
  { name: 'llm-config',    label: 'LLM 配置', icon: '🤖' },
  { name: 'audit-logs',    label: '审计日志', icon: '📜' },
]

defineProps({ open: Boolean })
const emit = defineEmits(['navigate'])
</script>

<template>
  <nav :class="[
    'shrink-0 transition-all',
    open ? 'block' : 'hidden md:block',
    'w-full md:w-48'
  ]">
    <ul class="space-y-1 md:sticky md:top-20">
      <li v-for="t in tabs" :key="t.name">
        <RouterLink :to="{ name: t.name }" @click="emit('navigate')"
                    active-class="bg-brand-50 text-brand-700 border-l-2 border-brand-500"
                    class="block w-full text-left px-4 py-2.5 rounded-r-lg text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors">
          <span class="mr-2">{{ t.icon }}</span>{{ t.label }}
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>
