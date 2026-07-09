<template>
  <div class="l6-tab-special-check">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L6-4 专项应付款检查表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('check')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>专项应付款核查要点：</strong>
        专项应付款需核查专款专用，逐项目检查实际用途与批准用途是否一致。
        ①拨款文件真实性（批文号/合同）②资金使用合规性（是否挪用/串用）③金额计算准确性
        ④手续完备性（审批流程）⑤项目进度与资金使用匹配度 ⑥结余处理合规性（到期退回/转入资本公积）。
      </div>
    </div>

    <!-- ═══ 凭证级检查表 ═══ -->
    <el-card shadow="never" class="check-table-card">
      <template #header>
        <div class="card-header">
          <span>凭证级检查行</span>
          <div class="card-header-actions">
            <el-tag size="small" :type="abnormalCount > 0 ? 'danger' : 'success'">
              异常 {{ abnormalCount }} 项
            </el-tag>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              @click="handleAddRow"
            >
              + 新增检查行
            </el-button>
            <el-button size="small" @click="handleAI('voucher')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="checkRows"
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
        border
      >
        <!-- 专项项目 -->
        <el-table-column label="专项项目" min-width="120" fixed>
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.project"
              size="small"
              placeholder="项目名称"
              @change="(val: string) => handleRowUpdate($index, 'project', val)"
            />
            <span v-else>{{ row.project || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 凭证日期 -->
        <el-table-column label="凭证日期" width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(val: string) => handleRowUpdate($index, 'voucherDate', val)"
            />
            <span v-else>{{ row.voucherDate || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 凭证号 -->
        <el-table-column label="凭证号" width="100">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherNo"
              size="small"
              placeholder="记-XXX"
              @change="(val: string) => handleRowUpdate($index, 'voucherNo', val)"
            />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 经济内容 -->
        <el-table-column label="经济内容" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.content"
              size="small"
              placeholder="经济内容摘要"
              @change="(val: string) => handleRowUpdate($index, 'content', val)"
            />
            <span v-else>{{ row.content || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 对方科目 -->
        <el-table-column label="对方科目" width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.counterAccount"
              size="small"
              placeholder="科目"
              @change="(val: string) => handleRowUpdate($index, 'counterAccount', val)"
            />
            <span v-else>{{ row.counterAccount || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 借方金额 -->
        <el-table-column label="借方金额" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.debitAmt"
              size="small"
              :controls="false"
              :precision="2"
              :min="0"
              style="width: 100%"
              @change="(val: number) => handleRowUpdate($index, 'debitAmt', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.debitAmt) }}</span>
          </template>
        </el-table-column>

        <!-- 贷方金额 -->
        <el-table-column label="贷方金额" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.creditAmt"
              size="small"
              :controls="false"
              :precision="2"
              :min="0"
              style="width: 100%"
              @change="(val: number) => handleRowUpdate($index, 'creditAmt', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.creditAmt) }}</span>
          </template>
        </el-table-column>

        <!-- 支持文件 -->
        <el-table-column label="支持文件" width="100">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.supportDoc"
              size="small"
              placeholder="📎"
              @change="(val: string) => handleRowUpdate($index, 'supportDoc', val)"
            />
            <span v-else>{{ row.supportDoc || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 5项核对 -->
        <el-table-column label="用途合规" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check1"
              size="small"
              placeholder="—"
              :class="{ 'check-fail': row.check1 === '否' }"
              @change="(val: string) => handleRowUpdate($index, 'check1', val)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="getCheckTagType(row.check1)" size="small">
              {{ row.check1 || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="金额准确" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check2"
              size="small"
              placeholder="—"
              @change="(val: string) => handleRowUpdate($index, 'check2', val)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="getCheckTagType(row.check2)" size="small">
              {{ row.check2 || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="手续完备" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check3"
              size="small"
              placeholder="—"
              @change="(val: string) => handleRowUpdate($index, 'check3', val)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="getCheckTagType(row.check3)" size="small">
              {{ row.check3 || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="进度匹配" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check4"
              size="small"
              placeholder="—"
              @change="(val: string) => handleRowUpdate($index, 'check4', val)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="getCheckTagType(row.check4)" size="small">
              {{ row.check4 || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="结余处理" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check5"
              size="small"
              placeholder="—"
              @change="(val: string) => handleRowUpdate($index, 'check5', val)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="getCheckTagType(row.check5)" size="small">
              {{ row.check5 || '—' }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" text size="small" @click="handleRemoveRow($index)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <div class="card-header-actions">
            <el-tag size="small" type="info">
              检查比例: {{ fmtPercent(checkRatio * 100) }}
            </el-tag>
            <el-tag size="small" :type="abnormalCount > 0 ? 'danger' : 'success'">
              异常: {{ abnormalCount }} 项
            </el-tag>
            <el-button size="small" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI生成结论
            </el-button>
          </div>
        </div>
      </template>

      <!-- 统计摘要 -->
      <div class="conclusion-summary">
        <div class="summary-item">
          <span class="summary-label">已检查金额</span>
          <span class="summary-value">{{ fmtAmount(totalCheckedAmount) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">本期发生额</span>
          <span class="summary-value">{{ fmtAmount(totalPeriodAmount) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">检查比例</span>
          <span class="summary-value highlight">{{ fmtPercent(checkRatio * 100) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">异常项目</span>
          <span class="summary-value" :class="{ 'text-danger': abnormalCount > 0 }">
            {{ abnormalCount }}
          </span>
        </div>
      </div>

      <!-- 结论文本 -->
      <el-input
        v-model="conclusionText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="根据上述专款专用核查结果，得出审计结论...（资金使用是否合规、是否存在挪用/串用情况、结余处理是否适当）"
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐笔检查专项应付款凭证，核实资金使用与批准用途是否一致</li>
        <li>用途合规选"否"时行自动红色高亮标记，需在备注说明具体不符情况</li>
        <li>5项核对覆盖：用途合规/金额准确/手续完备/进度匹配/结余处理</li>
        <li>检查比例 = 已检查借方金额合计 / 本期发生额，建议覆盖70%以上</li>
        <li>结余处理：到期退回原拨款单位或按规定转入资本公积</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L6TabSpecialCheck.vue — L6-4 专项应付款检查表
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 4.4
 * Requirements: 4.1-4.4
 *
 * 功能：
 * - 凭证级检查行（项目/凭证/经济内容/对方科目/借方/贷方/支持文件）
 * - 5项核对（用途合规/金额准确/手续完备/进度匹配/结余处理）下拉选择
 * - 红色高亮：check1(用途合规)='否' → row background red (isAbnormal=true)
 * - 审计结论区：检查比例+异常数量+结论textarea+AI辅助
 * - 每个section标题右侧AI辅助按钮
 * - 方法论上下文（琥珀色左边线块）
 *
 * Uses: useL6SpecialCheck + useL6FormData
 */
import { computed, inject, onMounted, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { fmtAmount, fmtPercent } from '@/utils/formatters'
import { useL6FormData } from '../../../composables/useL6FormData'
import { useL6SpecialCheck, type L6SpecialCheckRow } from '../../../composables/useL6SpecialCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useL6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetPrefix: 'L6-L6-4',
})

// ─── 检查行数据 ──────────────────────────────────────────────────────────────

const checkRows = ref<L6SpecialCheckRow[]>([])
const totalPeriodAmount = ref(0) // 本期发生额（从审定表/明细表获取）

// ─── SpecialCheck composable ─────────────────────────────────────────────────

const {
  conclusionText,
  totalCheckedAmount,
  checkRatio,
  abnormalCount,
  addRow,
  removeRow,
  updateRow,
  updateConclusion,
  saveAll,
} = useL6SpecialCheck(formData, checkRows, totalPeriodAmount)

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入专项项目名称',
      '新增检查行',
      { confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：XX科研经费' },
    )
    if (value?.trim()) {
      addRow(value.trim())
    }
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(index: number) {
  removeRow(index)
}

function handleRowUpdate(index: number, field: keyof L6SpecialCheckRow, value: string | number | boolean) {
  updateRow(index, field, value)
}

// ─── 结论更新 ─────────────────────────────────────────────────────────────────

function handleConclusionChange() {
  updateConclusion(conclusionText.value)
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  // AI辅助占位：后续集成vLLM
}

function handleReview() {
  openReviewDialog?.()
}

// ─── 行样式（红色高亮） ──────────────────────────────────────────────────────

function getRowClassName({ row }: { row: L6SpecialCheckRow }): string {
  return row.isAbnormal ? 'abnormal-row' : ''
}

function getCheckTagType(status: string): string {
  switch (status) {
    case '是': return 'success'
    case '否': return 'danger'
    case '不适用': return 'warning'
    default: return 'info'
  }
}

// ─── 数据加载 ─────────────────────────────────────────────────────────────────

async function loadCheckData() {
  await formData.loadData()

  // 从 checklist_responses 恢复检查行数据
  const rows: L6SpecialCheckRow[] = []
  let rowIdx = 1
  while (true) {
    const dataResp = formData.responses.value.get(`L6-L6-4-row-${rowIdx}-data`)
    if (!dataResp?.remark) break
    try {
      const parsed = JSON.parse(dataResp.remark)
      rows.push({
        key: parsed.key || `l6-check-${rowIdx}`,
        project: parsed.project || '',
        voucherDate: parsed.voucherDate || '',
        voucherNo: parsed.voucherNo || '',
        content: '',
        counterAccount: '',
        debitAmt: parsed.debitAmt ?? 0,
        creditAmt: parsed.creditAmt ?? 0,
        supportDoc: '',
        check1: parsed.check1 || '',
        check2: '',
        check3: '',
        check4: '',
        check5: '',
        indexRef: '',
        isAbnormal: parsed.isAbnormal ?? false,
        remark: '',
      })
    } catch {
      break
    }
    rowIdx++
  }

  // 恢复额外字段
  for (let i = 0; i < rows.length; i++) {
    const n = i + 1
    const contentResp = formData.responses.value.get(`L6-L6-4-row-${n}-content`)
    if (contentResp?.remark) rows[i].content = contentResp.remark
    const counterResp = formData.responses.value.get(`L6-L6-4-row-${n}-counter`)
    if (counterResp?.remark) rows[i].counterAccount = counterResp.remark
    const checksResp = formData.responses.value.get(`L6-L6-4-row-${n}-checks`)
    if (checksResp?.remark) {
      try {
        const checks = JSON.parse(checksResp.remark)
        if (Array.isArray(checks) && checks.length >= 5) {
          rows[i].check1 = checks[0] || ''
          rows[i].check2 = checks[1] || ''
          rows[i].check3 = checks[2] || ''
          rows[i].check4 = checks[3] || ''
          rows[i].check5 = checks[4] || ''
          rows[i].isAbnormal = checks[0] === '否'
        }
      } catch { /* ignore */ }
    }
    const refResp = formData.responses.value.get(`L6-L6-4-row-${n}-ref`)
    if (refResp?.remark) rows[i].indexRef = refResp.remark
  }

  checkRows.value = rows

  // 恢复结论
  const conclusionResp = formData.responses.value.get('L6-L6-4-conclusion')
  if (conclusionResp?.remark) {
    conclusionText.value = conclusionResp.remark
  }

  // 恢复本期发生额（从summary或审定表获取）
  const summaryResp = formData.responses.value.get('L6-L6-4-summary')
  if (summaryResp?.remark) {
    try {
      const summary = JSON.parse(summaryResp.remark)
      // totalPeriodAmount 来源于审定表的本期借方+贷方发生额合计
    } catch { /* ignore */ }
  }
}

onMounted(() => {
  loadCheckData()
})
</script>

<style scoped>
.l6-tab-special-check { padding: 12px; font-size: 13px; }

/* Header */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

/* 方法论上下文 */
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }

/* 检查表卡片 */
.check-table-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-header-actions { display: flex; align-items: center; gap: 8px; }

/* 红色高亮行（用途不符） */
:deep(.abnormal-row) {
  background-color: #fef0f0 !important;
}
:deep(.abnormal-row td) {
  background-color: #fef0f0 !important;
}
:deep(.abnormal-row:hover > td) {
  background-color: #fde2e2 !important;
}

/* 检查项否的下拉框标红 */
.check-fail :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

/* 结论区 */
.conclusion-card { margin-bottom: 16px; }
.conclusion-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
}
.summary-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.summary-label { font-size: 12px; color: #909399; }
.summary-value { font-size: 16px; font-weight: 600; color: #303133; }
.summary-value.highlight { color: #409eff; }
.summary-value.text-danger { color: #f56c6c; }

/* 表格字体统一13px */
:deep(.el-table) { font-size: 13px; }

/* 编制提示 */
.l6-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
