<template>
  <div class="k5-tab-decommission">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性与义务：</b>存在弃置义务的固定资产均已确认弃置费用预计负债；</li>
        <li><b>计价和分摊：</b>弃置费用按未来支出现值（折现）恰当计量，折现率与期间合理；</li>
        <li><b>列报与披露：</b>弃置费用及其增值已按 CAS13/CAS4 恰当处理与披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 ═══ -->
    <div class="section-header">
      <h3>K5-5 弃置费用检查表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI结论
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>弃置费用（弃置义务）现值折现：<strong>现值 = 预计弃置支出 / (1+折现率)^年数</strong>。期末 = 期初 + 本期增加 + 利息调整（期初×折现率）。K5-5期末合计应与K5-1弃置义务行审定数一致。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-5 期末合计: <strong>{{ fmtNum(crossCheck.decommissionTotal) }}</strong></span>
      <span>K5-1 弃置义务审定: <strong>{{ fmtNum(crossCheck.adjudicationDecommission) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══（一）弃置费用的完整性检查 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（一）弃置费用的完整性检查</span>
          <el-button v-if="!isReadonly" size="small" @click="addCompletenessRow()">＋ 新增行</el-button>
        </div>
      </template>
      <el-table :data="completenessRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="内部资料/外部评估报告" min-width="170">
          <template #default="{ row }"><el-input v-model="row.internalDesc" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'internalDesc', v)" /></template>
        </el-table-column>
        <el-table-column label="与第三方/监管机构函件" min-width="170">
          <template #default="{ row }"><el-input v-model="row.thirdPartyDesc" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'thirdPartyDesc', v)" /></template>
        </el-table-column>
        <el-table-column label="固定资产本期增加是否迹象计提不足" min-width="180">
          <template #default="{ row }"><el-input v-model="row.faIncreaseCheck" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'faIncreaseCheck', v)" /></template>
        </el-table-column>
        <el-table-column label="实地观察是否迹象计提不足" min-width="170">
          <template #default="{ row }"><el-input v-model="row.onSiteObservation" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'onSiteObservation', v)" /></template>
        </el-table-column>
        <el-table-column label="索引" width="90">
          <template #default="{ row }"><el-input v-model="row.indexNo" :disabled="isReadonly" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'indexNo', v)" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeCompletenessRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══（二）关键假设评估 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（二）关键假设评估</span>
          <el-button v-if="!isReadonly" size="small" @click="addAssumptionRow()">＋ 新增行</el-button>
        </div>
      </template>
      <el-table :data="assumptionRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="关键假设" min-width="200">
          <template #default="{ row }"><el-input v-model="row.assumption" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" placeholder="如：弃置支出金额、折现率、弃置时间等" @change="(v: string) => updateAssumptionCell(row.rowId, 'assumption', v)" /></template>
        </el-table-column>
        <el-table-column label="是否与历史/行业数据一致" width="150" align="center">
          <template #default="{ row }">
            <el-select v-model="row.consistentWithData" :disabled="isReadonly" size="small" placeholder="选择" @change="(v: string) => updateAssumptionCell(row.rowId, 'consistentWithData', v)">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="期后事项是否影响" width="140" align="center">
          <template #default="{ row }">
            <el-select v-model="row.affectedByPostEvent" :disabled="isReadonly" size="small" placeholder="选择" @change="(v: string) => updateAssumptionCell(row.rowId, 'affectedByPostEvent', v)">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="假设是否合理" width="130" align="center">
          <template #default="{ row }">
            <el-select v-model="row.isReasonable" :disabled="isReadonly" size="small" placeholder="选择" @change="(v: string) => updateAssumptionCell(row.rowId, 'isReasonable', v)">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="90">
          <template #default="{ row }"><el-input v-model="row.indexNo" :disabled="isReadonly" size="small" @change="(v: string) => updateAssumptionCell(row.rowId, 'indexNo', v)" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeAssumptionRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 现值折现测算（计量辅助）═══ -->
    <div class="sub-section-title">（三）弃置费用现值折现测算（计量辅助）</div>
    <!-- ═══ 主表 ═══ -->
    <el-table :data="decommissionRows" border size="small" style="width: 100%" max-height="480">
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="资产名称" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.assetName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'assetName', row.assetName)" />
        </template>
      </el-table-column>
      <el-table-column label="预计弃置支出" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.futureExpense" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => save(row.rowId, 'futureExpense', v)" />
        </template>
      </el-table-column>
      <el-table-column label="年数" width="70" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.expectedYears" :disabled="isReadonly" size="small" :controls="false" :precision="0" :min="0" style="width:55px" @change="(v:number) => save(row.rowId, 'expectedYears', v)" />
        </template>
      </el-table-column>
      <el-table-column label="折现率" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.discountRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:75px" @change="(v:number) => save(row.rowId, 'discountRate', v)" />
          <el-icon v-if="row.discountRate <= 0 && row.futureExpense > 0" color="#f56c6c" style="margin-left:2px"><WarningFilled /></el-icon>
        </template>
      </el-table-column>
      <el-table-column label="现值" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="future / (1+rate)^years" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.presentValue) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期初" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'beginBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="增加" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.periodIncrease" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'periodIncrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="利息调整" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 × 折现率" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.interestAdjustment) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 + 增加 + 利息调整" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.conclusion" :disabled="isReadonly" size="small" placeholder="结论" @blur="save(row.rowId, 'conclusion', row.conclusion)" />
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行 ═══ -->
    <div class="summary-bar">
      <span>合计行数: {{ subtotals.count }}</span>
      <span>现值合计: {{ fmtNum(subtotals.presentValue) }}</span>
      <span>期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
    </div>

    <!-- ═══ 借方/贷方发生额分析 ═══ -->
    <el-card shadow="never" class="k5-section-card" style="margin-top:12px">
      <template #header><span class="card-title">借方/贷方发生额分析</span></template>
      <div class="dc-grid">
        <div class="dc-col">
          <div class="dc-head">
            <span>借方发生额分析</span>
            <el-button v-if="!isReadonly" size="small" @click="addAmountRow('debit')">＋ 新增</el-button>
          </div>
          <el-table :data="debitRows" border size="small" style="width:100%">
            <el-table-column type="index" label="序" width="42" align="center" />
            <el-table-column label="对应科目" min-width="120"><template #default="{ row }"><el-input v-model="row.offsetAccount" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('debit', row.rowId, 'offsetAccount', v)" /></template></el-table-column>
            <el-table-column label="对应金额" width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.amount" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateAmountCell('debit', row.rowId, 'amount', v)" /></template></el-table-column>
            <el-table-column label="备注" min-width="110"><template #default="{ row }"><el-input v-model="row.remark" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('debit', row.rowId, 'remark', v)" /></template></el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="42" align="center"><template #default="{ $index }"><el-button link type="danger" size="small" @click="removeAmountRow('debit', $index)"><el-icon><Delete /></el-icon></el-button></template></el-table-column>
            <template #append><div class="table-total">借方小计：{{ fmtNum(debitTotal) }}</div></template>
          </el-table>
        </div>
        <div class="dc-col">
          <div class="dc-head">
            <span>贷方发生额分析</span>
            <el-button v-if="!isReadonly" size="small" @click="addAmountRow('credit')">＋ 新增</el-button>
          </div>
          <el-table :data="creditRows" border size="small" style="width:100%">
            <el-table-column type="index" label="序" width="42" align="center" />
            <el-table-column label="对应科目" min-width="120"><template #default="{ row }"><el-input v-model="row.offsetAccount" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('credit', row.rowId, 'offsetAccount', v)" /></template></el-table-column>
            <el-table-column label="对应金额" width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.amount" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateAmountCell('credit', row.rowId, 'amount', v)" /></template></el-table-column>
            <el-table-column label="备注" min-width="110"><template #default="{ row }"><el-input v-model="row.remark" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('credit', row.rowId, 'remark', v)" /></template></el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="42" align="center"><template #default="{ $index }"><el-button link type="danger" size="small" @click="removeAmountRow('credit', $index)"><el-icon><Delete /></el-icon></el-button></template></el-table-column>
            <template #append><div class="table-total">贷方小计：{{ fmtNum(creditTotal) }}</div></template>
          </el-table>
        </div>
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>现值 = 预计弃置支出 / (1+折现率)^年数</li>
        <li>利息调整 = 期初余额 × 折现率（时间价值累积增加负债）</li>
        <li>折现率为0或负时：现值=未来支出（兜底），利息调整=0</li>
        <li>适用资产：矿井、核电站、油气设施等有法定弃置义务的长期资产</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabDecommissionCheck.vue — K5-5 弃置费用检查表
 * 现值折现+利息调整+回连审定+错误状态
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.4
 * Requirements: 7.1-7.4
 */
import { toRef } from 'vue'
import { Plus, Delete, MagicStick, WarningFilled } from '@element-plus/icons-vue'
import { useK5Decommission } from '../../composables/useK5Decommission'
import type { Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  decommissionRows,
  subtotals,
  crossCheck,
  updateCell,
  addRow,
  removeRow,
  completenessRows,
  addCompletenessRow,
  updateCompletenessCell,
  removeCompletenessRow,
  assumptionRows,
  addAssumptionRow,
  updateAssumptionCell,
  removeAssumptionRow,
  debitRows,
  creditRows,
  debitTotal,
  creditTotal,
  addAmountRow,
  updateAmountCell,
  removeAmountRow,
} = useK5Decommission({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

function save(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }
function handleAddRow() { addRow() }
function handleAiGenerate() { emit('save', 'K5-5-ai-trigger', { remark: 'decommission-conclusion' }) }

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-decommission { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.cross-check-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-section-card { margin-bottom: 12px; }
.k5-section-card :deep(.el-card__header) { padding: 8px 14px; }
.k5-section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.sub-section-title { font-weight: 600; color: #303133; margin: 4px 0 8px; font-size: 13px; }
.hnum { width: 100%; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: #606266; font-weight: 600; }
.dc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.dc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-size: 12px; font-weight: 600; color: #606266; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
