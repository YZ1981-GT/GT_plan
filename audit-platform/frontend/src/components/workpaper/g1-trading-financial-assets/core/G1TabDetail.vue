<template>
  <div class="g1-detail">
    <h3 class="sheet-title">G1-2 交易性金融资产明细表</h3>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">新增证券</el-button>
    </div>
    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="rows" border size="small" max-height="500">
      <el-table-column prop="securityName" label="证券名称" width="140" fixed />

      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
      >
        <template #default="{ row }">
          <!-- 公式列（只读） -->
          <span v-if="col.formula" class="formula-cell" :title="formulaHint(col.prop)">
            {{ fmtCell(row[col.prop]) }}
          </span>
          <!-- 投资类型下拉 -->
          <el-select
            v-else-if="col.type === 'invest'"
            v-model="row.investType"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { investType: row.investType })"
          >
            <el-option v-for="o in investOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <!-- 公允价值来源 Level 下拉 -->
          <el-select
            v-else-if="col.type === 'level'"
            v-model="row.fairValueSource"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { fairValueSource: row.fairValueSource })"
          >
            <el-option value="1" label="Level 1" />
            <el-option value="2" label="Level 2" />
            <el-option value="3" label="Level 3" />
          </el-select>
          <!-- 数值输入 -->
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <!-- 日期 -->
          <el-input
            v-else-if="col.type === 'date'"
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            placeholder="YYYY-MM-DD"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <!-- 文本 -->
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分类小计 + 总计 -->
    <div class="totals">
      <div v-for="st in subtotalsByType" :key="st.investType" class="subtotal-line">
        <span class="subtotal-label">{{ st.investLabel }}小计({{ st.count }})</span>
        期末成本 {{ fmtCell(st.totals.closingCost) }} · 公允价值 {{ fmtCell(st.totals.closingFairValue) }} · 审定 {{ fmtCell(st.totals.adjusted) }}
      </div>
      <div class="grand-total">
        <span class="subtotal-label">总计</span>
        期末成本 {{ fmtCell(grandTotal.closingCost) }} · 公允价值 {{ fmtCell(grandTotal.closingFairValue) }} · 投资收益合计 {{ fmtCell(grandTotal.totalIncome) }} · 审定 {{ fmtCell(grandTotal.adjusted) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef, computed } from 'vue'
import {
  useG1Detail,
  G1_INVEST_TYPE_OPTIONS,
  type TradingDetailRow,
} from '../../composables/useG1Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// 解构到顶层：composable 返回的 ref 只有作为顶层绑定时才会在模板中自动解包
// （嵌套访问 detail.rows / detail.grandTotal.x 不解包 → el-table 收到 ref、computed.x 为 undefined）
const {
  segments,
  segment,
  rows,
  subtotalsByType,
  grandTotal,
  addRow,
  updateRow,
  removeRow,
} = useG1Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const investOptions = G1_INVEST_TYPE_OPTIONS

const segmentOptions = segments.map((s) => ({ label: s.label, value: s.key }))

const currentColumns = computed(() => {
  const seg = segments.find((s) => s.key === segment.value)
  // 基础信息区段的证券名称已作为 fixed 列展示，避免重复
  return (seg?.columns ?? []).filter((c) => c.prop !== 'securityName')
})

const FORMULA_HINTS: Partial<Record<keyof TradingDetailRow, string>> = {
  closingQuantity: '期末持有数量 = 期初 + 买入 - 卖出',
  closingFairValue: '期末公允价值 = 期末持有数量 × 期末单位公允值',
  fairValueChange: '公允价值变动 = 期末公允价值 - 期初公允价值',
  realizedGain: '已实现损益 = 处置收入 - 处置成本',
  totalIncome: '投资收益合计 = 已实现损益 + 利息/股利收入',
  closingCost: '期末成本 = 期初成本 + 本期增加成本 - 本期减少成本',
  adjusted: '审定余额 = 未审 + AJE + RJE',
  variance: '差异 = 审定余额 - 期末公允价值',
}

function formulaHint(prop: keyof TradingDetailRow): string {
  return FORMULA_HINTS[prop] ?? ''
}

function fmtCell(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g1-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.sheet-title { margin: 0 0 12px; }
.toolbar { margin-bottom: 8px; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-line { padding: 2px 0; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
</style>
