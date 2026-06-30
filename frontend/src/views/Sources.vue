<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api.js'

const sources = ref([])
const loading = ref(false)
const selected = ref(new Set())
const filters = ref({
  q: '',
  category: [],
  region: [],
  department: [],
  enabled: 'all',
})
const editModal = ref({ show: false, source: null })
const newModal = ref({ show: false, form: { source_id: '', name: '', url: '', category: '国家级', region: '全国', department: '', frequency: 'daily' } })
const toast = ref({ show: false, msg: '' })

function showToast(msg, ms = 2500) {
  toast.value = { show: true, msg }
  setTimeout(() => toast.value.show = false, ms)
}

async function load() {
  loading.value = true
  try {
    const r = await api.get('/sources')
    sources.value = r.data
  } finally { loading.value = false }
}

const facets = computed(() => {
  const cats = new Set(), regs = new Set(), depts = new Set()
  sources.value.forEach(s => {
    if (s.category) cats.add(s.category)
    if (s.region) regs.add(s.region)
    if (s.department) depts.add(s.department)
  })
  return {
    cats: [...cats].sort(),
    regs: [...regs].sort(),
    depts: [...depts].sort(),
  }
})

const statusCount = computed(() => {
  let ok = 0, failed = 0
  sources.value.forEach(s => {
    if (s.last_status === 'ok') ok++
    else if (s.last_status === 'failed') failed++
  })
  return { ok, failed }
})

const filtered = computed(() => {
  const q = filters.value.q.trim().toLowerCase()
  return sources.value.filter(s => {
    if (q && !((s.name || '').toLowerCase().includes(q) || (s.source_id || '').toLowerCase().includes(q))) return false
    if (filters.value.category.length && !filters.value.category.includes(s.category)) return false
    if (filters.value.region.length && !filters.value.region.includes(s.region)) return false
    if (filters.value.department.length && !filters.value.department.includes(s.department)) return false
    if (filters.value.enabled !== 'all' && s.enabled !== (filters.value.enabled === 'yes')) return false
    return true
  })
})

function toggle(id) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  selected.value = s
}
function toggleAll() {
  if (selected.value.size === filtered.value.length && filtered.value.length > 0) {
    selected.value = new Set()
  } else {
    selected.value = new Set(filtered.value.map(s => s.id))
  }
}
async function batchSet(enabled) {
  const ids = [...selected.value]
  if (!ids.length) return
  try {
    await api.post('/sources/batch-enabled', { enabled, only_id: ids })
    selected.value = new Set()
    showToast(enabled ? `✅ 启用 ${ids.length} 个` : `✅ 停用 ${ids.length} 个`)
    await load()
  } catch (e) { showToast('失败: ' + e.message) }
}
async function batchCrawl() {
  const ids = [...selected.value]
  if (!ids.length) return
  if (!confirm(`爬取 ${ids.length} 个源?`)) return
  await Promise.allSettled(ids.map(id => api.post(`/crawl/${id}`)))
  selected.value = new Set()
  showToast(`已触发 ${ids.length} 个源爬取`)
}
function clearFilters() {
  filters.value.q = ''
  filters.value.category = []
  filters.value.region = []
  filters.value.department = []
  filters.value.enabled = 'all'
}
function toggleArr(group, value) {
  const arr = filters.value[group]
  const i = arr.indexOf(value)
  if (i >= 0) arr.splice(i, 1); else arr.push(value)
}

function openEdit(s) {
  editModal.value = { show: true, source: { ...s, tags: (s.tags || []).join(',') } }
}
async function saveEdit() {
  const s = editModal.value.source
  try {
    const body = {
      name: s.name,
      url: s.url || null,
      category: s.category,
      region: s.region,
      department: s.department,
      tags: s.tags ? s.tags.split(',').map(x=>x.trim()).filter(Boolean) : [],
      frequency: s.frequency,
      enabled: s.enabled,
    }
    await api.patch(`/sources/${s.id}`, body)
    editModal.value.show = false
    showToast('✅ 已保存')
    await load()
  } catch (e) { showToast('保存失败: ' + (e.response?.data?.detail || e.message)) }
}
async function delSource(s) {
  if (!confirm(`删除源「${s.name}」?关联的政策也会级联删除!`)) return
  try {
    await api.delete(`/sources/${s.id}`)
    showToast('✅ 已删除')
    await load()
  } catch (e) { showToast('删除失败: ' + (e.response?.data?.detail || e.message)) }
}

async function createSource() {
  const f = newModal.value.form
  try {
    await api.post('/sources', {
      source_id: f.source_id, name: f.name, url: f.url || null,
      category: f.category, region: f.region, department: f.department,
      spider_config: {}, frequency: f.frequency, enabled: true,
    })
    newModal.value.show = false
    showToast('✅ 已新增')
    await load()
  } catch (e) { showToast('新增失败: ' + (e.response?.data?.detail || e.message)) }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4 gap-3 flex-wrap">
      <h2 class="text-xl font-semibold text-gray-900 whitespace-nowrap">🕷️ 政策源</h2>
      <input v-model="filters.q" placeholder="搜索名称 / source_id..."
             class="text-sm px-3 py-1.5 border border-gray-200 rounded-lg flex-1 min-w-[180px] max-w-sm">
      <button @click="load" :disabled="loading" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 disabled:opacity-50">刷新</button>
      <button @click="newModal.show = true" class="text-sm px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap">+ 新增</button>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
      <div class="bg-white border border-gray-200 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-semibold text-gray-700">🏷️ 类目</h4>
          <span class="text-xs text-gray-400">{{ filters.category.length || '全' }}</span>
        </div>
        <div class="max-h-40 overflow-auto space-y-0.5">
          <label v-for="c in facets.cats" :key="c"
                 class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="checkbox" :checked="filters.category.includes(c)" @change="toggleArr('category', c)" class="rounded text-brand-600">
            <span class="flex-1 truncate text-gray-700">{{ c }}</span>
          </label>
          <div v-if="!facets.cats.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-semibold text-gray-700">📍 区域</h4>
          <span class="text-xs text-gray-400">{{ filters.region.length || '全' }}</span>
        </div>
        <div class="max-h-40 overflow-auto space-y-0.5">
          <label v-for="r in facets.regs" :key="r"
                 class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="checkbox" :checked="filters.region.includes(r)" @change="toggleArr('region', r)" class="rounded text-brand-600">
            <span class="flex-1 truncate text-gray-700">{{ r }}</span>
          </label>
          <div v-if="!facets.regs.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-semibold text-gray-700">🏛️ 部门</h4>
          <span class="text-xs text-gray-400">{{ filters.department.length || '全' }}</span>
        </div>
        <div class="max-h-40 overflow-auto space-y-0.5">
          <label v-for="d in facets.depts" :key="d"
                 class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="checkbox" :checked="filters.department.includes(d)" @change="toggleArr('department', d)" class="rounded text-brand-600">
            <span class="flex-1 truncate text-gray-700">{{ d }}</span>
          </label>
          <div v-if="!facets.depts.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-xl p-3">
        <h4 class="text-sm font-semibold text-gray-700 mb-2">⚡ 状态</h4>
        <div class="space-y-0.5">
          <label class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="radio" :checked="filters.enabled === 'all'" @change="filters.enabled = 'all'" name="state">
            <span>全部</span>
          </label>
          <label class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="radio" :checked="filters.enabled === 'yes'" @change="filters.enabled = 'yes'" name="state">
            <span class="text-green-700">仅启用</span>
          </label>
          <label class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="radio" :checked="filters.enabled === 'no'" @change="filters.enabled = 'no'" name="state">
            <span class="text-gray-500">仅停用</span>
          </label>
        </div>
      </div>

      <div class="bg-white border border-gray-200 rounded-xl p-3 flex flex-col items-center justify-center text-center">
        <div class="text-xs text-gray-500 mb-2">已筛选</div>
        <div class="text-2xl font-bold text-brand-600 mb-2">
          {{ filtered.length }}<span class="text-base text-gray-400"> / {{ sources.length }}</span>
        </div>
        <button @click="clearFilters"
                class="text-xs px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50"
                :disabled="!filters.q && !filters.category.length && !filters.region.length && !filters.department.length && filters.enabled==='all'">清除筛选</button>
      </div>
    </div>

    <div v-if="selected.size" class="bg-brand-50 border-2 border-brand-300 rounded-xl p-3 mb-3 sticky top-16 z-10 flex items-center gap-3 flex-wrap shadow-sm">
      <span class="text-sm text-brand-700 font-medium">已选 {{ selected.size }} 个源</span>
      <button @click="toggleAll" class="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-white">取消选择</button>
      <button @click="batchSet(true)" class="text-xs px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700">批量启用</button>
      <button @click="batchSet(false)" class="text-xs px-3 py-1.5 rounded-lg bg-gray-600 text-white hover:bg-gray-700">批量停用</button>
      <button @click="batchCrawl" class="text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700">批量爬取</button>
    </div>

    <div class="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
      <div v-if="statusCount.failed > 0" class="px-4 py-2 bg-red-50 border-b border-red-100 text-xs text-red-700 flex items-center justify-between">
        <span>⚠️ 探测失败 {{ statusCount.failed }} / {{ sources.length }} 个源(RSSHub 上游 503)— 这些源暂时拉不到内容,不影响其他源</span>
        <span class="text-red-500">建议: 定期重跑 <code class="bg-white px-1 rounded">seed_rsshub_v2.py --probe</code></span>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
          <tr>
            <th class="px-3 py-2.5 w-10">
              <input type="checkbox" :checked="selected.size === filtered.length && filtered.length > 0" @change="toggleAll" class="rounded">
            </th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">名称</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">类目</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">区域</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">部门</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">Source ID</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">状态</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">探测</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-for="s in filtered" :key="s.id" :class="['hover:bg-gray-50', selected.has(s.id) ? 'bg-brand-50/50' : '']">
            <td class="px-3 py-2.5">
              <input type="checkbox" :checked="selected.has(s.id)" @change="toggle(s.id)" class="rounded">
            </td>
            <td class="px-3 py-2.5 font-medium text-gray-900">
              <router-link :to="{ name: 'policies', query: { source: s.source_id } }" class="hover:text-brand-600">{{ s.name }}</router-link>
            </td>
            <td class="px-3 py-2.5 text-gray-600">{{ s.category }}</td>
            <td class="px-3 py-2.5 text-gray-600">{{ s.region }}</td>
            <td class="px-3 py-2.5 text-gray-600">{{ s.department }}</td>
            <td class="px-3 py-2.5 text-xs text-gray-400 font-mono">{{ s.source_id }}</td>
            <td class="px-3 py-2.5">
              <span :class="s.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'" class="text-xs px-2 py-0.5 rounded-full font-medium">
                {{ s.enabled ? '启用' : '停用' }}
              </span>
            </td>
            <td class="px-3 py-2.5">
              <span v-if="s.last_status === 'ok'" class="text-xs px-2 py-0.5 rounded-full font-medium bg-emerald-50 text-emerald-700">✓ OK</span>
              <span v-else-if="s.last_status === 'failed'" class="text-xs px-2 py-0.5 rounded-full font-medium bg-red-50 text-red-600" :title="s.last_status">✗ 失败</span>
              <span v-else class="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-100 text-gray-500">?</span>
            </td>
            <td class="px-3 py-2.5">
              <div class="flex gap-1">
                <button @click="openEdit(s)" class="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50">编辑</button>
                <button @click="delSource(s)" class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50">删</button>
              </div>
            </td>
          </tr>
          <tr v-if="!filtered.length && !loading">
            <td colspan="9" class="px-5 py-12 text-center text-gray-400 text-sm">
              没有匹配的源 — <button @click="clearFilters" class="text-brand-600 hover:underline">清除筛选</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mt-3 text-xs text-gray-500 text-right">
      <span v-if="loading">加载中…</span>
      <span v-else>共 {{ sources.length }} 个源</span>
    </div>

    <!-- 编辑 modal -->
    <div v-if="editModal.show && editModal.source" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="editModal.show=false">
      <div class="bg-white rounded-xl max-w-lg w-full p-5 shadow-2xl">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-base font-semibold">编辑源 #{{ editModal.source.id }}</h3>
          <button @click="editModal.show=false" class="text-gray-400 text-xl">×</button>
        </div>
        <div class="space-y-3 text-sm">
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">名称</div>
            <input v-model="editModal.source.name" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">URL</div>
            <input v-model="editModal.source.url" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <div class="text-xs text-gray-500 mb-1">类目</div>
              <input v-model="editModal.source.category" class="w-full px-2 py-1.5 border border-gray-200 rounded">
            </label>
            <label class="block">
              <div class="text-xs text-gray-500 mb-1">区域</div>
              <input v-model="editModal.source.region" class="w-full px-2 py-1.5 border border-gray-200 rounded">
            </label>
          </div>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">部门</div>
            <input v-model="editModal.source.department" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">标签(逗号分隔)</div>
            <input v-model="editModal.source.tags" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <div class="text-xs text-gray-500 mb-1">频率</div>
              <select v-model="editModal.source.frequency" class="w-full px-2 py-1.5 border border-gray-200 rounded bg-white">
                <option value="daily">daily</option>
                <option value="weekly">weekly</option>
                <option value="hourly">hourly</option>
                <option value="manual">manual</option>
              </select>
            </label>
            <label class="flex items-end gap-2">
              <input type="checkbox" v-model="editModal.source.enabled" class="rounded text-blue-600">
              <span>启用</span>
            </label>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button @click="editModal.show=false" class="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">取消</button>
            <button @click="saveEdit" class="px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700">保存</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增 modal -->
    <div v-if="newModal.show" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="newModal.show=false">
      <div class="bg-white rounded-xl max-w-md w-full p-5 shadow-2xl">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-base font-semibold">新增政策源</h3>
          <button @click="newModal.show=false" class="text-gray-400 text-xl">×</button>
        </div>
        <div class="space-y-3 text-sm">
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">Source ID(英文短码)</div>
            <input v-model="newModal.form.source_id" placeholder="例:my_source" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">名称</div>
            <input v-model="newModal.form.name" class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">URL</div>
            <input v-model="newModal.form.url" placeholder="http(s)://..." class="w-full px-2 py-1.5 border border-gray-200 rounded">
          </label>
          <div class="grid grid-cols-3 gap-3">
            <label class="block">
              <div class="text-xs text-gray-500 mb-1">类目</div>
              <input v-model="newModal.form.category" class="w-full px-2 py-1.5 border border-gray-200 rounded">
            </label>
            <label class="block">
              <div class="text-xs text-gray-500 mb-1">区域</div>
              <input v-model="newModal.form.region" class="w-full px-2 py-1.5 border border-gray-200 rounded">
            </label>
            <label class="block">
              <div class="text-xs text-gray-500 mb-1">部门</div>
              <input v-model="newModal.form.department" class="w-full px-2 py-1.5 border border-gray-200 rounded">
            </label>
          </div>
          <label class="block">
            <div class="text-xs text-gray-500 mb-1">频率</div>
            <select v-model="newModal.form.frequency" class="w-full px-2 py-1.5 border border-gray-200 rounded bg-white">
              <option value="daily">daily</option>
              <option value="weekly">weekly</option>
              <option value="hourly">hourly</option>
              <option value="manual">manual</option>
            </select>
          </label>
          <div class="flex justify-end gap-2 pt-2">
            <button @click="newModal.show=false" class="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">取消</button>
            <button @click="createSource" class="px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700">创建</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="toast.show" class="fixed bottom-6 right-6 bg-gray-900 text-white px-5 py-3 rounded-xl shadow-lg z-50 text-sm">{{ toast.msg }}</div>
  </div>
</template>
