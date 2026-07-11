<template>
  <div class="f5-monthly">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示主营业务成本（科目6401）各品种的月度明细，用于月度波动分析与成本结转合理性验证。</p>
        <p>2. 灰色底纹列为自动计算列（合计/占比/月均/波动系数/变动额率），不可手工编辑。</p>
        <p>3. 波动系数（标准差/均值）超过 0.5、变动率超过 20% 自动标橙，请关注异常月度并在核对中说明。</p>
        <p>4. 上下半年两区段共享同一品种行，全年合计与 F5-1 审定表主营业务成本按品种核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实营业成本各品种月度结转的完整与准确，识别异常月度波动，验证成本结转与生产/销售节奏匹配。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddRow">+ 品种</el-button>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown v-if="importExportCtx" :wp-id="wpId" :api-prefix="importExportCtx.apiPrefix"
          :sheet="importExportCtx.sheet" :disabled="isReadonly" @imported="$emit('imported')" />
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-tabs v-model="segment" type="border-card">
      <!-- 上半年区段 -->
      <el-tab-pane label="上半年（1~6月 + 统计）" name="h1">
        <el-table :data="detail.rows.value" size="small" border stripe :row-class-name="rowClass" max-height="480">
          <el-table-column label="品种" width="130" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.product" size="small"
                @change="(v: string) => detail.updateCell(row.id, 'product', v)" />
              <span v-else>{{ row.product }}</span>
            </template>
          </el-table-column>
          <el-table-column v-for="m in 6" :key="`m${m}`" :label="`${m}月`" width="90" align="right">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model.number="row[`month${m}`]" size="small"
                @change="(v: any) => detail.updateCell(row.id, `month${m}`, v)" />
              <span v-else>{{ fmt(row[`month${m}`]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="上半年合计" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="f5-formula" title="1月+…+6月">{{ fmt(row.halfYear1Total) }}</span></template>
          </el-table-column>
          <el-table-column label="占比%" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="f5-formula" title="本品种全年/合计全年×100">{{ pct(row.halfYear1Ratio) }}</span></template>
          </el-table-column>
          <el-table-column label="月均" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="f5-formula" title="上半年合计/6">{{ fmt(row.halfYear1Avg) }}</span></template>
          </el-table-column>
          <el-table-column label="最高月" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(row.halfYear1Max) }}</template>
          </el-table-column>
          <el-table-column label="最低月" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(row.halfYear1Min) }}</template>
          </el-table-column>
          <el-table-column label="波动系数" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="f5-formula" :class="{ 'is-warn': detail.isVolatilityHigh(row) }" title="标准差/均值(12月)">
                {{ (row.coeffOfVariation ?? 0).toFixed(3) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60" v-if="!isReadonly">
            <template #default="{ row }">
              <el-popconfirm title="确认删除？" @confirm="detail.removeRow(row.id)">
                <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 下半年+合计区段 -->
      <el-tab-pane label="下半年（7~12月 + 合计对比）" name="h2">
        <el-table :data="detail.rows.value" size="small" border stripe :row-class-name="rowClass" max-height="480">
          <el-table-column label="品种" width="130" fixed>
            <template #default="{ row }"><span>{{ row.product }}</span></template>
          </el-table-column>
          <el-table-column v-for="m in 6" :key="`m${m + 6}`" :label="`${m + 6}月`" width="90" align="right">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model.number="row[`month${m + 6}`]" size="small"
                @change="(v: any) => detail.updateCell(row.id, `month${m + 6}`, v)" />
              <span v-else>{{ fmt(row[`month${m + 6}`]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="下半年合计" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="f5-formula" title="7月+…+12月">{{ fmt(row.halfYear2Total) }}</span></template>
          </el-table-column>
          <el-table-column label="全年合计" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="f5-formula" title="上半年+下半年">{{ fmt(row.yearTotal) }}</span></template>
          </el-table-column>
          <el-table-column label="上期合计" width="110" align="right">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model.number="row.priorYearTotal" size="small"
                @change="(v: any) => detail.updateCell(row.id, 'priorYearTotal', v)" />
              <span v-else>{{ fmt(row.priorYearTotal) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动额" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="f5-formula" title="全年-上期">{{ fmt(row.changeAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="变动率%" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="f5-formula" :class="{ 'is-warn': detail.isRowHighlighted(row) }" title="变动额/上期×100">
                {{ pct(row.changeRate) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 底部合计 -->
    <div class="f5-monthly-total">
      <span>全年合计：<b>{{ fmt(detail.totalRow.value.yearTotal) }}</b></span>
      <span>上半年：{{ fmt(detail.totalRow.value.halfYear1Total) }}</span>
      <span>下半年：{{ fmt(detail.totalRow.value.halfYear2Total) }}</span>
      <span>上期合计：{{ fmt(detail.totalRow.value.priorYearTotal) }}</span>
      <span>变动率：{{ pct(detail.totalRow.value.changeRate) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabMonthlyDetail.vue — F5-2 月度明细（24列 → 2区段Tab）
 * 区段间行同步（共享同一 storedRow）+ 变动>20%橙色 / 波动系数>0.5橙色 + 动态品种行增删 + 底部合计
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useF5MonthlyDetail } from '../composables/useF5MonthlyDetail'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
}>()

// 父组件模板绑定会自动解包 computed → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const segment = ref('h1')
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const detail = useF5MonthlyDetail({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const importExportCtx = computed(() =>
  isImportExportSheet('f5', 'F5-2') ? resolveImportExportSheet('f5', 'F5-2') : null,
)

async function promptAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '品种名称不能为空',
    })
    if (value) detail.addRow(value.trim())
  } catch { /* 取消 */ }
}

function rowClass() { return '' }
function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function pct(v: number | 'N/A' | null | undefined): string {
  if (v == null || v === 'N/A') return 'N/A'
  return `${v.toFixed(2)}%`
}
void reloadWorkpaperData
</script>

<style scoped>
.f5-monthly { padding: 12px; }
.f5-monthly :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f5-monthly :deep(.el-table .cell) { font-size: 13px !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
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
.f5-monthly-total { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; flex-wrap: wrap; }
</style>
