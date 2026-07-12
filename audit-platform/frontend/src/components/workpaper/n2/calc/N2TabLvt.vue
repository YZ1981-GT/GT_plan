<template>
  <div class="n2-tab-lvt">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>土地增值税测算表 N2-10</span>
        <el-tag type="info" size="small">51×7 四级累进</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增项目
        </el-button>
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
        <strong>土地增值税四级超率累进：</strong>
        增值额 = 转让收入 - 扣除项目金额；增值率 = 增值额 / 扣除项目。
        根据增值率自动匹配税率：≤50%→30%/0% | 50%~100%→40%/5% | 100%~200%→50%/15% | &gt;200%→60%/35%。
        应交 = 增值额 × 税率 - 扣除项目 × 速算扣除系数。
      </div>
    </div>

    <!-- ═══ 四级累进税率参考 ═══ -->
    <div class="bracket-reference">
      <div
        v-for="bracket in LVT_BRACKETS"
        :key="bracket.label"
        class="bracket-item"
      >
        <span class="bracket-label">{{ bracket.label }}</span>
      </div>
    </div>

    <!-- ═══ 土增税测算明细表 ═══ -->
    <el-table
      :data="lvt.rows.value"
      border
      size="small"
      style="width: 100%"
      show-summary
      :summary-method="getSummaryRow"
    >
      <el-table-column prop="projectName" label="项目名称" width="150">
        <template #default="{ row }">
          <el-input
            :model-value="row.projectName"
            size="small"
            :disabled="isReadonly"
            placeholder="项目名称"
            @change="(val: string) => lvt.updateRow(row.id, 'projectName', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="转让收入" width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.transferIncome"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 120px"
            @change="(val: number) => lvt.updateRow(row.id, 'transferIncome', val ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="扣除项目金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.deductItems"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 120px"
            @change="(val: number) => lvt.updateRow(row.id, 'deductItems', val ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="增值额" width="130" align="right">
        <template #header>
          <el-tooltip content="公式：转让收入 - 扣除项目金额" placement="top">
            <span class="formula-col-header">增值额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'formula-cell--negative': row.appreciation < 0 }">
            {{ fmtAmount(row.appreciation) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="增值率" width="100" align="center">
        <template #header>
          <el-tooltip content="公式：增值额 / 扣除项目（决定适用税率档次）" placement="top">
            <span class="formula-col-header">增值率</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tag
            :type="getAppreciationRateType(row.appreciationRate)"
            effect="plain"
            size="small"
          >
            {{ fmtPercent(row.appreciationRate) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="适用税率" width="90" align="center">
        <template #default="{ row }">
          <span class="rate-badge">{{ fmtPercent(row.taxRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="速算扣除" width="90" align="center">
        <template #default="{ row }">
          <span class="rate-badge">{{ fmtPercent(row.quickDeductCoef) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应交土增税" width="140" align="right">
        <template #header>
          <el-tooltip content="公式：增值额×税率 - 扣除项目×速算扣除系数" placement="top">
            <span class="formula-col-header">应交土增税</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.taxAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="档次" width="130" align="center">
        <template #default="{ row }">
          <el-tooltip :content="row.bracketLabel" placement="top">
            <el-tag size="small" type="info">{{ row.bracketLabel.split(':')[0] }}</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            type="danger"
            :icon="Delete"
            circle
            :disabled="isReadonly"
            @click="lvt.removeRow(row.id)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 空状态 ═══ -->
    <el-empty
      v-if="lvt.rows.value.length === 0"
      description="暂无项目数据，点击“新增项目”添加"
      :image-size="60"
    />

    <!-- ═══ 测算结果汇总 ═══ -->
    <el-card shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>测算结果汇总</span>
          <el-tag type="success" size="small" effect="dark">
            回填N2-1
          </el-tag>
        </div>
      </template>
      <div class="result-grid">
        <div class="result-item">
          <span class="result-label">转让收入合计</span>
          <span class="result-value">{{ fmtAmount(lvt.summary.value.totalTransferIncome) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">扣除项目合计</span>
          <span class="result-value">{{ fmtAmount(lvt.summary.value.totalDeductItems) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">增值额合计</span>
          <span class="result-value">{{ fmtAmount(lvt.summary.value.totalAppreciation) }}</span>
        </div>
        <div class="result-item result-item--total">
          <span class="result-label">应交土增税合计</span>
          <span class="result-value">{{ fmtAmount(lvt.summary.value.totalTaxAmount) }}</span>
        </div>
      </div>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="请输入土地增值税测算审计说明..."
        @change="handleNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>转让收入 = 不动产转让合同金额（含增值税的，需价税分离）</li>
        <li>扣除项目 = 取得土地使用权金额 + 开发成本 + 开发费用 + 税金 + 加计扣除</li>
        <li>增值额 = 转让收入 - 扣除项目（公式自动计算）</li>
        <li>增值率决定适用的累进税率档次（公式自动匹配）</li>
        <li>普通标准住宅增值率≤20%免征</li>
        <li>核对扣除项目的发票/票据完整性</li>
        <li>测算结果自动回填N2-1土地增值税行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabLvt — N2-10 土地增值税测算表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.13
 * Requirements: 7.1-7.5
 *
 * 核心职责：
 * - 51×7 增值额/增值率 + 四级累进税率自动匹配
 * - 速算扣除系数 + 应交土增税 = 增值额×税率 - 扣除项目×系数
 * - 回填N2-1
 * - Uses useN2Lvt composable
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus, Delete } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2Lvt, LVT_BRACKETS } from '../../composables/useN2Lvt'

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

// ─── Composable ──────────────────────────────────────────────────────────────

const lvt = useN2Lvt({
  allResponses: formData.allResponses,
  saveField: formData.saveField,
  getField: formData.getField,
})

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)
const auditNote = ref('')

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (!Number.isFinite(val)) return '—'
  return (val * 100).toFixed(1) + '%'
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getAppreciationRateType(rate: number): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (!Number.isFinite(rate) || rate <= 0) return 'info'
  if (rate <= 0.5) return 'success'
  if (rate <= 1.0) return 'warning'
  return 'danger'
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX花园一期',
    })
    if (value?.trim()) {
      await lvt.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

function handleNoteChange() {
  formData.debouncedSave('N2-10-note', { remark: auditNote.value || null })
}

function handleAiAssist() {
  ElMessage.info('AI辅助土地增值税测算...')
}

function handleReview() {
  openReviewDialog?.('N2-10-土地增值税测算')
}

/** 合计行 */
function getSummaryRow({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const s = lvt.summary.value
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    const map: Record<number, number> = {
      1: s.totalTransferIncome,
      2: s.totalDeductItems,
      3: s.totalAppreciation,
      7: s.totalTaxAmount,
    }
    sums[index] = map[index] != null ? fmtAmount(map[index]) : ''
  })
  return sums
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const noteResp = formData.allResponses.value.get('N2-10-note')
  if (noteResp?.remark) auditNote.value = noteResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-lvt {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 四级累进参考 ─── */
.bracket-reference {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.bracket-item {
  padding: 4px 10px;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}

/* ─── 表格 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-cell {
  color: #409eff;
  font-weight: 500;
}

.formula-cell--negative {
  color: #f56c6c;
}

.rate-badge {
  font-size: 12px;
  color: #606266;
  font-weight: 500;
}

/* ─── 结果卡片 ─── */
.result-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 6px;
}

.result-item--total {
  background: #ecf5ff;
}

.result-label {
  font-size: 12px;
  color: #909399;
}

.result-value {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}

.result-item--total .result-value {
  color: #409eff;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
}

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
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
