<script setup lang="ts">
/**
 * D1TabPledgeCheck.vue — D1-12 应收票据质押检查表 HTML渲染
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 11.1
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换（结构化视图 | 在线编辑）
 * - 审计目标区域（只读静态文本）
 * - el-table 16列宽表（横向滚动），嵌套分组表头：
 *   - "票据基本信息"二级表头（A-I 9列）
 *   - "质押详情"二级表头（J-P 7列）
 * - 票据类型+号码列 fixed="left"（横向滚动时可见）
 * - 金额列（票据金额/质押金额）右对齐，文本列左对齐
 * - "添加质押票据"按钮 + 动态行增删
 * - 合计行 Row18（H18票据金额合计 | J18质押金额合计）
 * - 质押汇总区：H18 | J18 | 审定表净值(跨Spec/-+⚠️) | 质押比例(%或N/A)
 * - 质押比例>50%：橙色预警标签
 * - 审计说明/结论 + 编制提示（CAS 36第六十六条/合法性/持续经营/期限匹配）
 * - GtOnlyOfficeSheet v-if isOOMode
 *
 * Requirements: 7.1-7.6, 8.1-8.6, 9.1-9.5, 14.1-14.5, 18.1-18.5, 18.7
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD1PledgeCheck } from '../composables/useD1PledgeCheck'
import {
  NOTE_TYPE_OPTIONS,
  formatNegativeAmount,
  type PledgeRow,
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

const injectedDisplayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  addRow,
  removeRow,
  updateRow,
  sumNoteAmount,
  sumPledgeAmount,
  adjBookValue,
  adjDataLoaded,
  pledgeRatio,
  pledgeRatioDisplay,
  isPledgeWarning,
  auditNote,
  auditConclusion,
  saveAuditNote,
  saveAuditConclusion,
  exportTemplate,
  exportData,
  importData,
  importFromMemo,
  appendFromMemo,
} = useD1PledgeCheck({
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

const wpIdRef = toRef(props, 'wpId')
const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

function buildPledgeAiContext(extra = ''): Record<string, unknown> {
  return {
    sheet: 'D1-12',
    rowCount: rows.value.length,
    sumNoteAmount: sumNoteAmount.value,
    sumPledgeAmount: sumPledgeAmount.value,
    adjBookValue: adjBookValue.value,
    pledgeRatio: pledgeRatio.value,
    pledgeRatioDisplay: pledgeRatioDisplay.value,
    isPledgeWarning: isPledgeWarning.value,
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
      buildPledgeAiContext('基于质押金额、质押比例、审定表净值及风险提示生成审计说明。'),
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
      buildPledgeAiContext(`质押比例：${pledgeRatioDisplay.value}`),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

// ─── 从备查簿导入 ─────────────────────────────────────────────────────────────

async function handleImportFromMemo() {
  // 先预检查有多少行可导入
  const preview = importFromMemo()
  if (preview.count === 0) {
    ElMessage.info('备查簿中未发现已质押票据')
    return
  }

  try {
    await ElMessageBox.confirm(
      `将新增${preview.count}行质押票据（不会覆盖已有行），是否继续？`,
      '从备查簿导入',
      { confirmButtonText: '确定导入', cancelButtonText: '取消', type: 'info' },
    )
    const count = appendFromMemo()
    ElMessage.success(`成功导入${count}行已质押票据`)
  } catch {
    // 用户取消
  }
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  '质押票据作为受限资产的披露要求（CAS 36第六十六条）：在附注中披露因担保、质押等受到限制的资产项目、账面价值及限制情况。',
  '质权设立的合法性审核要点：确认质押协议是否有效签署、质押登记是否完成（票据权利质押需通知出票人/承兑人）、质押生效条件是否满足。',
  '质押比例对持续经营假设的影响评估：当质押比例超过50%时，关注企业是否存在流动性风险，评估对持续经营假设的影响。',
  '质押期限与票据到期日匹配性检查：验证质押期限是否覆盖贷款期限，到期日早于质押解除日的票据需关注续质或替换安排。',
]
</script>

<template>
  <div class="d1-tab-pledge-check">
      <div class="tab-header">
        <h4>质押检查 D1-12</h4>
        <GtReviewTrigger section-id="D1-pledge-header" />
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
          <p>核实应收票据质押情况的完整性和准确性，评估受限资产的披露充分性和质押风险。</p>
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
          + 添加质押票据
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleImportFromMemo">
          从备查簿导入已质押票据
        </el-button>
      </div>

      <!-- 16列宽表 -->
      <el-table
        :data="rows"
        border
        size="small"
        max-height="500"
        class="pledge-table"
        style="width: 100%"
      >
        <!-- 票据基本信息（A-I 9列） -->
        <el-table-column label="票据基本信息" header-align="center">
          <!-- A: 票据类型 (fixed left) -->
          <el-table-column label="票据类型" width="130" fixed="left">
            <template #default="{ row }: { row: PledgeRow }">
              <el-select
                :model-value="row.noteType"
                placeholder="选择类型"
                size="small"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'noteType', v || '')"
              >
                <el-option v-for="o in NOTE_TYPE_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
              <GtReviewDot row-prefix="D1-pledge" :row-key="row.id" />
            </template>
          </el-table-column>

          <!-- B: 票据号码 (fixed left) -->
          <el-table-column label="票据号码" min-width="140" fixed="left">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.noteNo"
                size="small"
                placeholder="票据号码"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'noteNo', v || '')"
              />
            </template>
          </el-table-column>

          <!-- C: 收到日期 -->
          <el-table-column label="收到日期" width="120">
            <template #default="{ row }: { row: PledgeRow }">
              <el-date-picker
                :model-value="row.receiveDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="收到日期"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'receiveDate', v || '')"
              />
            </template>
          </el-table-column>

          <!-- D: 前手 -->
          <el-table-column label="前手" min-width="100">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.predecessor"
                size="small"
                placeholder="前手"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'predecessor', v || '')"
              />
            </template>
          </el-table-column>

          <!-- E: 出票日 -->
          <el-table-column label="出票日" width="120">
            <template #default="{ row }: { row: PledgeRow }">
              <el-date-picker
                :model-value="row.issueDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="出票日"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'issueDate', v || '')"
              />
            </template>
          </el-table-column>

          <!-- F: 出票人 -->
          <el-table-column label="出票人" min-width="100">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.drawer"
                size="small"
                placeholder="出票人"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'drawer', v || '')"
              />
            </template>
          </el-table-column>

          <!-- G: 承兑人 -->
          <el-table-column label="承兑人" min-width="100">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.acceptor"
                size="small"
                placeholder="承兑人"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'acceptor', v || '')"
              />
            </template>
          </el-table-column>

          <!-- H: 票据金额 -->
          <el-table-column label="票据金额" width="120" align="right">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input-number
                :model-value="row.noteAmount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => updateRow(row.id, 'noteAmount', v || 0)"
              />
            </template>
          </el-table-column>

          <!-- I: 到期日 -->
          <el-table-column label="到期日" width="120">
            <template #default="{ row }: { row: PledgeRow }">
              <el-date-picker
                :model-value="row.maturityDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="到期日"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'maturityDate', v || '')"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 质押详情（J-P 7列） -->
        <el-table-column label="质押详情" header-align="center">
          <!-- J: 质押金额 -->
          <el-table-column label="质押金额" width="120" align="right">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input-number
                :model-value="row.pledgeAmount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => updateRow(row.id, 'pledgeAmount', v || 0)"
              />
            </template>
          </el-table-column>

          <!-- K: 质权人 -->
          <el-table-column label="质权人" min-width="100">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.pledgee"
                size="small"
                placeholder="质权人"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'pledgee', v || '')"
              />
            </template>
          </el-table-column>

          <!-- L: 质押原因 -->
          <el-table-column label="质押原因" min-width="100">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.pledgeReason"
                size="small"
                placeholder="质押原因"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'pledgeReason', v || '')"
              />
            </template>
          </el-table-column>

          <!-- M: 质押条件 -->
          <el-table-column label="质押条件" min-width="100">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.pledgeCondition"
                size="small"
                placeholder="质押条件"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'pledgeCondition', v || '')"
              />
            </template>
          </el-table-column>

          <!-- N: 质押期限 (date range) -->
          <el-table-column label="质押期限" width="220">
            <template #default="{ row }: { row: PledgeRow }">
              <el-date-picker
                :model-value="row.pledgePeriod"
                type="daterange"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                start-placeholder="起始"
                end-placeholder="到期"
                range-separator="~"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: any) => updateRow(row.id, 'pledgePeriod', v ? (Array.isArray(v) ? v.join(' ~ ') : v) : '')"
              />
            </template>
          </el-table-column>

          <!-- O: 质押协议 -->
          <el-table-column label="质押协议" min-width="100">
            <template #default="{ row }: { row: PledgeRow }">
              <el-input
                :model-value="row.pledgeAgreement"
                size="small"
                placeholder="质押协议"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'pledgeAgreement', v || '')"
              />
            </template>
          </el-table-column>

          <!-- P: 索引号 -->
          <el-table-column label="索引号" width="130">
            <template #default="{ row }: { row: PledgeRow }">
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
        </el-table-column>

        <!-- 操作列：删除 -->
        <el-table-column label="" width="50" fixed="right">
          <template #default="{ row }: { row: PledgeRow }">
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

      <!-- 合计行 Row18 -->
      <div class="summary-row">
        <span class="summary-label">票据金额合计：</span>
        <span class="summary-value" v-html="fmtAmount(sumNoteAmount)" />
        <span class="summary-separator">|</span>
        <span class="summary-label">质押金额合计：</span>
        <span class="summary-value" v-html="fmtAmount(sumPledgeAmount)" />
      </div>

      <!-- 质押汇总区 -->
      <div class="section-title">质押汇总</div>
      <table class="recon-table">
        <thead>
          <tr>
            <th>票据金额合计 (H18)</th>
            <th>质押金额合计 (J18)</th>
            <th>审定表净值</th>
            <th>质押比例</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <!-- H18 票据金额合计 -->
            <td class="recon-num" v-html="fmtAmount(sumNoteAmount)" />

            <!-- J18 质押金额合计 -->
            <td class="recon-num" v-html="fmtAmount(sumPledgeAmount)" />

            <!-- 审定表净值 -->
            <td class="recon-num">
              <template v-if="adjDataLoaded">
                <span v-html="fmtAmount(adjBookValue ?? 0)" />
              </template>
              <template v-else>
                <el-tooltip content="跨Spec审定表数据未加载" placement="top">
                  <span class="adj-warn">- ⚠️</span>
                </el-tooltip>
              </template>
            </td>

            <!-- 质押比例 -->
            <td class="recon-num" :class="{ 'pledge-warning-cell': isPledgeWarning }">
              {{ pledgeRatioDisplay }}
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 质押比例>50%预警 -->
      <el-tag
        v-if="isPledgeWarning"
        type="warning"
        size="large"
        effect="light"
        class="pledge-warning-tag"
      >
        ⚠️ 质押比例超过50%，请关注受限资产披露
      </el-tag>

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
            @click="onReview('D1-pledge-note')"
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
            @click="onReview('D1-pledge-conclusion')"
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
.d1-tab-pledge-check {
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
  font-size: 13px;
  line-height: 1.6;
}

.table-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.pledge-table {
  margin-bottom: 12px;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 合计行 */
.summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 16px;
}

.summary-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.summary-value {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
}

.summary-separator {
  color: #c0c4cc;
  margin: 0 8px;
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
  font-size: 13px;
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

.adj-warn {
  color: #e6a23c;
  font-size: 13px;
}

.pledge-warning-cell {
  color: #e6a23c !important;
  font-weight: 600;
}

/* 质押预警标签 */
.pledge-warning-tag {
  margin-bottom: 16px;
  font-size: 13px;
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
  font-size: 13px;
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
