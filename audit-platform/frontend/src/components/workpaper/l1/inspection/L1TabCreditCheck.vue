<template>
  <div class="l1-tab-credit-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="credit-header">
      <div class="credit-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="credit-title">L1-4 征信报告核对表</h3>
      </div>
      <div class="credit-header-right">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增核对行
        </el-button>
      </div>
    </div>

    <!-- ═══ 蓝色引导区 ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="guide-num">①</span>
          <span>录入各授信银行的征信借款余额（来源：征信报告）</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">②</span>
          <span>录入对应银行的账面借款余额（来源：明细表L1-2）</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">③</span>
          <span>系统自动计算差异，差异≠0红色高亮需填写说明</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">④</span>
          <span>撰写核对结论，确认银行借款完整性</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>征信核对目标：</strong>
        通过比对征信报告借款余额与账面借款余额，验证银行借款的<strong>完整性</strong>认定。
        差异 = 征信借款余额 − 账面借款余额。差异≠0须查明原因并填写说明。
        账面余额合计应与L1-2明细表合计一致。
      </div>
    </div>

    <!-- ═══ 征信核对表主体 ═══ -->
    <el-table
      :data="computedRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      max-height="480"
    >
      <!-- 序号 -->
      <el-table-column type="index" label="#" width="42" align="center" />

      <!-- 授信银行 -->
      <el-table-column prop="bank" label="授信银行" min-width="130">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.bank"
              size="small"
              placeholder="银行名称"
              @input="(val: string) => handleFieldChange($index, 'bank', val)"
            />
          </template>
          <span v-else>{{ row.bank || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 授信额度 -->
      <el-table-column prop="creditLimit" label="授信额度" min-width="120" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.creditLimit"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'creditLimit', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.creditLimit) }}</span>
        </template>
      </el-table-column>

      <!-- 已用额度 -->
      <el-table-column prop="usedLimit" label="已用额度" min-width="120" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.usedLimit"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'usedLimit', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.usedLimit) }}</span>
        </template>
      </el-table-column>

      <!-- 征信借款余额 -->
      <el-table-column prop="creditBalance" label="征信借款余额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.creditBalance"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'creditBalance', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.creditBalance) }}</span>
        </template>
      </el-table-column>

      <!-- 账面借款余额 -->
      <el-table-column prop="bookBalance" label="账面借款余额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.bookBalance"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'bookBalance', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.bookBalance) }}</span>
        </template>
      </el-table-column>

      <!-- 差异（公式列） -->
      <el-table-column label="差异" min-width="100" align="right">
        <template #header>
          <el-tooltip content="差异 = 征信借款余额 − 账面借款余额" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="征信余额 − 账面余额" placement="top">
            <span :class="['formula-cell', { 'diff-warning': row.hasDiffWarning }]">
              {{ fmtAmount(row.computedDiff) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 差异说明 -->
      <el-table-column prop="diffExplanation" label="差异说明" min-width="180">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.diffExplanation"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              :placeholder="row.hasDiffWarning ? '差异≠0，必须说明原因' : '无差异'"
              :class="{ 'needs-explanation': row.needsExplanation }"
              @input="(val: string) => handleFieldChange($index, 'diffExplanation', val)"
            />
          </template>
          <span v-else>{{ row.diffExplanation || (row.hasDiffWarning ? '⚠️ 未填写' : '-') }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button
            text
            type="danger"
            size="small"
            @click="handleRemoveRow($index)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-section">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">征信余额合计</span>
          <span class="summary-value">{{ fmtAmount(totalCreditBalance) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">账面余额合计</span>
          <span class="summary-value">{{ fmtAmount(totalBookBalance) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">差异合计</span>
          <span :class="['summary-value', { 'diff-warning': Math.abs(totalDiff) > 0.01 }]">
            {{ fmtAmount(totalDiff) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">差异行数 / 待说明</span>
          <span :class="['summary-value', { 'diff-warning': pendingExplanationCount > 0 }]">
            {{ warningCount }} 行 / {{ pendingExplanationCount }} 待填
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :loading="aiNoteLoading"
            @click="handleAiNote"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="note"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="记录征信报告获取与核对过程、差异原因分析（承兑/信用证保证金等）、借款人担保信息及其他关注事项。"
        @input="onNoteInput"
      />
    </el-card>

    <!-- ═══ 审计结论区（textarea autosize + AI辅助） ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>征信核对结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :loading="aiConclusionLoading"
            @click="handleAiConclusion"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="根据征信核对结果，填写审计结论..."
        @input="onConclusionInput"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>数据来源</strong>：征信借款余额来自人民银行征信报告，账面余额来自明细表L1-2</li>
        <li><strong>差异公式</strong>：差异 = 征信借款余额 − 账面借款余额</li>
        <li><strong>完整性认定</strong>：账面余额≤征信余额为正常（可能有表外承诺）；账面>征信需特别关注</li>
        <li><strong>差异说明</strong>：差异≠0时必须填写说明，常见原因包括：承兑汇票保证金、信用证保证金等</li>
        <li><strong>交叉验证</strong>：账面余额合计应与审定表L1-1期末余额一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabCreditCheck — L1-4 征信报告核对表
 *
 * 差异 = 征信借款余额 − 账面借款余额
 * 差异≠0：红色高亮 + 必须填写差异说明
 * 与L1-2明细合计交叉验证
 * 叙述式结论区（textarea autosize + AI辅助）
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.5
 * Requirements: 5.1-5.5
 */
import { inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { CreditCheckRow } from '@/composables/useL1FormData'
import { useL1CreditCheck } from '@/composables/useL1CreditCheck'
import { useL1AiNote } from '@/composables/useL1AiNote'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  computedRows,
  totalCreditBalance,
  totalBookBalance,
  totalDiff,
  warningCount,
  pendingExplanationCount,
  addRow,
  removeRow,
  updateRow,
} = useL1CreditCheck(formData)

// ─── 审计说明 + 审计结论（AI 辅助，统一 useL1AiNote：修复刷新丢失+真实AI） ───

const {
  note, conclusion, aiNoteLoading, aiConclusionLoading,
  load: loadNote, onNoteInput, onConclusionInput, generateNote, generateConclusion,
} = useL1AiNote(formData, toRef(props, 'wpId'), 'cred', toRef(props, 'isReadonly'))

function _aiContext() {
  return {
    征信余额合计: totalCreditBalance.value,
    账面余额合计: totalBookBalance.value,
    差异合计: totalDiff.value,
    差异行数: warningCount.value,
    待说明行数: pendingExplanationCount.value,
  }
}
function handleAiNote() {
  generateNote('请基于征信报告核对情况撰写审计说明，重点分析征信余额与账面余额差异原因。', _aiContext())
}
function handleAiConclusion() {
  generateConclusion('请基于征信报告核对结果生成审计结论，确认银行借款完整性。', _aiContext())
}

onMounted(() => {
  loadNote()
})

// ─── 字段编辑处理 ────────────────────────────────────────────────────────────

function handleFieldChange(index: number, field: keyof CreditCheckRow, value: string | number): void {
  updateRow(index, field, value)
}

// ─── 新增行 ──────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入授信银行名称',
      '新增征信核对行',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：中国工商银行XX支行',
        inputValidator: (val: string) => {
          if (!val?.trim()) return '银行名称不能为空'
          return true
        },
      },
    )
    if (value?.trim()) {
      addRow(value.trim())
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

function handleRemoveRow(index: number): void {
  removeRow(index)
}

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row.hasDiffWarning) return 'warning-row'
  return ''
}

// ─── 工具函数 ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l1-tab-credit-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.credit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.credit-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.credit-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.credit-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 蓝色引导区 ─── */
.guide-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f7ff 100%);
  border: 1px solid #d9ecff;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 24px;
}

.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #409eff;
  line-height: 1.5;
}

.guide-num {
  font-weight: 700;
  font-size: 14px;
  min-width: 18px;
}

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 公式列表头 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 公式列单元格 ─── */
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 差异高亮 ─── */
.diff-warning {
  color: #f56c6c !important;
  font-weight: 700;
  border-bottom-color: #f56c6c;
}

/* ─── 待说明高亮 ─── */
.needs-explanation :deep(.el-textarea__inner) {
  border-color: #f56c6c;
  background: #fef0f0;
}

/* ─── 警告行背景 ─── */
:deep(.warning-row) {
  background-color: #fef0f0 !important;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 合计区 ─── */
.summary-section {
  margin-top: 16px;
  padding: 14px 18px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 15px;
  font-weight: 700;
  color: #303133;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
