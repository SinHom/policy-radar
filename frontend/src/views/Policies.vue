<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const policies = ref([])
const query = ref('')
const toast = ref({ show: false, msg: '' })

function showToast(msg) {
  toast.value = { show: true, msg }
  setTimeout(() => toast.value.show = false, 2500)
}

async function search() {
  const r = await api.get('/policies', { params: { query: query.value, limit: 50, summarized_only: false } })
  policies.value = r.data
}

async function crawl() {
  showToast('⏳ 爬取中...')
  await api.post('/crawl/all')
  showToast('✅ 爬取已触发')
}

function badgeColor(type) {
  const m = { '补贴': 'bg-green-100 text-green-700', '贷款': 'bg-blue-100 text-blue-700',
    '税收': 'bg-purple-100 text-purple-700', '人才': 'bg-pink-100 text-pink-700',
    '产业扶持': 'bg-orange-100 text-orange-700' }
  return m[type] || 'bg-gray-100 text-gray-600'
}

onMounted(search)
</script>

<template>
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-xl font-semibold text-gray-900">📜 政策库</h2>
    <div class="flex gap-2">
      <input v-model="query" @keyup.enter="search" placeholder="搜索关键词..."
             class="text-sm px-3 py-1.5 border border-gray-200 rounded-lg" />
      <button @click="search" class="text-sm px-3 py-1.5 rounded-lg bg-brand-500 text-white hover:bg-brand-600">搜索</button>
      <button @click="crawl" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">爬取</button>
    </div>
  </div>
  <div class="text-xs text-gray-500 mb-2">共 {{ policies.length }} 条</div>
  <div class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-[70vh] overflow-y-auto">
    <div v-for="p in policies" :key="p.id" class="px-5 py-3 hover:bg-gray-50">
      <div class="flex items-center gap-2 mb-1">
        <span :class="badgeColor(p.type)" class="text-xs px-2 py-0.5 rounded-full font-medium">{{ p.type || '其他' }}</span>
        <span class="text-xs text-gray-400">#{{ p.id }} · {{ p.source_id }}</span>
        <span v-if="p.deadline" class="text-xs text-orange-600">⏰ {{ p.deadline }}</span>
        <span v-if="p.amount" class="text-xs text-green-600">💰 {{ p.amount }}</span>
      </div>
      <h3 class="text-sm font-medium text-gray-900">{{ p.title }}</h3>
      <p class="text-xs text-gray-600 line-clamp-2 mt-1">{{ p.summary || '(无摘要)' }}</p>
    </div>
  </div>
  <div v-if="toast.show" class="fixed bottom-6 right-6 bg-gray-900 text-white px-5 py-3 rounded-xl shadow-lg z-50">{{ toast.msg }}</div>
</template>
