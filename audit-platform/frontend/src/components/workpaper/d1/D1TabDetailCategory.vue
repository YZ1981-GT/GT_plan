<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D1TabDetailCategory.vue — 原值明细按类别D1-2 HTML渲染
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 9.1
 *
 * 渲染 el-table：票据种类|期初未审|期初AJE|期初RJE|期初审定|本期增加|本期减少|期末未审|期末AJE|期末RJE|期末审定
 * 预设银行承兑/商业承兑固定行（不可删除）+ 动态行增删 + 小计行自动SUM
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1DetailCategory, type CategoryRow } from '../composables/useD1DetailCategory'
import type { ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import { useD1VirtualBrowse } from '../composables/useD1VirtualBrowse'
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

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  subtotalRow,
  auditProcedures,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  saveAuditProcedures,
  saveAuditNote,
  saveAuditConclusion,
} = useD1DetailCategory({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const rowCount = computed(() => rows.value.length)
const { useLargeTable, tableMaxHeight } = useD1VirtualBrowse(rowCount)

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span class="negative-amount">(${displayPrefs.fmtAmount(Math.abs(val))})</span>`
  return displayPrefs.fmtAmount(val)
}

// ─── Table Helpers ───────────────────────────────────────────────────────────

function getTableData(): CategoryRow[] {
  return [...rows.value, subtotalRow.value]
}

function getRowClass({ row }: { row: CategoryRow }): string {
  if (row.rowId === 'subtotal') return 'is-summary'
  return ''
}

function isComputedField(field: string): boolean {
  return ['priorAudited', 'currentUnadjusted', 'currentAudited'].includes(field)
}

function isCellEditable(row: CategoryRow, field: string): boolean {
  if (props.isReadonly) return false
  if (row.rowId === 'subtotal') return false
  if (isComputedField(field)) return false
  return true
}

// ─── Import/Export ───────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-2')

const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingProcedures = ref(false)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

const AUDIT_OBJECTIVES = [
  '资产负债表中的应收票据已得到恰当的确认和计量；',
  '评价调整已记录于账户中；',
  '披露已得到恰当计量和列报。',
]

function buildDetailContext(guidance: string): Record<string, unknown> {
  const lines = rows.value.map((r) => {
    return `${r.category || '未命名'}: 期初审定=${r.priorAudited}, 本期增加=${r.currentIncrease}, 本期减少=${r.currentDecrease}, 期末审定=${r.currentAudited}`
  })
  const st = subtotalRow.value
  return {
    sheet: 'D1-2',
    objectives: AUDIT_OBJECTIVES.join(' '),
    rowCount: rows.value.length,
    tableSummary: lines.slice(0, 20).join('\n'),
    subtotal: `小计 期初审定=${st.priorAudited}, 期末审定=${st.currentAudited}`,
    auditProcedures: auditProcedures.value || '',
    guidance,
  }
}

async function generateAuditProceduresWithAI() {
  if (props.isReadonly) return
  aiLoadingProcedures.value = true
  try {
    const text = await generateAndConfirm(
      'detail-audit-procedures',
      auditProcedures.value,
      buildDetailContext(
        '按编号列出D1-2原值明细表（按类别）应执行的审计过程，覆盖总账明细核对、分类核对、增减变动抽查、期末勾稽与披露。',
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
      'detail-audit-note',
      auditNote.value,
      buildDetailContext(
        '根据D1-2按类别明细数据生成审计说明：核对范围、种类构成、期初衔接、本期增减、勾稽结果及关注事项。',
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
      'detail-audit-conclusion',
      auditConclusion.value,
      buildDetailContext(
        '根据D1-2明细与审计说明生成审计结论：完整性、分类恰当性、与总账一致性、是否需调整。',
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
  <div class="d1-tab-detail-category">
    <div class="tab-header">
      <h4>应收票据原值明细表（原值）D1-2</h4>
      <GtReviewTrigger section-id="D1-detail-cat-header" />
    </div>

    <!-- 一、审计目标 + 二、审计过程（参照 D4 方法论区） -->
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
          placeholder="请记录执行的审计程序，如：1. 获取应收票据明细账并与总账核对……"
          :disabled="isReadonly"
          @input="(v: string) => saveAuditProcedures(v)"
        />
      </div>
    </details>

    <!-- 明细表工具栏 -->
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
      <el-button
        type="primary"
        size="small"
        :disabled="isReadonly"
        @click="addRow()"
      >
        + 添加种类
      </el-button>
    </div>

    <!-- Main Table -->
    <el-alert v-if="useLargeTable" type="info" :closable="false" show-icon class="large-table-hint">
      行数较多，已启用固定高度滚动浏览（{{ rowCount }} 行）
    </el-alert>
    <el-table
      class="detail-category-table"
      :data="getTableData()"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClass"
      :max-height="tableMaxHeight"
    >
      <!-- 票据种类 -->
      <el-table-column label="票据种类" min-width="140">
        <template #default="{ row }">
          <template v-if="row.rowId === 'subtotal'">
            <span style="font-weight: 600">{{ row.category }}</span>
          </template>
          <template v-else-if="row.isFixed">
            <span>{{ row.category }}</span>
            <GtReviewDot row-prefix="D1-cat" :row-key="row.rowId" />
          </template>
          <template v-else>
            <div class="category-cell">
              <el-input
                :model-value="row.category"
                size="small"
                placeholder="输入种类名称"
                :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'category', v)"
              />
              <GtReviewDot row-prefix="D1-cat" :row-key="row.rowId" />
              <el-button
                v-if="!isReadonly"
                type="danger"
                size="small"
                text
                class="delete-btn"
                @click="removeRow(row.rowId)"
              >
                ✕
              </el-button>
            </div>
          </template>
        </template>
      </el-table-column>

      <!-- 期初未审 -->
      <el-table-column label="期初未审" min-width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="isCellEditable(row, 'priorUnadjusted')"
            class="cell-amount-input"
            :model-value="row.priorUnadjusted"
            size="small"
            @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.priorUnadjusted)" />
        </template>
      </el-table-column>

      <!-- 期初AJE -->
      <el-table-column label="期初AJE" min-width="90" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="isCellEditable(row, 'priorAje')"
            class="cell-amount-input"
            :model-value="row.priorAje"
            size="small"
            @change="(v: number) => updateCell(row.rowId, 'priorAje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.priorAje)" />
        </template>
      </el-table-column>

      <!-- 期初RJE -->
      <el-table-column label="期初RJE" min-width="90" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="isCellEditable(row, 'priorRje')"
            class="cell-amount-input"
            :model-value="row.priorRje"
            size="small"
            @change="(v: number) => updateCell(row.rowId, 'priorRje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.priorRje)" />
        </template>
      </el-table-column>

      <!-- 期初审定 (computed) -->
      <el-table-column label="期初审定" min-width="100" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600" v-html="fmtAmount(row.priorAudited)" />
        </template>
      </el-table-column>

      <!-- 本期增加 -->
      <el-table-column label="本期增加" min-width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="isCellEditable(row, 'currentIncrease')"
            class="cell-amount-input"
            :model-value="row.currentIncrease"
            size="small"
            @change="(v: number) => updateCell(row.rowId, 'currentIncrease', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentIncrease)" />
        </template>
      </el-table-column>

      <!-- 本期减少 -->
      <el-table-column label="本期减少" min-width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="isCellEditable(row, 'currentDecrease')"
            class="cell-amount-input"
            :model-value="row.currentDecrease"
            size="small"
            @change="(v: number) => updateCell(row.rowId, 'currentDecrease', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentDecrease)" />
        </template>
      </el-table-column>

      <!-- 期末未审 (computed) -->
      <el-table-column label="期末未审" min-width="100" align="right">
        <template #default="{ row }">
          <span v-html="fmtAmount(row.currentUnadjusted)" />
        </template>
      </el-table-column>

      <!-- 期末AJE -->
      <el-table-column label="期末AJE" min-width="90" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="isCellEditable(row, 'currentAje')"
            class="cell-amount-input"
            :model-value="row.currentAje"
            size="small"
            @change="(v: number) => updateCell(row.rowId, 'currentAje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentAje)" />
        </template>
      </el-table-column>

      <!-- 期末RJE -->
      <el-table-column label="期末RJE" min-width="90" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="isCellEditable(row, 'currentRje')"
            class="cell-amount-input"
            :model-value="row.currentRje"
            size="small"
            @change="(v: number) => updateCell(row.rowId, 'currentRje', v || 0)"
          />
          <span v-else v-html="fmtAmount(row.currentRje)" />
        </template>
      </el-table-column>

      <!-- 期末审定 (computed) -->
      <el-table-column label="期末审定" min-width="100" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600" v-html="fmtAmount(row.currentAudited)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 三、审计说明 + 四、审计结论（参照 D4 审计意见区） -->
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
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-cat-note')">💬 复核</el-button>
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
            <el-button v-if="openReviewDialog" size="small" @click="onReview('D1-cat-conclusion')">💬 复核</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.d1-tab-detail-category {
  width: 100%;
  padding: 12px;
}

.detail-category-table {
  width: 100%;
}

.detail-category-table :deep(.cell-amount-input) {
  width: 100%;
}

.detail-category-table :deep(.el-input-number .el-input__wrapper) {
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

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

/* 小计行样式 */
:deep(.el-table .is-summary td) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 种类列带删除按钮 */
.category-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.category-cell .el-input {
  flex: 1;
}

.delete-btn {
  padding: 2px 4px;
  min-height: auto;
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
  margin: 4px 0 10px 16px;
  padding: 0;
}

.method-objectives li {
  margin-bottom: 3px;
}

.audit-opinion-card {
  margin-top: 16px;
}

.opinion-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.opinion-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.opinion-field label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
  font-weight: 500;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}
</style>
