<template>
  <div class="g1-detail">
    <h3 class="sheet-title">G1-2 交易性金融资产明细表</h3>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按投资品种（股票 / 基金 / 债券 / 衍生工具 / 其他）分区段列示交易性金融资产明细，涵盖成本、公允价值与投资收益。</p>
        <p>2. 灰底列为自动计算列（期末数量 / 期末公允价值 / 公允价值变动 / 已实现损益 / 投资收益合计 / 期末成本 / 审定余额 / 差异），不可手动编辑。</p>
        <p>3. 公允价值来源按层级（Level 1/2/3）划分，应与 G1-6 公允价值测试表保持一致。</p>
        <p>4. 本表分类小计与总计应与审定表（G1-1，科目 1501）勾稽一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实交易性金融资产各投资品种期末成本、公允价值及投资收益明细的准确与完整，验证公允价值层级划分与分类恰当，为审定表（G1-1，科目1501）提供明细支撑。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">新增证券</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
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

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：（1）执行的明细核对程序及结果；（2）各投资品种成本、公允价值、投资收益的核实情况及异常事项。" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：明细金额是否准确、完整，是否与审定表（G1-1，科目1501）勾稽一致。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, watch } from 'vue'
import {
  useG1Detail,
  G1_INVEST_TYPE_OPTIONS,
  type TradingDetailRow,
} from '../../composables/useG1Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

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

const AUDIT_NOTE_KEY = 'G1-2-audit-note'
const AUDIT_CONCLUSION_KEY = 'G1-2-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
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
.g1-detail :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-detail :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.conclusion-card { margin-top: 12px; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-line { padding: 2px 0; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
</style>
