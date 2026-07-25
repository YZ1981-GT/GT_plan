<template>
  <div class="l3-tab-disclosure-soe">
    <!-- ═══ 返回目录 + 标题 ═══ -->
    <div class="disclosure-header">
      <div class="disclosure-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="disclosure-title">附注披露（国企）信息核对</h3>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业长期借款附注披露：</strong>
        按担保方式（质押/抵押/保证/信用借款）分类列示期末余额、期初余额及利率区间，
        <strong>合计 = 小计 − 减一年内到期的长期借款</strong>。国企与上市结构一致（列头为「期初余额」），
        额外说明资产负债表日后已偿还金额及展期情况。数据自 L3-2 明细按类型聚合（只读）。
      </div>
    </div>

    <!-- ═══ 主表：长期借款分类 ═══ -->
    <div class="disclosure-section">
      <div class="section-header"><span class="section-title">（1）长期借款分类</span></div>
      <el-table :data="classificationRows" border size="small" style="width: 100%" :row-class-name="rowClass">
        <el-table-column prop="label" label="借款类别" min-width="200">
          <template #default="{ row }"><span :class="{ 'row-bold': row.isTotal || row.isSubtotal }">{{ row.label }}</span></template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="140" align="right">
          <template #default="{ row }">{{ fmtAmount(row.endAmount) }}</template>
        </el-table-column>
        <el-table-column label="利率区间" min-width="130">
          <template #default="{ row }">
            <el-input v-if="row.rateEditable && !isReadonly" :model-value="rateRange(row.rowKey, 'end')" size="small" placeholder="如3.5%~4.2%" @input="(v: string) => updateRate(row.rowKey, 'end', v)" />
            <span v-else>{{ row.rateEditable ? (rateRange(row.rowKey, 'end') || '-') : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="140" align="right">
          <template #default="{ row }">{{ fmtAmount(row.priorAmount) }}</template>
        </el-table-column>
        <el-table-column label="利率区间" min-width="130">
          <template #default="{ row }">
            <el-input v-if="row.rateEditable && !isReadonly" :model-value="rateRange(row.rowKey, 'prior')" size="small" placeholder="如3.5%~4.2%" @input="(v: string) => updateRate(row.rowKey, 'prior', v)" />
            <span v-else>{{ row.rateEditable ? (rateRange(row.rowKey, 'prior') || '-') : '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 国企额外说明 ═══ -->
    <div class="disclosure-section">
      <div class="section-header"><span class="section-title">① 资产负债表日后已偿还金额</span></div>
      <el-input :model-value="repaidNote" type="textarea" :autosize="{ minRows: 2 }" :readonly="isReadonly" placeholder="资产负债表日后已偿还金额 XX 元..." @input="(v: string) => updateNote('repaid-note', v)" />
    </div>
    <div class="disclosure-section">
      <div class="section-header"><span class="section-title">② 展期说明</span></div>
      <el-input :model-value="extensionNote" type="textarea" :autosize="{ minRows: 2 }" :readonly="isReadonly" placeholder="因逾期借款获得展期形成的长期借款，说明获得展期的条件、本金、利息、预计还款安排等..." @input="(v: string) => updateNote('extension-note', v)" />
    </div>

    <!-- ═══ (1) 一年内到期的长期借款 ═══ -->
    <div class="disclosure-section">
      <div class="section-header"><span class="section-title">（1）一年内到期的长期借款</span></div>
      <el-table :data="currentPortionRows" border size="small" style="width: 100%" :row-class-name="cpRowClass">
        <el-table-column prop="label" label="借款类别" min-width="200">
          <template #default="{ row }"><span :class="{ 'row-bold': row.isTotal }">{{ row.label }}</span></template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="150" align="right">
          <template #default="{ row }">{{ fmtAmount(row.endAmount) }}</template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="150" align="right">
          <template #default="{ row }">{{ fmtAmount(row.priorAmount) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 审计结论 ═══ -->
    <div class="conclusion-section">
      <el-card shadow="never">
        <template #header><span class="conclusion-title">审计结论</span></template>
        <el-input :model-value="conclusion" type="textarea" :autosize="{ minRows: 3 }" :readonly="isReadonly" placeholder="附注披露核对结论：披露分类/金额/利率是否完整准确，与审定表 L3-1 是否一致..." @input="(v: string) => updateNote('conclusion', v)" />
      </el-card>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>分类固定行</strong>：质押/抵押/保证/信用借款 + 小计 − 减一年内到期 = 合计，对齐源模板</li>
        <li><strong>数据来源</strong>：从 L3-2 明细按借款类型 SUMIF 聚合，期末=审定期末，期初=审定期初，只读</li>
        <li><strong>国企额外披露</strong>：资产负债表日后已偿还金额、逾期借款展期条件/本金/利息/预计还款安排</li>
        <li><strong>合计口径</strong>：合计 = 小计 − 一年内到期</li>
        <li><strong>交叉验证</strong>：合计应与审定表 L3-1 期末披露审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabDisclosureSoe — 附注披露（国企）信息核对（源模板重建）
 *
 * - 分类固定行（质押/抵押/保证/信用借款）+ 小计 − 减一年内到期 = 合计 + 利率区间
 * - ① 资产负债表日后已偿还 + ② 展期说明 + (1) 一年内到期子表 + 审计结论
 * - 与上市版共享 useL3Disclosure（variant='soe'），第二计量列为「期初余额」
 *
 * 科目：2501 长期借款（贷方/负债类）
 */
import { inject, onMounted, onUnmounted } from 'vue'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'
import { useL3Disclosure, type L3DisclosureRow, type L3CurrentPortionRow } from '@/components/workpaper/composables/useL3Disclosure'
import { eventBus } from '@/utils/eventBus'

defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{ (e: 'navigate', sheetName: string): void }>()

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

const {
  classificationRows,
  currentPortionRows,
  rateRange,
  updateRate,
  repaidNote,
  extensionNote,
  conclusion,
  updateNote,
} = useL3Disclosure(formData.allResponses, formData.debouncedSave, 'soe')

function handleAdjudicatedRefresh(): void {
  formData.loadData()
}
onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicatedRefresh)
})
onUnmounted(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicatedRefresh)
})

function rowClass({ row }: { row: L3DisclosureRow }): string {
  if (row.isTotal) return 'total-row'
  if (row.isSubtotal) return 'subtotal-row'
  if (row.isDeduction) return 'deduct-row'
  return ''
}
function cpRowClass({ row }: { row: L3CurrentPortionRow }): string {
  return row.isTotal ? 'total-row' : ''
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l3-tab-disclosure-soe {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.disclosure-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.disclosure-header-left { display: flex; align-items: center; gap: 12px; }
.disclosure-title { font-size: 15px; font-weight: 600; color: #303133; margin: 0; }

.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.6;
}
.methodology-text strong { color: #b45309; }

.disclosure-section { margin-bottom: 18px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding: 6px 10px; background: #f5f7fa; border-radius: 4px; }
.section-title { font-weight: 600; font-size: var(--wp-font-size, 13px); color: #303133; }

.row-bold { font-weight: 700; }
:deep(.total-row) { background-color: #f0f9eb !important; font-weight: 700; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.deduct-row) { color: #e6a23c; }

.conclusion-section { margin-top: 16px; }
.conclusion-title { font-size: 14px; font-weight: 600; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table th .cell) { font-size: var(--wp-font-size, 13px); font-weight: 600; }
:deep(.el-textarea__inner) { font-size: var(--wp-font-size, 13px); line-height: 1.6; }

.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.l3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.l3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
