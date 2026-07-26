<template>
  <div class="j3-share-based-payment">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 底稿目录（默认页） -->
      <J3TabIndex
        v-if="!currentSheet || currentSheet === 'J3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="props.isReadonly"
        :all-responses="allResponses"
        @navigate-sheet="handleNavigateSheet"
      />

      <!-- J3A 程序表（整册专属组件内分发，对齐 H1A/L1A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'J3A'"
        sheet-code="J3A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="props.isReadonly"
      />

      <!-- J3-1 股份支付情况表 -->
      <J3TabDetail
        v-else-if="currentSheet === 'J3-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="props.year"
        :html-data="props.htmlData"
        :all-responses="allResponses"
        :is-readonly="props.isReadonly"
        :save-immediate="handleChildSave"
      />

      <!-- J3-2 股份支付检查表 -->
      <J3TabCheck
        v-else-if="currentSheet === 'J3-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="props.year"
        :html-data="props.htmlData"
        :all-responses="allResponses"
        :is-readonly="props.isReadonly"
        :save-immediate="handleChildSave"
      />

      <!-- IPO 股份支付监管审计要点（整合页，两个 sheet 共用） -->
      <J3TabIpoFocus
        v-else-if="currentSheet === 'J3-IPO'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :html-data="props.htmlData"
        :all-responses="allResponses"
        :is-readonly="props.isReadonly"
        :save-immediate="handleChildSave"
      />

      <!-- 兜底 OnlyOffice -->
      <div v-else class="j3-sheet-placeholder">
        <el-empty :description="`J3 未识别的 sheet: ${currentSheet}（将使用 OnlyOffice）`" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ3ShareBasedPayment — J3 股份支付主入口组件
 *
 * J3 无独立科目（费用端走 K8/K9，权益端走 M4，现金端走 J1）。
 * persistence三连环：selfLoad + allResponses Map + handleChildSave
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 */
import { computed, ref, onMounted, onBeforeUnmount, defineAsyncComponent, toRef, inject, provide, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useChecklistPersistence,
  type ChecklistResponse,
} from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses } from '@/composables/workpaper/checklistPersistenceHelpers'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from '../composables/useWorkpaperReviewThreads'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'

// defineAsyncComponent 懒加载
const J3TabIndex = defineAsyncComponent(() => import('./core/J3TabIndex.vue'))
const J3TabDetail = defineAsyncComponent(() => import('./core/J3TabDetail.vue'))
const J3TabCheck = defineAsyncComponent(() => import('./core/J3TabCheck.vue'))
const J3TabIpoFocus = defineAsyncComponent(() => import('./core/J3TabIpoFocus.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  year?: string | number
  sheetName?: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  save: []
  completed: []
  'navigate-sheet': [sheetName: string]
}>()

const isLoading = ref(true)

/** 当前 sheet 名（从 props.sheetName 提取编码） */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  if (/\bJ3A\b/.test(sn) || sn.includes('实质性程序表')) return 'J3A'
  // IPO 监管要点 + 首发问答二 → 整合页
  if (sn.includes('IPO') || sn.includes('股权激励工具') || sn.includes('首发')) return 'J3-IPO'
  const m = sn.match(/(J3-\d+)/)
  if (m) return m[1]
  if (sn.includes('目录') || sn === 'J3') return 'J3'
  return sn
})

// ─── Runtime Boundary + Persistence Adapter ─────────────────────────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const persistence = useChecklistPersistence({
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || undefined),
  debounceMs: 800,
  onSaved: () => runtime?.version.scheduleAutoSnapshot(),
})
const allResponses = persistence.responses

// 复核圆点：子 tab 的 GtReviewTrigger 通过 inject 取得蓝/红点
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

async function selfLoad(): Promise<void> {
  const snapshot = collectChecklistResponses(
    (props.htmlData as any)?.responses_snapshot,
    (props.htmlData as any)?.allResponses,
    (props.htmlData as any)?.checklist_responses,
  )
  if (snapshot.length > 0) persistence.hydrate(snapshot)
  const fallback = new Map(allResponses.value)
  try {
    await persistence.load()
  } catch {
    if (fallback.size === 0) ElMessage.warning('J3 保存数据加载失败，请刷新后重试')
  }
  const merged = new Map(allResponses.value)
  for (const [itemId, item] of fallback) {
    if (!merged.has(itemId)) merged.set(itemId, item)
  }
  persistence.hydrate(merged)
}

/**
 * 子 tab 已完成业务序列化；统一交给 Adapter 管理逐 item debounce/flush/error。
 * 返回 Promise 以兼容子 composable 的 `saveImmediate(items).catch(...)` 契约。
 */
async function handleChildSave(items: ChecklistResponse[]): Promise<void> {
  for (const { item_id, ...patch } of items) {
    persistence.saveDebounced(item_id, patch)
  }
}

function handleNavigateSheet(sheetName: string) {
  emit('navigate-sheet', sheetName)
}

// sheet 切换时主动 flush 待保存 section。
watch(currentSheet, async (nextSheet, prevSheet) => {
  if (nextSheet === prevSheet) return
  try {
    await persistence.flush()
  } catch {
    ElMessage.error('J3 切换底稿时保存失败，数据已保留，可返回后重试')
  }
})

onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(async () => {
  await selfLoad()
  isLoading.value = false
})
</script>

<style scoped>
.j3-share-based-payment {
  padding: 16px;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.j3-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
