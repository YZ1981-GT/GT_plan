<script setup lang="ts">
/**
 * D4TabAdjudication — D4-1 审定表
 *
 * 双区块el-table（主营+其他）+ 合计行不可编辑 + 跨sheet浅蓝背景
 * 变动率>30%红色 + 差异≠0红色 + 交叉验证el-alert
 * 审计说明/结论textarea + AI按钮(disabled) + 💬复核 + GtIndexChip→D4-6/D4-7/D4-2
 *
 * Requirements: 2.1-2.10, 19.1, 21.1
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD4Adjudication, type AdjudicationRow, type AdjudicationSection } from '../../composables/useD4Adjudication'
import { isChangeRateExceeding } from '../../composables/useD4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// ─── 复核对话注入 ─────────────────────────────────────────────────────
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return rate === '' ? '-' : 'N/A'
  return (rate * 100).toFixed(1) + '%'
}

// ─── Composable ───────────────────────────────────────────────────────
const {
  sections,
  grandTotalRow,
  trialBalanceRow,
  differenceRow,
  mainCrossValidation,
  otherCrossValidation,
  auditNote,
  auditConclusion,
  updateCell,
  addProductRow,
  removeProductRow,
  publishAdjudicated,
} = useD4Adjudication({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 变动率计算（基于审定数） ───────────────────────────────────────────
function getChangeRate(row: AdjudicationRow): number | '' | 'N/A' {
  const prior = row.priorAudited
  const current = row.currentAudited
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}

// ─── 样式判断 ─────────────────────────────────────────────────────────
function getCellClass(row: AdjudicationRow, field: string): string {
  const classes: string[] = []
  if (row.isFromCrossSheet) classes.push('cross-sheet-cell')
  if (field === 'changeRate') {
    const rate = getChangeRate(row)
    if (isChangeRateExceeding(rate, 0.3)) classes.push('rate-warning')
  }
  return classes.join(' ')
}

function getRowClassName({ row }: { row: AdjudicationRow }): string {
  if (row.rowKey.includes('subtotal') || row.rowKey === 'grand-total') return 'subtotal-row-bg'
  return ''
}

// ─── 差异状态 ─────────────────────────────────────────────────────────
const hasDifference = computed(() => Math.abs(differenceRow.value) > 0.005)

// ─── 合并展示数据（按区块拼接） ────────────────────────────────────────
const tableData = computed(() => {
  const result: (AdjudicationRow & { _sectionLabel?: string })[] = []
  for (const section of sections.value) {
    // 添加明细行
    for (const row of section.rows) {
      result.push(row)
    }
    // 添加小计行
    result.push(section.subtotalRow)
  }
  // 添加营业收入合计行
  result.push(grandTotalRow.value)
  return result
})
</script>

<template>
  <div class="d4-tab-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表反映被审计单位营业收入（科目6001+6051）审定过程。</p>
        <p>2. "未审数"列取自试算平衡表，"AJE/RJE"列取自D4-4调整分录。</p>
        <p>3. 浅蓝背景单元格为跨sheet自动取数（D4-2/D4-3），不可手工编辑。</p>
        <p>4. 变动率超过30%的项目请在审计说明中解释原因。</p>
        <p>5. 审定完成后请点击"确认审定"回写试算表。</p>
      </div>
    </details>

    <!-- 交叉验证警告 -->
    <el-alert
      v-if="mainCrossValidation"
      type="warning"
      :closable="false"
      class="cross-alert"
    >
      {{ mainCrossValidation }}
    </el-alert>
    <el-alert
      v-if="otherCrossValidation"
      type="warning"
      :closable="false"
      class="cross-alert"
    >
      {{ otherCrossValidation }}
    </el-alert>

    <!-- 差异警告 -->
    <el-alert
      v-if="hasDifference"
      type="error"
      :closable="false"
      class="cross-alert"
    >
      审定合计与试算平衡表差异：{{ fmtAmount(differenceRow) }}元
    </el-alert>

    <!-- 区块标题 + 操作 -->
    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" :disabled="isReadonly" @click="addProductRow">+ 添加产品行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="gt-index-chip" title="跳转D4-2主营明细">D4-2</span>
        <span class="gt-index-chip" title="跳转D4-6指标分析">D4-6</span>
        <span class="gt-index-chip" title="跳转D4-7月度毛利">D4-7</span>
      </div>
    </div>

    <!-- 一、主营业务收入 -->
    <template v-for="(section, sIdx) in sections" :key="section.sectionKey">
      <h4 class="section-title">{{ section.sectionLabel }}</h4>
      <el-table
        :data="[...section.rows, section.subtotalRow]"
        border
        size="small"
        :row-class-name="getRowClassName"
        style="width: 100%; margin-bottom: 16px"
        @cell-contextmenu="(row: any, col: any, e: MouseEvent) => {
          if (!openReviewDialog) return
          e.preventDefault()
          openReviewDialog(`D4-1-adj-${section.sectionKey}-${row.rowKey}`)
        }"
      >
        <el-table-column prop="label" label="项目" width="160" fixed>
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable && !row.isFixed && !isReadonly"
              :model-value="row.label || ''"
              size="small"
              placeholder="产品名称"
              @change="(val: string) => updateCell(row.rowKey, 'label', val)"
            />
            <span v-else :class="{ 'font-bold': row.rowKey.includes('subtotal') }">{{ row.label || '(未命名)' }}</span>
          </template>
        </el-table-column>

        <!-- 本期 -->
        <el-table-column label="本期" align="center">
          <el-table-column label="未审数" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentUnadjusted"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'currentUnadjusted', val ?? 0)"
              />
              <span v-else :class="getCellClass(row, 'currentUnadjusted')">{{ fmtAmount(row.currentUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="AJE" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'currentAje', val ?? 0)"
              />
              <span v-else :class="getCellClass(row, 'currentAje')">{{ fmtAmount(row.currentAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'currentRje', val ?? 0)"
              />
              <span v-else :class="getCellClass(row, 'currentRje')">{{ fmtAmount(row.currentRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="130" align="right">
            <template #default="{ row }">
              <span class="audited-cell">{{ fmtAmount(row.currentAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 上期 -->
        <el-table-column label="上期" align="center">
          <el-table-column label="未审数" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly"
                :model-value="row.priorUnadjusted"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'priorUnadjusted', val ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="AJE" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly"
                :model-value="row.priorAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'priorAje', val ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly"
                :model-value="row.priorRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'priorRje', val ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="120" align="right">
            <template #default="{ row }">
              <span class="audited-cell">{{ fmtAmount(row.priorAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 变动 -->
        <el-table-column label="变动率" width="100" align="right">
          <template #default="{ row }">
            <span :class="getCellClass(row, 'changeRate')">{{ fmtRate(getChangeRate(row)) }}</span>
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column label="" width="60" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.isEditable && !row.isFixed && !isReadonly"
              type="danger"
              size="small"
              link
              @click="removeProductRow(row.rowKey)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 营业收入合计 -->
    <el-table
      :data="[grandTotalRow]"
      border
      size="small"
      :show-header="false"
      style="width: 100%; margin-bottom: 16px"
    >
      <el-table-column width="160" fixed>
        <template #default>
          <span class="font-bold">营业收入合计</span>
        </template>
      </el-table-column>
      <el-table-column width="120" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.currentUnadjusted) }}</span></template>
      </el-table-column>
      <el-table-column width="110" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.currentAje) }}</span></template>
      </el-table-column>
      <el-table-column width="110" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.currentRje) }}</span></template>
      </el-table-column>
      <el-table-column width="130" align="right">
        <template #default="{ row }"><span class="audited-cell">{{ fmtAmount(row.currentAudited) }}</span></template>
      </el-table-column>
      <el-table-column width="120" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.priorUnadjusted) }}</span></template>
      </el-table-column>
      <el-table-column width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.priorAje) }}</span></template>
      </el-table-column>
      <el-table-column width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.priorRje) }}</span></template>
      </el-table-column>
      <el-table-column width="120" align="right">
        <template #default="{ row }"><span class="audited-cell">{{ fmtAmount(row.priorAudited) }}</span></template>
      </el-table-column>
      <el-table-column width="100" align="right">
        <template #default="{ row }"><span :class="{ 'rate-warning': isChangeRateExceeding(getChangeRate(row), 0.3) }">{{ fmtRate(getChangeRate(row)) }}</span></template>
      </el-table-column>
      <el-table-column width="60" />
    </el-table>

    <!-- TB核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">试算平衡表数（6001+6051）：</span>
      <span>{{ fmtAmount(trialBalanceRow.total) }}</span>
      <el-tag v-if="hasDifference" type="danger" size="small" class="diff-tag">
        差异 {{ fmtAmount(differenceRow) }}
      </el-tag>
      <el-tag v-else type="success" size="small" class="diff-tag">核对一致</el-tag>
    </div>

    <!-- 确认审定按钮 -->
    <div class="action-row">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="publishAdjudicated">
        确认审定（回写TB）
      </el-button>
    </div>

    <!-- 审计说明 -->
    <div class="audit-note-section">
      <div class="note-header">
        <h4>审计说明</h4>
        <div class="note-actions">
          <el-button size="small" disabled title="AI生成审计说明（开发中）">🤖 AI生成</el-button>
          <el-button
            size="small"
            circle
            title="发起复核对话"
            @click="openReviewDialog?.('D4-1-adj-note')"
          >💬</el-button>
        </div>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入审计说明（变动率>30%的项目需解释原因）..."
        :disabled="isReadonly"
      />
    </div>

    <!-- 审计结论 -->
    <div class="audit-note-section">
      <div class="note-header">
        <h4>审计结论</h4>
        <div class="note-actions">
          <el-button size="small" disabled title="AI生成审计结论（开发中）">🤖 AI生成</el-button>
        </div>
      </div>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="请输入审计结论..."
        :disabled="isReadonly"
      />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-adjudication {
  padding: 12px;
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
.cross-alert {
  margin-bottom: 8px;
}
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
}
.toolbar-right {
  display: flex;
  gap: 6px;
}
.gt-index-chip {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 4px;
  color: #1890ff;
  cursor: pointer;
}
.gt-index-chip:hover {
  background: #bae7ff;
}
.section-title {
  margin: 12px 0 8px;
  font-size: 14px;
  color: #303133;
}
.cross-sheet-cell {
  background-color: #e6f7ff;
  padding: 2px 4px;
  border-radius: 2px;
}
.rate-warning {
  color: #f56c6c;
  font-weight: 600;
}
.audited-cell {
  font-weight: 600;
}
.font-bold {
  font-weight: 600;
}
:deep(.subtotal-row-bg) {
  background-color: #fafafa !important;
  font-weight: 600;
}
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 13px;
}
.tb-label {
  color: #909399;
}
.diff-tag {
  margin-left: 8px;
}
.action-row {
  margin-bottom: 16px;
}
.audit-note-section {
  margin-bottom: 16px;
}
.note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.note-header h4 {
  margin: 0;
  font-size: 14px;
  color: #303133;
}
.note-actions {
  display: flex;
  gap: 6px;
}
</style>
