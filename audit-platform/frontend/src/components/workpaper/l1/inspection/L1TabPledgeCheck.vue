<template>
  <div class="l1-tab-pledge-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="pledge-header">
      <div class="pledge-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="pledge-title">L1-8 抵质押资产检查表</h3>
      </div>
      <div class="pledge-header-right">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增检查行
        </el-button>
      </div>
    </div>

    <!-- ═══ 蓝色引导区 ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="guide-num">①</span>
          <span>录入抵质押资产名称、账面价值、担保借款金额</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">②</span>
          <span>系统自动计算担保比例（担保借款/账面价值×100%）</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">③</span>
          <span>比例>100%红色警告（贷款超过资产价值）</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">④</span>
          <span>核验权属证书（房产证/土地证/股权证明等）</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>担保比例公式：</strong>
        担保比例 = 担保借款 / 账面价值 × 100%。
        <strong>警告阈值：</strong>比例 &gt; 100% 表示借款超过抵质押资产价值，存在担保不足风险。
        应关注：①资产评估是否及时更新；②是否存在重复抵押；③权属是否清晰完整。
      </div>
    </div>

    <!-- ═══ 抵质押检查表主体 ═══ -->
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

      <!-- 抵质押资产 -->
      <el-table-column prop="assetName" label="抵质押资产" min-width="160">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.assetName"
              size="small"
              placeholder="资产名称/描述"
              @input="(val: string) => handleFieldChange($index, 'assetName', val)"
            />
          </template>
          <span v-else>{{ row.assetName || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 账面价值 -->
      <el-table-column prop="bookValue" label="账面价值" min-width="130" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.bookValue"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'bookValue', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.bookValue) }}</span>
        </template>
      </el-table-column>

      <!-- 担保借款 -->
      <el-table-column prop="guaranteedLoan" label="担保借款" min-width="130" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.guaranteedLoan"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'guaranteedLoan', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.guaranteedLoan) }}</span>
        </template>
      </el-table-column>

      <!-- 担保比例（公式列） -->
      <el-table-column label="担保比例" width="110" align="center">
        <template #header>
          <el-tooltip content="担保比例 = 担保借款 / 账面价值 × 100%" placement="top">
            <span class="formula-col-header">担保比例</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="担保借款 / 账面价值 × 100%" placement="top">
            <span :class="['formula-cell', { 'ratio-warning': row.hasRatioWarning }]">
              {{ row.computedPledgeRatio > 0 ? row.computedPledgeRatio.toFixed(2) + '%' : '-' }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 权属核验 -->
      <el-table-column prop="ownershipVerified" label="权属核验" min-width="150">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-select
              :model-value="row.ownershipVerified"
              size="small"
              placeholder="核验结果"
              style="width: 100%"
              @change="(val: string) => handleFieldChange($index, 'ownershipVerified', val)"
            >
              <el-option label="已核验-权属清晰" value="已核验-权属清晰" />
              <el-option label="已核验-存在瑕疵" value="已核验-存在瑕疵" />
              <el-option label="未取得权属证明" value="未取得权属证明" />
              <el-option label="待核验" value="待核验" />
            </el-select>
          </template>
          <span v-else>{{ row.ownershipVerified || '-' }}</span>
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

    <!-- ═══ 合计区 + 综合担保比例 ═══ -->
    <div class="summary-section">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">账面价值合计</span>
          <span class="summary-value">{{ fmtAmount(totalBookValue) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">担保借款合计</span>
          <span class="summary-value">{{ fmtAmount(totalGuaranteedLoan) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">综合担保比例</span>
          <span :class="['summary-value', { 'ratio-warning': overallPledgeRatio > 100 }]">
            {{ overallPledgeRatio > 0 ? overallPledgeRatio.toFixed(2) + '%' : '-' }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">超限行数</span>
          <span :class="['summary-value', { 'ratio-warning': warningCount > 0 }]">
            {{ warningCount }} 行
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ 叙述式结论区 ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>抵质押检查结论</span>
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
        placeholder="根据抵质押资产检查结果，填写审计结论..."
        @input="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>担保比例</strong>：担保借款 / 账面价值 × 100%，比例>100%为担保不足</li>
        <li><strong>综合担保比例</strong>：所有抵质押资产合计口径的担保比例</li>
        <li><strong>权属核验</strong>：需取得并检查权属证书原件（房产证/土地使用权证/股权出质登记证明等）</li>
        <li><strong>重复抵押</strong>：关注同一资产是否为多笔借款提供担保（需分别列示）</li>
        <li><strong>价值评估</strong>：对于抵押物，关注评估时点的时效性（通常不超过1年）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabPledgeCheck — L1-8 抵质押资产检查表
 *
 * 担保比例 = 担保借款 / 账面价值 × 100%
 * 比例>100% 红色警告
 * 综合担保比例（合计口径）
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.5
 * Requirements: 6.4-6.5
 */
import { inject, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { PledgeCheckRow } from '@/composables/useL1FormData'
import { useL1PledgeCheck } from '@/composables/useL1PledgeCheck'

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
  totalGuaranteedLoan,
  totalBookValue,
  overallPledgeRatio,
  warningCount,
  addRow,
  removeRow,
  updateRow,
} = useL1PledgeCheck(formData)

// ─── 结论区 ──────────────────────────────────────────────────────────────────

const conclusion = ref('')

function handleConclusionChange(val: string): void {
  conclusion.value = val
  formData.debounceSave([{
    item_id: 'L1-plg-conclusion',
    conclusion: val || null,
    remark: null,
  }])
}

async function handleAiConclusion(): Promise<void> {
  ElMessageBox.alert('AI辅助结论生成功能即将上线', '提示')
}

// ─── 字段编辑处理 ────────────────────────────────────────────────────────────

function handleFieldChange(index: number, field: keyof PledgeCheckRow, value: string | number): void {
  updateRow(index, field, value)
}

// ─── 新增行 ──────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入抵质押资产名称',
      '新增抵质押检查行',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：XX路XX号房产/XX公司股权',
        inputValidator: (val: string) => {
          if (!val?.trim()) return '资产名称不能为空'
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
  if (row.hasRatioWarning) return 'warning-row'
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
.l1-tab-pledge-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.pledge-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.pledge-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pledge-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pledge-title {
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

/* ─── 担保比例>100%警告 ─── */
.ratio-warning {
  color: #f56c6c !important;
  font-weight: 700;
  border-bottom-color: #f56c6c;
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
