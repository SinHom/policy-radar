<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '../api.js'

const cfg = ref(null)
const usage = ref(null)
const editKey = ref('')
const editModel = ref('')
const editBaseUrl = ref('')
const saving = ref(false)
const testing = false
const testResult = ref(null)
const toast = ref({ show: false, msg: '' })

function showToast(msg, ms = 2500) {
  toast.value = { show: true, msg }
  setTimeout(() => toast.value.show = false, ms)
}

async function load() {
  const [r1, r2] = await Promise.all([
    api.get('/config/llm'),
    api.get('/llm/usage', { params: { days: 7 } }),
  ])
  cfg.value = r1.data
  usage.value = r2.data
  editModel.value = r1.data.model
  editBaseUrl.value = r1.data.base_url
  editKey.value = ''
}

async function save() {
  saving.value = true
  try {
    const body = { model: editModel.value, base_url: editBaseUrl.value }
    if (editKey.value) body.api_key = editKey.value
    const r = await api.put('/config/llm', body)
    showToast('✅ 已保存' + (r.data.source ? '(' + r.data.source + ')' : ''))
    await load()
  } catch (e) {
    showToast('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function testConn() {
  testResult.value = null
  try {
    const r = await api.post('/config/llm/test')
    testResult.value = r.data
    showToast(r.data.ok ? '✅ 测试通过' : '❌ 测试失败')
  } catch (e) {
    testResult.value = { ok: false, error: e.message }
  }
}

onMounted(load)
</script>

<template>
  <div v-if="cfg">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xl font-semibold text-gray-900">🤖 LLM 配置 & 用量</h2>
      <button @click="load" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">刷新</button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <div class="bg-white border border-gray-200 rounded-xl p-4">
        <div class="text-xs text-gray-500">总 token({{ usage?.period_days || 7 }} 天)</div>
        <div class="text-2xl font-semibold mt-1 text-gray-900">{{ usage?.total?.total_tokens?.toLocaleString() || 0 }}</div>
        <div class="text-xs text-gray-400 mt-1">{{ usage?.total?.calls || 0 }} 次调用</div>
      </div>
      <div class="bg-white border border-gray-200 rounded-xl p-4">
        <div class="text-xs text-gray-500">输入 token</div>
        <div class="text-2xl font-semibold mt-1 text-blue-600">{{ usage?.total?.input_tokens?.toLocaleString() || 0 }}</div>
      </div>
      <div class="bg-white border border-gray-200 rounded-xl p-4">
        <div class="text-xs text-gray-500">输出 token</div>
        <div class="text-2xl font-semibold mt-1 text-orange-600">{{ usage?.total?.output_tokens?.toLocaleString() || 0 }}</div>
      </div>
    </div>

    <div class="bg-white border border-gray-200 rounded-xl p-5 mb-6">
      <h3 class="text-sm font-semibold text-gray-900 mb-3">当前配置<span class="text-xs text-gray-400 ml-2">(来源: {{ cfg.source === 'db' ? '数据库' : '环境变量' }})</span></h3>
      <div class="grid grid-cols-3 gap-3 text-sm mb-4">
        <div><div class="text-xs text-gray-500">Model</div><div class="font-mono">{{ cfg.model }}</div></div>
        <div><div class="text-xs text-gray-500">Base URL</div><div class="font-mono text-xs">{{ cfg.base_url }}</div></div>
        <div><div class="text-xs text-gray-500">API Key</div><div class="font-mono text-xs">{{ cfg.api_key }}</div></div>
      </div>

      <h3 class="text-sm font-semibold text-gray-900 mb-3 mt-4">编辑</h3>
      <div class="space-y-3">
        <label class="block">
          <div class="text-xs text-gray-500 mb-1">Model</div>
          <input v-model="editModel" class="w-full text-sm px-3 py-1.5 border border-gray-200 rounded-lg">
        </label>
        <label class="block">
          <div class="text-xs text-gray-500 mb-1">Base URL</div>
          <input v-model="editBaseUrl" class="w-full text-sm px-3 py-1.5 border border-gray-200 rounded-lg">
        </label>
        <label class="block">
          <div class="text-xs text-gray-500 mb-1">API Key(留空则保留原 key)</div>
          <input v-model="editKey" type="password" placeholder="输入新 key 才更新" class="w-full text-sm px-3 py-1.5 border border-gray-200 rounded-lg">
        </label>
        <div class="flex gap-2">
          <button @click="save" :disabled="saving"
                  class="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 disabled:opacity-50">保存</button>
          <button @click="testConn"
                  class="px-3 py-1.5 rounded-lg border border-gray-300 text-sm hover:bg-gray-50">测连通性</button>
        </div>
      </div>
      <div v-if="testResult" class="mt-3 text-xs" :class="testResult.ok ? 'text-green-600' : 'text-red-600'">
        {{ testResult.ok ? '✅ ' + (testResult.model || 'OK') : '❌ ' + (testResult.error || 'failed') }}
      </div>
    </div>

    <div v-if="usage?.daily?.length" class="bg-white border border-gray-200 rounded-xl p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-3">近 {{ usage.period_days }} 天用量</h3>
      <table class="w-full text-sm">
        <thead class="text-xs text-gray-500"><tr><th class="text-left">日期</th><th class="text-right">输入</th><th class="text-right">输出</th><th class="text-right">合计</th><th class="text-right">调用</th></tr></thead>
        <tbody>
          <tr v-for="d in usage.daily" :key="d.day" class="border-t border-gray-100">
            <td class="py-1.5">{{ d.day }}</td>
            <td class="text-right">{{ d.input_tokens.toLocaleString() }}</td>
            <td class="text-right">{{ d.output_tokens.toLocaleString() }}</td>
            <td class="text-right font-semibold">{{ d.total_tokens.toLocaleString() }}</td>
            <td class="text-right">{{ d.calls }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="toast.show" class="fixed bottom-6 right-6 bg-gray-900 text-white px-5 py-3 rounded-xl shadow-lg z-50 text-sm">{{ toast.msg }}</div>
  </div>
</template>
