<script setup lang="ts">
/**
 * D1TabBadDebt.vue — 坏账准备 D1-4 HTML渲染
 *
 * 对齐 D1-3：审计目标/过程 + 明细表 + 审计意见区（说明/结论）+ AI
 * 列：项目|期初未审|期初AJE|期初RJE|期初审定|本期计提|本期收回|本期转回|本期核销|本期其他|期末未审|期末AJE|期末RJE|期末审定
 * 固定行结构：按单项计提（可展开子行）+ 按组合计提（可展开子行）+ 小计
 * ECL差异警告（小计行旁黄色 el-alert）
 */
import { ref, inject, toRef, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1BadDebt, type BadDebtRow } from '../composables/useD1BadDebt'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import http from '@/utils/http'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const openReviewDialog = inject<((params: { sectionId: string }) => void) | null>('openReviewDialog', null)

// ─── ECL Test Total (from allResponses or default 0) ─────────────────────────

const eclTestTotal = ref(0)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  individualRows,
  portfolioRows,
  subtotalRow,
  eclWarning,
  auditProcedures,
  auditNote,
  auditConclusion,
  addSubRow,
  removeSubRow,
  updateCell,
  saveAuditProcedures,
  saveAuditNote,
  saveAuditConclusion,
} = useD1BadDebt({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  eclTestTotal,
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Table Data ──────────────────────────────────────────────────────────────

const tableData = computed<BadDebtRow[]>(() => {
  return [
    ...individualRows.value,
    ...portfolioRows.value,
    subtotalRow.value,
  ]
})

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getRowClass({ row }: { row: BadDebtRow }): string {
  if (row.rowId === 'subtotal') return 'is-summary'
  if (!row.isSubRow) return 'is-parent-row'
  return 'is-sub-row'
}

function isComputedField(field: string): boolean {
  return ['priorAudited', 'currentUnadjusted', 'currentAudited'].includes(field)
}

function isCellEditable(row: BadDebtRow, field: string): boolean {
  if (props.isReadonly) return false
  if (row.rowId === 'subtotal') return false
  if (isComputedField(field)) return false
  return true
}

function isParentRow(row: BadDebtRow): boolean {
  return !row.isSubRow && row.rowId !== 'subtotal'
}

// ─── Import/Export + AI ──────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-4')

const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingProcedures = ref(false)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

const AUDIT_OBJECTIVES = [
  '坏账准备已按预期信用损失模型恰当计提；',
  '按单项/按组合分类完整、准确；',
  '本期计提、转回、核销与账面及 D1-15/D1-16 勾稽一致；',
  '披露已得到恰当计量和列报。',
]

function buildBadDebtContext(guidance: string): Record<string, unknown> {
  const lines = [...individualRows.value, ...portfolioRows.value].map((r) => {
    const tag = r.isSubRow ? '子项' : '父行'
    return `${r.label || '未命名'}[${r.category}/${tag}]: 期初审定=${r.priorAudited}, 计提=${r.currentProvision}, 转回=${r.currentReversal}, 核销=${r.currentWriteOff}, 期末审定=${r.currentAudited}`
  })
  const st = subtotalRow.value
  return {
    sheet: 'D1-4',
    objectives: AUDIT_OBJECTIVES.join(' '),
    individualCount: individualRows.value.filter((r) => r.isSubRow).length,
    portfolioCount: portfolioRows.value.filter((r) => r.isSubRow).length,
    tableSummary: lines.slice(0, 20).join('\n'),
    subtotal: `小计 期初审定=${st.priorAudited}, 期末审定=${st.currentAudited}`,
    eclWarning: eclWarning.value || '',
    auditProcedures: auditProcedures.value || '',
    guidance,
  }
}

async function generateAuditProceduresWithAI() {
  if (props.isReadonly) return
  aiLoadingProcedures.value = true
  try {
    const text = await generateAndConfirm(
      'baddebt-audit-procedures',
      auditProcedures.value,
      buildBadDebtContext(
        '按编号列出D1-4坏账准备明细表应执行的审计过程，覆盖单项/组合分类、期初衔接、本期变动抽查、与D1-15 ECL及D1-16转回核销勾稽。',
      ),
      'AI · 审计过程',
    )
    if (text) saveAuditProcedures(text)
  } finally {
    aiLoadingProcedures.value = false
  }
}

async function generateAuditNoteWithAI() {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'baddebt-audit-note',
      auditNote.value,
      buildBadDebtContext(
        '根据D1-4坏账准备明细生成审计说明：单项/组合构成、本期计提转回核销、与ECL测算及转回核销检查勾稽结果。',
      ),
      'AI · 审计说明',
    )
    if (text) saveAuditNote(text)
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateAuditConclusionWithAI() {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'baddebt-audit-conclusion',
      auditConclusion.value,
      buildBadDebtContext(
        '根据D1-4明细与审计说明生成审计结论：坏账准备计提是否充分、分类是否恰当、与总账/ECL是否一致、是否需调整。',
      ),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

function onReview(sectionId: string) {
  openReviewDialog?.({ sectionId })
}
</script>

<template>
  <div class="d1-tab-bad-debt">
    <div class="tab-header">
      <h4>坏账准备明细表 D1-4</h4>
      <GtReviewTrigger section-id="D1-baddebt-header" />
    </div>

    <!-- 一、审计目标 + 二、审计过程 -->
    <details class="methodology-collapse" open>
      <summary class="methodology-summary">📖 审计目标与审计过程（点击展开/收起）</summary>
      <div class="methodology-body">
        <p class="method-title"><strong>一、审计目标：</strong></p>
        <ol class="method-objectives">
          <li v-for="(item, i) in AUDIT_OBJECTIVES" :key="'obj-' + i">{{ item }}</li>
        </ol>
        <div class="method-title-row">
          <p class="method-title"><strong>二、审计过程：</strong></p>
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计过程' : 'AI服务暂不可用'" placement="top">
            <el-button
              size="small"
              :loading="aiLoadingProcedures"
              :disabled="isReadonly || !aiAvailable"
              @click="generateAuditProceduresWithAI"
            >
              🤖 AI
            </el-button>
          </el-tooltip>
        </div>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :model-value="auditProcedures"
          placeholder="请记录执行的审计程序，如：1. 获取坏账准备明细并与总账/D1-15核对……"
          :disabled="isReadonly"
          @input="(v: string) => saveAuditProcedures(v)"
        />
      </div>
    </details>

    <!-- Toolbar -->
    <div class="table-toolbar">
      <el-button-group size="small">
        <el-button @click="onExportTemplate">导出模板</el-button>
        <el-button @click="onExportData">导出数据</el-button>
        <el-upload
          :show-file-list="false"
          accept=".xlsx"
          :before-upload="onImportFile"
          style="display:inline-block"
        >
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
      <el-button-group>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="addSubRow('individual')"
        >
          + 按单项子行
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="addSubRow('portfolio')"
        >
          + 按组合子行
        </el-button>
      </el-button-group>
    </div>

    <details class="prep-hint-collapse">
      <summary class="prep-hint-summary">编制提示（导入导出注意事项）</summary>
      <ul class="prep-hint-list">
        <li>导出模板含「编制说明」工作表，请先阅读填写要求与注意事项。</li>
        <li>D1-4 表头为双行合并：第1行分组、第2行叶子列；导入时系统自动识别叶子表头行。</li>
        <li>请保留「按单项计提」「按组合计提」分区行；空占位行可保留，导入时自动跳过。</li>
        <li>期初审定 / 期末未审 / 期末审定为计算列，导入后由系统重算。</li>
        <li>期末审定应与 D1-15 ECL 测算、D1-16 转回核销勾稽。</li>
      </ul>
    </details>

    <!-- ECL Warning -->
    <el-alert
      v-if="eclWarning"
      :title="eclWarning"
      type="warning"
      show-icon
      :closable="false"
      class="ecl-warning"
    />

    <!-- Main Table -->
    <div class="table-scroll">
      <el-table
        class="bad-debt-table"
        :data="tableData"
        border
        size="small"
        :row-class-name="getRowClass"
        style="width: 100%"
      >
        <!-- 项目 -->
        <el-table-column label="项目" min-width="160" fixed>
          <template #default="{ row }">
            <template v-if="row.rowId === 'subtotal'">
              <span style="font-weight: 600">小计</span>
            </template>
            <template v-else-if="isParentRow(row)">
              <span style="font-weight: 600">{{ row.label }}</span>
              <GtReviewDot row-prefix="D1-baddebt" :row-key="row.rowId" />
            </template>
            <template v-else>
              <div class="sub-row-cell">
                <span class="sub-row-indent">└</span>
                <el-input
                  :model-value="row.label"
                  size="small"
                  placeholder="子项名称"
                  :disabled="isReadonly"
                  @change="(v: string) => updateCell(row.rowId, 'label', v as any)"
                />
                <GtReviewDot row-prefix="D1-baddebt" :row-key="row.rowId" />
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  size="small"
                  text
                  class="delete-btn"
                  @click="removeSubRow(row.rowId)"
                >
                  ✕
                </el-button>
              </div>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'priorUnadjusted')"
              class="cell-amount-input"
              :model-value="row.priorUnadjusted"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.priorUnadjusted)" />
          </template>
        </el-table-column>

        <el-table-column label="期初AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'priorAje')"
              class="cell-amount-input"
              :model-value="row.priorAje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'priorAje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.priorAje)" />
          </template>
        </el-table-column>

        <el-table-column label="期初RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'priorRje')"
              class="cell-amount-input"
              :model-value="row.priorRje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'priorRje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.priorRje)" />
          </template>
        </el-table-column>

        <el-table-column label="期初审定" min-width="110" align="right">
          <template #default="{ row }">
            <span style="font-weight: 600" v-html="fmtAmount(row.priorAudited)" />
          </template>
        </el-table-column>

        <el-table-column label="本期计提" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentProvision')"
              class="cell-amount-input"
              :model-value="row.currentProvision"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentProvision', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentProvision)" />
          </template>
        </el-table-column>

        <el-table-column label="本期收回" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentRecovery')"
              class="cell-amount-input"
              :model-value="row.currentRecovery"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentRecovery', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentRecovery)" />
          </template>
        </el-table-column>

        <el-table-column label="本期转回" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentReversal')"
              class="cell-amount-input"
              :model-value="row.currentReversal"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentReversal', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentReversal)" />
          </template>
        </el-table-column>

        <el-table-column label="本期核销" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentWriteOff')"
              class="cell-amount-input"
              :model-value="row.currentWriteOff"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentWriteOff', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentWriteOff)" />
          </template>
        </el-table-column>

        <el-table-column label="本期其他" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentOther')"
              class="cell-amount-input"
              :model-value="row.currentOther"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentOther', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentOther)" />
          </template>
        </el-table-column>

        <el-table-column label="期末未审" min-width="110" align="right">
          <template #default="{ row }">
            <span v-html="fmtAmount(row.currentUnadjusted)" />
          </template>
        </el-table-column>

        <el-table-column label="期末AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentAje')"
              class="cell-amount-input"
              :model-value="row.currentAje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentAje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentAje)" />
          </template>
        </el-table-column>

        <el-table-column label="期末RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="isCellEditable(row, 'currentRje')"
              class="cell-amount-input"
              :model-value="row.currentRje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number) => updateCell(row.rowId, 'currentRje', v || 0)"
            />
            <span v-else v-html="fmtAmount(row.currentRje)" />
          </template>
        </el-table-column>

        <el-table-column label="期末审定" min-width="110" align="right">
          <template #default="{ row }">
            <span style="font-weight: 600" v-html="fmtAmount(row.currentAudited)" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 三、审计说明 + 四、审计结论 -->
    <el-card class="audit-opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计意见区</span>
        </div>
      </template>
      <div class="opinion-body">
        <div class="opinion-field">
          <label>三、审计说明</label>
          <el-input
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 12 }"
            :model-value="auditNote"
            placeholder="请输入审计说明..."
            :disabled="isReadonly"
            @input="(v: string) => saveAuditNote(v)"
          />
          <div class="note-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成审计说明' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingNote"
                :disabled="isReadonly || !aiAvailable"
                @click="generateAuditNoteWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-bd-note')">💬 复核</el-button>
          </div>
        </div>
        <div class="opinion-field">
          <label>四、审计结论</label>
          <el-input
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            :model-value="auditConclusion"
            placeholder="请输入审计结论..."
            :disabled="isReadonly"
            @input="(v: string) => saveAuditConclusion(v)"
          />
          <div class="note-actions">
            <el-tooltip :content="aiAvailable ? 'AI辅助生成审计结论' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingConclusion"
                :disabled="isReadonly || !aiAvailable"
                @click="generateAuditConclusionWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-bd-conclusion')">💬 复核</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.d1-tab-bad-debt {
  width: 100%;
  padding: 12px;
}

.bad-debt-table {
  width: 100%;
}

.bad-debt-table :deep(.el-table th),
.bad-debt-table :deep(.el-table td),
.bad-debt-table :deep(.el-input__inner),
.bad-debt-table :deep(.el-input-number .el-input__inner) {
  font-size: var(--wp-font-size, 13px);
}

.bad-debt-table :deep(.cell-amount-input) {
  width: 100%;
}

.bad-debt-table :deep(.el-input-number .el-input__wrapper) {
  width: 100%;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
}

.ecl-warning {
  margin-bottom: 12px;
}

.sub-row-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sub-row-indent {
  color: #909399;
  flex-shrink: 0;
}

.sub-row-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

:deep(.el-table .is-parent-row td) {
  background-color: #f0f9eb !important;
}

:deep(.negative-amount) {
  color: #f56c6c;
}

.methodology-collapse {
  margin-bottom: 16px;
  border-radius: 6px;
  border: 1px solid #faecd8;
  border-left: 3px solid #e6a23c;
  background: #fffbf0;
}

.methodology-summary {
  cursor: pointer;
  padding: 8px 14px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #b88230;
}

.methodology-body {
  padding: 8px 14px 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.8;
}

.method-title {
  margin: 8px 0 4px;
  font-size: var(--wp-font-size, 13px);
}

.method-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 0 4px;
}

.method-title-row .method-title {
  margin: 0;
}

.method-objectives {
  margin: 0 0 8px 1.2em;
  padding: 0;
}

.prep-hint-collapse {
  margin-bottom: 12px;
  border-radius: 6px;
  border: 1px solid #d9ecff;
  border-left: 3px solid #409eff;
  background: #f0f7ff;
}

.prep-hint-summary {
  cursor: pointer;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  color: #337ecc;
}

.prep-hint-list {
  margin: 0 0 8px;
  padding: 0 12px 8px 28px;
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}

.audit-opinion-card {
  margin-top: 16px;
  border: 1px solid #ebeef5;
}

.opinion-header {
  display: flex;
  align-items: center;
}

.opinion-title {
  font-weight: 600;
  font-size: 14px;
}

.opinion-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.opinion-field label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  font-size: var(--wp-font-size, 13px);
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
