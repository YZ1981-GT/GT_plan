<template>
  <div class="g5-balance-detail">
    <!-- 区段Tab切换 -->
    <div class="segment-tabs">
      <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions">
        <el-button size="small" type="primary" plain @click="detail.addRow()" :disabled="props.readonly">
          + 新增债务人
        </el-button>
      </div>
    </div>

    <!-- Tab1: 债务人基础信息 -->
    <el-table
      v-show="detail.activeTab.value === 'basic'"
      :data="detail.rows.value"
      :height="500"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorName" label="债务人名称" min-width="120" />
      <el-table-column prop="businessType" label="业务类型" width="100">
        <template #default="{ row }">
          <el-select v-model="row.businessType" size="small" :disabled="props.readonly">
            <el-option label="融资租赁" value="lease" />
            <el-option label="分期销售" value="installment" />
            <el-option label="保理" value="factoring" />
            <el-option label="其他" value="other" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="contractNo" label="合同编号" min-width="100" />
      <el-table-column prop="startDate" label="起始日" width="100" />
      <el-table-column prop="maturityDate" label="到期日" width="100" />
      <el-table-column prop="contractAmount" label="合同总额" min-width="100" align="right" />
      <el-table-column prop="recoveredAmount" label="已收回金额" min-width="100" align="right" />
      <el-table-column label="期末余额" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="合同总额-已收回">{{ fmt(row.closingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="isRelatedParty" label="关联方" width="70" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.isRelatedParty" :disabled="props.readonly" />
        </template>
      </el-table-column>
    </el-table>

    <!-- Tab2: 余额分析+账龄 -->
    <el-table
      v-show="detail.activeTab.value === 'aging'"
      :data="detail.rows.value"
      :height="500"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorName" label="债务人名称" min-width="120" />
      <el-table-column prop="unrealizedIncome" label="未实现融资收益" min-width="110" align="right" />
      <el-table-column label="净额" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末余额-未实现融资收益">{{ fmt(row.netAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="aging1Year" label="1年以内" min-width="80" align="right" />
      <el-table-column prop="aging1to2" label="1-2年" min-width="70" align="right" />
      <el-table-column prop="aging2to3" label="2-3年" min-width="70" align="right" />
      <el-table-column prop="aging3to4" label="3-4年" min-width="70" align="right" />
      <el-table-column prop="aging4to5" label="4-5年" min-width="70" align="right" />
      <el-table-column prop="aging5Plus" label="5年以上" min-width="80" align="right" />
      <el-table-column label="账龄合计" min-width="90" align="right">
        <template #default="{ row }">
          <span
            class="formula-cell"
            :class="{ 'mismatch': Math.abs(row.agingTotal - row.netAmount) > 0.01 }"
            title="各账龄段之和"
          >{{ fmt(row.agingTotal) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100" />
    </el-table>

    <!-- 底部合计 -->
    <div class="totals-bar">
      合同总额: {{ fmt(detail.totals.value.contractAmount) }} |
      已收回: {{ fmt(detail.totals.value.recoveredAmount) }} |
      期末余额: {{ fmt(detail.totals.value.closingBalance) }} |
      净额: {{ fmt(detail.totals.value.netAmount) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { useG5BalanceDetail } from '../../composables/useG5BalanceDetail'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const detail = useG5BalanceDetail()

const tabOptions = [
  { label: '债务人基础信息', value: 'basic' },
  { label: '余额分析+账龄', value: 'aging' },
]

function onRowChange(row: any) {
  if (row) {
    const idx = detail.rows.value.findIndex(r => r.id === row.id)
    if (idx >= 0) detail.activeRowIndex.value = idx
  }
}

function fmt(v: number): string {
  return v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '-'
}
</script>

<style scoped>
.g5-balance-detail { font-size: 13px; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.tab-actions { margin-left: auto; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.mismatch { color: #f56c6c; font-weight: 600; }
.totals-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
</style>
