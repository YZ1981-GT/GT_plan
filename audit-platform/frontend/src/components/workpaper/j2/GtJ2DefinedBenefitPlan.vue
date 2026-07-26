<template>
  <div class="j2-defined-benefit-plan">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 底稿目录 -->
      <J2TabIndex
        v-if="currentSheet === '底稿目录'"
        :wp-id="wpId"
        :project-id="projectId"
        :all-responses="allResponses"
      />
      <!-- J2A 程序表（整册专属组件内分发，对齐 H1A/L1A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'J2A'"
        sheet-code="J2A"
        :html-data="htmlData"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
      />
      <!-- J2-1 审定表 -->
      <J2TabAdjudication
        v-else-if="currentSheet === 'J2-1'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :save-immediate="handleChildSave"
        @save="onSave"
      />
      <!-- J2-2 明细表 -->
      <J2TabDetail
        v-else-if="currentSheet === 'J2-2'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :save-immediate="handleChildSave"
      />
      <!-- J2-3 调整分录 -->
      <J2TabAdjustment
        v-else-if="currentSheet === 'J2-3'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :save-immediate="handleChildSave"
      />
      <!-- J2-4 计提情况检查表 -->
      <J2TabAccrualCheck
        v-else-if="currentSheet === 'J2-4'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :save-immediate="handleChildSave"
      />
      <!-- 附注（上市公司） -->
      <J2TabDisclosureListed
        v-else-if="currentSheet === 'J2附注(上市)'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :save-immediate="handleChildSave"
      />
      <!-- 附注（国有企业） -->
      <J2TabDisclosureSoe
        v-else-if="currentSheet === 'J2附注(国企)'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :all-responses="allResponses"
        :is-readonly="isReadonly"
        :save-immediate="handleChildSave"
      />
      <!-- 兜底 -->
      <div v-else class="j2-sheet-placeholder">
        <el-empty :description="`J2 未识别的 sheet: ${currentSheet}`" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ2DefinedBenefitPlan — J2 设定受益计划主入口组件
 *
 * 按 sheetName v-if 分发到各子组件（defineAsyncComponent lazy 加载）。
 * 科目2221长期应付职工薪酬-设定受益计划（贷方/负债类）：期末=期初+贷方-借方
 *
 * persistence三连环：selfLoad(checklist-responses GET) + allResponses Map + handleChildSave(PUT)
 */
import { computed, ref, onMounted, defineAsyncComponent, inject, provide, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'
import {
  useChecklistPersistence,
  type ChecklistResponse,
} from '@/composables/workpaper/useChecklistPersistence'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from '../composables/useWorkpaperReviewThreads'

// ── defineAsyncComponent lazy loading ───────────────────────────────────────
const J2TabIndex = defineAsyncComponent(() => import('./J2TabIndex.vue'))
const J2TabAdjudication = defineAsyncComponent(() => import('./J2TabAdjudication.vue'))
const J2TabDetail = defineAsyncComponent(() => import('./J2TabDetail.vue'))
const J2TabAdjustment = defineAsyncComponent(() => import('./J2TabAdjustment.vue'))
const J2TabAccrualCheck = defineAsyncComponent(() => import('./J2TabAccrualCheck.vue'))
const J2TabDisclosureListed = defineAsyncComponent(() => import('./J2TabDisclosureListed.vue'))
const J2TabDisclosureSoe = defineAsyncComponent(() => import('./J2TabDisclosureSoe.vue'))

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
const runtime = inject(WorkpaperRuntimeContextKey, null)

// 目录页跳转：J2TabIndex inject('jumpToSection') → 转发为 navigate-sheet 交 GtWpRenderer 切页
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

// 复核圆点：子 tab 的 GtReviewTrigger 通过 inject 取得蓝/红点
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

/** 当前 sheet 名（从 props.sheetName 提取） */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  if (/\bJ2A\b/.test(sn) || sn.includes('实质性程序表')) return 'J2A'
  if (sn.includes('底稿目录')) return '底稿目录'
  if (/(?:^|[^A-Z0-9])J2-1(?!\d)/.test(sn) || sn.includes('审定表')) return 'J2-1'
  if (/(?:^|[^A-Z0-9])J2-2(?!\d)/.test(sn) || sn.includes('明细表')) return 'J2-2'
  if (/(?:^|[^A-Z0-9])J2-3(?!\d)/.test(sn) || sn.includes('调整分录')) return 'J2-3'
  if (/(?:^|[^A-Z0-9])J2-4(?!\d)/.test(sn) || sn.includes('计提') || sn.includes('检查表')) return 'J2-4'
  if (sn.includes('上市')) return 'J2附注(上市)'
  if (sn.includes('国有') || sn.includes('国企')) return 'J2附注(国企)'
  const m = sn.match(/^(J2-\d+)/)
  return m ? m[1] : sn
})

// ─── Persistence Adapter：多 section 按 item 隔离保存 ────────────────────────
const persistence = useChecklistPersistence({
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || undefined),
  debounceMs: 800,
  onSaved: () => runtime?.version.scheduleAutoSnapshot(),
})
const allResponses = persistence.responses

async function selfLoad(): Promise<void> {
  // render-config 快照作为断网/旧数据兼容基线；GET 成功后以服务端为准，
  // 再补齐快照中服务端未返回的 section。
  persistence.hydrate(props.htmlData)
  const fallback = new Map(allResponses.value)
  try {
    await persistence.load()
  } catch {
    if (fallback.size === 0) ElMessage.warning('J2 保存数据加载失败，请刷新后重试')
  }
  const merged = new Map(allResponses.value)
  for (const [itemId, item] of fallback) {
    if (!merged.has(itemId)) merged.set(itemId, item)
  }
  persistence.hydrate(merged)
}

/** 子 tab 已完成业务序列化；统一交给 Adapter 管理逐 item debounce/flush/error state。 */
function handleChildSave(items: ChecklistResponse[]): void {
  for (const { item_id, ...patch } of items) {
    persistence.saveDebounced(item_id, patch)
  }
}

async function onSave(): Promise<void> {
  try {
    await persistence.flush()
    emit('save')
  } catch {
    ElMessage.error('J2 保存失败，数据已保留，可重试')
  }
}

// 整册专属组件在 sheet 切换时不会卸载主入口；主动 flush，避免子 section
// 已销毁后仍依赖防抖定时器完成保存。
watch(currentSheet, async (nextSheet, previousSheet) => {
  if (nextSheet === previousSheet) return
  try {
    await persistence.flush()
  } catch {
    ElMessage.error('J2 切换底稿时保存失败，数据已保留，可返回后重试')
  }
})

onMounted(async () => {
  await selfLoad()
  isLoading.value = false
})
</script>

<style scoped>
.j2-defined-benefit-plan {
  padding: 16px;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.j2-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
