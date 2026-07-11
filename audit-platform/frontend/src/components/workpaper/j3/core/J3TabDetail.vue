<template>
  <div class="j3-tab-detail">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证股份支付各方案授予日公允价值（Black-Scholes 定价）、等待期费用分摊及权益/现金结算分类的准确性，核验费用确认是否随等待期正确摊销。
      </template>
    </el-alert>

    <!-- 顶部引导区 -->
    <div class="guide-banner">
      <div class="guide-step"><span class="step-num">①</span> 录入各方案基本信息</div>
      <div class="guide-step"><span class="step-num">②</span> BS定价自动计算公允价值</div>
      <div class="guide-step"><span class="step-num">③</span> 等待期费用自动分摊</div>
    </div>

    <!-- 双模式切换 + 导入导出 -->
    <div class="toolbar">
      <el-segmented v-model="dualMode.mode.value" :options="modeOptions" size="small" />
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:J3-2" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ detail.filteredPlans.value.length }} 个方案</el-tag>
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 情况表主体（HTML模式） -->
    <template v-if="dualMode.isHtml.value">
      <!-- 权益/现金分类标识 -->
      <div class="settlement-summary">
        <el-tag type="success" size="small">权益结算 {{ detail.equitySummary.value.count }} 个方案</el-tag>
        <el-tag type="warning" size="small">现金结算 {{ detail.cashSummary.value.count }} 个方案</el-tag>
      </div>

      <!-- 动态行表格 -->
      <el-table :data="detail.filteredPlans.value" border size="small" show-summary :summary-method="getSummary">
        <el-table-column prop="name" label="方案名称" min-width="120" fixed />
        <el-table-column prop="type" label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.type === 'equity' ? 'success' : 'warning'" size="small">
              {{ row.type === 'equity' ? '权益' : '现金' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="grantDate" label="授予日" width="100" />
        <el-table-column prop="exercisePrice" label="行权价" width="90" align="right" />
        <el-table-column prop="sharesCount" label="标的股数" width="100" align="right" />
        <el-table-column prop="vestingPeriod" label="等待期(年)" width="80" align="center" />
        <el-table-column prop="serviceYears" label="已服务(年)" width="80" align="center" />
        <el-table-column prop="unitFairValue" label="单位FV" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="Black-Scholes定价：C=S·N(d1)-K·e^(-rT)·N(d2)">{{ row.unitFairValue?.toFixed(4) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期费用" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="computed-value formula-cell" title="本期费用=总公允价值÷等待期×已服务年数 - 以前累计">{{ row.currentExpense?.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计费用" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="累计费用=总公允价值×(已服务年数÷等待期)">{{ row.cumulativeExpense?.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="剩余费用" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="剩余费用=总公允价值-累计费用">{{ row.remainingExpense?.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="记账方向" width="120">
          <template #default="{ row }">
            <span :class="row.type === 'equity' ? 'text-success' : 'text-warning'">
              {{ row.type === 'equity' ? '贷记资本公积' : '贷记应付薪酬' }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新增行 -->
      <div v-if="!isReadonly" class="add-row">
        <el-button type="primary" plain size="small" @click="handleAddPlan">+ 新增方案</el-button>
      </div>

      <!-- 联动状态 -->
      <div class="linkage-section">
        <el-card shadow="never">
          <template #header><span style="font-size:13px;font-weight:600">跨科目联动状态</span></template>
          <div class="linkage-items">
            <div class="linkage-item">
              <span>M4 资本公积（权益结算）：</span>
              <el-tag :type="crossSheet.m4LinkageStatus.value.isLinked ? 'success' : 'info'" size="small">
                {{ crossSheet.m4LinkageStatus.value.amount.toFixed(2) }} 元
              </el-tag>
            </div>
            <div class="linkage-item">
              <span>J1 应付职工薪酬（现金结算）：</span>
              <el-tag :type="crossSheet.j1LinkageStatus.value.isLinked ? 'warning' : 'info'" size="small">
                {{ crossSheet.j1LinkageStatus.value.amount.toFixed(2) }} 元
              </el-tag>
            </div>
          </div>
        </el-card>
      </div>
    </template>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 11《股份支付》，权益结算按授予日权益工具公允价值计量（贷记资本公积 M4），不后续重新计量。</p>
        <p>2. 现金结算按每个资产负债表日重新计量的公允价值计量（贷记应付职工薪酬 J1）。</p>
        <p>3. 灰色底纹列为自动计算列（Black-Scholes 定价、等待期费用分摊），不可手动编辑。</p>
        <p>4. 费用应在等待期内按最佳估计的可行权数量分期确认，取消/失效时按 CAS 11 加速或转回处理。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * J3TabDetail — J3-1 股份支付情况表（18列明细 + 费用分摊 + BS参数）
 */
import { ElMessageBox } from 'element-plus'
import { useJ3FormData, type J3Plan } from '@/composables/workpaper/j3/useJ3FormData'
import { useJ3Detail } from '@/composables/workpaper/j3/useJ3Detail'
import { useJ3CrossSheet } from '@/composables/workpaper/j3/useJ3CrossSheet'
import { useJ3DualMode } from '@/composables/workpaper/j3/useJ3DualMode'
import { useJ3ImportExport } from '@/composables/workpaper/j3/useJ3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  year?: string | number
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const modeOptions = [
  { label: 'HTML', value: 'html' },
  { label: 'OnlyOffice', value: 'onlyoffice' },
]

const formData = useJ3FormData({ wpId: props.wpId, projectId: props.projectId, htmlData: props.htmlData })
const detail = useJ3Detail(formData.plans)
const crossSheet = useJ3CrossSheet({ projectId: props.projectId, wpId: props.wpId }, formData.plans)
const dualMode = useJ3DualMode(props.wpId)
const importExport = useJ3ImportExport(props.wpId)

// 初始加载
formData.loadData()

function statusTagType(status: string) {
  const map: Record<string, string> = { vesting: '', exercisable: 'success', expired: 'info', cancelled: 'danger' }
  return map[status] || ''
}

function statusLabel(status: string) {
  const map: Record<string, string> = { vesting: '等待中', exercisable: '可行权', expired: '已过期', cancelled: '已取消' }
  return map[status] || status
}

function getSummary({ columns, data }: { columns: any[]; data: J3Plan[] }) {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    if (col.property === 'sharesCount') return detail.subtotals.value.totalShares
    return ''
  })
}

async function handleAddPlan() {
  const { value: name } = await ElMessageBox.prompt('请输入方案名称', '新增股份支付方案', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：2024年股票期权激励计划',
  })
  if (name) {
    detail.addPlan({
      id: `plan-${Date.now()}`,
      name,
      type: 'equity',
      grantDate: '',
      exercisePrice: 0,
      sharesCount: 0,
      vestingPeriod: 3,
      vestingDate: '',
      expiryDate: '',
      unitFairValue: 0,
      priorCumulative: 0,
      currentExpense: 0,
      cumulativeExpense: 0,
      remainingExpense: 0,
      serviceYears: 0,
      status: 'vesting',
    })
  }
}

function handleImportExport(command: string) {
  if (command === 'template') importExport.exportTemplate()
  else if (command === 'export') importExport.exportData()
  else if (command === 'import') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData(file)
    }
    input.click()
  }
}
</script>

<style scoped>
.j3-tab-detail { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.guide-banner {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecf7 100%);
  border-radius: 8px;
}
.guide-step { font-size: 13px; color: #303133; }
.step-num { font-weight: 700; color: #409eff; margin-right: 4px; }
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.toolbar-right { display: flex; gap: 8px; }
.settlement-summary { margin-bottom: 12px; display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.computed-value { font-weight: 600; color: #409eff; }
.text-success { color: #67c23a; font-size: 12px; }
.text-warning { color: #e6a23c; font-size: 12px; }
.add-row { margin: 12px 0; }
.linkage-section { margin-top: 16px; }
.linkage-items { display: flex; flex-direction: column; gap: 8px; }
.linkage-item { font-size: 13px; display: flex; align-items: center; gap: 8px; }
</style>
