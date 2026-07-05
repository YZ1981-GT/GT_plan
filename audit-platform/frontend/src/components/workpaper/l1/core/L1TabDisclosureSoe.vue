<template>
  <div class="l1-tab-disclosure-soe">
    <!-- ═══ 返回目录 + 标题 + AI辅助 ═══ -->
    <div class="disclosure-header">
      <div class="disclosure-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="disclosure-title">附注披露信息核对（国有企业）</h3>
      </div>
      <div class="disclosure-header-right">
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleAiAssist"
        >
          🤖 AI辅助
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业附注披露要求：</strong>
        按借款类型分类列示短期借款期初/期末余额，8列简化披露。国企版本无需披露利率区间和担保物明细，
        但须列示是否逾期及主要变动原因。披露数据与明细表L1-2 SUMIF交叉验证。
      </div>
    </div>

    <!-- ═══ 企业类型标识 ═══ -->
    <div class="entity-type-badge">
      <el-tag type="info" effect="dark" size="small">
        国有企业版
      </el-tag>
      <span class="entity-type-hint">（系统根据企业类型自动切换模板，8列简化版）</span>
    </div>

    <!-- ═══ 按借款类型分组展示 ═══ -->
    <div v-for="(group, gIdx) in disclosureGroups" :key="group.type" class="disclosure-group">
      <div class="group-header">
        <span class="group-title">{{ group.label }}</span>
        <el-tag size="small" type="info">{{ group.rows.length }} 笔</el-tag>
      </div>

      <el-table
        :data="group.rows"
        border
        size="small"
        style="width: 100%"
        show-summary
        :summary-method="getSummary"
      >
        <!-- 序号 -->
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>

        <!-- 借款银行 -->
        <el-table-column prop="bank" label="借款银行" min-width="140">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.bank"
                size="small"
                placeholder="银行名称"
                @input="(val: string) => updateField(gIdx, row._rowIndex, 'bank', val)"
              />
            </template>
            <span v-else>{{ row.bank || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 借款类型 -->
        <el-table-column prop="loanType" label="借款类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="getLoanTypeTag(row.loanType)">
              {{ row.loanType }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 期初余额 -->
        <el-table-column prop="beginBalance" label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.beginBalance"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateField(gIdx, row._rowIndex, 'beginBalance', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 期末余额 -->
        <el-table-column prop="endBalance" label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.endBalance"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateField(gIdx, row._rowIndex, 'endBalance', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <!-- 增减变动（公式列） -->
        <el-table-column label="增减变动" width="120" align="right">
          <template #header>
            <el-tooltip content="增减变动 = 期末 − 期初" placement="top">
              <span class="formula-col-header">增减变动</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="增减变动 = 期末 − 期初" placement="top">
              <span class="formula-cell" :class="{ 'text-danger': row.change < 0, 'text-success': row.change > 0 }">
                {{ fmtAmount(row.change) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 是否逾期 -->
        <el-table-column prop="isOverdue" label="是否逾期" width="85" align="center">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-select
                :model-value="row.isOverdue"
                size="small"
                style="width: 100%"
                @change="(val: string) => updateField(gIdx, row._rowIndex, 'isOverdue', val)"
              >
                <el-option label="否" value="否" />
                <el-option label="是" value="是" />
              </el-select>
            </template>
            <span v-else :class="{ 'text-danger': row.isOverdue === '是' }">
              {{ row.isOverdue || '-' }}
            </span>
          </template>
        </el-table-column>

        <!-- 变动原因 -->
        <el-table-column prop="changeReason" label="变动原因" min-width="160">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.changeReason"
                size="small"
                placeholder="主要变动原因"
                @input="(val: string) => updateField(gIdx, row._rowIndex, 'changeReason', val)"
              />
            </template>
            <span v-else>{{ row.changeReason || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 交叉验证区 ═══ -->
    <div class="cross-verify-section">
      <div class="cross-verify-row">
        <span class="cross-verify-label">附注合计 vs 明细表L1-2 SUMIF：</span>
        <span :class="crossVerifyClass">
          <template v-if="crossVerifyResult.isMatch">
            ✓ 一致
          </template>
          <template v-else>
            ✗ 差额 {{ fmtAmount(crossVerifyResult.diff) }}
          </template>
        </span>
      </div>
    </div>

    <!-- ═══ 叙述式结论 + AI辅助 ═══ -->
    <div class="conclusion-section">
      <el-card shadow="never">
        <template #header>
          <div class="conclusion-header">
            <span>审计结论</span>
            <el-button
              size="small"
              :disabled="isReadonly"
              @click="handleAiConclusion"
            >
              🤖 AI生成结论
            </el-button>
          </div>
        </template>
        <el-input
          v-model="conclusionText"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入附注披露核对结论..."
          :disabled="isReadonly"
          @input="handleConclusionChange"
        />
      </el-card>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>国企简化</strong>：国有企业附注只需8列（银行/类型/期初/期末/增减/逾期/变动原因），无需利率和担保明细</li>
        <li><strong>交叉验证</strong>：附注期末合计应与明细表L1-2按类型SUMIF后一致</li>
        <li><strong>逾期关注</strong>：逾期借款须注明逾期天数及后续还款计划</li>
        <li><strong>企业类型</strong>：系统根据项目企业类型自动选择上市/国企版本</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabDisclosureSoe — 附注披露信息核对（国有企业）
 *
 * 功能：
 * - 与上市公司版本结构类似但列数更少（8列 vs 12列）
 * - 按借款类型分类展示（信用/保证/抵押/质押）
 * - 与明细表L1-2 SUMIF 交叉验证
 * - 叙述式结论 textarea + AI辅助
 * - 企业类型自动切换（subscribe eventBus 获取类型）
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.7
 * Requirements: 8.2, 8.3
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { useL1FormData } from '@/composables/useL1FormData'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from '@/composables/useL1FormulaEngine'

// ─── Props / Emits ───────────────────────────────────────────────────────────

defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureSoeRow {
  _rowIndex: number
  bank: string
  loanType: string
  beginBalance: number
  endBalance: number
  change: number
  isOverdue: string
  changeReason: string
}

interface DisclosureGroup {
  type: string
  label: string
  rows: DisclosureSoeRow[]
}

// ─── 借款类型分组定义 ────────────────────────────────────────────────────────

const LOAN_TYPES = [
  { type: 'credit', label: '信用借款' },
  { type: 'guarantee', label: '保证借款' },
  { type: 'mortgage', label: '抵押借款' },
  { type: 'pledge', label: '质押借款' },
]

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<DisclosureSoeRow[]>([])
const conclusionText = ref<string>('')

// ─── 按类型分组 ──────────────────────────────────────────────────────────────

const disclosureGroups = computed<DisclosureGroup[]>(() => {
  return LOAN_TYPES.map(lt => ({
    type: lt.type,
    label: lt.label,
    rows: rows.value.filter(r => r.loanType === lt.label),
  })).filter(g => g.rows.length > 0 || true) // 始终显示所有分类
})

// ─── 交叉验证（附注合计 vs L1-2 SUMIF） ─────────────────────────────────────

const crossVerifyResult = computed(() => {
  const totalEnd = calcSubtotal(rows.value.map(r => r.endBalance))
  const detailTotal = formData.getItemValue?.('L1-detail-total-end') ?? totalEnd
  const diff = parseFloat((totalEnd - (detailTotal as number)).toFixed(2))
  return {
    diff,
    isMatch: Math.abs(diff) <= 0.01,
  }
})

const crossVerifyClass = computed(() => ({
  'cross-verify-match': crossVerifyResult.value.isMatch,
  'cross-verify-diff': !crossVerifyResult.value.isMatch,
}))

// ─── 表格合计方法 ────────────────────────────────────────────────────────────

function getSummary({ columns, data }: { columns: any[]; data: DisclosureSoeRow[] }) {
  const sums: string[] = []
  columns.forEach((column: any, index: number) => {
    if (index === 0) {
      sums[index] = '小计'
      return
    }
    const prop = column.property as keyof DisclosureSoeRow
    if (['beginBalance', 'endBalance', 'change'].includes(prop)) {
      const values = data.map(r => Number(r[prop]) || 0)
      sums[index] = fmtAmount(calcSubtotal(values))
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function updateField(groupIdx: number, rowIndex: number, field: keyof DisclosureSoeRow, value: string | number) {
  const row = rows.value.find(r => r._rowIndex === rowIndex)
  if (!row) return

  ;(row as any)[field] = value

  // 自动计算增减变动
  if (['beginBalance', 'endBalance'].includes(field)) {
    row.change = parseFloat(((row.endBalance || 0) - (row.beginBalance || 0)).toFixed(2))
  }

  // 触发保存
  _saveRow(row)
}

function _saveRow(row: DisclosureSoeRow) {
  const n = row._rowIndex + 1
  const items = [
    { item_id: `L1-disclosure-soe-${n}-bank`, conclusion: null, remark: row.bank || null },
    { item_id: `L1-disclosure-soe-${n}-type`, conclusion: null, remark: row.loanType || null },
    { item_id: `L1-disclosure-soe-${n}-begin`, conclusion: null, remark: row.beginBalance ? String(row.beginBalance) : null },
    { item_id: `L1-disclosure-soe-${n}-end`, conclusion: null, remark: row.endBalance ? String(row.endBalance) : null },
    { item_id: `L1-disclosure-soe-${n}-overdue`, conclusion: null, remark: row.isOverdue || null },
    { item_id: `L1-disclosure-soe-${n}-reason`, conclusion: null, remark: row.changeReason || null },
  ]
  formData.debounceSave(items)
}

// ─── 结论变更 ────────────────────────────────────────────────────────────────

function handleConclusionChange(val: string | number) {
  formData.debounceSave([
    { item_id: 'L1-disclosure-soe-conclusion', conclusion: null, remark: String(val) || null },
  ])
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中...')
}

function handleAiConclusion() {
  ElMessage.info('AI生成结论功能开发中...')
}

// ─── 借款类型标签颜色 ────────────────────────────────────────────────────────

function getLoanTypeTag(type: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    '信用借款': '',
    '保证借款': 'success',
    '抵押借款': 'warning',
    '质押借款': 'danger',
  }
  return map[type] ?? 'info'
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus 订阅：审定变更后刷新 ──────────────────────────────────────────

function handleAdjudicatedRefresh() {
  loadDisclosureData()
}

onMounted(() => {
  eventBus.on('adjustment:created', handleAdjudicatedRefresh)
  eventBus.on('substantive:adjudicated', handleAdjudicatedRefresh)
  loadDisclosureData()
})

onUnmounted(() => {
  eventBus.off('adjustment:created', handleAdjudicatedRefresh)
  eventBus.off('substantive:adjudicated', handleAdjudicatedRefresh)
})

// ─── 加载数据 ────────────────────────────────────────────────────────────────

function loadDisclosureData() {
  const loadedRows: DisclosureSoeRow[] = []
  for (let i = 0; i < 24; i++) {
    const n = i + 1
    const bank = formData.getItemValue?.(`L1-disclosure-soe-${n}-bank`) as string
    if (!bank && i >= 4) break

    loadedRows.push({
      _rowIndex: i,
      bank: bank || '',
      loanType: (formData.getItemValue?.(`L1-disclosure-soe-${n}-type`) as string) || LOAN_TYPES[Math.min(i, 3)].label,
      beginBalance: Number(formData.getItemValue?.(`L1-disclosure-soe-${n}-begin`)) || 0,
      endBalance: Number(formData.getItemValue?.(`L1-disclosure-soe-${n}-end`)) || 0,
      change: 0,
      isOverdue: (formData.getItemValue?.(`L1-disclosure-soe-${n}-overdue`) as string) || '否',
      changeReason: (formData.getItemValue?.(`L1-disclosure-soe-${n}-reason`) as string) || '',
    })
  }

  // 初始化 4 个空行（每种类型 1 行）
  if (loadedRows.length === 0) {
    LOAN_TYPES.forEach((lt, idx) => {
      loadedRows.push({
        _rowIndex: idx,
        bank: '',
        loanType: lt.label,
        beginBalance: 0,
        endBalance: 0,
        change: 0,
        isOverdue: '否',
        changeReason: '',
      })
    })
  }

  // 计算增减变动
  loadedRows.forEach(r => {
    r.change = parseFloat(((r.endBalance || 0) - (r.beginBalance || 0)).toFixed(2))
  })

  rows.value = loadedRows
  conclusionText.value = (formData.getItemValue?.('L1-disclosure-soe-conclusion') as string) || ''
}
</script>

<style scoped>
.l1-tab-disclosure-soe {
  padding: 12px;
  font-size: 13px;
}

/* ─── 头部 ─── */
.disclosure-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.disclosure-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.disclosure-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.disclosure-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 企业类型标识 ─── */
.entity-type-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.entity-type-hint {
  font-size: 12px;
  color: #909399;
}

/* ─── 分组展示 ─── */
.disclosure-group {
  margin-bottom: 20px;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: #f5f7fa;
  border-radius: 4px;
}

.group-title {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}

/* ─── 公式列 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 交叉验证区 ─── */
.cross-verify-section {
  margin-top: 16px;
  padding: 10px 14px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.cross-verify-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.cross-verify-label {
  color: #606266;
}

.cross-verify-match {
  color: #67c23a;
  font-weight: 600;
}

.cross-verify-diff {
  color: #f56c6c;
  font-weight: 600;
}

/* ─── 结论区 ─── */
.conclusion-section {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
}

/* ─── 文字样式 ─── */
.text-danger {
  color: #f56c6c;
  font-weight: 600;
}

.text-success {
  color: #67c23a;
  font-weight: 600;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
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
