<template>
  <div class="i5-other-noncurrent-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'I5'" class="i5-header-toolbar">
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !dualMode.checking.value" size="small" type="info">仅结构化视图</el-tag>
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else-if="dualMode.currentMode.value === 'html'">
        <!-- 底稿目录 -->
        <I5TabIndex
          v-if="currentSheet === 'I5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I5A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'I5A'"
          sheet-code="I5A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- I5-1 审定表 -->
        <I5TabAdjudication
          v-else-if="currentSheet === 'I5-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I5-2 明细表 -->
        <I5TabDetail
          v-else-if="currentSheet === 'I5-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I5-3 调整分录 -->
        <I5TabAdjustment
          v-else-if="currentSheet === 'I5-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I5-4 针对性检查 -->
        <I5TabTargetedCheck
          v-else-if="currentSheet === 'I5-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市） -->
        <I5TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :applicable-standards="applicableStandards"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（国企） -->
        <I5TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :applicable-standards="applicableStandards"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 未匹配 → OnlyOffice fallback -->
        <GtOnlyOfficeSheet
          v-else
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName || ''"
          :readonly="isReadonly"
          style="height: calc(100vh - 180px)"
        />
      </template>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtI5OtherNoncurrentAssets.vue — I5 其他非流动资产底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "I5-{sheet}-{field}"
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { useI5FormData } from './composables/useI5FormData'
import { useI5CrossSheet } from './composables/useI5CrossSheet'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useI5DualMode } from './composables/useI5DualMode'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

// core
const I5TabIndex = defineAsyncComponent(() => import('./i5/core/I5TabIndex.vue'))
const I5TabAdjudication = defineAsyncComponent(() => import('./i5/core/I5TabAdjudication.vue'))
const I5TabDetail = defineAsyncComponent(() => import('./i5/core/I5TabDetail.vue'))
const I5TabAdjustment = defineAsyncComponent(() => import('./i5/core/I5TabAdjustment.vue'))
const I5TabTargetedCheck = defineAsyncComponent(() => import('./i5/core/I5TabTargetedCheck.vue'))
const I5TabDisclosureListed = defineAsyncComponent(() => import('./i5/core/I5TabDisclosureListed.vue'))
const I5TabDisclosureSoe = defineAsyncComponent(() => import('./i5/core/I5TabDisclosureSoe.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void; (e: 'navigate-sheet', sheetName: string): void }>()

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const runtime = inject(WorkpaperRuntimeContextKey, null)
const applicableStandards = computed<string[]>(() => {
  const fromProp = props.applicableStandards
  if (Array.isArray(fromProp) && fromProp.length) return fromProp.map(String)
  const fromRuntime = (runtime as any)?.applicableStandards?.value
  if (Array.isArray(fromRuntime) && fromRuntime.length) return fromRuntime.map(String)
  const fromHtml = props.htmlData?.applicableStandards
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml.map(String)
  return []
})

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const htmlDataRef = toRef(props, 'htmlData')

const {
  isLoading,
  allResponses,
  tbData,
  selfLoad,
  saveImmediate,
} = useI5FormData(wpIdRef, projectIdRef, { htmlData: htmlDataRef })

const crossSheet = useI5CrossSheet(allResponses)
provide('i5CrossSheet', crossSheet)
provide('i5AllResponses', allResponses)

// ─── 双模式 useI5DualMode (OO 健康检查 + el-segmented) ──────────────────────
const dualMode = useI5DualMode({
  wpId: computed(() => props.wpId),
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/** 从 sheetName 提取编码 (I5/I5A/I5-1~I5-4/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'I5'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 I5A
  if (/I5A/.test(name)) return 'I5A'
  // I5-N 编码（I5-1 到 I5-4）
  const m = name.match(/(I5-\d+)/)
  if (m) return m[1]
  // 底稿目录 I5（无后缀）
  if (/底稿目录/.test(name) || (/\bI5\b/.test(name) && !/I5-/.test(name) && !/I5A/.test(name))) return 'I5'
  return ''
})

// ─── 子组件 save 回调（持久化 checklist_responses） ────────────────────────────
async function handleChildSave(itemId: string, value: any): Promise<void> {
  await saveImmediate(itemId, value)
}

// ─── selfLoad（由 useI5FormData 提供） ────────────────────────────────────────

// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('i5VersionTrailRef', versionTrailRef)
provide('i5OpenVersionHistory', openVersionHistory)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
})
</script>

<style scoped>
.i5-other-noncurrent-assets {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.i5-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
