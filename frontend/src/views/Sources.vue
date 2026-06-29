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

async function load() {
  loading.value = true
  try {
    const r = await api.get('/sources')
    sources.value = r.data
  } finally {
    loading.value = false
  }
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

const filtered = computed(() => {
  const q = filters.value.q.trim().toLowerCase()
  return sources.value.filter(s => {
    if (q && !((s.name || '').toLowerCase().includes(q) ||
               (s.source_id || '').toLowerCase().includes(q))) return false
    if (filters.value.category.length && !filters.value.category.includes(s.category)) return false
    if (filters.value.region.length && !filters.value.region.includes(s.region)) return false
    if (filters.value.department.length && !filters.value.department.includes(s.department)) return false
    if (filters.value.enabled !== 'all' && s.enabled !== (filters.value.enabled === 'yes')) return false
    return true
  })
})

function toggle(id) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
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
    await load()
  } catch (e) {
    alert('批量操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function batchCrawl() {
  const ids = [...selected.value]
  if (!ids.length) return
  if (!confirm(`对所选 ${ids.length} 个源发起爬取?`)) return
  await Promise.allSettled(ids.map(id => api.post(`/crawl/${id}`)))
  selected.value = new Set()
  alert(`已触发 ${ids.length} 个源的爬取,详见 app 日志 / dashboard`)
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
  if (i >= 0) arr.splice(i, 1)
  else arr.push(value)
}

onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4 gap-3 flex-wrap">
      <h2 class="text-xl font-semibold text-gray-900 whitespace-nowrap">🕷️ 政策源</h2>
      <input v-model="filters.q" placeholder="搜索名称 / source_id..."
             class="text-sm px-3 py-1.5 border border-gray-200 rounded-lg flex-1 min-w-[180px] max-w-sm">
      <button @click="load" :disabled="loading"
              class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-50">刷新</button>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
      <!-- 类目 -->
      <div class="bg-white border border-gray-200 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-semibold text-gray-700">🏷️ 类目</h4>
          <span class="text-xs text-gray-400">{{ filters.category.length || '全' }}</span>
        </div>
        <div class="max-h-40 overflow-auto space-y-0.5">
          <label v-for="c in facets.cats" :key="c"
                 class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="checkbox" :checked="filters.category.includes(c)" @change="toggleArr('category', c)"
                   class="rounded text-brand-600">
            <span class="flex-1 truncate text-gray-700">{{ c }}</span>
          </label>
          <div v-if="!facets.cats.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
        </div>
      </div>

      <!-- 区域 -->
      <div class="bg-white border border-gray-200 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-semibold text-gray-700">📍 区域</h4>
          <span class="text-xs text-gray-400">{{ filters.region.length || '全' }}</span>
        </div>
        <div class="max-h-40 overflow-auto space-y-0.5">
          <label v-for="r in facets.regs" :key="r"
                 class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="checkbox" :checked="filters.region.includes(r)" @change="toggleArr('region', r)"
                   class="rounded text-brand-600">
            <span class="flex-1 truncate text-gray-700">{{ r }}</span>
          </label>
          <div v-if="!facets.regs.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
        </div>
      </div>

      <!-- 部门 -->
      <div class="bg-white border border-gray-200 rounded-xl p-3">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-semibold text-gray-700">🏛️ 部门</h4>
          <span class="text-xs text-gray-400">{{ filters.department.length || '全' }}</span>
        </div>
        <div class="max-h-40 overflow-auto space-y-0.5">
          <label v-for="d in facets.depts" :key="d"
                 class="flex items-center gap-2 text-sm hover:bg-gray-50 px-1.5 py-1 rounded cursor-pointer">
            <input type="checkbox" :checked="filters.department.includes(d)" @change="toggleArr('department', d)"
                   class="rounded text-brand-600">
            <span class="flex-1 truncate text-gray-700">{{ d }}</span>
          </label>
          <div v-if="!facets.depts.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
        </div>
      </div>

      <!-- 启用状态 -->
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

      <!-- 清筛选 -->
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

    <!-- 批量操作栏(勾选后浮动显示) -->
    <div v-if="selected.size" class="bg-brand-50 border-2 border-brand-300 rounded-xl p-3 mb-3 sticky top-16 z-10 flex items-center gap-3 flex-wrap shadow-sm">
      <span class="text-sm text-brand-700 font-medium">已选 {{ selected.size }} 个源</span>
      <button @click="toggleAll" class="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-white">取消选择</button>
      <button @click="batchSet(true)" class="text-xs px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700">批量启用</button>
      <button @click="batchSet(false)" class="text-xs px-3 py-1.5 rounded-lg bg-gray-600 text-white hover:bg-gray-700">批量停用</button>
      <button @click="batchCrawl" class="text-xs px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700">批量爬取</button>
    </div>

    <!-- 表格 -->
    <div class="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
          <tr>
            <th class="px-3 py-2.5 w-10">
              <input type="checkbox"
                     :checked="selected.size === filtered.length && filtered.length > 0"
                     @change="toggleAll" class="rounded">
            </th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">名称</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">类目</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">区域</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">部门</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">Source ID</th>
            <th class="px-3 py-2.5 text-left font-medium text-gray-700">状态</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-for="s in filtered" :key="s.id"
              :class="['hover:bg-gray-50', selected.has(s.id) ? 'bg-brand-50/50' : '']">
            <td class="px-3 py-2.5">
              <input type="checkbox" :checked="selected.has(s.id)" @change="toggle(s.id)" class="rounded">
            </td>
            <td class="px-3 py-2.5 font-medium text-gray-900">
              <router-link :to="{ name: 'policies', query: { source: s.source_id } }"
                           class="hover:text-brand-600">{{ s.name }}</router-link>
            </td>
            <td class="px-3 py-2.5 text-gray-600">{{ s.category }}</td>
            <td class="px-3 py-2.5 text-gray-600">{{ s.region }}</td>
            <td class="px-3 py-2.5 text-gray-600">{{ s.department }}</td>
            <td class="px-3 py-2.5 text-xs text-gray-400 font-mono">{{ s.source_id }}</td>
            <td class="px-3 py-2.5">
              <span :class="s.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                    class="text-xs px-2 py-0.5 rounded-full font-medium">
                {{ s.enabled ? '启用' : '停用' }}
              </span>
            </td>
          </tr>
          <tr v-if="!filtered.length && !loading">
            <td colspan="7" class="px-5 py-12 text-center text-gray-400 text-sm">
              没有匹配的源 — 试试 <button @click="clearFilters" class="text-brand-600 hover:underline">清除筛选</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mt-3 text-xs text-gray-500 text-right">
      <span v-if="loading">加载中…</span>
      <span v-else>共 {{ sources.length }} 个源</span>
    </div>
  </div>
</template>
