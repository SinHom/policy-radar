<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api.js'

const funnel = ref(null)
const companies = ref(null)
const health = ref(null)

onMounted(async () => {
  const [f, c] = await Promise.all([
    api.get('/dashboard/funnel'),
    api.get('/dashboard/companies'),
  ])
  funnel.value = f.data
  companies.value = c.data
  try {
    health.value = (await fetch('/health')).json()
  } catch {}
})

const stats = computed(() => {
  if (!funnel.value) return []
  const s = funnel.value.stats || {}
  return [
    { label: '推送成功', value: s.push_success, color: 'text-green-600' },
    { label: '触达',   value: s.reached,      color: 'text-brand-600' },
    { label: '企业',   value: companies.value?.count || 0, color: 'text-accent-600' },
    { label: '成功率', value: `${(s.push_success_rate * 100).toFixed(0)}%`, color: 'text-gray-900' },
  ]
})
</script>

<template>
  <h2 class="text-xl font-semibold text-gray-900 mb-4">📊 概览</h2>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
    <div v-for="s in stats" :key="s.label" class="bg-white border border-gray-200 rounded-xl p-4">
      <div class="text-xs text-gray-500">{{ s.label }}</div>
      <div class="text-2xl font-semibold mt-1" :class="s.color">{{ s.value }}</div>
    </div>
  </div>
  <div class="bg-white border border-gray-200 rounded-xl p-4">
    <h3 class="text-sm font-semibold text-gray-900 mb-3">漏斗（推送 → 触达 → 咨询）</h3>
    <div v-if="funnel" class="flex items-end gap-4 h-32">
      <div v-for="(stage, i) in funnel.funnel" :key="stage.stage" class="flex-1 flex flex-col items-center">
        <div class="text-xs text-gray-500 mb-1">{{ stage.stage }}</div>
        <div class="w-full rounded-t-md transition-all"
             :class="i === 0 ? 'bg-brand-500' : i === 1 ? 'bg-brand-400' : 'bg-accent-500'"
             :style="{ height: (stage.count / Math.max(funnel.funnel[0].count, 1) * 100) + '%' }">
        </div>
        <div class="text-lg font-semibold mt-2">{{ stage.count }}</div>
      </div>
    </div>
  </div>
  <div v-if="companies?.companies?.length" class="bg-white border border-gray-200 rounded-xl p-4 mt-6">
    <h3 class="text-sm font-semibold text-gray-900 mb-3">企业概览</h3>
    <table class="w-full text-sm">
      <thead class="text-xs text-gray-500">
        <tr><th class="text-left">企业</th><th>行业</th><th>地区</th><th>订阅</th><th>匹配</th><th>推送</th></tr>
      </thead>
      <tbody>
        <tr v-for="c in companies.companies" :key="c.company_id" class="border-t border-gray-100">
          <td class="py-2 font-medium">{{ c.name }}</td>
          <td class="text-center">{{ c.industry || '-' }}</td>
          <td class="text-center">{{ c.region || '-' }}</td>
          <td class="text-center">{{ c.subscriptions }}</td>
          <td class="text-center">{{ c.matches }}</td>
          <td class="text-center">{{ c.pushed }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
