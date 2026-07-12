<template>
  <div class="g1-level3">
    <div class="section-head">
      <h3 class="sheet-title">G1-7 第三层次公允价值变动调节表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="l3.addRow()">新增调节行</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-6" /></span>
        <el-tag size="small" type="info">共 {{ l3.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-7-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实第三层次（Level 3）公允价值期初至期末变动调节的完整与准确，确认估值方法、关键假设及敏感性分析披露充分，公允价值变动确认恰当。"
      class="objective-alert"
    />

    <el-table :data="l3.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in l3.columns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :fixed="col.prop === 'itemName' ? 'left' : undefined"
      >
        <template #default="{ row, $index }">
          <!-- 序号 -->
          <span v-if="col.prop === 'seq'">{{ $index + 1 }}</span>
          <!-- 公式列（只读） -->
          <span v-else-if="col.formula" class="formula-cell" :title="FORMULA_HINT">
            {{ fmtNum(row[col.prop]) }}
          </span>
          <!-- 数值输入 -->
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="l3.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <!-- 文本 -->
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="l3.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="l3.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <span class="total-label">合计</span>
      期初 {{ fmtNum(l3.grandTotal.value.openingBalance) }} ·
      本期公允变动 {{ fmtNum(l3.grandTotal.value.fairValueChange) }} ·
      期末余额 {{ fmtNum(l3.grandTotal.value.closingBalance) }} ·
      累计变动 {{ fmtNum(l3.grandTotal.value.cumulativeChange) }}
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="l3.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对第三层次公允价值变动的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>期末余额 = 期初余额 + 本期增加 - 本期减少 + 本期公允变动，系统自动计算。</li>
        <li>第三层次（Level 3）采用不可观察输入估值，需说明估值方法、关键假设及敏感性分析。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, inject } from 'vue'
import { useG1Level3 } from '../../composables/useG1Level3'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const l3 = useG1Level3({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const FORMULA_HINT = '期末余额 = 期初余额 + 本期增加 - 本期减少 + 本期公允变动'

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g1-level3 { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-level3 :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-level3 :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.totals { margin-top: 12px; padding-top: 8px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.total-label { margin-right: 12px; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
