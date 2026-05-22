<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :show-close="false"
    width="600px"
    top="20vh"
    append-to-body
    class="gt-global-search-dialog"
    @opened="onOpened"
  >
    <!-- 搜索输入 -->
    <div class="gt-search-input-wrap">
      <el-input
        ref="inputRef"
        v-model="keyword"
        placeholder="搜索底稿、科目、报表、项目..."
        size="large"
        clearable
        @keydown.up.prevent="moveUp"
        @keydown.down.prevent="moveDown"
        @keydown.enter.prevent="confirmSelect"
        @keydown.esc="$emit('update:visible', false)"
      >
        <template #prefix>🔍</template>
        <template #suffix>
          <kbd class="gt-kbd">ESC</kbd>
        </template>
      </el-input>
    </div>

    <!-- 结果区域 -->
    <div class="gt-search-results" v-loading="loading">
      <!-- 无输入时显示最近访问 -->
      <template v-if="!keyword && recentItems.length > 0">
        <div class="gt-search-section-title">最近访问</div>
        <div
          v-for="(item, idx) in recentItems"
          :key="'recent-' + idx"
          class="gt-search-item"
          :class="{ 'gt-search-item--active': activeIndex === idx }"
          @click="onSelect(item)"
          @mouseenter="activeIndex = idx"
        >
          <span class="gt-search-item-icon">{{ typeIcon(item.type) }}</span>
          <span class="gt-search-item-title">{{ item.title }}</span>
          <span class="gt-search-item-subtitle">{{ item.subtitle }}</span>
        </div>
      </template>

      <!-- 搜索结果 -->
      <template v-if="keyword && results.length > 0">
        <div class="gt-search-section-title">搜索结果 ({{ results.length }})</div>
        <div
          v-for="(item, idx) in results"
          :key="item.id"
          class="gt-search-item"
          :class="{ 'gt-search-item--active': activeIndex === idx }"
          @click="onSelect(item)"
          @mouseenter="activeIndex = idx"
        >
          <span class="gt-search-item-icon">{{ typeIcon(item.type) }}</span>
          <span class="gt-search-item-title">{{ item.title }}</span>
          <span class="gt-search-item-subtitle">{{ item.subtitle }}</span>
        </div>
      </template>

      <!-- 无结果 -->
      <div v-if="keyword && !loading && results.length === 0" class="gt-search-empty">
        无匹配结果
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'

interface SearchResultItem {
  type: string
  id: string
  title: string
  subtitle: string
  route: { name: string; params?: Record<string, string>; query?: Record<string, string> }
  relevance: number
}

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [val: boolean] }>()

const router = useRouter()
const inputRef = ref<any>(null)
const keyword = ref('')
const results = ref<SearchResultItem[]>([])
const loading = ref(false)
const activeIndex = ref(0)

// 最近访问（localStorage）
const RECENT_KEY = 'gt_recent_search'
const recentItems = ref<SearchResultItem[]>(loadRecent())

function loadRecent(): SearchResultItem[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveRecent(item: SearchResultItem) {
  const list = loadRecent().filter(r => r.id !== item.id)
  list.unshift(item)
  const trimmed = list.slice(0, 10)
  localStorage.setItem(RECENT_KEY, JSON.stringify(trimmed))
  recentItems.value = trimmed
}

// 搜索防抖
let debounceTimer: ReturnType<typeof setTimeout> | null = null

watch(keyword, (val) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (!val || val.length < 2) {
    results.value = []
    activeIndex.value = 0
    return
  }
  loading.value = true
  debounceTimer = setTimeout(async () => {
    try {
      const { data } = await http.get('/api/search/global', { params: { q: val } })
      results.value = data?.results ?? []
    } catch {
      results.value = []
    } finally {
      loading.value = false
      activeIndex.value = 0
    }
  }, 300)
})

// 键盘导航
function moveUp() {
  const max = keyword.value ? results.value.length : recentItems.value.length
  activeIndex.value = (activeIndex.value - 1 + max) % max
}

function moveDown() {
  const max = keyword.value ? results.value.length : recentItems.value.length
  activeIndex.value = (activeIndex.value + 1) % max
}

function confirmSelect() {
  const list = keyword.value ? results.value : recentItems.value
  if (list[activeIndex.value]) {
    onSelect(list[activeIndex.value])
  }
}

// 选中跳转
function onSelect(item: SearchResultItem) {
  saveRecent(item)
  emit('update:visible', false)
  keyword.value = ''
  router.push({ name: item.route.name, params: item.route.params, query: item.route.query })
}

// 类型图标
function typeIcon(type: string): string {
  const map: Record<string, string> = {
    workpaper: '📋',
    account: '📊',
    report_line: '📄',
    project: '📁',
  }
  return map[type] || '🔗'
}

// 打开时聚焦
function onOpened() {
  nextTick(() => inputRef.value?.focus())
}
</script>

<style scoped>
.gt-global-search-dialog :deep(.el-dialog__header) { display: none; }
.gt-global-search-dialog :deep(.el-dialog__body) { padding: 0; }

.gt-search-input-wrap {
  padding: 12px 16px;
  border-bottom: 1px solid var(--gt-border-color, #e4e7ed);
}

.gt-search-results {
  max-height: 360px;
  overflow-y: auto;
  padding: 8px 0;
}

.gt-search-section-title {
  padding: 4px 16px;
  font-size: 12px;
  color: #999;
}

.gt-search-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.gt-search-item:hover,
.gt-search-item--active {
  background: var(--gt-table-row-hover, #f5f8fc);
}

.gt-search-item-icon { font-size: 16px; flex-shrink: 0; }
.gt-search-item-title { flex: 1; font-size: 14px; color: #333; }
.gt-search-item-subtitle { font-size: 12px; color: #999; }

.gt-search-empty {
  padding: 32px 16px;
  text-align: center;
  color: #999;
  font-size: 14px;
}

.gt-kbd {
  display: inline-block;
  padding: 1px 5px;
  font-size: 11px;
  border: 1px solid #ddd;
  border-radius: 3px;
  background: #f5f5f5;
  color: #666;
}
</style>
