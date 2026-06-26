<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const subs = ref([])
const toast = ref({ show: false, msg: '' })

function showToast(msg, ms = 2500) {
  toast.value = { show: true, msg }
  setTimeout(() => toast.value.show = false, ms)
}

async function load() {
  const r = await api.get('/subscriptions')
  subs.value = r.data.subscriptions || []
}

async function toggle(s, enable) {
  const endpoint = enable ? 'resume_subscription' : 'pause_subscription'
  await api.post(`/${endpoint}`, null, { params: { company_id: s.company_id } })
  showToast(enable ? '✅ 已启用' : '✅ 已暂停')
  await load()
}

async function del(s) {
  if (!confirm(`删除「${s.company_name}」？`)) return
  await api.post('/delete_subscription', null, { params: { company_id: s.company_id } })
  showToast('✅ 已删除')
  await load()
}

function badgeColor(enabled) {
  return enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
}

onMounted(load)
</script>

<template>
  <div class="flex items-center justify-between mb-4">
    <h2 class="text-xl font-semibold text-gray-900">📋 订阅管理</h2>
    <button @click="load" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">刷新</button>
  </div>
  <div v-if="subs.length === 0" class="bg-white border border-gray-200 rounded-xl p-8 text-center text-gray-400 text-sm">
    暂无订阅（通过 MCP 的 start_setup 注册）
  </div>
  <div v-else class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
    <div v-for="s in subs" :key="s.subscription_id" class="px-5 py-4 hover:bg-gray-50">
      <div class="flex items-start justify-between gap-4">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-medium text-gray-900">{{ s.company_name }}</span>
            <span :class="badgeColor(s.enabled)" class="text-xs px-2 py-0.5 rounded-full font-medium">
              {{ s.enabled ? '启用' : '暂停' }}
            </span>
            <span class="text-xs text-gray-400">sub #{{ s.subscription_id }}</span>
          </div>
          <div class="text-xs text-gray-500">
            关注：{{ (s.types || []).join('、') || '-' }} · 地区：{{ (s.regions || []).join('、') || '-' }} · 频率：{{ s.push_schedule }}
          </div>
          <div class="text-xs text-gray-400 mt-1 truncate">webhook: {{ s.webhook_url || '(无)' }}</div>
        </div>
        <div class="flex flex-col gap-1 shrink-0">
          <button v-if="s.enabled" @click="toggle(s, false)" class="text-xs px-2 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50">暂停</button>
          <button v-else @click="toggle(s, true)" class="text-xs px-2 py-1 rounded bg-green-500 text-white hover:bg-green-600">启用</button>
          <button @click="del(s)" class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50">删除</button>
        </div>
      </div>
    </div>
  </div>
  <div v-if="toast.show" class="fixed bottom-6 right-6 bg-gray-900 text-white px-5 py-3 rounded-xl shadow-lg z-50">{{ toast.msg }}</div>
</template>
