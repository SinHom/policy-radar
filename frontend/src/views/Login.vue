<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api.js'

const router = useRouter()
const route = useRoute()
const username = ref('admin')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    await api.post('/auth/login', {
      username: username.value,
      password: password.value,
    })
    // 登录成功 → 跳回 redirect 或 dashboard
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '登录失败'
  } finally {
    loading.value = false
  }
}

// 已登录直接跳走
onMounted(async () => {
  try {
    await api.get('/auth/me')
    router.replace('/')
  } catch {}
})
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-brand-50 via-white to-accent-50 flex items-center justify-center p-6">
    <div class="bg-white border border-gray-200 rounded-2xl shadow-xl max-w-md w-full p-8">
      <div class="flex items-center gap-3 mb-6">
        <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-bold text-xl">雷</div>
        <div>
          <h1 class="text-xl font-semibold text-gray-900">政策雷达</h1>
          <p class="text-xs text-gray-500">管理后台登录</p>
        </div>
      </div>

      <form @submit.prevent="submit" class="space-y-4">
        <label class="block">
          <div class="text-xs text-gray-600 mb-1">用户名</div>
          <input v-model="username" type="text" autocomplete="username"
                 class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-200"
                 placeholder="admin" />
        </label>
        <label class="block">
          <div class="text-xs text-gray-600 mb-1">密码</div>
          <input v-model="password" type="password" autocomplete="current-password"
                 class="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-200"
                 placeholder="••••••••" />
        </label>
        <div v-if="error" class="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          {{ error }}
        </div>
        <button type="submit" :disabled="loading"
                class="w-full bg-brand-600 text-white font-medium py-2.5 rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {{ loading ? '登录中…' : '登 录' }}
        </button>
      </form>

      <p class="text-xs text-gray-400 text-center mt-6">
        默认密码见 <code class="bg-gray-100 px-1 rounded">python/app/config.py</code> → admin_password
      </p>
    </div>
  </div>
</template>