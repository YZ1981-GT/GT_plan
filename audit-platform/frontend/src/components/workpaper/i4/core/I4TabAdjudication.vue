<template>
  <div class="i4-adjudication">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>长期待摊费用审定原理：</strong>科目1801（借方/资产类）。期末=期初+增加-摊销-减少。</p>
      <p>摊销通常采用直线法（月平均），少数项目用工作量法。审定数=未审数+AJE+RJE。</p>
      <p>三角勾稽：期末余额必须等于(期初+增加-摊销-减少)，不等则红色高亮差额。</p>
    </div>

    <!-- 三角勾稽错误警告 -->
    <el-alert
      v-if="reconciliationStatus === 'mismatch'"
      type="error"
      title="三角勾稽不平：期末 ≠ 期初+增加-摊销-减少，请检查数据"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <!-- 主审定表（10列） -->
    <div class="table-section">
      <div class="block-header">
        <span class="block-title">长期待摊费用审定表（I4-1）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" @click="addRow" :disabled="isReadonly">
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
        :data="computedRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        show-summary
        :summary-method="getSummaryMethod"
      >
        <!-- 1. 项目 -->
        <el-table-column prop="项目" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span>{{ row.项目 }}</span>
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

        <!-- 2. 期初 -->
        <el-table-column prop="期初" label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.期初"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '期初', $event)"
            />
            <span v-else>{{ fmtAmount(row.期初) }}</span>
          </template>
        </el-table-column>

        <!-- 3. 本期增加 -->
        <el-table-column prop="增加" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.增加"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '增加', $event)"
            />
            <span v-else>{{ fmtAmount(row.增加) }}</span>
          </template>
        </el-table-column>

        <!-- 4. 本期摊销 -->
        <el-table-column prop="摊销" label="本期摊销" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.摊销"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '摊销', $event)"
            />
            <span v-else>{{ fmtAmount(row.摊销) }}</span>
          </template>
        </el-table-column>

        <!-- 5. 本期减少 -->
        <el-table-column prop="减少" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.减少"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '减少', $event)"
            />
            <span v-else>{{ fmtAmount(row.减少) }}</span>
          </template>
        </el-table-column>

        <!-- 6. 期末（公式列） -->
        <el-table-column label="期末" min-width="110" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 增加 - 摊销 - 减少" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 增加 - 摊销 - 减少" placement="top">
              <span class="formula-value" :class="{ 'cell-error-text': row.hasError }">
                {{ fmtAmount(row.期末) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 7. 未审 -->
        <el-table-column prop="未审" label="未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.未审"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '未审', $event)"
            />
            <span v-else>{{ fmtAmount(row.未审) }}</span>
          </template>
        </el-table-column>

        <!-- 8. AJE -->
        <el-table-column prop="AJE" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.AJE"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'AJE', $event)"
            />
            <span v-else>{{ fmtAmount(row.AJE) }}</span>
          </template>
        </el-table-column>

        <!-- 9. RJE -->
        <el-table-column prop="RJE" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.RJE"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'RJE', $event)"
            />
            <span v-else>{{ fmtAmount(row.RJE) }}</span>
          </template>
        </el-table-column>

        <!-- 10. 审定数（公式列） -->
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
              <span class="formula-value">{{ fmtAmount(row.审定) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- TB差异区 -->
    <div class="tb-section">
      <div class="block-header">
        <span class="block-title">TB取数与差异</span>
        <el-button size="small" type="success" @click="handleWriteback" :disabled="isReadonly">
          回写TB(1801)
        </el-button>
      </div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="160" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.tbAmount) }}</template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.audited) }}</template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">
              {{ fmtAmount(row.difference) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 跨底稿联动跳转 -->
    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="I4-2" @click="navigateTo('I4-2')" />
      <GtIndexChip value="I4-3" @click="navigateTo('I4-3')" />
      <GtIndexChip value="I4-6" @click="navigateTo('I4-6')" />
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
        placeholder="请填写审计说明（长期待摊费用摊销完整性、准确性检查情况）..."
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
        <el-option value="长期待摊费用期末余额列报恰当，摊销计提充分" label="长期待摊费用期末余额列报恰当，摊销计提充分" />
        <el-option value="经审计调整后，长期待摊费用列报恰当" label="经审计调整后，长期待摊费用列报恰当" />
        <el-option value="摊销政策合理，期末余额公允" label="摊销政策合理，期末余额公允" />
        <el-option value="需进一步关注" label="需进一步关注" />
      </el-select>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>长期待摊费用科目1801（借方/资产类）：期末=期初+增加-摊销-减少</li>
        <li>三角勾稽差额≠0将红色高亮，需查明原因</li>
        <li>"回写TB"按钮将审定合计数回写试算平衡表(1801)</li>
        <li>AJE/RJE来自I4-3调整分录表（EventBus自动同步）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabAdjudication.vue — I4-1 审定表（47公式）
 *
 * 列结构（10列）：
 *   项目 | 期初 | 本期增加 | 本期摊销 | 本期减少 | 期末 | 未审 | AJE | RJE | 审定数
 *
 * 核心公式：
 *   - 期末 = 期初 + 增加 - 摊销 - 减少（资产类借方科目1801）
 *   - 审定 = 未审 + AJE + RJE
 *   - 三角勾稽：差额 = 期末 - (期初 + 增加 - 摊销 - 减少) → 应为0
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 4.2
 * Requirements: 2.1-2.6
 */
import { ref, computed, toRef, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import {
  useI4Adjudication,
  type I4AdjudicationRow,
} from '../../composables/useI4Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1801: number; audited1801: number }
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
  rows: computedRows,
  auditNote,
  auditConclusion,
  subtotals,
  reconciliationStatus,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  writeback,
  saveNote,
  saveConclusion,
} = useI4Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbUnadjusted1801: computed(() => props.tbData?.unadjusted1801 ?? 0),
    tbAudited1801: computed(() => props.tbData?.audited1801 ?? 0),
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── Summary (合计行) ────────────────────────────────────────────────────────

function getSummaryMethod({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const sub = subtotals.value

  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (!prop) {
      // formula columns: 期末=5, 审定数=9
      const colLabel = col.label
      if (colLabel === '期末') { sums[idx] = fmtAmount(sub.期末); return }
      if (colLabel === '审定数') { sums[idx] = fmtAmount(sub.审定); return }
      sums[idx] = ''
      return
    }
    const val = (sub as any)[prop]
    sums[idx] = val != null ? fmtAmount(val) : ''
  })
  return sums
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: I4AdjudicationRow }): string {
  if (row.hasError) return 'row-has-error'
  return ''
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onCellChange(rowId: string, field: keyof I4AdjudicationRow, value: number | null): void {
  updateCell(rowId, field, value ?? 0)
}

// ─── Note / Conclusion ───────────────────────────────────────────────────────

function onNoteBlur(): void {
  saveNote(auditNote.value)
}

function onConclusionChange(val: string): void {
  saveConclusion(val)
}

// ─── Writeback ───────────────────────────────────────────────────────────────

async function handleWriteback(): Promise<void> {
  await writeback()
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `I4长期待摊费用审定表${section}`,
      context: {
        wpCode: 'I4-1',
        rule: '期末=期初+增加-摊销-减少，科目1801借方资产类',
        auditedTotal: subtotals.value.审定,
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
  openReviewDialog('I4-1 审定表')
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
.i4-adjudication {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
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
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }

/* 警告 */
.adj-warning { margin-bottom: 12px; }

/* 区块通用 */
.table-section { margin-bottom: 20px; }
.block-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0; font-weight: 600; font-size: 14px;
}
.block-actions { display: flex; align-items: center; gap: 4px; }
.block-title { font-size: 14px; }

/* 审定表 */
.adjudication-table { font-size: var(--wp-font-size, 13px); }
.adjudication-table :deep(.el-table__footer td) {
  font-weight: 600; background: #f0f9ff;
}

/* 公式列虚线下划线 + cursor:help */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help; padding-bottom: 2px;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help; padding-bottom: 1px;
  color: #303133; font-weight: 500;
}

/* 行级样式 */
.adjudication-table :deep(.row-has-error td) { background: #fef2f2 !important; }
.cell-error-text { color: #dc2626; font-weight: 600; }
.row-delete-btn { margin-left: 4px; font-size: 11px; padding: 2px 4px; }

/* TB差异 */
.tb-section { margin-bottom: 20px; margin-top: 24px; }
.tb-table { font-size: var(--wp-font-size, 13px); }
.difference-warning { color: #dc2626; font-weight: 600; }

/* 跨底稿联动 */
.cross-ref-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 0; margin-bottom: 16px; flex-wrap: wrap;
}
.cross-ref-label { color: #606266; font-size: var(--wp-font-size, 13px); }

/* 审计说明/结论 el-card */
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 500;
}
.conclusion-select { width: 100%; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
