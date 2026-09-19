<script setup lang="ts">
/**
 * KamEmbedPanel — ch12 内嵌 KAM 列表面板
 *
 * 展示 A17-2-1 KAM 条目列表（title、description、wp_refs 渲染为 RefChip）。
 * 点击条目跳转至 A17-2-1 对应条目。
 * A17-2-1 不存在时显示占位提示。
 *
 * Requirements: 5.1, 5.2, 5.3, 5.5
 */
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import { resolveWpCodeState } from '@/composables/useA17Navigation'
import { extractWpCodes } from '@/composables/useWpCodeParser'
import RefChipInline from './RefChipInline.vue'

// ─── Types ───
export interface KamEntry {
  item_id: string
  title: string
  description: string
  wp_refs: string
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const router = useRouter()

// ─── State ───
const kamEntries = ref<KamEntry[]>([])
const loading = ref(false)
const a17_2_1_exists = ref(false)
const a17_2_1_wpId = ref<string | null>(null)
const wpIndex = ref<WpIndexItem[]>([])

// ─── Computed ───
const hasEntries = computed(() => kamEntries.value.length > 0)

// ─── Methods ───

async function loadKamData() {
  if (!props.projectId) return
  loading.value = true
  try {
    // 先加载 wp_index 确认 A17-2-1 是否存在
    wpIndex.value = await getWpIndex(props.projectId)
    const kamState = resolveWpCodeState('A17-2-1', wpIndex.value)
    a17_2_1_exists.value = kamState.exists
    a17_2_1_wpId.value = kamState.wpId

    if (!kamState.exists || !kamState.wpId) {
      kamEntries.value = []
      return
    }

    // 加载 KAM 条目（从 checklist_responses 获取 A17-2-1-KAM* 记录）
    const data = await api.get(`/api/workpapers/${kamState.wpId}/checklist-responses`, {
      params: { project_id: props.projectId },
    })
    const records = (data as Array<{ item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null }>) || []

    // 过滤 KAM 条目
    kamEntries.value = records
      .filter((r) => r.item_id?.startsWith('A17-2-1-KAM'))
      .map((r) => {
        let description = ''
        try {
          const remarkData = r.remark ? JSON.parse(r.remark) : {}
          description = remarkData.situation || remarkData.reason || ''
        } catch {
          description = r.remark || ''
        }
        return {
          item_id: r.item_id,
          title: r.conclusion || `KAM-${r.item_id.replace('A17-2-1-KAM-', '')}`,
          description: description.slice(0, 100),
          wp_refs: r.wp_ref || '',
        }
      })
  } catch {
    kamEntries.value = []
  } finally {
    loading.value = false
  }
}

function handleRefresh() {
  loadKamData()
  emit('refresh')
}

function navigateToKam(entry: KamEntry) {
  if (!a17_2_1_wpId.value || !props.projectId) return
  router.push({
    name: 'WorkpaperEditor',
    params: {
      projectId: props.projectId,
      wpId: a17_2_1_wpId.value,
    },
  })
}

/** 解析 wp_refs 中的 wp_code 并返回导航状态 */
function getRefCodes(wpRefs: string): Array<{ code: string; wpId: string | null; disabled: boolean }> {
  if (!wpRefs) return []
  const codes = extractWpCodes(wpRefs)
  return codes.map((code) => {
    const state = resolveWpCodeState(code, wpIndex.value)
    return { code, wpId: state.wpId, disabled: state.disabled }
  })
}

// ─── Lifecycle ───
onMounted(() => {
  loadKamData()
})

defineExpose({ refresh: handleRefresh })
</script>

<template>
  <div class="kam-embed-panel" v-loading="loading">
    <div class="kam-embed-panel__header">
      <span class="kam-embed-panel__title">关键审计事项 (KAM)</span>
      <el-button size="small" text type="primary" @click="handleRefresh">
        刷新
      </el-button>
    </div>

    <!-- A17-2-1 不存在 -->
    <div v-if="!loading && !a17_2_1_exists" class="kam-embed-panel__placeholder">
      <el-alert type="info" :closable="false" show-icon>
        <template #title>尚未创建 KAM 底稿（A17-2-1），如属上市公司审计请先创建</template>
      </el-alert>
    </div>

    <!-- 有 KAM 条目 -->
    <div v-else-if="!loading && hasEntries" class="kam-embed-panel__list">
      <div
        v-for="entry in kamEntries"
        :key="entry.item_id"
        class="kam-embed-panel__item"
        @click="navigateToKam(entry)"
      >
        <div class="kam-item__title">{{ entry.title }}</div>
        <div v-if="entry.description" class="kam-item__desc">{{ entry.description }}</div>
        <div v-if="entry.wp_refs" class="kam-item__refs">
          <RefChipInline
            v-for="ref in getRefCodes(entry.wp_refs)"
            :key="ref.code"
            :wp-code="ref.code"
            :disabled="ref.disabled"
            :wp-id="ref.wpId || undefined"
            :project-id="projectId"
          />
        </div>
      </div>
    </div>

    <!-- A17-2-1 存在但无 KAM 条目 -->
    <div v-else-if="!loading && a17_2_1_exists && !hasEntries" class="kam-embed-panel__empty">
      <span>A17-2-1 中暂无 KAM 条目</span>
    </div>
  </div>
</template>

<style scoped>
.kam-embed-panel { border: 1px solid var(--gt-color-border-light, #ebeef5); border-radius: var(--gt-radius-sm, 4px); padding: var(--gt-space-3, 12px); margin-bottom: var(--gt-space-3, 12px); background: var(--gt-color-bg-elevated, #fafafa); }
.kam-embed-panel__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--gt-space-2, 8px); }
.kam-embed-panel__title { font-size: var(--gt-font-size-sm, 13px); font-weight: 600; color: var(--gt-color-text-secondary, #606266); }
.kam-embed-panel__placeholder { margin-top: var(--gt-space-2, 8px); }
.kam-embed-panel__list { display: flex; flex-direction: column; gap: var(--gt-space-2, 8px); }
.kam-embed-panel__item { padding: var(--gt-space-2, 8px); border: 1px solid var(--gt-color-border-lighter, #ebeef5); border-radius: var(--gt-radius-sm, 4px); cursor: pointer; transition: background 0.2s, border-color 0.2s; }
.kam-embed-panel__item:hover { background: var(--gt-color-primary-bg, #ecf5ff); border-color: var(--gt-color-primary-light, #b3d8ff); }
.kam-item__title { font-size: var(--gt-font-size-sm, 13px); font-weight: 600; color: var(--gt-color-text, #303133); margin-bottom: 4px; }
.kam-item__desc { font-size: var(--gt-font-size-xs, 12px); color: var(--gt-color-text-secondary, #606266); line-height: 1.4; margin-bottom: 4px; }
.kam-item__refs { display: flex; flex-wrap: wrap; gap: 4px; }
.kam-embed-panel__empty { font-size: var(--gt-font-size-sm, 13px); color: var(--gt-color-text-tertiary, #a8abb2); text-align: center; padding: var(--gt-space-3, 12px); }
</style>
