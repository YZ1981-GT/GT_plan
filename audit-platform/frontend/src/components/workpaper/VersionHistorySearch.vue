<!--
  历史版本搜索 — proposal-remaining-18 task 5.4 (S-4)

  在底稿版本对比抽屉/弹窗中嵌入。用户输入关键字后 debounce 500ms 调用
  GET /api/working-papers/{wp_id}/versions/search，结果列表按版本分组展示，
  点击可 emit `jump` 事件携带 { versionId, sheet, cellRef } 由父组件跳转。
-->

<template>
  <div class="gt-vh-search">
    <el-input
      v-model="keyword"
      :placeholder="placeholder"
      size="default"
      clearable
      :prefix-icon="Search"
      data-testid="vh-search-input"
      @input="onKeywordInput"
      @clear="onKeywordClear"
    />

    <div v-loading="loading" class="gt-vh-search__results">
      <el-empty
        v-if="!loading && keyword && results.length === 0"
        :image-size="48"
        description="未找到匹配结果"
      />
      <el-empty
        v-else-if="!loading && !keyword"
        :image-size="48"
        description="输入关键字搜索历史值"
      />
      <ul v-else class="gt-vh-search__list">
        <li
          v-for="(row, idx) in results"
          :key="`${row.version_id}-${row.sheet}-${row.cell_ref}-${idx}`"
          class="gt-vh-search__item"
          data-testid="vh-search-item"
          @click="onJump(row)"
        >
          <div class="gt-vh-search__row1">
            <el-tag size="small" :type="tagTypeFor(row.trigger_event)">
              {{ triggerLabel(row.trigger_event) }}
            </el-tag>
            <span class="gt-vh-search__addr">{{ row.sheet ? `${row.sheet}!${row.cell_ref}` : row.cell_ref }}</span>
            <span class="gt-vh-search__time">{{ formatTime(row.snapshot_at) }}</span>
          </div>
          <div class="gt-vh-search__value" :title="String(row.value)">
            {{ formatValue(row.value) }}
          </div>
        </li>
      </ul>
    </div>

    <div v-if="!loading && results.length > 0" class="gt-vh-search__summary">
      共找到 {{ total }} 条匹配
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

export interface VersionSearchHit {
  version_id: string
  trigger_event: string
  snapshot_at: string | null
  sheet: string
  cell_ref: string
  value: unknown
  field: string
}

const props = withDefaults(
  defineProps<{
    wpId: string
    /** 搜索关键字最小长度（默认 1） */
    minLength?: number
    /** debounce 间隔 ms（默认 500） */
    debounceMs?: number
    placeholder?: string
  }>(),
  {
    minLength: 1,
    debounceMs: 500,
    placeholder: '搜索历史版本中的值（数字 / 文本）',
  }
)

const emit = defineEmits<{
  (
    e: 'jump',
    payload: { versionId: string; sheet: string; cellRef: string; row: VersionSearchHit }
  ): void
  (e: 'results', payload: { total: number; results: VersionSearchHit[] }): void
}>()

const keyword = ref('')
const loading = ref(false)
const results = ref<VersionSearchHit[]>([])
const total = ref(0)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function clearDebounce() {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
}

function onKeywordInput() {
  clearDebounce()
  const k = keyword.value.trim()
  if (k.length < props.minLength) {
    results.value = []
    total.value = 0
    loading.value = false
    return
  }
  debounceTimer = setTimeout(() => {
    runSearch()
  }, props.debounceMs)
}

function onKeywordClear() {
  clearDebounce()
  keyword.value = ''
  results.value = []
  total.value = 0
  loading.value = false
}

async function runSearch() {
  const k = keyword.value.trim()
  if (!k || !props.wpId) return
  loading.value = true
  try {
    const data = await api.get(P_wp.searchVersions(props.wpId), {
      params: { q: k, limit: 100 },
    })
    const list: VersionSearchHit[] = Array.isArray(data?.results) ? data.results : []
    results.value = list
    total.value = typeof data?.total === 'number' ? data.total : list.length
    emit('results', { total: total.value, results: list })
  } catch (e) {
    handleApiError(e, '历史版本搜索')
    results.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onJump(row: VersionSearchHit) {
  emit('jump', {
    versionId: row.version_id,
    sheet: row.sheet,
    cellRef: row.cell_ref,
    row,
  })
}

// wp_id 切换时清空
watch(
  () => props.wpId,
  () => {
    clearDebounce()
    keyword.value = ''
    results.value = []
    total.value = 0
    loading.value = false
  }
)

onBeforeUnmount(() => {
  clearDebounce()
})

// ---- 显示工具 ----

function triggerLabel(evt: string): string {
  const map: Record<string, string> = {
    sign: '签字',
    review: '提交复核',
    prefill: '预填充',
    current: '当前',
  }
  return map[evt] || evt || '—'
}

function tagTypeFor(evt: string): 'success' | 'warning' | 'info' | 'primary' | 'danger' {
  if (evt === 'sign') return 'success'
  if (evt === 'review') return 'warning'
  if (evt === 'current') return 'primary'
  return 'info'
}

function formatTime(t: string | null): string {
  if (!t) return ''
  // 截 yyyy-MM-dd HH:mm
  const s = t.length >= 16 ? t.replace('T', ' ').slice(0, 16) : t
  return s
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  const s = String(v)
  return s.length > 80 ? `${s.slice(0, 80)}…` : s
}

defineExpose({ runSearch, keyword, results, total })
</script>

<style scoped>
.gt-vh-search {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.gt-vh-search__results {
  min-height: 80px;
  max-height: 360px;
  overflow-y: auto;
}
.gt-vh-search__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.gt-vh-search__item {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}
.gt-vh-search__item:hover {
  background-color: var(--gt-color-bg-secondary, #f5f7fa);
}
.gt-vh-search__row1 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}
.gt-vh-search__addr {
  font-family: var(--gt-font-mono, monospace);
  color: var(--gt-color-text-primary);
  font-weight: 600;
}
.gt-vh-search__time {
  margin-left: auto;
  color: var(--gt-color-text-tertiary);
}
.gt-vh-search__value {
  margin-top: 4px;
  font-family: var(--gt-font-mono, monospace);
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
  word-break: break-all;
}
.gt-vh-search__summary {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  text-align: right;
}
</style>
