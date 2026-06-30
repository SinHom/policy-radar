<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '../api.js'

const logs = ref([])
const loading = ref(false)
const filters = ref({ status: '', target: '' })

async function load() {
  loading.value = true
  try {
    const params = { limit: 100 }
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.target) params.target = filters.value.target
    const r = await api.get('/push-logs', { params })
    logs.value = r.data
  } finally {
    loading.value = false
  }
}

function badge(status) {
  return status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
}

const filtered = computed(() => logs.value)

function clearFilter() { filters.value = { status: '', target: '' }; load() }

async function viewPolicyDetail(polId) {
  if (!polId) return
  try {
    const r = await api.get(`/policies/${polId}/content`)
    if (r.data?.markdown) {
      alert('政策内容预览:\n\n' + r.data.markdown.slice(0, 800) + (r.data.markdown.length > 800 ? '\n...(更多请到 Policies 页面查看)' : ''))
    }
  } catch (e) { alert('获取失败: ' + e.message) }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4 gap-3 flex-wrap">
      <h2 class="text-xl font-semibold text-gray-900">📤 推送历史</h2>
      <input v-model="filters.target" @keyup.enter="load" placeholder="按 target 过滤..."
             class="text-sm px-3 py-1.5 border border-gray-200 rounded-lg flex-1 max-w-xs">
      <select v-model="filters.status" @change="load" class="text-sm px-3 py-1.5 border border-gray-200 rounded-lg bg-white">
        <option value="">全部状态</option>
        <option value="success">成功</option>
        <option value="failed">失败</option>
      </select>
      <button @click="load" :disabled="loading" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50">刷新</button>
      <button @click="clearFilter" v-if="filters.status || filters.target"
              class="text-sm px-2 py-1 rounded-lg text-brand-600 hover:underline">清除筛选</button>
    </div>

    <div class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-[78vh] overflow-y-auto shadow-sm">
      <div v-if="!logs.length && !loading" class="px-5 py-12 text-center text-gray-400 text-sm">暂无推送记录</div>
      <div v-for="log in filtered" :key="log.id" class="px-5 py-3 hover:bg-gray-50">
        <div class="flex items-center gap-2 text-xs mb-1 flex-wrap">
          <span class="font-mono text-gray-500">{{ log.created_at }}</span>
          <span :class="badge(log.status)" class="px-2 py-0.5 rounded-full font-medium">{{ log.status }}</span>
          <button v-if="log.policy_id" @click="viewPolicyDetail(log.policy_id)"
                  class="text-blue-600 hover:underline">policy #{{ log.policy_id }}</button>
          <span v-else class="text-gray-400">policy -</span>
          <button v-if="log.target" @click="filters.target = log.target; load()"
                  class="text-gray-400 hover:text-brand-600 font-mono truncate max-w-[200px]" :title="log.target">
            {{ log.target }}
          </button>
        </div>
        <pre class="text-xs text-gray-600 whitespace-pre-wrap font-sans mt-1 max-h-32 overflow-y-auto bg-gray-50 px-2 py-1.5 rounded">{{ log.content }}</pre>
        <div v-if="log.error_msg" class="text-xs text-red-600 mt-1 font-mono">{{ log.error_msg }}</div>
      </div>
    </div>
  </div>
</template>
