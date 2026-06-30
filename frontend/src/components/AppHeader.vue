<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const health = ref(null)
const emit = defineEmits(['toggle-menu'])

async function loadHealth() {
  try {
    const r = await fetch('/health')
    health.value = await r.json()
  } catch { health.value = null }
}

onMounted(() => {
  loadHealth()
  setInterval(loadHealth, 30000)
})

async function doLogout() {
  if (!confirm('确定登出?')) return
  try {
    await api.post('/auth/logout')
  } catch (e) {}
  // 清 cookie:失效的 cookie 已由后端 delete,直接刷新让 require_admin 重定向
  location.reload()
}
</script>

<template>
  <header class="sticky top-0 z-20 bg-white/80 backdrop-blur-lg border-b border-gray-200/60">
    <div class="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <button @click="emit('toggle-menu')" class="md:hidden p-2 rounded-lg hover:bg-gray-100">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-bold">雷</div>
        <div>
          <h1 class="text-lg font-semibold text-gray-900">政策雷达</h1>
          <p class="text-xs text-gray-500">管理后台 · Vue 3 + Vite</p>
        </div>
      </div>
      <div class="flex items-center gap-3 text-xs">
        <span :class="health?.status === 'ok' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'" class="px-2 py-1 rounded-full">
          <span :class="health?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'" class="inline-block w-1.5 h-1.5 rounded-full mr-1"></span>
          服务 {{ health?.status || '离线' }}
        </span>
        <span class="text-gray-500 hidden sm:inline">v0.2.0</span>
        <button @click="doLogout"
                class="px-2.5 py-1 rounded border border-gray-300 hover:bg-red-50 hover:border-red-200 hover:text-red-700 text-gray-600">
          登出
        </button>
      </div>
    </div>
  </header>
</template>
