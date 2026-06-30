<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const subs = ref([])
const toast = ref({ show: false, msg: '' })
const editModal = ref({ show: false, sub: null })
const testModal = ref({ show: false })
const sourceOpts = ref({ regions: [], departments: [], categories: [], total_sources: 0 })

function showToast(msg, ms = 2500) {
  toast.value = { show: true, msg }
  setTimeout(() => toast.value.show = false, ms)
}

async function load() {
  const r = await api.get('/subscriptions')
  subs.value = r.data.subscriptions || []
  // 顺手加载 source 选项
  try {
    const r2 = await api.get('/subscriptions/sources/options')
    sourceOpts.value = r2.data
  } catch (e) {
    console.warn('load source options failed', e)
  }
}

async function toggle(s, enable) {
  const ep = enable ? `${s.subscription_id}/resume` : `${s.subscription_id}/pause`
  try {
    await api.post(`/subscriptions/${ep}`)
    showToast(enable ? '✅ 已启用' : '✅ 已暂停')
    await load()
  } catch (e) { showToast('失败: ' + e.message) }
}

async function del(s) {
  if (!confirm(`删除「${s.company_name}」订阅?`)) return
  try {
    await api.delete(`/subscriptions/${s.subscription_id}`)
    showToast('✅ 已删除')
    await load()
  } catch (e) { showToast('删除失败: ' + e.message) }
}

async function pushNow(s) {
  showToast('📨 正在推送...')
  try {
    const r = await api.post(`/subscriptions/${s.subscription_id}/push`)
    showToast(`✅ 推送成功 → ${r.data.target}`)
  } catch (e) {
    showToast('❌ 推送失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function openEdit(s) {
  // 保证三个数组都存在
  const copy = JSON.parse(JSON.stringify(s))
  copy.regions = copy.regions || []
  copy.dept_codes = copy.dept_codes || []
  copy.city_codes = copy.city_codes || []
  copy.types = copy.types || []
  editModal.value = { show: true, sub: copy }
}

function toggleArr(obj, key, val) {
  const arr = obj[key] || (obj[key] = [])
  const i = arr.indexOf(val)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(val)
}
async function saveEdit() {
  const s = editModal.value.sub
  try {
    const r = await api.patch(`/subscriptions/${s.subscription_id}`, {
      push_schedule: s.push_schedule,
      push_time: s.push_time,
      webhook_url: s.webhook_url || null,
      types: s.types,
      regions: s.regions,
      dept_codes: s.dept_codes,
      city_codes: s.city_codes,
      enabled: s.enabled,
      push_channel: s.push_channel,
    })
    editModal.value.show = false
    const autoN = r.data?.auto_enabled_sources || 0
    showToast(autoN > 0 ? `✅ 已保存,自动启用 ${autoN} 个源` : '✅ 已保存')
    await load()
  } catch (e) { showToast('保存失败: ' + (e.response?.data?.detail || e.message)) }
}

function openTest() { testModal.value = { show: true, channel: 'mock', url: '', ok: null, error: null } }
async function runTest() {
  const t = testModal.value
  const cfg = {}
  if (t.channel === 'webhook' && t.url) cfg.webhook_url = t.url
  try {
    const r = await api.post('/subscriptions/test-push', cfg, { params: { channel: t.channel } })
    t.ok = r.data.ok
    t.error = r.data.error
    showToast(r.data.ok ? '✅ 渠道 OK' : '❌ 渠道失败')
  } catch (e) {
    t.ok = false
    t.error = e.response?.data?.detail || e.message
    showToast('测试失败')
  }
}

async function createCompany() {
  const name = prompt('公司名:')
  if (!name) return
  const sub = confirm('同时创建订阅吗?(ok=是,cancel=否)')
  try {
    await api.post('/companies', {
      name,
      push_schedule: sub ? 'daily' : undefined,
    })
    showToast('✅ 公司已创建(到订阅页关联)')
    load()
  } catch (e) { showToast('失败: ' + e.message) }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4 gap-3 flex-wrap">
      <h2 class="text-xl font-semibold text-gray-900 whitespace-nowrap">📋 订阅管理</h2>
      <div class="flex gap-2 flex-wrap">
        <button @click="load" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">刷新</button>
        <button @click="openTest" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">🧪 测渠道</button>
        <button @click="createCompany" class="text-sm px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap">+ 新建公司</button>
      </div>
    </div>

    <div v-if="!subs.length" class="bg-white border border-gray-200 rounded-xl p-8 text-center text-gray-400 text-sm">
      暂无订阅(通过 + 新建公司 创建)
    </div>
    <div v-else class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-[75vh] overflow-y-auto shadow-sm">
      <div v-for="s in subs" :key="s.subscription_id" class="px-5 py-4 hover:bg-gray-50">
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1 flex-wrap">
              <span class="font-medium text-gray-900">{{ s.company_name }}</span>
              <span :class="s.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'" class="text-xs px-2 py-0.5 rounded-full font-medium">
                {{ s.enabled ? '启用' : '暂停' }}
              </span>
              <span class="text-xs text-gray-400">sub #{{ s.subscription_id }}</span>
              <span v-if="s.push_channel" class="text-xs px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded font-mono">{{ s.push_channel }}</span>
            </div>
            <div class="text-xs text-gray-500">
              关注：{{ (s.types || []).join('、') || '-' }} · 地区：{{ (s.regions || []).join('、') || '-' }} · 委办：{{ (s.dept_codes || []).join('、') || '-' }} · 地市：{{ (s.city_codes || []).join('、') || '-' }} · 频率：{{ s.push_schedule }}{{ s.push_time ? ' ' + s.push_time : '' }}
            </div>
            <div class="text-xs text-gray-400 mt-1 truncate">webhook: {{ s.webhook_url || '(无)' }}</div>
            <div v-if="s.last_push_at" class="text-xs text-gray-400 mt-0.5">最近推送: {{ s.last_push_at }}</div>
          </div>
          <div class="flex flex-col gap-1 shrink-0">
            <button v-if="s.enabled" @click="toggle(s, false)" class="text-xs px-2 py-1 rounded border border-gray-200 text-gray-600 hover:bg-gray-50">暂停</button>
            <button v-else @click="toggle(s, true)" class="text-xs px-2 py-1 rounded bg-green-500 text-white hover:bg-green-600">启用</button>
            <button @click="pushNow(s)" class="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100">📨 立即推</button>
            <button @click="openEdit(s)" class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50">编辑</button>
            <button @click="del(s)" class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑 modal -->
    <div v-if="editModal.show" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="editModal.show=false">
      <div class="bg-white rounded-xl max-w-lg w-full p-5 shadow-2xl">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-base font-semibold">编辑订阅 #{{ editModal.sub.subscription_id }}</h3>
          <button @click="editModal.show=false" class="text-gray-400 text-xl">×</button>
        </div>
        <div v-if="editModal.sub" class="space-y-3 text-sm">
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">频率</div>
            <select v-model="editModal.sub.push_schedule" class="w-full px-2 py-1.5 border border-gray-200 rounded bg-white">
              <option value="realtime">realtime</option>
              <option value="daily">daily</option>
              <option value="weekly">weekly</option>
              <option value="manual">manual</option>
            </select>
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">推送时间(若 daily)</div>
            <input v-model="editModal.sub.push_time" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">Webhook URL(留空则不推送)</div>
            <input v-model="editModal.sub.webhook_url" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">类型(逗号分隔)</div>
            <input :value="(editModal.sub.types || []).join(',')"
                   @change="e => editModal.sub.types = e.target.value.split(',').map(s=>s.trim()).filter(Boolean)"
                   class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">省级地区(逗号分隔,自动启用对应源的爬取)</div>
            <input :value="(editModal.sub.regions || []).join(',')"
                   @change="e => editModal.sub.regions = e.target.value.split(',').map(s=>s.trim()).filter(Boolean)"
                   placeholder="北京,广东,浙江,..."
                   class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">委办部门(逗号分隔,自动启用对应委办源)</div>
            <input :value="(editModal.sub.dept_codes || []).join(',')"
                   @change="e => editModal.sub.dept_codes = e.target.value.split(',').map(s=>s.trim()).filter(Boolean)"
                   placeholder="发改委,工信部,财政部,..."
                   class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">地市(逗号分隔,自动启用对应市级源)</div>
            <input :value="(editModal.sub.city_codes || []).join(',')"
                   @change="e => editModal.sub.city_codes = e.target.value.split(',').map(s=>s.trim()).filter(Boolean)"
                   placeholder="深圳,杭州,苏州,..."
                   class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <div v-if="sourceOpts.regions.length || sourceOpts.departments.length" class="bg-blue-50 border border-blue-100 rounded p-2 text-xs text-blue-800">
            <div class="font-semibold mb-1">📌 可选({{ sourceOpts.total_sources }} 源)</div>
            <details class="mb-1">
              <summary class="cursor-pointer">省级({{ sourceOpts.regions.length }})</summary>
              <div class="flex flex-wrap gap-1 mt-1">
                <button v-for="v in sourceOpts.regions" :key="'r-'+v" type="button"
                        @click="toggleArr(editModal.sub, 'regions', v)"
                        :class="(editModal.sub.regions||[]).includes(v) ? 'bg-blue-600 text-white' : 'bg-white border border-blue-200 text-blue-700'"
                        class="text-xs px-1.5 py-0.5 rounded">{{ v }}</button>
              </div>
            </details>
            <details>
              <summary class="cursor-pointer">部委({{ sourceOpts.departments.length }})</summary>
              <div class="flex flex-wrap gap-1 mt-1">
                <button v-for="v in sourceOpts.departments" :key="'d-'+v" type="button"
                        @click="toggleArr(editModal.sub, 'dept_codes', v)"
                        :class="(editModal.sub.dept_codes||[]).includes(v) ? 'bg-blue-600 text-white' : 'bg-white border border-blue-200 text-blue-700'"
                        class="text-xs px-1.5 py-0.5 rounded">{{ v }}</button>
              </div>
            </details>
          </div>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">推送渠道</div>
            <select v-model="editModal.sub.push_channel" class="w-full px-2 py-1.5 border border-gray-200 rounded bg-white">
              <option value="mock">mock</option>
              <option value="wechat">wechat</option>
              <option value="feishu">feishu</option>
              <option value="wecom">wecom</option>
              <option value="email">email</option>
              <option value="webhook">webhook</option>
            </select>
          </label>
          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="editModal.sub.enabled" class="rounded text-blue-600">
            <span>启用此订阅</span>
          </label>
          <div class="flex justify-end gap-2 pt-2">
            <button @click="editModal.show=false" class="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">取消</button>
            <button @click="saveEdit" class="px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700">保存</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 测试渠道 modal -->
    <div v-if="testModal.show" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="testModal.show=false">
      <div class="bg-white rounded-xl max-w-md w-full p-5 shadow-2xl">
        <h3 class="text-base font-semibold mb-3">🧪 测试推送渠道</h3>
        <label class="block mb-3 text-sm">
          <div class="text-xs text-gray-500 mb-1">渠道</div>
          <select v-model="testModal.channel" class="w-full px-2 py-1.5 border border-gray-200 rounded bg-white">
            <option value="mock">mock</option>
            <option value="wechat">wechat</option>
            <option value="feishu">feishu</option>
            <option value="wecom">wecom</option>
            <option value="email">email</option>
            <option value="webhook">webhook</option>
          </select>
        </label>
        <label v-if="testModal.channel === 'webhook'" class="block mb-3 text-sm">
          <div class="text-xs text-gray-500 mb-1">webhook URL</div>
          <input v-model="testModal.url" placeholder="https://..." class="w-full px-2 py-1.5 border border-gray-200 rounded">
        </label>
        <div v-if="testModal.ok !== null" :class="testModal.ok ? 'text-green-600' : 'text-red-600'" class="text-sm mb-3">
          {{ testModal.ok ? '✅ 渠道 OK' : '❌ ' + testModal.error }}
        </div>
        <div class="flex justify-end gap-2">
          <button @click="testModal.show=false" class="px-3 py-1.5 rounded-lg border border-gray-200">关闭</button>
          <button @click="runTest" class="px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700">测试</button>
        </div>
      </div>
    </div>

    <div v-if="toast.show" class="fixed bottom-6 right-6 bg-gray-900 text-white px-5 py-3 rounded-xl shadow-lg z-50 text-sm">{{ toast.msg }}</div>
  </div>
</template>
