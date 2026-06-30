<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const logs = ref([])
const stats = ref(null)
const filters = ref({ actor: '', action: '', status: '' })
const loading = ref(false)
const total = ref(0)

async function load() {
  loading.value = true
  try {
    const params = { limit: 200 }
    Object.keys(filters.value).forEach(k => {
      if (filters.value[k]) params[k] = filters.value[k]
    })
    const r = await api.get('/audit/logs', { params })
    logs.value = r.data.logs || []
    total.value = r.data.count || 0
    const rs = await api.get('/audit/stats')
    stats.value = rs.data
  } finally {
    loading.value = false
  }
}

function badge(status) {
  return status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
}

function clearFilters() {
  filters.value = { actor: '', action: '', status: '' }
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4 gap-3 flex-wrap">
      <h2 class="text-xl font-semibold text-gray-900">📜 审计日志</h2>
      <button @click="load" :disabled="loading" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50">刷新</button>
    </div>

    <div v-if="stats" class="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
      <div class="bg-white border border-gray-200 rounded-xl p-4">
        <div class="text-xs text-gray-500">总日志</div>
        <div class="text-2xl font-semibold mt-1">{{ stats.total }}</div>
      </div>
      <div class="bg-white border border-gray-200 rounded-xl p-4">
        <div class="text-xs text-gray-500">今日</div>
        <div class="text-2xl font-semibold mt-1 text-blue-600">{{ stats.today }}</div>
      </div>
      <div class="bg-white border border-gray-200 rounded-xl p-4">
        <div class="text-xs text-gray-500">Top Action</div>
        <div class="text-sm font-semibold mt-1">{{ stats.by_action?.[0]?.action || '-' }} ({{ stats.by_action?.[0]?.count || 0 }})</div>
      </div>
    </div>

    <div class="bg-white border border-gray-200 rounded-xl p-3 mb-4 flex gap-3 items-end flex-wrap text-sm">
      <label class="flex-1 min-w-[150px]">
        <div class="text-xs text-gray-500 mb-1">用户</div>
        <input v-model="filters.actor" @change="load" placeholder="admin / ..." class="w-full px-2 py-1 border border-gray-200 rounded">
      </label>
      <label class="flex-1 min-w-[150px]">
        <div class="text-xs text-gray-500 mb-1">操作</div>
        <input v-model="filters.action" @change="load" placeholder="login / crawl / ..." class="w-full px-2 py-1 border border-gray-200 rounded">
      </label>
      <label class="flex-1 min-w-[120px]">
        <div class="text-xs text-gray-500 mb-1">状态</div>
        <select v-model="filters.status" @change="load" class="w-full px-2 py-1 border border-gray-200 rounded bg-white">
          <option value="">全部</option>
          <option value="success">success</option>
          <option value="failed">failed</option>
        </select>
      </label>
      <button @click="clearFilters"
              class="px-3 py-1 border border-gray-200 rounded text-gray-600 hover:bg-gray-50">清除</button>
    </div>

    <div class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-[75vh] overflow-y-auto shadow-sm">
      <div v-if="!logs.length && !loading" class="px-5 py-12 text-center text-gray-400 text-sm">暂无日志</div>
      <div v-for="l in logs" :key="l.id" class="px-5 py-3 hover:bg-gray-50">
        <div class="flex items-center gap-2 text-xs mb-1 flex-wrap">
          <span class="font-mono text-gray-500">{{ l.created_at }}</span>
          <span class="px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded">{{ l.actor }}</span>
          <span class="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded font-mono">{{ l.action }}</span>
          <span class="text-gray-500">{{ l.target_type }}:{{ l.target_id }}</span>
          <span :class="badge(l.status)" class="px-1.5 py-0.5 rounded-full font-medium">{{ l.status }}</span>
        </div>
        <div v-if="l.detail" class="text-xs text-gray-600 mt-0.5 line-clamp-2">{{ l.detail }}</div>
        <div v-if="l.ip" class="text-xs text-gray-400 font-mono mt-0.5">{{ l.ip }}</div>
      </div>
    </div>

    <div class="mt-3 text-xs text-gray-500 text-right">
      共 {{ total }} 条 <span v-if="loading">加载中…</span>
    </div>
  </div>
</template>
