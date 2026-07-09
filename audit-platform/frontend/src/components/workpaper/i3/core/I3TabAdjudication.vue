<template>
  <div class="i3-adjudication">
    <!-- 双模式切换 -->
    <div class="mode-switcher">
      <el-segmented v-model="viewMode" :options="['结构化视图', '在线编辑']" />
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>商誉审定原理：</strong>商誉不摊销！仅年度减值测试。期末=期初+新并购-减值（只减不增）。</p>
      <p>科目1711商誉（借方/资产类）。"本期增加"仅来自新并购（正常年份为0），"本期减少"仅来自减值。</p>
      <p>商誉减值不可转回！审定数=未审数+AJE+RJE。净额=初始确认(商誉原值)-累计减值准备。</p>
    </div>

    <!-- 新并购黄色警告 -->
    <el-alert
      v-for="w in newAcquisitionWarnings"
      :key="w.rowId"
      type="warning"
      :title="w.message"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <!-- 减值转回红色错误 -->
    <el-alert
      v-for="w in impairmentReversalWarnings"
      :key="w.rowId"
      type="error"
      :title="w.message"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <!-- 主审定表（13列） -->
    <div class="table-section">
      <div class="block-header">
        <span class="block-title">商誉审定表（I3-1）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" @click="addRow">
            + 新增
          </el-button>
          <el-button size="small" type="primary" text @click="handleAiGenerate('adjudication')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
          <el-button size="small" type="default" text @click="handleReview">
            复核
          </el-button>
        </div>
      </div>

      <el-table
        :data="displayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        show-summary
        :summary-method="getSummaryMethod"
      >
        <!-- 1. 被投资单位 -->
        <el-table-column prop="investee" label="被投资单位" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.rowId === 'row-subtotal' }">{{ row.investee }}</span>
            <el-button
              v-if="row.isEditable && !isReadonly"
              size="small"
              type="danger"
              text
              class="row-delete-btn"
              @click="removeRow(row.rowId)"
            >✕</el-button>
          </template>
        </el-table-column>

        <!-- 2. 初始确认 -->
        <el-table-column prop="initialRecognition" label="初始确认" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.initialRecognition"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'initialRecognition', $event)"
            />
            <span v-else>{{ fmtAmount(row.initialRecognition) }}</span>
          </template>
        </el-table-column>

        <!-- 3. 期初余额 -->
        <el-table-column prop="beginBalance" label="期初余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'beginBalance', $event)"
            />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 4. 本期增加(新并购) -->
        <el-table-column prop="newAcquisition" label="本期增加(新并购)" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.newAcquisition"
              size="small"
              :controls="false"
              :class="{ 'cell-warning': row.newAcquisition !== 0 }"
              @change="onCellChange(row.rowId, 'newAcquisition', $event)"
            />
            <span v-else :class="{ 'cell-warning-text': row.newAcquisition !== 0 }">
              {{ fmtAmount(row.newAcquisition) }}
            </span>
          </template>
        </el-table-column>

        <!-- 5. 本期减少(减值) -->
        <el-table-column prop="impairment" label="本期减少(减值)" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.impairment"
              size="small"
              :controls="false"
              :min="0"
              :class="{ 'cell-error': row.impairment < 0 }"
              @change="onCellChange(row.rowId, 'impairment', $event)"
            />
            <span v-else :class="{ 'cell-error-text': row.impairment < 0 }">
              {{ fmtAmount(row.impairment) }}
            </span>
          </template>
        </el-table-column>

        <!-- 6. 期末余额（公式列） -->
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #header>
            <el-tooltip content="期末余额 = 期初 + 新并购 - 减值（不摊销！）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 新并购 - 减值" placement="top">
              <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 7. 未审数 -->
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'unadjusted', $event)"
            />
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- 8. AJE -->
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'aje', $event)"
            />
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- 9. RJE -->
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'rje', $event)"
            />
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 10. 审定数（公式列） -->
        <el-table-column label="审定数" min-width="120" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
              <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 11. 减值准备 -->
        <el-table-column prop="accImpairment" label="减值准备" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.accImpairment"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'accImpairment', $event)"
            />
            <span v-else>{{ fmtAmount(row.accImpairment) }}</span>
          </template>
        </el-table-column>

        <!-- 12. 净额（公式列） -->
        <el-table-column label="净额" min-width="120" align="right">
          <template #header>
            <el-tooltip content="净额 = 初始确认(商誉原值) - 累计减值准备" placement="top">
              <span class="formula-col-header">净额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="净额 = 初始确认 - 累计减值" placement="top">
              <span class="formula-value">{{ fmtAmount(row.netValue) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- TB差异 section -->
    <div class="tb-section">
      <div class="block-header">
        <span class="block-title">TB取数与差异</span>
      </div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="160" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.tbAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip
              :content="`差异 = 审定数(${fmtAmount(row.audited)}) - TB未审数(${fmtAmount(row.tbAmount)})`"
              placement="top"
            >
              <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">
                {{ fmtAmount(row.difference) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 跨底稿联动跳转 -->
    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="I3-2" @click="navigateTo('I3-2')" />
      <GtIndexChip value="I3-3" @click="navigateTo('I3-3')" />
      <GtIndexChip value="I3-6" @click="navigateTo('I3-6')" />
      <GtIndexChip value="A13" @click="navigateTo('A13')" />
    </div>

    <!-- 审计说明 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请填写审计说明（商誉不摊销，仅减值变动）..."
        :disabled="isReadonly"
        @blur="onNoteBlur"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-select
        v-model="auditConclusion"
        placeholder="请选择审计结论"
        :disabled="isReadonly"
        class="conclusion-select"
        @change="onConclusionChange"
      >
        <el-option value="商誉期末余额列报恰当，减值准备计提充分" label="商誉期末余额列报恰当，减值准备计提充分" />
        <el-option value="商誉减值测试结论合理，无需追加减值" label="商誉减值测试结论合理，无需追加减值" />
        <el-option value="经审计调整后，商誉列报恰当" label="经审计调整后，商誉列报恰当" />
        <el-option value="需进一步关注" label="需进一步关注" />
      </el-select>
    </el-card>

    <!-- 复核对话 -->
    <div class="review-action-bar">
      <el-button type="primary" @click="handleReview">
        发起复核对话
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabAdjudication.vue — I3-1 商誉审定表（66公式，不摊销！）
 *
 * 列结构（13列）：
 *   被投资单位 | 初始确认 | 期初余额 | 本期增加(新并购) | 本期减少(减值)
 *   | 期末余额 | 未审数 | AJE | RJE | 审定数 | 减值准备 | 净额
 *
 * 特殊规则：
 *   - 商誉不摊销！期末=期初+新并购-减值
 *   - "本期增加"非零→黄色提示
 *   - 商誉减值不可转回（impairment<0→红色错误）
 *   - 动态行（+新增按钮→ElMessageBox prompt）
 *   - 合计行 (sticky bottom)
 *   - 公式列(endBalance/audited/netValue)虚线下划线+cursor:help+tooltip
 *   - TB差异 = audited - TB
 *   - 审计说明+结论+复核对话
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 4.2
 * Requirements: 2.1-2.8
 */
import { ref, computed, toRef, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import {
  useI3Adjudication,
  type I3AdjudicationRow,
  type I3Warning,
} from '../../composables/useI3Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1711: number; audited1711: number }
  isReadonly: boolean
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject (openReviewDialog from main entry) ───────────────────────────────

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  auditNote,
  auditConclusion,
  subtotals,
  warnings,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  saveAdjudication,
  saveNote,
  saveConclusion,
} = useI3Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbUnadjusted1711: computed(() => props.tbData?.unadjusted1711 ?? 0),
    tbAudited1711: computed(() => props.tbData?.audited1711 ?? 0),
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── View Mode ───────────────────────────────────────────────────────────────

const viewMode = ref('结构化视图')

// ─── Display Rows (detail + subtotal) ────────────────────────────────────────

const displayRows = computed<I3AdjudicationRow[]>(() => {
  return [...rows.value]
})

// ─── Warnings separation ─────────────────────────────────────────────────────

const newAcquisitionWarnings = computed<I3Warning[]>(() =>
  warnings.value.filter(w => w.type === 'newAcquisition'),
)

const impairmentReversalWarnings = computed<I3Warning[]>(() =>
  warnings.value.filter(w => w.type === 'impairmentReversal'),
)

// ─── Summary (合计行) ────────────────────────────────────────────────────────

function getSummaryMethod({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const sub = subtotals.value

  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property as keyof I3AdjudicationRow | undefined
    if (!prop) {
      // formula columns by index: 期末余额=5, 审定数=9, 净额=11
      const colLabel = col.label
      if (colLabel === '期末余额') { sums[idx] = fmtAmount(sub.endBalance); return }
      if (colLabel === '审定数') { sums[idx] = fmtAmount(sub.audited); return }
      if (colLabel === '净额') { sums[idx] = fmtAmount(sub.netValue); return }
      sums[idx] = ''
      return
    }
    const val = (sub as any)[prop]
    sums[idx] = val != null ? fmtAmount(val) : ''
  })
  return sums
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: I3AdjudicationRow }): string {
  const classes: string[] = []
  if (row.newAcquisition !== 0) classes.push('row-has-warning')
  if (row.impairment < 0) classes.push('row-has-error')
  return classes.join(' ')
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onCellChange(rowId: string, field: keyof I3AdjudicationRow, value: number | null): void {
  updateCell(rowId, field, value ?? 0)
  saveAdjudication()
}

// ─── Note / Conclusion ───────────────────────────────────────────────────────

function onNoteBlur(): void {
  saveNote(auditNote.value)
}

function onConclusionChange(val: string): void {
  saveConclusion(val)
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `I3商誉审定表${section}`,
      context: {
        wpCode: 'I3-1',
        goodwillRule: '商誉不摊销，仅年度减值测试',
        auditedTotal: subtotals.value.audited,
        netValue: subtotals.value.netValue,
      },
    })
    if (res.data?.data?.content) {
      if (section === 'note') {
        auditNote.value = res.data.data.content
        saveNote(auditNote.value)
      } else if (section === 'conclusion') {
        auditConclusion.value = res.data.data.content
        saveConclusion(auditConclusion.value)
      }
    }
  } catch {
    // AI生成失败不阻塞
  }
}

// ─── Review (复核对话) ───────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('I3-1 审定表')
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

// ─── Amount Formatter ────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i3-adjudication {
  font-size: 13px;
  padding: 16px;
}

/* 双模式切换 */
.mode-switcher {
  margin-bottom: 16px;
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p {
  margin: 0;
}
.methodology-context strong {
  color: #78350f;
}

/* 警告 */
.adj-warning {
  margin-bottom: 8px;
}

/* 区块通用 */
.table-section {
  margin-bottom: 20px;
}
.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  font-weight: 600;
  font-size: 14px;
}
.block-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.block-title {
  font-size: 14px;
}

/* 审定表 */
.adjudication-table {
  font-size: 13px;
}
.adjudication-table :deep(.el-table__footer td) {
  font-weight: 600;
  background: #f0f9ff;
  position: sticky;
  bottom: 0;
}

/* 公式列虚线下划线 + cursor:help + tooltip */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 2px;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  color: #303133;
  font-weight: 500;
}

/* 合计行文字 */
.subtotal-text {
  font-weight: 600;
  color: #303133;
}

/* 单元格警告/错误 */
.cell-warning :deep(.el-input__inner) {
  background: #fffbeb !important;
}
.cell-warning-text {
  color: #d97706;
  font-weight: 500;
}
.cell-error :deep(.el-input__inner) {
  background: #fef2f2 !important;
}
.cell-error-text {
  color: #dc2626;
  font-weight: 600;
}

/* 行级样式 */
.adjudication-table :deep(.row-has-warning td) {
  background: #fffbeb !important;
}
.adjudication-table :deep(.row-has-error td) {
  background: #fef2f2 !important;
}

/* 行内删除按钮 */
.row-delete-btn {
  margin-left: 4px;
  font-size: 11px;
  padding: 2px 4px;
}

/* TB差异 */
.tb-section {
  margin-bottom: 20px;
  margin-top: 24px;
}
.tb-table {
  font-size: 13px;
}
.difference-warning {
  color: #dc2626;
  font-weight: 600;
}

/* 跨底稿联动 */
.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.cross-ref-label {
  color: #606266;
  font-size: 13px;
}

/* 审计说明/结论 el-card */
.audit-note-card {
  margin-bottom: 16px;
}
.audit-note-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
}
.conclusion-select {
  width: 100%;
}

/* 复核操作栏 */
.review-action-bar {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}
</style>
