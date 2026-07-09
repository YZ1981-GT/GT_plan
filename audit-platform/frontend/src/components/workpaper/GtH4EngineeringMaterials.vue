<template>
  <div class="h4-engineering-materials">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部工具栏（双模式切换） -->
      <div class="h4-header-toolbar">
        <el-segmented
          v-model="currentMode"
          :options="modeOptions"
          size="small"
          :disabled="!isOoAvailable && currentMode === 'html'"
          @change="onModeChange"
        />
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else>
        <!-- 底稿目录 -->
        <H4TabIndex
          v-if="currentSheet === 'H4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4A 程序表（selfLoad） -->
        <GtAProgramConsole
          v-else-if="currentSheet === 'H4A'"
          sheet-code="H4A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H4-1 审定表 -->
        <H4TabAdjudication
          v-else-if="currentSheet === 'H4-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（上市公司） -->
        <H4TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（国有企业） -->
        <H4TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-2 明细表 -->
        <H4TabDetail
          v-else-if="currentSheet === 'H4-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-3 调整分录汇总 -->
        <H4TabAdjustment
          v-else-if="currentSheet === 'H4-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-4 增加检查表 -->
        <H4TabAdditionCheck
          v-else-if="currentSheet === 'H4-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-5 减少检查表 -->
        <H4TabDisposalCheck
          v-else-if="currentSheet === 'H4-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H4-6 盘点检查表 -->
        <H4TabStocktakeCheck
          v-else-if="currentSheet === 'H4-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H4-7 减值测算表（OO为主） -->
        <H4TabImpairment
          v-else-if="currentSheet === 'H4-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :sheet-name="props.sheetName || ''"
        />

        <!-- H4-8 可收回金额测试表（OO为主） -->
        <H4TabRecoverable
          v-else-if="currentSheet === 'H4-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :sheet-name="props.sheetName || ''"
        />

        <!-- H4-9 关联交易检查表 -->
        <H4TabRelatedParty
          v-else-if="currentSheet === 'H4-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
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
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH4EngineeringMaterials.vue — H4 工程物资底稿主入口
 *
 * sheetName prop v-if 分发到全部12个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * useVersionTrail: autoSnapshot on save。
 * 双模式: HTML↔OnlyOffice切换+OO健康检查。
 *
 * Spec: .kiro/specs/h4-engineering-materials/ Task 1.1
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import useVersionTrail from './composables/useVersionTrail'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtAProgramConsole = defineAsyncComponent(() => import('./GtCycleAProgramRouter.vue'))

// core
const H4TabIndex = defineAsyncComponent(() => import('./h4/core/H4TabIndex.vue'))
const H4TabAdjudication = defineAsyncComponent(() => import('./h4/core/H4TabAdjudication.vue'))
const H4TabDetail = defineAsyncComponent(() => import('./h4/core/H4TabDetail.vue'))
const H4TabAdjustment = defineAsyncComponent(() => import('./h4/core/H4TabAdjustment.vue'))
const H4TabDisclosureListed = defineAsyncComponent(() => import('./h4/core/H4TabDisclosureListed.vue'))
const H4TabDisclosureSoe = defineAsyncComponent(() => import('./h4/core/H4TabDisclosureSoe.vue'))

// inspection
const H4TabAdditionCheck = defineAsyncComponent(() => import('./h4/inspection/H4TabAdditionCheck.vue'))
const H4TabDisposalCheck = defineAsyncComponent(() => import('./h4/inspection/H4TabDisposalCheck.vue'))
const H4TabStocktakeCheck = defineAsyncComponent(() => import('./h4/inspection/H4TabStocktakeCheck.vue'))
const H4TabRelatedParty = defineAsyncComponent(() => import('./h4/inspection/H4TabRelatedParty.vue'))

// impairment
const H4TabImpairment = defineAsyncComponent(() => import('./h4/impairment/H4TabImpairment.vue'))
const H4TabRecoverable = defineAsyncComponent(() => import('./h4/impairment/H4TabRecoverable.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void; (e: 'navigate-sheet', sheetName: string): void }>()

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())

// ─── 双模式切换（简化版，Phase 3 替换为 useH4DualMode） ──────────────────────
const currentMode = ref<'html' | 'onlyoffice'>('html')
const isOoAvailable = ref(true)
const modeOptions = [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice' },
]

function onModeChange(_val: string | number): void {
  // Phase 3 will integrate useH4DualMode with OO health check
}

/** 从 sheetName 提取编码 (H4/H4A/H4-1~H4-9/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表
  if (/H4A/.test(name)) return 'H4A'
  // H4-N 编码（H4-1 到 H4-9）
  const m = name.match(/(H4-\d+)/)
  if (m) return m[1]
  // 底稿目录 H4（无后缀）
  if (/\bH4\b/.test(name) && !/H4-/.test(name) && !/H4A/.test(name)) return 'H4'
  return ''
})

// ─── selfLoad ────────────────────────────────────────────────────────────────
async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      if (props.htmlData.allResponses) {
        const map = new Map<string, any>()
        for (const [k, v] of Object.entries(props.htmlData.allResponses)) {
          map.set(k, v)
        }
        allResponses.value = map
      }
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h4-engineering-materials' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          if (sheet.html_data?.allResponses) {
            for (const [k, v] of Object.entries(sheet.html_data.allResponses)) {
              map.set(k, v)
            }
          }
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtH4EngineeringMaterials] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[H4] openReviewDialog:', sectionId, sectionLabel)
}
provide('openReviewDialog', openReviewDialog)
provide('allResponses', allResponses)

// ─── 版本追踪 useVersionTrail (autoSnapshot on save) ─────────────────────────
const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})
provide('versionTrail', versionTrail)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  // Subscribe to TB updates: refresh H4-1 取数 when trial_balance changes externally
  window.addEventListener('tb:updated', _handleTbUpdated)
  window.addEventListener('substantive:adjudicated', _handleTbUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('tb:updated', _handleTbUpdated)
  window.removeEventListener('substantive:adjudicated', _handleTbUpdated)
})

/**
 * TB更新事件处理：当试算表外部更新时（如其他底稿回写），刷新H4数据。
 * 过滤：仅科目1605相关的更新触发刷新（避免无关科目刷新噪音）。
 */
function _handleTbUpdated(e: Event) {
  const detail = (e as CustomEvent).detail
  // 仅在科目1605相关或无明确科目信息时刷新
  if (!detail || !detail.accountCode || detail.accountCode === '1605' || detail.wpCode === 'H4') {
    void selfLoad()
  }
}
</script>

<style scoped>
.h4-engineering-materials {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h4-header-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}
</style>
