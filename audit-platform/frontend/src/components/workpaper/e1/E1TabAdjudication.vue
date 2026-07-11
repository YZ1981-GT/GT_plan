<script setup lang="ts">
/**
 * E1TabAdjudication.vue — E1-1 货币资金审定表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.1
 *
 * 渲染：
 * - 固定项目行矩阵 el-table（项目名称 | 期初未审数 | 期初账项调整 | 期初审定数 |
 *   期末未审数 | 期末账项调整 | 期末审定数 | 变动额 | 变动率 | 原因分析）
 * - 变动率>30% → 红色高亮
 * - 合计/试算平衡/差异行 → bold背景
 * - AI按钮生成原因分析
 * - el-skeleton加载占位
 *
 * Requirements: 1.1-1.7, 12.1-12.5
 */
import { ref, inject, computed, toRef, onMounted, type Ref } from 'vue'
import {
  useE1Adjudication,
  type UseE1BaseOptions,
  type AdjRow,
} from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  diffRow,
  isLoading,
  isRateExceeding,
  hasDifference,
  saveVarianceNote,
  aiGenerateNote,
} = useE1Adjudication(options)

// ─── AI Generation ───────────────────────────────────────────────────────────

const aiLoadingKey = ref<string | null>(null)

async function handleAiGenerate(row: AdjRow): Promise<void> {
  if (props.isReadonly) return
  aiLoadingKey.value = row.itemKey
  try {
    const text = await aiGenerateNote(row.itemKey)
    if (text) {
      saveVarianceNote(row.itemKey, text)
    }
  } finally {
    aiLoadingKey.value = null
  }
}

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtRate(rate: number | ''): string {
  if (rate === '' || rate === 0) return '-'
  return (rate * 100).toFixed(2) + '%'
}

function getRowClass({ row }: { row: AdjRow }): string {
  const classes: string[] = []
  if (row.isSubtotal || row.itemKey === 'total' || row.itemKey === 'tb_amount' || row.itemKey === 'diff') {
    classes.push('e1-adj-subtotal-row')
  }
  if (isRateExceeding(row)) {
    classes.push('e1-adj-red-highlight')
  }
  if (row.itemKey === 'diff' && hasDifference()) {
    classes.push('e1-adj-red-highlight')
  }
  return classes.join(' ')
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  // hydration is done inside composable
})
</script>

<template>
  <div class="e1-tab-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总货币资金各项目（库存现金1001、银行存款1002、其他货币资金1012、数字货币）的期初、期末审定过程。</p>
        <p>2. 审定数 = 未审数 + 账项调整；灰色底纹列（期初/期末审定数）为自动计算，不可手工录入。</p>
        <p>3. 未审数取自 E1-2 现金明细、E1-3 银行存款明细、E1-4 数字货币明细（跨sheet自动取数）；账项调整取自 E1-5 调整分录。</p>
        <p>4. 变动率超过30%的项目请在"原因分析"列说明；审定合计应与试算平衡表核对一致，差异≠0时须查明原因。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认货币资金期初、期末余额的存在、完整与准确，评价账项调整的恰当性，并与试算平衡表（科目1001/1002/1012）核对一致。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-4" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="12" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          :row-class-name="getRowClass"
          style="width: 100%"
          max-height="680"
        >
          <!-- 项目名称 -->
          <el-table-column
            prop="itemName"
            label="项目名称"
            fixed="left"
            width="200"
          >
            <template #default="{ row }">
              <span :class="{ 'font-bold': row.isSubtotal || row.isReadonly }">
                {{ row.itemName }}
              </span>
            </template>
          </el-table-column>

          <!-- 期初未审数 -->
          <el-table-column label="期初未审数" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.openingUnaudited) }}
            </template>
          </el-table-column>

          <!-- 期初账项调整 -->
          <el-table-column label="期初账项调整" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.openingAdjustment) }}
            </template>
          </el-table-column>

          <!-- 期初审定数 -->
          <el-table-column label="期初审定数" width="130" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">
                {{ displayPrefs.fmtAmount(row.openingAudited) }}
              </span>
            </template>
          </el-table-column>

          <!-- 期末未审数 -->
          <el-table-column label="期末未审数" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.endingUnaudited) }}
            </template>
          </el-table-column>

          <!-- 期末账项调整 -->
          <el-table-column label="期末账项调整" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.endingAdjustment) }}
            </template>
          </el-table-column>

          <!-- 期末审定数 -->
          <el-table-column label="期末审定数" width="130" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">
                {{ displayPrefs.fmtAmount(row.endingAudited) }}
              </span>
            </template>
          </el-table-column>

          <!-- 变动额 -->
          <el-table-column label="变动额" width="130" align="right">
            <template #default="{ row }">
              {{ displayPrefs.fmtAmount(row.changeAmount) }}
            </template>
          </el-table-column>

          <!-- 变动率 -->
          <el-table-column label="变动率" width="100" align="center">
            <template #default="{ row }">
              <span :class="{ 'red-text': isRateExceeding(row) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>

          <!-- 原因分析 -->
          <el-table-column label="原因分析" min-width="220">
            <template #default="{ row }">
              <div v-if="row.isReadonly && row.itemKey !== 'diff'" class="readonly-cell">
                {{ row.varianceNote || '-' }}
              </div>
              <div v-else class="note-cell">
                <el-input
                  type="textarea"
                  :model-value="row.varianceNote"
                  :disabled="isReadonly"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="填写原因分析"
                  @change="(val: string) => saveVarianceNote(row.itemKey, val)"
                />
                <el-button
                  v-if="!isReadonly"
                  :loading="aiLoadingKey === row.itemKey"
                  size="small"
                  type="primary"
                  text
                  class="ai-btn"
                  @click="handleAiGenerate(row)"
                >
                  🤖
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 核对行 -->
        <div class="tb-check-row">
          <span class="tb-label">审定合计与试算平衡表核对（科目1001/1002/1012）：</span>
          <el-tag v-if="hasDifference()" type="danger" size="small">差异 {{ displayPrefs.fmtAmount(diffRow.endingAudited) }}</el-tag>
          <el-tag v-else type="success" size="small">核对一致</el-tag>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-adjudication {
  padding: 12px 0;
}
.e1-tab-adjudication :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.e1-tab-adjudication :deep(.el-table .cell) {
  font-size: 13px !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-top: 12px;
  font-size: 13px;
}
.tb-label {
  color: #909399;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.red-text {
  color: #f56c6c;
  font-weight: 600;
}
.readonly-cell {
  color: #909399;
}
.note-cell {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.note-cell .el-textarea {
  flex: 1;
}
.ai-btn {
  flex-shrink: 0;
  margin-top: 2px;
}
.font-bold {
  font-weight: 700;
}

:deep(.e1-adj-subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 700;
}
:deep(.e1-adj-red-highlight) {
  background-color: #fef0f0 !important;
}
:deep(.e1-adj-red-highlight td) {
  color: #f56c6c;
}
</style>
