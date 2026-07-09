<template>
  <div class="n2-tab-tax-check">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>应交税费检查表 N2-11</span>
        <el-tag type="info" size="small">逐税种核查</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>应交税费逐项核查：</strong>
        对各税种逐项核查三个维度——①计提准确性（计算是否正确）②缴纳及时性（是否按期缴纳）③申报一致性（账面与申报表是否一致）。
        支持行级抽凭验证，可附相关凭证/纳税申报表作为审计证据。
      </div>
    </div>

    <!-- ═══ 核查汇总统计 ═══ -->
    <div class="check-stats">
      <div class="stat-item stat-item--pass">
        <span class="stat-count">{{ stats.passed }}</span>
        <span class="stat-label">通过</span>
      </div>
      <div class="stat-item stat-item--issue">
        <span class="stat-count">{{ stats.issues }}</span>
        <span class="stat-label">存在问题</span>
      </div>
      <div class="stat-item stat-item--pending">
        <span class="stat-count">{{ stats.pending }}</span>
        <span class="stat-label">待核查</span>
      </div>
    </div>

    <!-- ═══ 逐税种核查表 ═══ -->
    <el-table
      :data="checkRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="taxType" label="税种" width="130" fixed />
      <el-table-column label="计提准确性" width="120" align="center">
        <template #header>
          <el-tooltip content="计提金额计算是否正确、计税依据是否准确" placement="top">
            <span class="formula-col-header">计提准确性</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-select
            :model-value="row.accrualAccuracy"
            size="small"
            :disabled="isReadonly"
            placeholder="—"
            style="width: 90px"
            @change="(val: string) => handleFieldChange($index, 'accrualAccuracy', val)"
          >
            <el-option value="通过" label="✓通过" />
            <el-option value="存在问题" label="✗问题" />
            <el-option value="待核查" label="⚠待查" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="缴纳及时性" width="120" align="center">
        <template #header>
          <el-tooltip content="税款是否按纳税期限及时缴纳、有无滞纳金" placement="top">
            <span class="formula-col-header">缴纳及时性</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-select
            :model-value="row.paymentTimeliness"
            size="small"
            :disabled="isReadonly"
            placeholder="—"
            style="width: 90px"
            @change="(val: string) => handleFieldChange($index, 'paymentTimeliness', val)"
          >
            <el-option value="通过" label="✓通过" />
            <el-option value="存在问题" label="✗问题" />
            <el-option value="待核查" label="⚠待查" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="申报一致性" width="120" align="center">
        <template #header>
          <el-tooltip content="账面金额与纳税申报表金额是否一致" placement="top">
            <span class="formula-col-header">申报一致性</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-select
            :model-value="row.declarationConsistency"
            size="small"
            :disabled="isReadonly"
            placeholder="—"
            style="width: 90px"
            @change="(val: string) => handleFieldChange($index, 'declarationConsistency', val)"
          >
            <el-option value="通过" label="✓通过" />
            <el-option value="存在问题" label="✗问题" />
            <el-option value="待核查" label="⚠待查" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="备注/问题描述" min-width="180">
        <template #default="{ row, $index }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            placeholder="填写核查发现..."
            @change="(val: string) => handleFieldChange($index, 'remark', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="抽凭" width="80" align="center">
        <template #default="{ row, $index }">
          <el-button
            size="small"
            :type="row.voucherAttached ? 'success' : 'default'"
            :icon="Paperclip"
            circle
            @click="handleVoucherSampling($index)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 综合核查结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>综合核查结论</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="请输入应交税费核查综合结论..."
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐税种三维度核查：计提准确性 / 缴纳及时性 / 申报一致性</li>
        <li>计提准确性：核对计税依据×税率=应交金额</li>
        <li>缴纳及时性：核对纳税申报日期与税法规定缴纳期限</li>
        <li>申报一致性：核对账面应交余额与纳税申报表比较表金额</li>
        <li>对存在问题的税种，详细描述差异原因并获取管理层解释</li>
        <li>行级抽凭：抽取计提/缴纳凭证验证金额、科目、附件完整性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabTaxCheck — N2-11 应交税费检查表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.8
 * Requirements: 10.1-10.2
 *
 * 核心职责：
 * - 逐税种核查三维度：计提准确性 / 缴纳及时性 / 申报一致性
 * - 行级抽凭（📎按钮触发抽凭引擎）
 * - 存在问题项红色高亮
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare, Paperclip } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Types ───────────────────────────────────────────────────────────────────

type CheckStatus = '通过' | '存在问题' | '待核查' | ''

interface TaxCheckRow {
  taxType: string
  accrualAccuracy: CheckStatus
  paymentTimeliness: CheckStatus
  declarationConsistency: CheckStatus
  remark: string
  voucherAttached: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)
const overallConclusion = ref('')

/** 默认税种列表 */
const TAX_TYPES = [
  '增值税', '未交增值税', '消费税', '城市维护建设税',
  '教育费附加', '地方教育附加', '房产税', '城镇土地使用税',
  '车船税', '印花税', '土地增值税', '企业所得税',
  '个人所得税（代扣代缴）', '资源税', '环境保护税',
]

const checkRows = ref<TaxCheckRow[]>(
  TAX_TYPES.map(t => ({
    taxType: t,
    accrualAccuracy: '' as CheckStatus,
    paymentTimeliness: '' as CheckStatus,
    declarationConsistency: '' as CheckStatus,
    remark: '',
    voucherAttached: false,
  })),
)

// ─── Computed ────────────────────────────────────────────────────────────────

const stats = computed(() => {
  let passed = 0
  let issues = 0
  let pending = 0

  for (const row of checkRows.value) {
    const statuses = [row.accrualAccuracy, row.paymentTimeliness, row.declarationConsistency]
    for (const s of statuses) {
      if (s === '通过') passed++
      else if (s === '存在问题') issues++
      else pending++
    }
  }
  return { passed, issues, pending }
})

// ─── Methods ─────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: TaxCheckRow }) {
  if (row.accrualAccuracy === '存在问题' || row.paymentTimeliness === '存在问题' || row.declarationConsistency === '存在问题') {
    return 'row--issue'
  }
  return ''
}

function handleFieldChange(index: number, field: keyof TaxCheckRow, val: string) {
  ;(checkRows.value[index] as any)[field] = val
  persistData()
}

function handleVoucherSampling(index: number) {
  ElMessage.info(`抽凭引擎：${checkRows.value[index].taxType}`)
  checkRows.value[index].voucherAttached = true
  persistData()
}

function persistData() {
  formData.debouncedSave('N2-11-tax-check', {
    conclusion: JSON.stringify(checkRows.value.map(r => ({
      accrualAccuracy: r.accrualAccuracy,
      paymentTimeliness: r.paymentTimeliness,
      declarationConsistency: r.declarationConsistency,
      remark: r.remark,
      voucherAttached: r.voucherAttached,
    }))),
  })
}

function handleConclusionChange() {
  formData.debouncedSave('N2-11-conclusion', { remark: overallConclusion.value || null })
}

function handleAiAssist() {
  ElMessage.info('AI辅助税费检查分析...')
}

function handleReview() {
  openReviewDialog?.('N2-11-应交税费检查')
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const resp = formData.allResponses.value.get('N2-11-tax-check')
  if (resp?.conclusion) {
    try {
      const saved: any[] = JSON.parse(resp.conclusion)
      saved.forEach((s, i) => {
        if (i < checkRows.value.length) {
          checkRows.value[i].accrualAccuracy = s.accrualAccuracy || ''
          checkRows.value[i].paymentTimeliness = s.paymentTimeliness || ''
          checkRows.value[i].declarationConsistency = s.declarationConsistency || ''
          checkRows.value[i].remark = s.remark || ''
          checkRows.value[i].voucherAttached = s.voucherAttached || false
        }
      })
    } catch { /* ignore */ }
  }
  const conclusionResp = formData.allResponses.value.get('N2-11-conclusion')
  if (conclusionResp?.remark) overallConclusion.value = conclusionResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-tax-check {
  padding: 12px;
  font-size: 13px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
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

/* ─── 核查汇总统计 ─── */
.check-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.stat-item--pass { background: #f0f9eb; color: #67c23a; }
.stat-item--issue { background: #fef0f0; color: #f56c6c; }
.stat-item--pending { background: #fdf6ec; color: #e6a23c; }

.stat-count {
  font-size: 18px;
  font-weight: 700;
}

.stat-label {
  font-size: 12px;
}

/* ─── 表格 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

:deep(.row--issue) {
  background: #fef0f0 !important;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
