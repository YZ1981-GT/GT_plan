<template>
  <div class="h2-tab-cost-comparison">
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：（1）在建工程存在且记入恰当账户；（2）单方造价与可比价无重大异常；（3）本期增加与现金流量表购建固定资产等支付的现金勾稽一致或差异可解释。" />

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-7" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag size="small" type="warning" v-if="alertCount > 0">关注 {{ alertCount }} 项</el-tag>
      </div>
    </div>

    <!-- （一）单方造价比较 + 项目层现金流勾稽 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>工程造价比较分析表（H2-7）</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-2" label="→ H2-2明细" />
            <el-button size="small" circle @click="openReview('H2-7')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="displayRows" border stripe size="small" class="cost-table"
        :row-class-name="costRowClass" max-height="480">
        <el-table-column type="index" label="序号" width="50" align="center" fixed />
        <el-table-column prop="name" label="项目" min-width="120" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-name': row.isTotal }">{{ row.name }}</span>
          </template>
        </el-table-column>

        <el-table-column label="工程项目总造价" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.totalCost"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'totalCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.totalCost) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="建筑面积(㎡)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.buildingArea ?? undefined"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'buildingArea', $event)" />
            <span v-else class="amt-cell">{{ row.buildingArea != null ? fmtAmt(row.buildingArea) : '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="单方造价" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=总造价/建筑面积（面积为空则不计算）">{{ fmtAmt(row.unitCost) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="可比价1" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.comparable1 ?? undefined"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'comparable1', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.comparable1) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可比价2" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.comparable2 ?? undefined"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'comparable2', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.comparable2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可比价3" min-width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.comparable3 ?? undefined"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'comparable3', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.comparable3) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="可比价均值" min-width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.isTotal">-</span>
            <span v-else class="formula-cell" title="=AVERAGE(可比价1~3中有值项)">{{ fmtAmt(row.comparableAvg) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与可比价差异" min-width="110" align="right">
          <template #default="{ row }">
            <span v-if="row.isTotal">-</span>
            <span v-else class="formula-cell" title="=单方造价-可比价均值">{{ fmtAmt(row.unitCostDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率(%)" min-width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.isTotal">-</span>
            <span v-else
              :class="['formula-cell', { 'error-amount': isUnitDiffAlert(row) }]"
              title="=与可比价差异/可比价均值×100；|差异率|>15%红色关注">
              {{ row.unitCostDiffRate != null ? row.unitCostDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="可比价来源索引" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.comparableSourceIndex" size="small"
              @change="onCellChange(row.rowId, 'comparableSourceIndex', $event)" />
            <span v-else>{{ row.comparableSourceIndex || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期增加额" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!row.isTotal && !isReadonly" v-model="row.periodIncrease" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'periodIncrease', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.periodIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计入现金流量金额" min-width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!row.isTotal && !isReadonly" v-model="row.cashFlowAmount" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'cashFlowAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.cashFlowAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="勾稽差异" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.cashDiff != null && Math.abs(row.cashDiff) > 0.005 }]"
              title="=本期增加额-本期计入现金流量金额">
              {{ fmtAmt(row.cashDiff) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="差异原因/关注事项" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.diffReason" size="small"
              @change="onCellChange(row.rowId, 'diffReason', $event)" />
            <span v-else>{{ row.diffReason || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="标记" width="72" align="center">
          <template #default="{ row }">
            <el-tag v-if="!row.isTotal && isUnitDiffAlert(row)" type="danger" size="small">造价</el-tag>
            <el-tag v-else-if="!row.isTotal && row.cashDiff != null && Math.abs(row.cashDiff) > 0.005"
              type="warning" size="small">勾稽</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button v-if="!row.isTotal" size="small" type="danger" link
              @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增工程</el-button>
      </div>
    </el-card>

    <!-- （二）主体层现金流勾稽 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <span>与现金流量表勾稽汇总（主体层面）</span>
      </template>
      <el-descriptions :column="1" border size="small" class="recon-desc">
        <el-descriptions-item label="① 本期在建工程增加额合计">
          <span class="amt-cell formula-cell" title="=上表本期增加额合计">{{ fmtAmt(state.totalRow.value.periodIncrease) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="② 现金流量表：购置固定资产、无形资产和其他长期资产支付的现金">
          <el-input-number v-if="!isReadonly"
            :model-value="state.cashFlowRecon.value.cfsCapexAmount ?? undefined"
            :controls="false" size="small" class="amt-input recon-input"
            @change="onReconChange('cfsCapexAmount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(state.cashFlowRecon.value.cfsCapexAmount) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="③ 勾稽差异（①−②）">
          <span :class="['amt-cell', 'formula-cell', { 'error-amount': hasEntityCashDiff }]">
            {{ fmtAmt(state.entityCashDiff.value) }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="勾稽说明">
          <el-input v-if="!isReadonly" v-model="state.cashFlowRecon.value.reconNote" type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="说明口径差异：应付/预付工程款、购入不经CIP的固定资产、无形资产、非现金投入、资本化利息等…"
            @blur="onReconChange('reconNote', state.cashFlowRecon.value.reconNote)" />
          <span v-else>{{ state.cashFlowRecon.value.reconNote || '-' }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="说明可比价选取口径、重大单方造价差异原因、主体层现金流勾稽结果及已执行的追加程序…"
        :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="结论示例：经比较，各工程单方造价与可比价差异均在可接受范围；本期增加与现金流量表勾稽差异已合理解释，未见重大异常。"
        :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>从可研/概预算取总造价与建筑面积，计算单方造价并与可比价比较；填列来源索引便于复核。</li>
        <li>|单方造价差异率|＞15%（或项目组自定阈值）须说明原因，评估是否追加程序。</li>
        <li>无建筑面积的装置/管网类工程：面积留空，改用单位产能/长度等口径在备注说明。</li>
        <li>现金流勾稽优先做主体层汇总；项目层分摊仅在可可靠归集时填写。</li>
        <li>数据可从 H2-2 自动带入（预算→总造价、面积、增加合计），可比价与现金流需手工补录。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H2TabCostComparison.vue — H2-7 工程造价比较分析表
 * 对齐致同：单方造价vs可比价 + 本期增加vs现金流量勾稽
 */
import { inject, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  useH2CostComparison,
  UNIT_DIFF_THRESHOLD,
  type H2CostComparisonRow,
} from '../../composables/useH2CostComparison'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2CostComparison({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const displayRows = computed(() => [
  ...state.rows.value,
  { ...state.totalRow.value, isTotal: true, rowId: 'row-total' },
])

const alertCount = computed(() =>
  state.rows.value.filter(r =>
    isUnitDiffAlert(r) || (r.cashDiff != null && Math.abs(r.cashDiff) > 0.005),
  ).length,
)

const hasEntityCashDiff = computed(() => {
  const d = state.entityCashDiff.value
  return d != null && Math.abs(d) > 0.005
})

function isUnitDiffAlert(row: Partial<H2CostComparisonRow>): boolean {
  return row.unitCostDiffRate != null && Math.abs(row.unitCostDiffRate) > UNIT_DIFF_THRESHOLD
}

function costRowClass({ row }: any) {
  if (row.isTotal) return 'total-row'
  if (isUnitDiffAlert(row)) return 'alert-unit-row'
  if (row.cashDiff != null && Math.abs(row.cashDiff) > 0.005) return 'alert-cash-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

function onReconChange(field: 'cfsCapexAmount' | 'reconNote', value: any) {
  state.updateRecon({ [field]: value })
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增工程', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value)
  } catch { /* cancelled */ }
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-cost-comparison { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.cost-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.recon-input { width: 220px; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.total-name { font-weight: 600; }
.add-row-bar { margin-top: 12px; }
.audit-note-card { margin-bottom: 12px; }
.recon-desc { max-width: 960px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background-color: var(--el-fill-color-light) !important; }
:deep(.alert-unit-row) { background-color: #fef0f0 !important; }
:deep(.alert-cash-row) { background-color: #fdf6ec !important; }
</style>
