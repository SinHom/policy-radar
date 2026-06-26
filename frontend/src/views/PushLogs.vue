<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const logs = ref([])

async function load() {
  const r = await api.get('/push-logs', { params: { limit: 50 } })
  logs.value = r.data
}

onMounted(load)
</script>

<template>
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-xl font-semibold text-gray-900">📤 推送历史</h2>
    <button @click="load" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">刷新</button>
  </div>
  <div class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-[70vh] overflow-y-auto">
    <div v-for="log in logs" :key="log.id" class="px-5 py-3">
      <div class="flex items-center gap-2 text-xs mb-1">
        <span class="font-mono text-gray-500">{{ log.created_at }}</span>
        <span :class="log.status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'" class="px-2 py-0.5 rounded-full font-medium">{{ log.status }}</span>
        <span class="text-gray-400">policy #{{ log.policy_id }}</span>
      </div>
      <pre class="text-xs text-gray-600 whitespace-pre-wrap font-sans">{{ log.content }}</pre>
    </div>
  </div>
</template>
