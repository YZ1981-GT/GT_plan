<template>
  <div class="f5-comparison">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按品种对比本期与上期的收入、成本、毛利及毛利率，用于毛利分析与成本合理性验证。</p>
        <p>2. 灰色底纹列为自动计算列（毛利/毛利率/变动额率/毛利率变动），不可手工编辑。</p>
        <p>3. 毛利率变动超过 5pp、收入与成本变动率不匹配（差异>10%）自动标橙，请填写变动原因与审计评价。</p>
        <p>4. 毛利率异常波动可能提示成本结转错误或收入截止问题，须结合 F5-6 量本核对与 F5-7 成本倒轧综合判断。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过毛利率同比分析识别营业成本异常波动，验证成本与收入配比的合理性，为营业成本整体合理性结论提供分析证据。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddRow">+ 品种</el-button>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" /></span>
        <el-tag size="small" type="info">共 {{ cmp.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="cmp.rows.value" size="small" border stripe :row-class-name="rowClass" max-height="500">
      <el-table-column label="品种" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.product" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'product', v)" />
          <span v-else>{{ row.product }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期收入" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentRevenue" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'currentRevenue', v)" />
          <span v-else>{{ fmt(row.currentRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期成本" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentCost" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'currentCost', v)" />
          <span v-else>{{ fmt(row.currentCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期毛利" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" title="收入-成本">{{ fmt(row.currentGrossProfit) }}</span></template>
      </el-table-column>
      <el-table-column label="本期毛利率%" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" title="毛利/收入×100">{{ pct(row.currentGrossMargin) }}</span></template>
      </el-table-column>
      <el-table-column label="上期收入" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.priorRevenue" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'priorRevenue', v)" />
          <span v-else>{{ fmt(row.priorRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期成本" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.priorCost" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'priorCost', v)" />
          <span v-else>{{ fmt(row.priorCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期毛利" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" title="收入-成本">{{ fmt(row.priorGrossProfit) }}</span></template>
      </el-table-column>
      <el-table-column label="上期毛利率%" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" title="毛利/收入×100">{{ pct(row.priorGrossMargin) }}</span></template>
      </el-table-column>
      <el-table-column label="收入变动额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula">{{ fmt(row.revenueChange) }}</span></template>
      </el-table-column>
      <el-table-column label="收入变动率%" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" :class="{ 'is-warn': cmp.isMismatch(row) }">{{ pct(row.revenueChangeRate) }}</span></template>
      </el-table-column>
      <el-table-column label="成本变动额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula">{{ fmt(row.costChange) }}</span></template>
      </el-table-column>
      <el-table-column label="成本变动率%" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" :class="{ 'is-warn': cmp.isMismatch(row) }">{{ pct(row.costChangeRate) }}</span></template>
      </el-table-column>
      <el-table-column label="毛利率变动(pp)" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" :class="{ 'is-warn': cmp.isMarginChangeHigh(row) }" title="本期毛利率-上期毛利率">{{ pp(row.marginChange) }}</span></template>
      </el-table-column>
      <el-table-column label="变动原因" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.changeReason" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'changeReason', v)" />
          <span v-else>{{ row.changeReason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.auditEvaluation" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'auditEvaluation', v)" />
          <span v-else>{{ row.auditEvaluation }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="cmp.removeRow(row.id)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="f5-cmp-total">
      <span>本期毛利率：<b>{{ pct(cmp.totalRow.value.currentGrossMargin) }}</b></span>
      <span>上期毛利率：{{ pct(cmp.totalRow.value.priorGrossMargin) }}</span>
      <span>本期毛利：{{ fmt(cmp.totalRow.value.currentGrossProfit) }}</span>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReview">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="毛利率比较分析结论..." @change="saveConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** F5TabComparison — F5-5 比较分析（17列 + 毛利率变动>5pp橙色 + 收入成本不匹配>10%橙色 + 品种增删 + 导入导出） */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useF5Comparison } from '../composables/useF5Comparison'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{ allResponses: Map<string, ChecklistResponse>; wpId: string; isReadonly: boolean }>()

// 父组件模板绑定会自动解包 computed → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const CONCLUSION_KEY = 'F5-5-conclusion'

const cmp = useF5Comparison({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})
const conclusion = ref(allResponsesRef.value.get(CONCLUSION_KEY)?.remark ?? '')
const ieCtx = computed(() => (isImportExportSheet('f5', 'F5-5') ? resolveImportExportSheet('f5', 'F5-5') : null))

function saveConclusion() {
  allResponsesRef.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value }] } }))
}
async function promptAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '品种名称不能为空',
    })
    if (value) cmp.addRow(value.trim())
  } catch { /* 取消 */ }
}
function rowClass({ row }: { row: any }): string { return cmp.isRowHighlighted(row) ? 'f5-row-orange' : '' }
function fmt(v: number | null | undefined): string { return v == null ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function pct(v: number | 'N/A' | null | undefined): string { return v == null || v === 'N/A' ? 'N/A' : `${v.toFixed(2)}%` }
function pp(v: number | 'N/A' | null | undefined): string { return v == null || v === 'N/A' ? 'N/A' : `${v.toFixed(2)}pp` }
function openReview() { openReviewDialog('F5-5-conclusion') }
</script>

<style scoped>
.f5-comparison { padding: 12px; }
.f5-comparison :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-comparison :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 表格 */
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.f5-cmp-total { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }
:deep(.f5-row-orange) { background: #fdf6ec; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
