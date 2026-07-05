<template>
  <div class="c-control-test" :class="{ 'is-readonly': readonly }">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- ═══ 目录导航视图 ═══ -->
      <div v-if="currentView === 'directory'" class="cct-directory">
        <!-- 顶部项目信息 + 循环上下文 -->
        <div class="cct-header">
          <div class="cct-header-title">
            <span class="cct-cycle-badge">{{ wpCode }}</span>
            <span class="cct-cycle-name">{{ cycleName }}控制测试</span>
          </div>
          <div class="cct-project-info">
            <span class="cct-info-item">客户：{{ clientName || '—' }}</span>
            <span class="cct-info-item">会计期间：{{ year }}年度</span>
          </div>
          <!-- B23/B50 快捷跳转 Chips -->
          <div class="cct-linkage-chips">
            <span class="cct-linkage-label">关联底稿：</span>
            <GtIndexChip value="B23" :context="b23Context" />
            <GtIndexChip value="B50" :context="b50Context" />
          </div>
        </div>

        <!-- 蓝色渐变引导区 -->
        <div class="cct-guidance-area">
          <div class="cct-guidance-header">
            <el-icon><InfoFilled /></el-icon>
            <span>操作流程引导</span>
          </div>
          <div class="cct-guidance-steps">
            <div class="step-item">
              <span class="step-num">①</span>
              <span class="step-text">目录导航</span>
            </div>
            <div class="step-item">
              <span class="step-num">②</span>
              <span class="step-text">控制清单</span>
            </div>
            <div class="step-item">
              <span class="step-num">③</span>
              <span class="step-text">逐控制抽样</span>
            </div>
            <div class="step-item">
              <span class="step-num">④</span>
              <span class="step-text">偏差评价</span>
            </div>
          </div>
        </div>

        <!-- 目录列表 -->
        <div class="cct-nav-list">
          <div class="cct-nav-section-title">底稿目录</div>

          <!-- 汇总表 -->
          <div class="cct-nav-item" @click="navigateTo('summary')">
            <span class="cct-nav-icon">📋</span>
            <span class="cct-nav-label">{{ wpCode }} 控制测试汇总表</span>
            <el-icon class="cct-nav-arrow"><ArrowRight /></el-icon>
          </div>

          <!-- 各控制测试子页 -->
          <template v-for="ctrl in controlPointList" :key="ctrl.id">
            <div class="cct-nav-item" @click="navigateTo(`ctrl-${ctrl.index}`)">
              <span class="cct-nav-icon">🧪</span>
              <span class="cct-nav-label">{{ wpCode }}-1-{{ ctrl.index }} {{ ctrl.name || '控制测试' }}</span>
              <el-icon class="cct-nav-arrow"><ArrowRight /></el-icon>
            </div>
          </template>

          <!-- 偏差评价 -->
          <div class="cct-nav-item" @click="navigateTo('deviation')">
            <span class="cct-nav-icon">⚖️</span>
            <span class="cct-nav-label">{{ wpCode }}-2 评价控制偏差</span>
            <el-icon class="cct-nav-arrow"><ArrowRight /></el-icon>
          </div>
        </div>
      </div>

      <!-- ═══ 汇总表视图 ═══ -->
      <CControlTestSummaryTable
        v-else-if="currentView === 'summary'"
        :wp-code="wpCode"
        :rows="state.summaryRows"
        :readonly="isReadonly"
        :update-summary-text="updateSummaryText"
        :update-summary-enum="updateSummaryEnum"
        :update-summary-sample-size="updateSummarySampleSize"
        :add-control-point="addControlPoint"
        :remove-control-point="removeControlPoint"
        @navigate="navigateTo"
      />

      <!-- ═══ 控制测试子页视图 (Cx-1-X) ═══ -->
      <CControlTestSubPage
        v-else-if="currentView.startsWith('ctrl-')"
        :wp-id="wpId"
        :project-id="projectId"
        :wp-code="wpCode"
        :page-index="currentCtrlIndex - 1"
        :page="currentControlPage"
        :control-name="currentControlName"
        :readonly="isReadonly"
        :update-ctrl-page-text="updateCtrlPageText"
        :update-ctrl-page-enum="updateCtrlPageEnum"
        :update-ctrl-page-sample-size="updateCtrlPageSampleSize"
        :add-sample="addSample"
        :remove-sample="removeSample"
        :update-sample-description="updateSampleDescription"
        :update-sample-result="updateSampleResult"
        :update-summary-deviation="handleDeviationBackfill"
        @navigate="navigateTo"
      />

      <!-- ═══ 偏差评价视图 (Cx-2) ═══ -->
      <CControlTestDecisionTree
        v-else-if="currentView.startsWith('deviation')"
        :wp-code="wpCode"
        :dev-index="currentDevIndex"
        :dev-state="currentDeviationState"
        :control-name="currentDevControlName"
        :control-names="allControlNames"
        :control-count="state.summaryRows.length"
        :readonly="isReadonly"
        :update-deviation-step="updateDeviationStep"
        :writeback-defect="writebackDefect"
        :build-defect-summary="buildDefectSummary"
        @navigate="navigateTo"
        @change-dev-index="handleChangeDevIndex"
      />

      <!-- ═══ 编制提示（底部折叠） ═══ -->
      <details class="cct-compilation-tips">
        <summary>编制提示</summary>
        <div class="cct-tips-content">
          <p>1. 控制测试旨在验证内部控制在审计期间运行的有效性。</p>
          <p>2. 汇总表需按循环列示所有被测控制点，确保覆盖认定层次重大风险所涉及的关键控制。</p>
          <p>3. 样本规模参照致同 2025 修订版样本规模区间表确定（频率×次数→最小样本量），可根据职业判断调整。</p>
          <p>4. 抽样结果中标记为「偏差」的项目，需在 Cx-2 偏差评价决策树中进一步分析其性质并推导结论。</p>
          <p>5. 如决策树推导至「控制缺陷」，应联动 A14 内控缺陷评价底稿进行缺陷等级评价。</p>
          <p>6. 循环整体结论变更时通过 EventBus 通知 B50 更新控制风险评估。</p>
        </div>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { ArrowRight, InfoFilled } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useCControlTestData } from '@/composables/useCControlTestData'
import { createEmptyState, type DecisionTreeState } from '@/composables/useDeviationDecisionTree'
import { CYCLE_CONFIG } from './composables/useCControlTest'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import CControlTestSummaryTable from './cControlTest/CControlTestSummaryTable.vue'
import CControlTestSubPage from './cControlTest/CControlTestSubPage.vue'
import CControlTestDecisionTree from './cControlTest/CControlTestDecisionTree.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
  sheetName?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Derived ─────────────────────────────────────────────────────────────────

const cycleNum = computed(() => parseInt(props.wpCode.replace(/^C/i, ''), 10) || 2)
const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const wpCodeRef = toRef(props, 'wpCode')
const isReadonly = computed(() => props.readonly ?? false)

const cycleName = computed(() => {
  const config = CYCLE_CONFIG[cycleNum.value]
  return config?.name || `循环${cycleNum.value}`
})

/** B23 流程编号（用于 GtIndexChip context） */
const b23Context = computed(() => {
  const config = CYCLE_CONFIG[cycleNum.value]
  if (!config) return ''
  return `${config.name} — 流程${config.b23ProcessNum}`
})

/** B50 上下文（用于 GtIndexChip context） */
const b50Context = computed(() => {
  const config = CYCLE_CONFIG[cycleNum.value]
  if (!config) return ''
  return `${config.name} — 控制风险评估`
})

// ─── Project Info ────────────────────────────────────────────────────────────

const projectStore = useProjectStore()
const clientName = computed(() => projectStore.clientName || '')

// ─── Data Composable ─────────────────────────────────────────────────────────

const { state, loading, selfLoad, flushPendingSaves,
  updateSummaryText, updateSummaryEnum, updateSummarySampleSize,
  addControlPoint, removeControlPoint,
  updateCtrlPageText, updateCtrlPageEnum, updateCtrlPageSampleSize,
  addSample, removeSample, updateSampleDescription, updateSampleResult,
  updateDeviationStep, writebackDefect, buildDefectSummary } =
  useCControlTestData(wpIdRef, projectIdRef, wpCodeRef, isReadonly)

// ─── View Dispatching ────────────────────────────────────────────────────────

/** 当前视图：directory / summary / ctrl-{m} / deviation / deviation-{m} */
const currentView = ref<string>('directory')

/** 从 currentView 提取当前控制点索引 */
const currentCtrlIndex = computed(() => {
  const m = currentView.value.match(/^ctrl-(\d+)$/)
  return m ? parseInt(m[1], 10) : 0
})

/** 导航到指定视图 */
function navigateTo(view: string) {
  currentView.value = view
}

// ─── Control Point List (from saved data) ────────────────────────────────────

interface NavControlPoint {
  id: string
  index: number
  name: string
}

/** 从 state.summaryRows 中获取控制点列表用于目录导航 */
const controlPointList = computed<NavControlPoint[]>(() => {
  return state.value.summaryRows.map((row, i) => ({
    id: `ctrl-${i + 1}`,
    index: i + 1,
    name: row.controlName || '',
  }))
})

// ─── Control Page & Deviation helpers for sub-components ─────────────────────

/** 当前控制测试子页数据 */
const currentControlPage = computed(() => {
  const idx = currentCtrlIndex.value - 1
  if (idx >= 0 && idx < state.value.controlPages.length) {
    return state.value.controlPages[idx]
  }
  return { attribute: '', frequency: '', relatedRisk: '', testMethod: '',
    testProcedure: '', populationDef: '', populationSource: '',
    sampleSize: null, samplingMethod: '', samplingProcess: '',
    deviationDef: '', samples: [] }
})

/** 当前控制点名称 */
const currentControlName = computed(() => {
  const idx = currentCtrlIndex.value - 1
  if (idx >= 0 && idx < state.value.summaryRows.length) {
    return state.value.summaryRows[idx].controlName || ''
  }
  return ''
})

/** 偏差回填汇总表 */
function handleDeviationBackfill(pageIndex: number, hasDeviation: '是' | '否') {
  if (isReadonly.value) return
  if (pageIndex >= 0 && pageIndex < state.value.summaryRows.length) {
    updateSummaryEnum(pageIndex, 'hasDeviation', hasDeviation)
  }
}

/** 当前偏差评价的控制点索引（deviation 或 deviation-{m}） */
const currentDevIndex = computed(() => {
  const m = currentView.value.match(/^deviation-(\d+)$/)
  if (m) return parseInt(m[1], 10) - 1
  return 0
})

/** 当前偏差评价状态 */
const currentDeviationState = computed<DecisionTreeState>(() => {
  const idx = currentDevIndex.value
  if (idx >= 0 && idx < state.value.deviationStates.length) {
    return state.value.deviationStates[idx]
  }
  return createEmptyState()
})

/** 当前偏差评价控制点名称 */
const currentDevControlName = computed(() => {
  const idx = currentDevIndex.value
  if (idx >= 0 && idx < state.value.summaryRows.length) {
    return state.value.summaryRows[idx].controlName || ''
  }
  return ''
})

/** 全部控制点名称列表 */
const allControlNames = computed(() => {
  return state.value.summaryRows.map(r => r.controlName || '')
})

/** 切换偏差评价的控制点 */
function handleChangeDevIndex(index: number) {
  currentView.value = `deviation-${index + 1}`
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await selfLoad()
})

onBeforeUnmount(() => {
  flushPendingSaves()
})
</script>

<style scoped>
.c-control-test {
  padding: 16px;
  max-width: 1200px;
  margin: 0 auto;
  font-size: 13px;
}

.c-control-test.is-readonly {
  pointer-events: auto;
}

.loading-container {
  padding: 24px;
}

/* ─── Header ─── */
.cct-header {
  margin-bottom: 16px;
}

.cct-header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.cct-cycle-badge {
  background: #e6f7ff;
  color: #1890ff;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
}

.cct-cycle-name {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.cct-project-info {
  display: flex;
  gap: 24px;
  color: #6b7280;
  font-size: 13px;
}

.cct-info-item {
  display: inline-flex;
  align-items: center;
}

/* ─── Linkage Chips (B23/B50) ─── */
.cct-linkage-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.cct-linkage-label {
  font-size: 12px;
  color: #9ca3af;
}

/* ─── Guidance Area ─── */
.cct-guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 20px;
}

.cct-guidance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: 13px;
}

.cct-guidance-steps {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #374151;
}

.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #1a73e8;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.step-text {
  font-size: 13px;
}

/* ─── Navigation List ─── */
.cct-nav-list {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.cct-nav-section-title {
  padding: 12px 20px;
  font-weight: 600;
  font-size: 14px;
  color: #374151;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.cct-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  cursor: pointer;
  border-bottom: 1px solid #f3f4f6;
  transition: background 0.15s;
}

.cct-nav-item:last-child {
  border-bottom: none;
}

.cct-nav-item:hover {
  background: #f0f7ff;
}

.cct-nav-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.cct-nav-label {
  flex: 1;
  font-size: 13px;
  color: #1f2937;
}

.cct-nav-arrow {
  color: #9ca3af;
  flex-shrink: 0;
}

/* ─── View Header (sub-pages) ─── */
.cct-view-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.cct-view-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

/* ─── Readonly 铁律：全局禁止编辑 ─── */
.c-control-test.is-readonly :deep(.el-input__inner),
.c-control-test.is-readonly :deep(.el-textarea__inner),
.c-control-test.is-readonly :deep(.el-select .el-input__inner),
.c-control-test.is-readonly :deep(.el-input-number) {
  cursor: not-allowed;
}

/* readonly 隐藏增删操作按钮（保留导航按钮） */
.c-control-test.is-readonly :deep(.cct-view-actions) {
  display: none;
}

/* ─── 编制提示 <details> 折叠 ─── */
.cct-compilation-tips {
  margin-top: 24px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}

.cct-compilation-tips summary {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  background: #f9fafb;
  cursor: pointer;
  user-select: none;
}

.cct-compilation-tips summary:hover {
  background: #f3f4f6;
}

.cct-compilation-tips[open] summary {
  border-bottom: 1px solid #e5e7eb;
}

.cct-tips-content {
  padding: 12px 16px;
  font-size: 12px;
  color: #4b5563;
  line-height: 1.8;
}

.cct-tips-content p {
  margin: 0 0 4px;
}

/* ─── Print ─── */
@media print {
  .cct-guidance-area {
    display: none;
  }
  .cct-compilation-tips {
    display: none;
  }
}
</style>
