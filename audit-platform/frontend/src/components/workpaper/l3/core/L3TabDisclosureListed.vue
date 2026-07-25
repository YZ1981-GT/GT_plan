<template>
  <div class="l3-tab-disclosure-listed">
    <!-- ═══ 返回目录 + 标题 ═══ -->
    <div class="disclosure-header">
      <div class="disclosure-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="disclosure-title">附注披露信息核对（上市公司）</h3>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司长期借款附注披露：</strong>
        按担保方式（质押/抵押/保证/信用借款）分类列示期末余额、上年年末余额及利率区间，
        <strong>合计 = 小计 − 减一年内到期的长期借款</strong>（一年内到期部分单独列示于流动负债）。
        数据自 L3-2 明细按类型聚合（只读），审定变化时自动刷新。
      </div>
    </div>

    <!-- ═══ 主表：长期借款分类 ═══ -->
    <div class="disclosure-section">
      <div class="section-header"><span class="section-title">① 长期借款（按担保方式分类）</span></div>
      <el-table :data="classificationRows" border size="small" style="width: 100%" :row-class-name="rowClass">
        <el-table-column prop="label" label="项目" min-width="200">
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
        <el-table-column label="上年年末余额" min-width="140" align="right">
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

    <!-- ═══ 财产抵押质押说明 ═══ -->
    <div class="disclosure-section">
      <div class="section-header"><span class="section-title">说明：公司用于抵押、质押的财产</span></div>
      <el-input :model-value="propertyNote" type="textarea" :autosize="{ minRows: 2 }" :readonly="isReadonly" placeholder="说明公司用于抵押、质押的财产情况（可关联 L3-8 抵质押资产检查）..." @input="(v: string) => updateNote('property-note', v)" />
    </div>

    <!-- ═══ (1) 一年内到期的长期借款 ═══ -->
    <div class="disclosure-section">
      <div class="section-header"><span class="section-title">（1）一年内到期的长期借款</span></div>
      <el-table :data="currentPortionRows" border size="small" style="width: 100%" :row-class-name="cpRowClass">
        <el-table-column prop="label" label="项目" min-width="200">
          <template #default="{ row }"><span :class="{ 'row-bold': row.isTotal }">{{ row.label }}</span></template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="150" align="right">
          <template #default="{ row }">{{ fmtAmount(row.endAmount) }}</template>
        </el-table-column>
        <el-table-column label="上年年末余额" min-width="150" align="right">
          <template #default="{ row }">{{ fmtAmount(row.priorAmount) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 审计结论 ═══ -->
    <div class="conclusion-section">
      <el-card shadow="never">
        <template #header><span class="conclusion-title">审计结论</span></template>
        <el-input :model-value="conclusion" type="textarea" :autosize="{ minRows: 3 }" :readonly="isReadonly" placeholder="附注披露核对结论：披露分类/金额/利率/担保是否完整准确，与审定表 L3-1 是否一致..." @input="(v: string) => updateNote('conclusion', v)" />
      </el-card>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>分类固定行</strong>：质押/抵押/保证/信用借款 + 小计 − 减一年内到期 = 合计，对齐源模板</li>
        <li><strong>数据来源</strong>：从 L3-2 明细按借款类型 SUMIF 聚合，期末=审定期末，上年年末=审定期初，只读</li>
        <li><strong>利率区间</strong>：同类借款利率不一致时按行手工填列利率区间</li>
        <li><strong>合计口径</strong>：合计 = 小计 − 一年内到期（一年内到期在流动负债单独列示，见（1）子表）</li>
        <li><strong>交叉验证</strong>：合计应与审定表 L3-1 期末披露审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabDisclosureListed — 附注披露信息核对（上市公司，源模板重建）
 *
 * - 分类固定行（质押/抵押/保证/信用借款）+ 小计 − 减一年内到期 = 合计 + 利率区间
 * - (1) 一年内到期的长期借款 子表 + 财产抵押质押说明 + 审计结论
 * - 数据从 L3-2 明细按类型聚合（只读），订阅 substantive:adjudicated 自动刷新
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
  propertyNote,
  conclusion,
  updateNote,
} = useL3Disclosure(formData.allResponses, formData.debouncedSave, 'listed')

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
.l3-tab-disclosure-listed {
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
