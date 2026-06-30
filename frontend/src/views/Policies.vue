<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'

const policies = ref([])
const facets = ref({ regions: [], departments: [], categories: [] })
const total = ref(0)
const query = ref('')
const selected = ref({
  region: [],     // 多选,例:['国家级','省级']
  department: [], // 多选,例:['发改委','工信部']
  category: []    // 多选
})
const toast = ref({ show: false, msg: '' })
const loading = ref(false)

function showToast(msg) {
  toast.value = { show: true, msg }
  setTimeout(() => toast.value.show = false, 2500)
}

function toggleFacet(group, value) {
  const arr = selected.value[group]
  const idx = arr.indexOf(value)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(value)
  search()
}

function clearFacet(group) {
  selected.value[group] = []
  search()
}

function clearAll() {
  selected.value = { region: [], department: [], category: [] }
  query.value = ''
  search()
}

async function search() {
  loading.value = true
  try {
    const params = { query: query.value, limit: 50, summarized_only: false }
    if (selected.value.region.length) params.region = selected.value.region
    if (selected.value.department.length) params.department = selected.value.department
    if (selected.value.category.length) params.category = selected.value.category
    const r = await api.get('/policies/search', { params })
    policies.value = r.data.policies
    facets.value = r.data.facets
    total.value = r.data.total
  } finally {
    loading.value = false
  }
}

async function crawl() {
  showToast('⏳ 爬取中...')
  await api.post('/crawl/all')
  showToast('✅ 爬取已触发')
}

function badgeColor(type) {
  const m = {
    '补贴': 'bg-green-100 text-green-700',
    '贷款': 'bg-blue-100 text-blue-700',
    '税收': 'bg-purple-100 text-purple-700',
    '人才': 'bg-pink-100 text-pink-700',
    '产业扶持': 'bg-orange-100 text-orange-700'
  }
  return m[type] || 'bg-gray-100 text-gray-600'
}

onMounted(search)

// ============== 详情预览 modal(后端 /content 拿 markdown) ==============
const preview = ref({ show: false, id: null, markdown: '', loading: false })
async function openPreview(p) {
  preview.value = { show: true, id: p.id, markdown: '加载中…', loading: true }
  try {
    const r = await api.get(`/policies/${p.id}/content`)
    preview.value = { show: true, id: p.id, markdown: r.data.markdown, loading: false }
  } catch (e) {
    preview.value = {
      show: true,
      id: p.id,
      markdown: '加载失败: ' + (e.response?.data?.detail || e.message),
      loading: false,
    }
  }
}
function closePreview() { preview.value.show = false }

// ============== 操作(摘要 / 推送 / 删除) ==============
const busyIds = ref([])

async function summarizeOne(p) {
  busyIds.value.push(p.id)
  try {
    showToast('🤖 AI 摘要中...')
    const r = await api.post(`/policies/${p.id}/summarize`)
    showToast('✅ 摘要完成')
    await search()
  } catch (e) {
    showToast('❌ 摘要失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    busyIds.value = busyIds.value.filter(x => x !== p.id)
  }
}

async function pushOne(p) {
  busyIds.value.push(p.id)
  try {
    showToast('📨 推送中...')
    const r = await api.post(`/policies/${p.id}/push`)
    showToast('✅ 推送成功')
  } catch (e) {
    showToast('❌ 推送失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    busyIds.value = busyIds.value.filter(x => x !== p.id)
  }
}

async function delOne(p) {
  if (!confirm(`删除政策「${p.title.slice(0, 40)}...」?`)) return
  busyIds.value.push(p.id)
  try {
    await api.delete(`/policies/${p.id}`)
    showToast('✅ 已删除')
    await search()
  } catch (e) {
    showToast('❌ 删除失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    busyIds.value = busyIds.value.filter(x => x !== p.id)
  }
}
</script>

<template>
  <div class="flex gap-6 items-start">
    <!-- 左侧 sidebar 多维筛选(类似 taobao 商品列表) -->
    <aside class="w-60 shrink-0 sticky top-4">
      <div class="bg-white border border-gray-200 rounded-xl p-4 mb-3 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-sm text-gray-900">🔍 筛选</h3>
          <button
            v-if="selected.region.length || selected.department.length || selected.category.length"
            @click="clearAll" class="text-xs text-brand-600 hover:underline">清空</button>
        </div>

        <!-- 级别(region) -->
        <details open class="mb-3 border-b border-gray-100 pb-3">
          <summary class="flex items-center justify-between cursor-pointer text-sm font-medium text-gray-700 mb-2 select-none">
            <span>级别</span>
            <span v-if="selected.region.length" class="text-xs px-1.5 py-0.5 bg-brand-100 text-brand-700 rounded">{{ selected.region.length }}</span>
          </summary>
          <div class="max-h-48 overflow-auto space-y-0.5">
            <label
              v-for="f in facets.regions" :key="f.value"
              class="flex items-center gap-2 text-sm px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer">
              <input
                type="checkbox"
                :checked="selected.region.includes(f.value)"
                @change="toggleFacet('region', f.value)"
                class="rounded text-brand-600 focus:ring-brand-500">
              <span class="flex-1 truncate text-gray-700">{{ f.value }}</span>
              <span class="text-xs text-gray-400 tabular-nums">{{ f.count }}</span>
            </label>
            <div v-if="!facets.regions.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
          </div>
          <button v-if="selected.region.length" @click="clearFacet('region')" class="text-xs text-brand-600 mt-1.5 hover:underline">清除</button>
        </details>

        <!-- 委办部门(department) -->
        <details open class="mb-3 border-b border-gray-100 pb-3">
          <summary class="flex items-center justify-between cursor-pointer text-sm font-medium text-gray-700 mb-2 select-none">
            <span>委办部门</span>
            <span v-if="selected.department.length" class="text-xs px-1.5 py-0.5 bg-brand-100 text-brand-700 rounded">{{ selected.department.length }}</span>
          </summary>
          <div class="max-h-48 overflow-auto space-y-0.5">
            <label
              v-for="f in facets.departments" :key="f.value"
              class="flex items-center gap-2 text-sm px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer">
              <input
                type="checkbox"
                :checked="selected.department.includes(f.value)"
                @change="toggleFacet('department', f.value)"
                class="rounded text-brand-600 focus:ring-brand-500">
              <span class="flex-1 truncate text-gray-700">{{ f.value }}</span>
              <span class="text-xs text-gray-400 tabular-nums">{{ f.count }}</span>
            </label>
            <div v-if="!facets.departments.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
          </div>
          <button v-if="selected.department.length" @click="clearFacet('department')" class="text-xs text-brand-600 mt-1.5 hover:underline">清除</button>
        </details>

        <!-- 类目(category) -->
        <details open class="mb-1">
          <summary class="flex items-center justify-between cursor-pointer text-sm font-medium text-gray-700 mb-2 select-none">
            <span>类目</span>
            <span v-if="selected.category.length" class="text-xs px-1.5 py-0.5 bg-brand-100 text-brand-700 rounded">{{ selected.category.length }}</span>
          </summary>
          <div class="max-h-48 overflow-auto space-y-0.5">
            <label
              v-for="f in facets.categories" :key="f.value"
              class="flex items-center gap-2 text-sm px-2 py-1.5 rounded hover:bg-gray-50 cursor-pointer">
              <input
                type="checkbox"
                :checked="selected.category.includes(f.value)"
                @change="toggleFacet('category', f.value)"
                class="rounded text-brand-600 focus:ring-brand-500">
              <span class="flex-1 truncate text-gray-700">{{ f.value }}</span>
              <span class="text-xs text-gray-400 tabular-nums">{{ f.count }}</span>
            </label>
            <div v-if="!facets.categories.length" class="text-xs text-gray-400 px-2 py-1">暂无</div>
          </div>
          <button v-if="selected.category.length" @click="clearFacet('category')" class="text-xs text-brand-600 mt-1.5 hover:underline">清除</button>
        </details>
      </div>

      <!-- 已选条件 chip 摘要 -->
      <div v-if="selected.region.length || selected.department.length || selected.category.length" class="bg-brand-50 border border-brand-100 rounded-xl p-3 text-xs text-gray-700">
        <div class="font-semibold mb-1.5 text-brand-700">已选 {{ total }} 条</div>
        <div v-if="selected.region.length" class="flex flex-wrap gap-1 mb-1">
          <span v-for="v in selected.region" :key="v" class="px-1.5 py-0.5 bg-white border border-brand-200 text-brand-700 rounded">{{ v }}</span>
        </div>
        <div v-if="selected.department.length" class="flex flex-wrap gap-1 mb-1">
          <span v-for="v in selected.department" :key="v" class="px-1.5 py-0.5 bg-white border border-brand-200 text-brand-700 rounded">{{ v }}</span>
        </div>
        <div v-if="selected.category.length" class="flex flex-wrap gap-1">
          <span v-for="v in selected.category" :key="v" class="px-1.5 py-0.5 bg-white border border-brand-200 text-brand-700 rounded">{{ v }}</span>
        </div>
      </div>
    </aside>

    <!-- 主区 -->
    <main class="flex-1 min-w-0">
      <div class="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h2 class="text-xl font-semibold text-gray-900 whitespace-nowrap">📜 政策库</h2>
        <input
          v-model="query" @keyup.enter="search" placeholder="搜索标题关键词..."
          class="text-sm px-3 py-1.5 border border-gray-200 rounded-lg flex-1 min-w-[200px] max-w-md focus:outline-none focus:ring-2 focus:ring-brand-200" />
        <button @click="search" class="text-sm px-3 py-1.5 rounded-lg bg-brand-500 text-white hover:bg-brand-600 whitespace-nowrap">搜索</button>
        <button @click="crawl" class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 whitespace-nowrap">爬取</button>
      </div>

      <div class="text-xs text-gray-500 mb-2">
        共 <span class="font-semibold text-gray-700">{{ total }}</span> 条
        <span v-if="loading" class="ml-2 text-brand-600">加载中...</span>
      </div>

      <div class="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 max-h-[75vh] overflow-y-auto shadow-sm">
        <div v-if="!policies.length && !loading" class="px-5 py-12 text-center text-gray-400 text-sm">
          暂无匹配。试着清空筛选,或点"爬取"拉新数据。
        </div>
        <div v-for="p in policies" :key="p.id" class="px-5 py-3 hover:bg-gray-50">
          <div class="flex items-center gap-2 mb-1 flex-wrap">
            <span v-if="p.summary_type" :class="badgeColor(p.summary_type)" class="text-xs px-2 py-0.5 rounded-full font-medium">{{ p.summary_type }}</span>
            <span v-else-if="p.category" class="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-100 text-gray-600">{{ p.category }}</span>
            <span v-if="p.region" class="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">{{ p.region }}</span>
            <span v-if="p.department" class="text-xs px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded">{{ p.department }}</span>
            <span class="text-xs text-gray-400 font-mono">{{ p.source_id }}</span>
            <span v-if="p.published_at" class="text-xs text-orange-600">📅 {{ p.published_at.slice(0, 10) }}</span>
          </div>
          <a :href="p.url" target="_blank" rel="noopener noreferrer" class="block">
            <h3 class="text-sm font-medium text-gray-900 hover:text-brand-600">{{ p.title }}</h3>
            <p class="text-xs text-gray-600 line-clamp-2 mt-1">
              {{ p.summary_text || '(无摘要 — 等待 AI 摘要)' }}
            </p>
          </a>
          <div class="mt-1.5 flex gap-1.5 flex-wrap">
            <button @click="openPreview(p)"
                    class="text-xs px-2.5 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100">
              📖 查看详情
            </button>
            <a :href="`/api/policies/${p.id}/pdf`" target="_blank" rel="noopener noreferrer"
               @click.stop
               class="text-xs px-2.5 py-1 rounded bg-green-50 text-green-700 hover:bg-green-100">
              📄 下载 PDF
            </a>
            <button @click="summarizeOne(p)" :disabled="busyIds.includes(p.id)"
                    class="text-xs px-2.5 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-50">
              🤖 AI 摘要
            </button>
            <button @click="pushOne(p)" :disabled="busyIds.includes(p.id)"
                    class="text-xs px-2.5 py-1 rounded bg-orange-50 text-orange-700 hover:bg-orange-100 disabled:opacity-50">
              📨 推送
            </button>
            <button @click="delOne(p)" :disabled="busyIds.includes(p.id)"
                    class="text-xs px-2.5 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50">
              🗑
            </button>
          </div>
        </div>
      </div>

      <div v-if="toast.show" class="fixed bottom-6 right-6 bg-gray-900 text-white px-5 py-3 rounded-xl shadow-lg z-50 text-sm">{{ toast.msg }}</div>

      <!-- 详情预览 modal -->
      <div v-if="preview.show"
           class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
           @click.self="closePreview">
        <div class="bg-white rounded-xl max-w-4xl w-full max-h-[88vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h3 class="text-base font-semibold text-gray-900">📖 政策详情 (Markdown)</h3>
            <button @click="closePreview"
                    class="text-gray-400 hover:text-gray-700 text-2xl leading-none">×</button>
          </div>
          <div class="flex-1 overflow-auto px-6 py-4">
            <div v-if="preview.loading" class="text-sm text-brand-600">加载中…</div>
            <pre v-else class="whitespace-pre-wrap text-xs text-gray-800 font-mono leading-relaxed">{{ preview.markdown }}</pre>
          </div>
          <div class="border-t border-gray-200 px-6 py-3 flex gap-2">
            <a :href="`/api/policies/${preview.id}/pdf`" target="_blank" rel="noopener noreferrer"
               class="text-sm px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700">📥 下载 PDF</a>
            <a :href="policies.find(x => x.id === preview.id)?.url || '#'" target="_blank" rel="noopener noreferrer"
               class="text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">🔗 原始链接</a>
            <button @click="closePreview"
                    class="ml-auto text-sm px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50">关闭</button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
