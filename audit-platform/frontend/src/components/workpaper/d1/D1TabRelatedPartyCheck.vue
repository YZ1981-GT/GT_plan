<script setup lang="ts">
/**
 * D1TabRelatedPartyCheck.vue — D1-11 关联方关系及交易检查表 HTML渲染
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 10.1
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换（结构化视图 | 在线编辑）
 * - 审计目标区域（只读静态文本）
 * - el-table 13列（flat columns, 无嵌套表头）：
 *   A关联方名称 | B关联关系 | C期初余额 | D借方发生 | E贷方发生 |
 *   F期末余额(只读公式C+D-E) | G减坏账准备 | H账面价值(只读公式F-G) |
 *   I账龄 | J款项性质 | K期后兑现 | L索引号 | M备注
 * - 金额列（C/D/E/F/G/H/K）右对齐，文本列左对齐
 * - F和H列灰色背景表示公式列
 * - "添加关联方"按钮 + 动态行增删
 * - 合计行 Row14（7列SUM：C/D/E/F/G/H/K）
 * - 核对区：关联方期末余额合计 vs 审定表期末余额 → 差异
 * - 审计说明/结论 + 编制提示（CAS 36披露/公允性/期后回收）
 * - GtOnlyOfficeSheet v-if isOOMode
 *
 * Requirements: 4.1-4.6, 5.1-5.5, 6.1-6.5, 14.1-14.5, 18.1-18.3, 18.5, 18.7
 */
import { inject, toRef, ref, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAgingConfig, PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useD1RelatedPartyCheck } from '../composables/useD1RelatedPartyCheck'
import {
  RELATIONSHIP_OPTIONS,
  formatNegativeAmount,
  type RelatedPartyRow,
} from '../composables/d1InspectionFormulas'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  displayPrefs: any
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const injectedDisplayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// 复核对话
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  addRow,
  removeRow,
  updateRow,
  summaryRow,
  adjClosingBalance,
  adjDataLoaded,
  reconDifference,
  auditNote,
  auditConclusion,
  saveAuditNote,
  saveAuditConclusion,
  exportTemplate,
  exportData,
  importData,
} = useD1RelatedPartyCheck({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  saveDebouncedText: (item: ChecklistItem) => {
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items: [item] })
      .catch(() => { /* silent */ })
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

/** 账龄下拉选项 = 项目账龄配置段（枚举账龄：3年段 / 5年段 / 自定义），仍允许自定义输入。 */
const { segments: d1AgingSegments } = useAgingConfig(toRef(props, 'projectId') as Ref<string>, 'D1')
const agingBandLabels = computed<string[]>(() => {
  const list = d1AgingSegments.value
  if (Array.isArray(list) && list.length > 0) return list.map((seg) => seg.label)
  return PRESET_SEGMENTS.FIVE_YEAR.map((seg) => seg.label)
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) {
    const formatted = formatNegativeAmount(val)
    return `<span class="negative-amount">${formatted}</span>`
  }
  return injectedDisplayPrefs.fmtAmount(val)
}

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  'CAS 36 关联方披露准则要求：识别关联方关系及交易，披露关联方名称、关系、交易金额、余额及承诺事项。',
  '关联方票据交易公允性判断：比较关联方与非关联方类似交易的条件（利率、期限、金额），评估是否存在不公允条件。',
  '期后回收情况对坏账准备的影响评估：关注期后已兑现或贴现的金额，评估坏账准备计提的合理性和充分性。',
]

const wpIdRef = toRef(props, 'wpId')
const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

function buildRpAiContext(extra = ''): Record<string, unknown> {
  return {
    sheet: 'D1-11',
    rowCount: rows.value.length,
    closingBalanceTotal: summaryRow.value.closingBalance,
    adjClosingBalance: adjClosingBalance.value,
    reconDifference: reconDifference.value,
    adjDataLoaded: adjDataLoaded.value,
    guidance: extra,
  }
}

async function handleImportUpload(file: File): Promise<boolean> {
  const result = await importData(file)
  if (result.success) {
    ElMessage.success(`导入成功：${result.rowCount} 行`)
  } else {
    ElMessage.warning(result.errors?.[0] || '导入失败')
  }
  return false
}

async function generateAuditNoteWithAI() {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'sampling-audit-note',
      auditNote.value,
      buildRpAiContext('基于关联方余额结构、核对区差异、期后兑现及公允性判断生成审计说明。'),
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
      'sampling-audit-conclusion',
      auditConclusion.value,
      buildRpAiContext(`核对差异：${reconDifference.value}`),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

</script>

<template>
  <div class="d1-tab-related-party-check">
      <div class="tab-header">
        <h4>关联方检查 D1-11</h4>
        <GtReviewTrigger section-id="D1-related-party-header" />
      </div>
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        class="audit-objective"
      >
        <template #default>
          <p>核实关联方票据往来余额的完整性和准确性，评估关联方交易的公允性和披露充分性。</p>
        </template>
      </el-alert>

      <!-- Toolbar -->
      <div class="table-toolbar">
        <el-button-group size="small">
          <el-button @click="exportTemplate">导出模板</el-button>
          <el-button @click="exportData">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx,.xls"
            :before-upload="handleImportUpload"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
          + 添加关联方
        </el-button>
      </div>

      <!-- 13列表格 -->
      <el-table
        :data="rows"
        border
        size="small"
        max-height="500"
        class="related-party-table"
        style="width: 100%"
      >
        <!-- A: 关联方名称 -->
        <el-table-column label="关联方名称" min-width="120">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input
              :model-value="row.partyName"
              size="small"
              placeholder="关联方名称"
              :disabled="isReadonly"
              @change="(v: string) => updateRow(row.id, 'partyName', v || '')"
            />
            <GtReviewDot row-prefix="D1-related-party" :row-key="row.id" />
          </template>
        </el-table-column>

        <!-- B: 关联关系 -->
        <el-table-column label="关联关系" width="130">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-select
              :model-value="row.relationship"
              placeholder="选择关系"
              size="small"
              clearable
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => updateRow(row.id, 'relationship', v || '')"
            >
              <el-option v-for="o in RELATIONSHIP_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <!-- C: 期初余额 -->
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input-number
              :model-value="row.openingBalance"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: number) => updateRow(row.id, 'openingBalance', v || 0)"
            />
          </template>
        </el-table-column>

        <!-- D: 借方发生 -->
        <el-table-column label="借方发生" width="120" align="right">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input-number
              :model-value="row.debitOccurrence"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: number) => updateRow(row.id, 'debitOccurrence', v || 0)"
            />
          </template>
        </el-table-column>

        <!-- E: 贷方发生 -->
        <el-table-column label="贷方发生" width="120" align="right">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input-number
              :model-value="row.creditOccurrence"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: number) => updateRow(row.id, 'creditOccurrence', v || 0)"
            />
          </template>
        </el-table-column>

        <!-- F: 期末余额 (READONLY, computed C+D-E) -->
        <el-table-column label="期末余额" width="120" align="right" class-name="formula-column">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <span class="formula-value" v-html="fmtAmount(row.closingBalance)" />
          </template>
        </el-table-column>

        <!-- G: 减坏账准备 -->
        <el-table-column label="减：坏账准备" width="120" align="right">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input-number
              :model-value="row.badDebtProvision"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: number) => updateRow(row.id, 'badDebtProvision', v || 0)"
            />
          </template>
        </el-table-column>

        <!-- H: 账面价值 (READONLY, computed F-G) -->
        <el-table-column label="账面价值" width="120" align="right" class-name="formula-column">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <span class="formula-value" v-html="fmtAmount(row.bookValue)" />
          </template>
        </el-table-column>

        <!-- I: 账龄（枚举账龄：项目账龄配置段，可自定义） -->
        <el-table-column label="账龄" min-width="130">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-select
              :model-value="row.agingInfo"
              size="small"
              filterable
              allow-create
              default-first-option
              clearable
              style="width:100%"
              placeholder="选择账龄段"
              :disabled="isReadonly"
              @change="(v: string) => updateRow(row.id, 'agingInfo', v || '')"
            >
              <el-option v-for="label in agingBandLabels" :key="label" :label="label" :value="label" />
            </el-select>
          </template>
        </el-table-column>

        <!-- J: 款项性质 (textarea) -->
        <el-table-column label="款项性质" min-width="130">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input
              type="textarea"
              :rows="2"
              :model-value="row.transactionNature"
              placeholder="款项性质..."
              :disabled="isReadonly"
              @change="(v: string) => updateRow(row.id, 'transactionNature', v || '')"
            />
          </template>
        </el-table-column>

        <!-- K: 期后兑现 -->
        <el-table-column label="期后兑现" width="120" align="right">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input-number
              :model-value="row.postHonored"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: number) => updateRow(row.id, 'postHonored', v || 0)"
            />
          </template>
        </el-table-column>

        <!-- L: 索引号 -->
        <el-table-column label="索引号" width="130">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <div class="index-cell">
              <el-input
                :model-value="row.indexRef"
                size="small"
                placeholder="索引号"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'indexRef', v || '')"
              />
              <GtIndexChip
                v-if="row.indexRef"
                :value="row.indexRef"
                :context-project-id="projectId"
              />
            </div>
          </template>
        </el-table-column>

        <!-- M: 备注 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-input
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              :disabled="isReadonly"
              @change="(v: string) => updateRow(row.id, 'remark', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 操作列：删除 -->
        <el-table-column label="" width="50" fixed="right">
          <template #default="{ row }: { row: RelatedPartyRow }">
            <el-popconfirm
              title="确定删除该行？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="removeRow(row.id)"
            >
              <template #reference>
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  size="small"
                  text
                  class="delete-btn"
                >
                  ✕
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 Row14 (7列SUM) -->
      <div class="summary-row">
        <table class="summary-table">
          <thead>
            <tr>
              <th>期初余额合计</th>
              <th>借方发生合计</th>
              <th>贷方发生合计</th>
              <th>期末余额合计</th>
              <th>坏账准备合计</th>
              <th>账面价值合计</th>
              <th>期后兑现合计</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="sum-value" v-html="fmtAmount(summaryRow.openingBalance)" />
              <td class="sum-value" v-html="fmtAmount(summaryRow.debitOccurrence)" />
              <td class="sum-value" v-html="fmtAmount(summaryRow.creditOccurrence)" />
              <td class="sum-value formula-cell" v-html="fmtAmount(summaryRow.closingBalance)" />
              <td class="sum-value" v-html="fmtAmount(summaryRow.badDebtProvision)" />
              <td class="sum-value formula-cell" v-html="fmtAmount(summaryRow.bookValue)" />
              <td class="sum-value" v-html="fmtAmount(summaryRow.postHonored)" />
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 核对区 -->
      <div class="section-title">核对区</div>
      <table class="recon-table">
        <thead>
          <tr>
            <th>关联方期末余额合计</th>
            <th>审定表期末余额</th>
            <th>差异</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <!-- 关联方期末余额合计 -->
            <td class="recon-num" v-html="fmtAmount(summaryRow.closingBalance)" />

            <!-- 审定表期末余额 -->
            <td class="recon-num">
              <template v-if="adjDataLoaded">
                <span v-html="fmtAmount(adjClosingBalance)" />
              </template>
              <template v-else>
                <el-tooltip content="跨Spec审定表数据未加载" placement="top">
                  <span class="book-balance-warn">- ⚠️</span>
                </el-tooltip>
              </template>
            </td>

            <!-- 差异 -->
            <td
              class="recon-num"
              :class="{ 'diff-nonzero': reconDifference !== 0 }"
              v-html="fmtAmount(reconDifference)"
            />
          </tr>
        </tbody>
      </table>

      <!-- 审计说明 -->
      <div class="section-title">审计说明</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditNote"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditNote(v || '')"
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
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-rp-note')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 审计结论 -->
      <div class="section-title">审计结论</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditConclusion"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditConclusion(v || '')"
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
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-rp-conclusion')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 编制提示 -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
  </div>
</template>

<style scoped>
.d1-tab-related-party-check {
  padding: 12px;
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

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective p {
  margin: 0 0 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.table-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.related-party-table {
  margin-bottom: 12px;
}

/* 公式列(F和H)灰色背景 */
:deep(.el-table .formula-column) {
  background-color: #f5f7fa !important;
}

/* 公式值样式 */
.formula-value {
  font-variant-numeric: tabular-nums;
  color: #606266;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 合计行 */
.summary-row {
  margin-bottom: 16px;
}

.summary-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
}

.summary-table th,
.summary-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  text-align: right;
}

.summary-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.sum-value {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #303133;
}

.formula-cell {
  background-color: #f5f7fa;
}

/* 段落标题 */
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 18px 0 10px;
}

/* 核对区表格 */
.recon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 16px;
}

.recon-table th,
.recon-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  vertical-align: middle;
}

.recon-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.recon-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.diff-nonzero {
  color: #f56c6c !important;
  font-weight: 600;
}

.book-balance-warn {
  color: #e6a23c;
  font-size: var(--wp-font-size, 13px);
}

/* 索引号单元格 */
.index-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.index-cell .el-input {
  flex: 1;
}

/* 删除按钮 */
.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

/* 审计说明/结论 */
.note-section {
  margin-bottom: 8px;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

/* 编制提示折叠区 */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
