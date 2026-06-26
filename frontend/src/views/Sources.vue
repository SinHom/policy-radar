<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const sources = ref([])

async function load() {
  const r = await api.get('/sources')
  sources.value = r.data
}

onMounted(load)
</script>

<template>
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-xl font-semibold text-gray-900">🕷️ 政策源</h2>
    <button @click="load" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">刷新</button>
  </div>
  <div class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
    <div v-for="s in sources" :key="s.id" class="px-5 py-3 flex items-center justify-between">
      <div>
        <div class="font-medium text-gray-900 text-sm">{{ s.name }}</div>
        <div class="text-xs text-gray-500">{{ s.category }} · {{ s.source_id }}</div>
      </div>
      <span :class="s.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'" class="text-xs px-2 py-0.5 rounded-full font-medium">
        {{ s.enabled ? '启用' : '停用' }}
      </span>
    </div>
  </div>
</template>
