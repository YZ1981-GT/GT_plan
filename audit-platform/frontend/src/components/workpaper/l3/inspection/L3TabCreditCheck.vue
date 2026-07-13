<template>
  <div class="l3-tab-credit-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="credit-header">
      <div class="credit-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="credit-title">L3-4 征信报告核对表</h3>
      </div>
      <div class="credit-header-right">
        <el-dropdown
          size="small"
          trigger="click"
          @command="handleImportExportCommand"
        >
          <el-button size="small" :loading="isExporting || isImporting">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增核对行
        </el-button>
        <el-button size="small" type="warning" plain @click="handleAiConclusion">
          AI 辅助
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
          <span>录入对应银行的账面借款余额（来源：明细表L3-2）</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">③</span>
          <span>系统自动计算差异，差异≠0红色高亮需填写说明</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">④</span>
          <span>交叉验证L3-2合计，撰写核对结论确认完整性</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>征信核对目标：</strong>
        通过比对征信报告借款余额与账面借款余额，验证长期银行借款的<strong>完整性</strong>认定。
        差异 = 征信借款余额 − 账面借款余额。差异≠0须查明原因并填写差异说明。
        账面余额合计应与L3-2明细表期末余额合计一致（交叉验证）。
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

    <!-- ═══ 合计区 + 交叉验证 ═══ -->
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

    <!-- ═══ 叙述式结论区（textarea autosize + AI辅助） ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>征信核对结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="warning"
            plain
            @click="handleAiConclusion"
          >
            AI 辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="根据征信核对结果，填写审计结论..."
        @input="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>数据来源</strong>：征信借款余额来自人民银行征信报告，账面余额来自明细表L3-2</li>
        <li><strong>差异公式</strong>：差异 = 征信借款余额 − 账面借款余额（calcCreditDiff）</li>
        <li><strong>完整性认定</strong>：账面余额≤征信余额为正常（可能有表外承诺）；账面>征信需特别关注</li>
        <li><strong>差异说明</strong>：差异≠0时必须填写说明，常见原因包括：期末新增借款征信未更新、已还未核销等</li>
        <li><strong>交叉验证</strong>：账面余额合计应与L3-2明细表期末余额合计一致（crossValidateWithDetail）</li>
        <li><strong>导入导出</strong>：支持导出模板/导出数据/导入数据（sheet='L3-4'）</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabCreditCheck — L3-4 征信报告核对表
 *
 * 差异 = 征信借款余额 − 账面借款余额 (calcCreditDiff)
 * 差异≠0：红色高亮 + 必须填写差异说明
 * 与L3-2明细合计交叉验证 (crossValidateWithDetail)
 * 叙述式结论区（textarea autosize + AI辅助）
 * 导入导出三级 sheet='L3-4'
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.5
 * Requirements: 6.1-6.5
 */
import { inject, ref, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useL3CreditCheck, type L3CreditCheckRow } from '@/composables/useL3CreditCheck'
import { useL3ImportExport } from '@/composables/useL3ImportExport'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

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

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── Reactive rows ───────────────────────────────────────────────────────────

const creditCheckRows = ref<L3CreditCheckRow[]>([])

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  computedRows,
  totalCreditBalance,
  totalBookBalance,
  totalDiff,
  warningCount,
  pendingExplanationCount,
  crossValidateWithDetail,
  addRow,
  removeRow,
  updateRow,
} = useL3CreditCheck(formData, creditCheckRows)

// ─── Composable: 导入导出 ────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const {
  isExporting,
  isImporting,
  exportTemplate,
  exportData,
  importData,
} = useL3ImportExport(wpIdRef, projectIdRef)

// ─── 结论区 ──────────────────────────────────────────────────────────────────

const conclusion = ref('')

function handleConclusionChange(val: string): void {
  conclusion.value = val
  formData.debouncedSave('L3-cred-conclusion', {
    remark: val || null,
  })
}

async function handleAiConclusion(): Promise<void> {
  try {
    const res = await (await import('@/utils/http')).default.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'credit-check-conclusion',
      prompt: '请基于征信报告核对情况，生成审计结论（包含余额一致性、差异说明、信用风险评估）',
      context: { rowCount: creditRows.value.length },
    })
    const content = res.data?.data?.content
    if (content) { conclusion.value = content; handleConclusionChange(content) }
  } catch { (await import('element-plus')).ElMessage.info('AI辅助暂不可用') }
}

// ─── 字段编辑处理 ────────────────────────────────────────────────────────────

function handleFieldChange(index: number, field: keyof L3CreditCheckRow, value: string | number): void {
  updateRow(index, field, value)
}

// ─── 新增行（ElMessageBox.prompt） ───────────────────────────────────────────

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

// ─── 导入导出命令 ────────────────────────────────────────────────────────────

const fileInputRef = ref<HTMLInputElement | null>(null)

function handleImportExportCommand(command: string): void {
  switch (command) {
    case 'export-template':
      exportTemplate('L3-4')
      break
    case 'export-data':
      exportData('L3-4')
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const result = await importData(file, 'L3-4')
  if (result) {
    ElMessage.success(`导入完成：${result.rowCount} 行`)
  }

  // 重置 input
  input.value = ''
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
.l3-tab-credit-check {
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
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
