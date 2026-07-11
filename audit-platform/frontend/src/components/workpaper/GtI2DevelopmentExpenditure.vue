<template>
  <div class="i2-development-expenditure">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="showHtmlToolbar" class="i2-header-toolbar">
        <el-segmented
          v-model="currentMode"
          :options="modeOptions"
          size="small"
          @change="onModeChange"
        />

        <!-- 6.5: GtIndexChip 跨底稿跳转 I2→I6/I1/A13 -->
        <div class="cross-ref-chips">
          <GtIndexChip value="I6" @click="emit('navigate-sheet', 'I6')" />
          <GtIndexChip value="I1" @click="emit('navigate-sheet', 'I1')" />
          <GtIndexChip value="A13" @click="emit('navigate-sheet', 'A13')" />
        </div>

        <!-- 6.2: I6↔I2 联动状态指示 -->
        <span
          v-if="!i6LinkageStatus.isBalanced && i6LinkageStatus.total > 0"
          class="linkage-warn"
        >
          ⚠️ 费用化+资本化≠研发总额
        </span>
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
        <!-- 底稿目录 I2 -->
        <I2TabIndex
          v-if="currentSheet === 'I2'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I2A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'I2A'"
          sheet-code="I2A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- I2-1 审定表 -->
        <I2TabAdjudication
          v-else-if="currentSheet === 'I2-1'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-2 明细表 -->
        <I2TabDetail
          v-else-if="currentSheet === 'I2-2'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-3 调整分录 -->
        <I2TabAdjustment
          v-else-if="currentSheet === 'I2-3'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-4 会计政策检查 -->
        <I2TabPolicyCheck
          v-else-if="currentSheet === 'I2-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- I2-5 实质性分析 -->
        <I2TabAnalysis
          v-else-if="currentSheet === 'I2-5'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-6 资本化时点判断（CAS6五条件核心） -->
        <I2TabCapitalization
          v-else-if="currentSheet === 'I2-6'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-7 研发项目构成明细表 -->
        <I2TabProjectDetail
          v-else-if="currentSheet === 'I2-7'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-8 研发材料投入检查 -->
        <I2TabMaterialCheck
          v-else-if="currentSheet === 'I2-8'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-9 研发人员认定检查 -->
        <I2TabStaffCheck
          v-else-if="currentSheet === 'I2-9'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-10 研发人员工时检查 -->
        <I2TabWorkHourCheck
          v-else-if="currentSheet === 'I2-10'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-11 委外研发检查 -->
        <I2TabOutsourceCheck
          v-else-if="currentSheet === 'I2-11'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-12 针对性检查 -->
        <I2TabTargetedCheck
          v-else-if="currentSheet === 'I2-12'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-13 截止性测试（账到单据） -->
        <I2TabCutoffForward
          v-else-if="currentSheet === 'I2-13'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-14 截止性测试（单据到账） -->
        <I2TabCutoffBackward
          v-else-if="currentSheet === 'I2-14'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-15 减值准备测试 -->
        <I2TabImpairment
          v-else-if="currentSheet === 'I2-15'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- I2-16 可收回金额测试 -->
        <I2TabRecoverable
          v-else-if="currentSheet === 'I2-16'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市公司） -->
        <I2TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <I2TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :sheet-name="props.sheetName || ''"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :save-response="saveResponse"
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
 * GtI2DevelopmentExpenditure.vue — I2 开发支出底稿主入口
 *
 * sheetName prop v-if 分发到全部18个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * 双模式: el-segmented(HTML/OnlyOffice) + useI2DualMode
 *
 * 集成联动（Phase 6）：
 * - 6.1 writebackTrialBalance(1717) 在 I2TabAdjudication 保存后通过 emit 触发
 * - 6.2 useI2CrossSheet: subscribe research:expense-updated / publish development:capitalized-updated
 * - 6.3 useI2CrossSheet: publish development:capitalized-to-intangible (watch i1TransferAmount)
 * - 6.5 GtIndexChip: I2→I6/I1/A13
 * - 6.6 useI2Cutoff.loadFromAutoSampling integrated in cutoff child components
 * - 6.7 useI2Disclosure: subscribe substantive:adjudicated / publish disclosure:note-text-updated
 *       useI2DualMode: el-segmented HTML/OO switching with OO health check
 *
 * Spec: .kiro/specs/i2-development-expenditure/ Task 1.1, Phase 6
 * Requirements: 1.1-1.10, 9.1-9.5, 11.1-11.3, 12.1-12.3
 */
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import useVersionTrail from './composables/useVersionTrail'
import { useI2CrossSheet } from './composables/useI2CrossSheet'
import { useI2DualMode } from './composables/useI2DualMode'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

// core
const I2TabIndex = defineAsyncComponent(() => import('./i2/core/I2TabIndex.vue'))
const I2TabAdjudication = defineAsyncComponent(() => import('./i2/core/I2TabAdjudication.vue'))
const I2TabDetail = defineAsyncComponent(() => import('./i2/core/I2TabDetail.vue'))
const I2TabAdjustment = defineAsyncComponent(() => import('./i2/core/I2TabAdjustment.vue'))
const I2TabAnalysis = defineAsyncComponent(() => import('./i2/core/I2TabAnalysis.vue'))
const I2TabDisclosureListed = defineAsyncComponent(() => import('./i2/core/I2TabDisclosureListed.vue'))
const I2TabDisclosureSoe = defineAsyncComponent(() => import('./i2/core/I2TabDisclosureSoe.vue'))

// inspection
const I2TabPolicyCheck = defineAsyncComponent(() => import('./i2/inspection/I2TabPolicyCheck.vue'))
const I2TabCapitalization = defineAsyncComponent(() => import('./i2/inspection/I2TabCapitalization.vue'))
const I2TabProjectDetail = defineAsyncComponent(() => import('./i2/inspection/I2TabProjectDetail.vue'))
const I2TabMaterialCheck = defineAsyncComponent(() => import('./i2/inspection/I2TabMaterialCheck.vue'))
const I2TabStaffCheck = defineAsyncComponent(() => import('./i2/inspection/I2TabStaffCheck.vue'))
const I2TabWorkHourCheck = defineAsyncComponent(() => import('./i2/inspection/I2TabWorkHourCheck.vue'))
const I2TabOutsourceCheck = defineAsyncComponent(() => import('./i2/inspection/I2TabOutsourceCheck.vue'))
const I2TabTargetedCheck = defineAsyncComponent(() => import('./i2/inspection/I2TabTargetedCheck.vue'))

// cutoff
const I2TabCutoffForward = defineAsyncComponent(() => import('./i2/cutoff/I2TabCutoffForward.vue'))
const I2TabCutoffBackward = defineAsyncComponent(() => import('./i2/cutoff/I2TabCutoffBackward.vue'))

// impairment
const I2TabImpairment = defineAsyncComponent(() => import('./i2/impairment/I2TabImpairment.vue'))
const I2TabRecoverable = defineAsyncComponent(() => import('./i2/impairment/I2TabRecoverable.vue'))

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

/** 从 sheetName 提取编码 (I2/I2A/I2-1~I2-16/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市|I2-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|I2-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  // 程序表 I2A
  if (/I2A/.test(name)) return 'I2A'
  // I2-N 编码（I2-1 到 I2-16）
  const m = name.match(/(I2-\d+)/)
  if (m) return m[1]
  // 底稿目录 I2（无后缀）
  if (/\bI2\b/.test(name) && !/I2-/.test(name) && !/I2A/.test(name)) return 'I2'
  return ''
})

const showHtmlToolbar = computed(() => {
  return currentSheet.value !== ''
})

// ─── 6.2 / 6.3: useI2CrossSheet（I6↔I2 双向 + I2→I1 转入联动）──────────────
const { detailTotals, i6LinkageStatus, i1TransferAmount } = useI2CrossSheet(allResponses)
provide('i2CrossSheet', { detailTotals, i6LinkageStatus, i1TransferAmount })

// ─── 6.7: useI2DualMode（el-segmented HTML/OO 双模式切换）────────────────────
const dualMode = useI2DualMode({
  wpId: toRef(props, 'wpId') as any,
  sheetName: toRef(props, 'sheetName') as any,
})
const currentMode = dualMode.mode
const modeOptions = dualMode.modeOptions

// ─── 双模式切换 ──────────────────────────────────────────────────────────────
function onModeChange(mode: string | number) {
  dualMode.onModeChange(mode)
}

// ─── 子组件 saveResponse 回调（持久化 checklist_responses） ─────────────────
// I2 子组件契约: props.saveResponse(sheetCode, { [itemId]: value }) => Promise<void>
// 父级须提供此函数，否则子组件保存时调用 undefined 崩溃（Bug C）。
async function saveResponse(_sheetCode: string, data: Record<string, any>): Promise<void> {
  if (!props.wpId) return
  const items = Object.entries(data).map(([item_id, value]) => ({
    item_id,
    conclusion: null,
    remark: value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null,
  }))
  // 乐观更新本地 Map
  for (const it of items) allResponses.value.set(it.item_id, it)
  try {
    await http.put(`/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
  } catch {
    // 静默失败，数据保留在本地
  }
}

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
        params: { force_component_type: 'i2-development-expenditure' },
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
    console.warn('[GtI2DevelopmentExpenditure] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[I2] openReviewDialog:', sectionId, sectionLabel)
}
provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 useVersionTrail (autoSnapshot on save) ─────────────────────────
const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})
provide('versionTrail', versionTrail)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
})
</script>

<style scoped>
.i2-development-expenditure {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.i2-header-toolbar {
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  gap: 12px;
}

.cross-ref-chips {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.linkage-warn {
  font-size: 12px;
  color: var(--el-color-danger);
  font-weight: 500;
}
</style>
