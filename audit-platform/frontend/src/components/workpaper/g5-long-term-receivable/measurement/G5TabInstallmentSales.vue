<template>
  <div class="g5-installment-sales">
    <div class="method-context">
      <p><strong>实际利率法</strong>：融资收益 = 期初摊余成本 × 实际利率</p>
      <p>未实现融资收益 = 应收总额 - 公允价值；摊余成本 = 应收 - 未实现</p>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      对分期收款销售形成的长期应收款按实际利率法测算未实现融资收益的摊销，验证各期融资收益与账面确认金额的一致性。
    </el-alert>

    <div class="segment-tabs">
      <el-segmented v-model="sales.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions">
        <GtIndexChip value="wp:G5-6" />
        <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-6" @imported="onImported" />
        <el-button size="small" type="primary" plain @click="sales.addGroup()" :disabled="props.readonly">+ 新增项目</el-button>
      </div>
    </div>

    <div v-show="sales.activeTab.value === 'initial'">
      <template v-for="group in sales.groups.value" :key="group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }}</span>
          <el-button size="small" type="danger" text @click="sales.removeGroup(group.id)" :disabled="props.readonly">删除</el-button>
        </div>
        <el-table :data="[group.initial]" border style="width:100%;font-size:13px">
          <el-table-column label="应收总额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.contractTotal" size="small" :controls="false" :disabled="props.readonly" @change="onRecalcInitial(group)" />
            </template>
          </el-table-column>
          <el-table-column label="公允价值" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.fairValue" size="small" :controls="false" :disabled="props.readonly" @change="onRecalcInitial(group)" />
            </template>
          </el-table-column>
          <el-table-column label="未实现收益" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="应收-公允价值">{{ fmt(row.unrealizedIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="实际利率" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.effectiveRate" size="small" :controls="false" :precision="6" :disabled="props.readonly" @change="sales.recalcGroup(group)" />
            </template>
          </el-table-column>
          <el-table-column label="收款期限" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.collectionTerm" size="small" :disabled="props.readonly" />
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>

    <div v-show="sales.activeTab.value === 'amortization'">
      <template v-for="group in sales.groups.value" :key="group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }}</span>
          <el-button size="small" type="primary" text @click="sales.addPeriod(group.id)" :disabled="props.readonly">+ 新增期间</el-button>
        </div>
        <el-table :data="group.periods" border stripe style="width:100%;font-size:13px">
          <el-table-column prop="periodNo" label="期次" width="55" align="center" />
          <el-table-column label="期初应收" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.openingReceivable" size="small" :controls="false" :disabled="props.readonly" @change="onRecalc(group, row)" />
            </template>
          </el-table-column>
          <el-table-column label="期初摊余成本" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="应收-未实现">{{ fmt(row.openingAmortizedCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期收益" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="摊余成本×实际利率">{{ fmt(row.periodIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期收款" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.periodCollection" size="small" :controls="false" :disabled="props.readonly" @change="onRecalc(group, row)" />
            </template>
          </el-table-column>
          <el-table-column label="期末应收" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingReceivable) }}</span></template>
          </el-table-column>
          <el-table-column label="期末摊余" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingAmortizedCost) }}</span></template>
          </el-table-column>
        </el-table>
        <div v-if="!sales.validateContinuity(group)" class="continuity-warning">⚠ 期间连续性校验未通过</div>
      </template>
    </div>

    <div class="totals-bar">融资收益合计：{{ fmt(sales.totalIncome.value) }}</div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><div class="section-header"><span>审计结论</span><el-button size="small" type="primary" text>AI 辅助</el-button></div></template>
      <el-input v-model="sales.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="props.readonly" />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>初始交易要素：未实现收益 = 应收总额 − 公允价值；实际利率按现值等式反推</li>
        <li>分期摊销：本期收益 = 期初摊余成本 × 实际利率</li>
        <li>期末应收 = 期初应收 − 本期收款；期末摊余 = 期初摊余 + 本期收益 − 本期收款</li>
        <li>期间连续性：第 N 期期初 = 第 N−1 期期末，校验未通过会橙色告警</li>
        <li>融资收益合计与账面确认的利息收入比较，差异需分析</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { useG5InstallmentSales } from '../../composables/useG5InstallmentSales'
import type { InstallmentSalesGroup, InstallmentPeriod } from '../../composables/useG5InstallmentSales'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const sales = useG5InstallmentSales()
const tabOptions = [{ label: '初始交易要素', value: 'initial' }, { label: '分期摊销', value: 'amortization' }]

function onRecalcInitial(group: InstallmentSalesGroup) { sales.recalcInitial(group); sales.recalcGroup(group) }
function onRecalc(group: InstallmentSalesGroup, period: InstallmentPeriod) { sales.recalcPeriod(period, group.initial.effectiveRate) }
function onImported(rows: unknown[]) {
  sales.loadData({ groups: rows })
}
function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g5-installment-sales { font-size: 13px; }
.method-context { margin-bottom: 12px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 0 4px 4px 0; font-size: 12px; color: #865c0a; }
.audit-objective { margin-bottom: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.tab-actions { margin-left: auto; display: flex; gap: 8px; }
.group-header { display: flex; align-items: center; gap: 8px; margin: 12px 0 4px; padding: 6px 12px; background: #f0f9eb; border-left: 3px solid #67c23a; border-radius: 0 4px 4px 0; }
.group-title { font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.continuity-warning { color: #e6a23c; font-size: 12px; margin: 4px 0 8px 12px; }
.totals-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
.conclusion-card { margin-top: 12px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
</style>
