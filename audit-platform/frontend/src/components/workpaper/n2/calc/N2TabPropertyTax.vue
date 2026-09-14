<template>
  <div class="n2-tab-property-tax">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>房产税测算表 N2-9</span>
        <el-tag type="info" size="small">30×7 从价/从租</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增房产
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
        <strong>房产税测算逻辑：</strong>
        从价计征 = (房产原值 - 不计税原值) × (1 - 扣除比例) × 1.2% × 当年月份/12；
        从租计征 = 租金收入 × 12%。
        扣除比例由各省规定（10%~30%），需选择适用地区。
        自有自用房产按从价，出租房产按从租。新增/处置房产按实际持有月份折算。
      </div>
    </div>

    <!-- ═══ 地区扣除比例配置 ═══ -->
    <div class="calc-toolbar">
      <div class="toolbar-section">
        <span class="toolbar-label">地区默认扣除比例：</span>
        <el-select
          :model-value="propertyTax.defaultDeductRate.value"
          size="small"
          :disabled="isReadonly"
          style="width: 100px"
          @change="handleDeductRateChange"
        >
          <el-option
            v-for="opt in DEDUCT_RATE_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-tooltip content="各省市房产税扣除比例不同，常见为20%~30%" placement="top">
          <el-icon class="info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="toolbar-section">
        <span class="toolbar-label">房产数：</span>
        <el-tag effect="plain">{{ propertyTax.summary.value.propertyCount }} 项</el-tag>
      </div>
    </div>

    <!-- ═══ 房产税测算明细表 ═══ -->
    <el-table
      :data="propertyTax.rows.value"
      border
      size="small"
      style="width: 100%"
      show-summary
      :summary-method="getSummaryRow"
    >
      <el-table-column prop="propertyName" label="房产名称" width="150">
        <template #default="{ row }">
          <el-input
            :model-value="row.propertyName"
            size="small"
            :disabled="isReadonly"
            placeholder="房产名称"
            @change="(val: string) => propertyTax.updateRow(row.id, 'propertyName', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="计税方式" width="110" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.method"
            size="small"
            :disabled="isReadonly"
            style="width: 80px"
            @change="(val: string) => propertyTax.updateRow(row.id, 'method', val)"
          >
            <el-option value="从价" label="从价" />
            <el-option value="从租" label="从租" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="房产原值" width="140" align="right">
        <template #header>
          <el-tooltip content="从价计征时使用：房产原值(账面)" placement="top">
            <span class="formula-col-header">房产原值</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="row.method === '从价'"
            :model-value="row.originalValue"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 120px"
            @change="(val: number) => propertyTax.updateRow(row.id, 'originalValue', val ?? 0)"
          />
          <span v-else class="cell-na">—</span>
        </template>
      </el-table-column>
      <el-table-column label="不计税原值" width="130" align="right">
        <template #header>
          <el-tooltip content="从价计征时使用：房产原值中免于计税的部分（如按规定不计税的设备/地下建筑）" placement="top">
            <span class="formula-col-header">不计税原值</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="row.method === '从价'"
            :model-value="row.deductibleOriginalValue"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 110px"
            @change="(val: number) => propertyTax.updateRow(row.id, 'deductibleOriginalValue', val ?? 0)"
          />
          <span v-else class="cell-na">—</span>
        </template>
      </el-table-column>
      <el-table-column label="租金收入" width="140" align="right">
        <template #header>
          <el-tooltip content="从租计征时使用：年租金收入" placement="top">
            <span class="formula-col-header">租金收入</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="row.method === '从租'"
            :model-value="row.rentIncome"
            :disabled="isReadonly"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 120px"
            @change="(val: number) => propertyTax.updateRow(row.id, 'rentIncome', val ?? 0)"
          />
          <span v-else class="cell-na">—</span>
        </template>
      </el-table-column>
      <el-table-column label="扣除比例" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-if="row.method === '从价'"
            :model-value="row.deductRate"
            size="small"
            :disabled="isReadonly"
            style="width: 75px"
            @change="(val: number) => propertyTax.updateRow(row.id, 'deductRate', val)"
          >
            <el-option :value="0.10" label="10%" />
            <el-option :value="0.15" label="15%" />
            <el-option :value="0.20" label="20%" />
            <el-option :value="0.25" label="25%" />
            <el-option :value="0.30" label="30%" />
          </el-select>
          <span v-else class="cell-na">—</span>
        </template>
      </el-table-column>
      <el-table-column label="当年月份" width="100" align="center">
        <template #header>
          <el-tooltip content="当年实际纳税义务月份（1~12），新增/处置房产按实际持有月数，用于部分年度房产税" placement="top">
            <span class="formula-col-header">当年月份</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            :model-value="row.months"
            :min="1"
            :max="12"
            :step="1"
            :disabled="isReadonly"
            :controls="false"
            :precision="0"
            size="small"
            style="width: 72px"
            @change="(val: number) => propertyTax.updateRow(row.id, 'months', val ?? 12)"
          />
        </template>
      </el-table-column>
      <el-table-column label="应交房产税" width="140" align="right">
        <template #header>
          <el-tooltip content="从价=(原值-不计税原值)×(1-扣除比例)×1.2%×月份/12；从租=租金×12%" placement="top">
            <span class="formula-col-header">应交房产税</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.taxAmount) }}</span>
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
            @click="propertyTax.removeRow(row.id)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 空状态 ═══ -->
    <el-empty
      v-if="propertyTax.rows.value.length === 0"
      description="暂无房产数据，点击“新增房产”添加"
      :image-size="60"
    />

    <!-- ═══ 测算结果汇总 ═══ -->
    <el-card shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>测算结果汇总</span>
          <el-tag type="success" size="small" effect="dark">
            回填N2-1 + 联动N4
          </el-tag>
        </div>
      </template>
      <div class="result-grid">
        <div class="result-item">
          <span class="result-label">从价计征合计</span>
          <span class="result-value">{{ fmtAmount(propertyTax.summary.value.byValueTotal) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">从租计征合计</span>
          <span class="result-value">{{ fmtAmount(propertyTax.summary.value.byRentTotal) }}</span>
        </div>
        <div class="result-item result-item--total">
          <span class="result-label">应交房产税合计</span>
          <span class="result-value">{{ fmtAmount(propertyTax.summary.value.total) }}</span>
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
        placeholder="请输入房产税测算审计说明..."
        @change="handleNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>从价计征：自有自用房产 = (房产原值 - 不计税原值) × (1 - 扣除比例) × 1.2% × 当年月份/12</li>
        <li>从租计征：出租房产 = 年租金收入 × 12%</li>
        <li>不计税原值：房产原值中按规定免于计税的部分（如独立设备、地下建筑等），从价时可填</li>
        <li>当年月份：新增/处置房产按实际持有月数（1~12）折算，全年持有填12</li>
        <li>扣除比例各省不同：北京/上海30%、浙江/江苏30%、广东20%等</li>
        <li>关注房产原值是否含土地出让金（部分地区要求含）</li>
        <li>测算结果自动回填N2-1房产税行，联动N4税金及附加</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabPropertyTax — N2-9 房产税测算表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.12
 * Requirements: 6.1-6.4
 *
 * 核心职责：
 * - 30×7 从价(原值×(1-扣除比例)×1.2%)/从租(租金×12%)
 * - 扣除比例地区配置
 * - 动态行 + 回填N2-1及联动N4
 * - Uses useN2PropertyTax composable
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus, Delete, InfoFilled } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2PropertyTax, DEDUCT_RATE_OPTIONS } from '../../composables/useN2PropertyTax'

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

const propertyTax = useN2PropertyTax({
  allResponses: formData.allResponses,
  // 🔴 useN2PropertyTax 期望 `(sheet, field, value)` → 必须传 setField。
  //    误传 saveField（`(itemId, {conclusion})`）会让 item_id 写成 '9'、数据整体丢弃。
  saveField: formData.setField,
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

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleDeductRateChange(val: number) {
  propertyTax.setDefaultDeductRate(val)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入房产名称', '新增房产', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：办公楼A栋',
    })
    if (value?.trim()) {
      await propertyTax.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

function handleNoteChange() {
  formData.debouncedSave('N2-9-note', { remark: auditNote.value || null })
}

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-property-tax',
      prompt: '请基于应交税费底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('N2-9-房产税测算')
}

/** 合计行（应交房产税列现为第7列：名称0/方式1/原值2/不计税原值3/租金4/扣除比例5/月份6/应交7/操作8） */
function getSummaryRow({ columns }: { columns: any[] }) {
  const sums: string[] = []
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (index === 7) { sums[index] = fmtAmount(propertyTax.summary.value.total); return }
    sums[index] = ''
  })
  return sums
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const noteResp = formData.allResponses.value.get('N2-9-note')
  if (noteResp?.remark) auditNote.value = noteResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-property-tax {
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

/* ─── 工具栏 ─── */
.calc-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 6px;
}

.toolbar-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: nowrap;
}

.info-icon {
  color: #909399;
  cursor: help;
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

.cell-na {
  color: #c0c4cc;
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
  grid-template-columns: repeat(3, 1fr);
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
