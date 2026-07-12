<template>
  <div class="f5-other-cost">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示其他业务成本（科目6402）各项目本期/上期对比，用于分析成本与对应收入的配比合理性。</p>
        <p>2. 灰色底纹列为自动计算列（变动额/变动率/占比/成本率），不可手工编辑。</p>
        <p>3. 变动率超过 30% 自动标橙，请填写变动原因；成本率异常需关注收入确认与成本结转时点是否配比。</p>
        <p>4. 本期合计应与 F5-1 审定表其他业务成本小计核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他业务成本的完整与准确，验证成本结转与对应收入的配比恰当，识别异常波动的成本项目。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="other.addRow()">+ 新增行</el-button>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" /></span>
        <el-tag size="small" type="info">共 {{ other.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="other.rows.value" size="small" border stripe :row-class-name="rowClass" max-height="500">
      <el-table-column label="#" prop="seq" width="44" />
      <el-table-column label="成本项目" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.costItem" size="small"
            @change="(v: string) => other.updateCell(row.id, 'costItem', v)" />
          <span v-else>{{ row.costItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentAmount" size="small"
            @change="(v: any) => other.updateCell(row.id, 'currentAmount', v)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.priorAmount" size="small"
            @change="(v: any) => other.updateCell(row.id, 'priorAmount', v)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" title="本期-上期">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="变动率%" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="f5-formula" :class="{ 'is-warn': other.isRowHighlighted(row) }" title="(本期-上期)/上期×100">
            {{ pct(row.changeRate) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="占比%" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" title="本期/合计×100">{{ pct(row.proportion) }}</span></template>
      </el-table-column>
      <el-table-column label="对应收入" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.correspondingRevenue" size="small"
            @change="(v: any) => other.updateCell(row.id, 'correspondingRevenue', v)" />
          <span v-else>{{ fmt(row.correspondingRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成本率%" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="f5-formula" title="本期金额/对应收入×100">{{ pct(row.costRate) }}</span></template>
      </el-table-column>
      <el-table-column label="收入确认时点" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.revenueRecognitionTiming" size="small"
            @change="(v: string) => other.updateCell(row.id, 'revenueRecognitionTiming', v)" />
          <span v-else>{{ row.revenueRecognitionTiming }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成本结转时点" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.costRecognitionTiming" size="small"
            @change="(v: string) => other.updateCell(row.id, 'costRecognitionTiming', v)" />
          <span v-else>{{ row.costRecognitionTiming }}</span>
        </template>
      </el-table-column>
      <el-table-column label="配比合理性" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.matchingReasonability" size="small"
            @change="(v: string) => other.updateCell(row.id, 'matchingReasonability', v)" />
          <span v-else>{{ row.matchingReasonability }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.auditEvaluation" size="small"
            @change="(v: string) => other.updateCell(row.id, 'auditEvaluation', v)" />
          <span v-else>{{ row.auditEvaluation }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small"
            @change="(v: string) => other.updateCell(row.id, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="other.removeRow(row.id)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="f5-oc-total">
      <span>本期合计：<b>{{ fmt(other.totalRow.value.currentAmount) }}</b></span>
      <span>上期合计：{{ fmt(other.totalRow.value.priorAmount) }}</span>
      <span>变动额：{{ fmt(other.totalRow.value.changeAmount) }}</span>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReview">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="note" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="其他业务成本分析说明（成本与收入配比、变动原因等）..." @change="saveNote" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** F5TabOtherCost — F5-3 其他业务成本明细（14列 + 变动>30%橙色 + 导入导出） */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { useF5OtherCost } from '../composables/useF5OtherCost'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{ allResponses: Map<string, ChecklistResponse>; wpId: string; isReadonly: boolean }>()

// 父组件模板绑定会自动解包 computed → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const NOTE_KEY = 'F5-3-audit-note'

const other = useF5OtherCost({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})
const note = ref(allResponsesRef.value.get(NOTE_KEY)?.remark ?? '')
const ieCtx = computed(() => (isImportExportSheet('f5', 'F5-3') ? resolveImportExportSheet('f5', 'F5-3') : null))

function saveNote() {
  allResponsesRef.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: note.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: NOTE_KEY, conclusion: null, remark: note.value }] } }))
}
function rowClass({ row }: { row: any }): string { return other.isRowHighlighted(row) ? 'f5-row-orange' : '' }
function fmt(v: number | null | undefined): string { return v == null ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function pct(v: number | 'N/A' | null | undefined): string { return v == null || v === 'N/A' ? 'N/A' : `${v.toFixed(2)}%` }
function openReview() { openReviewDialog('F5-3-conclusion') }
</script>

<style scoped>
.f5-other-cost { padding: 12px; }
.f5-other-cost :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-other-cost :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

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
.f5-oc-total { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }
:deep(.f5-row-orange) { background: #fdf6ec; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
