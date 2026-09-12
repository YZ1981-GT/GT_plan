<template>
<div class="d3-detail">
  <!-- 审计目标 -->
  <el-alert type="info" :closable="false" show-icon class="audit-objective">
    <template #title>
      <strong>审计目标</strong>：核实预收账款明细的完整性、准确性与列报，验证期初/期末审定数与账龄勾稽，识别关联方、款项性质及超期未结转情况（CAS 1101 / CAS 14 收入）。
    </template>
  </el-alert>

  <!-- 搜索 + 工具栏 -->
  <div class="detail-toolbar">
    <el-input
      v-model="searchQuery"
      size="small"
      placeholder="搜索客户名称..."
      clearable
      style="width: 240px"
    />
    <div class="toolbar-actions">
      <el-button-group size="small">
        <el-button @click="onExportTemplate">导出模板</el-button>
        <el-button @click="onExportData">导出数据</el-button>
        <el-upload
          :show-file-list="false"
          accept=".xlsx"
          :before-upload="onImportFile"
        >
          <el-button>导入数据</el-button>
        </el-upload>
      </el-button-group>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加客户</el-button>
      <el-button size="small" :disabled="isReadonly" @click="onImportFromAuxBalance">从余额表导入</el-button>
      <!-- ⚙ 列设置（宽表列自定义） -->
      <el-popover placement="bottom-end" :width="360" trigger="click">
        <template #reference>
          <el-button size="small">⚙ 列设置（{{ visibleCount }}/{{ totalCount }}）</el-button>
        </template>
        <div class="col-prefs-panel">
          <div class="col-prefs-presets">
            <span class="col-prefs-label">预设：</span>
            <el-radio-group :model-value="activePreset" size="small" @change="(v: any) => applyPreset(v)">
              <el-radio-button v-for="p in colPresets" :key="p.name" :value="p.name" :title="p.description">
                {{ p.label }}
              </el-radio-button>
            </el-radio-group>
          </div>
          <div class="col-prefs-actions">
            <el-button size="small" @click="hideEmptyColumns">隐藏空列</el-button>
            <el-button size="small" @click="applyPreset('all')">全部显示</el-button>
          </div>
          <el-scrollbar max-height="320px">
            <div v-for="g in prefGroups" :key="g" class="col-prefs-group">
              <el-checkbox
                :model-value="isGroupVisible(g)"
                :indeterminate="isGroupPartial(g)"
                @change="(v: any) => toggleGroup(g, !!v)"
              >
                <strong>{{ g }}</strong>
              </el-checkbox>
              <div class="col-prefs-items">
                <el-checkbox
                  v-for="col in getGroupColumns(g)"
                  :key="col.key"
                  :model-value="isColumnVisible(col.key)"
                  @change="(v: any) => toggleColumn(col.key, !!v)"
                >{{ col.label }}</el-checkbox>
              </div>
            </div>
          </el-scrollbar>
        </div>
      </el-popover>
    </div>
  </div>

  <!-- 27列宽表 -->
  <div v-if="useVirtualScroll" class="virtual-toolbar">
    <el-alert type="info" :closable="false" class="virtual-hint">
      行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
    </el-alert>
    <el-button size="small" @click="toggleBrowseMode">
      {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
    </el-button>
  </div>
  <el-table-v2
    v-if="useVirtualScroll && browseMode"
    :columns="virtualColumns"
    :data="browseRows"
    :width="tableWidth"
    :height="tableHeight"
    :row-height="36"
    :header-height="40"
    :row-event-handlers="rowEventHandlers"
    fixed
    class="virtual-table"
  />
  <div v-if="!useVirtualScroll || !browseMode" :style="wrapperStyle">
  <el-table
    :data="displayRows"
    size="small"
    border
    stripe
    :height="wideTableHeight"
    :style="{ width: '100%', minWidth: minTableWidth }"
    :row-class-name="rowClassName"
  >
    <!-- A: 对方单位名称 -->
    <el-table-column prop="customerName" label="对方单位名称" width="140" fixed>
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__' || row.rowId === '__verification__'">
          <span class="subtotal-label">{{ row.customerName }}</span>
        </template>
        <el-input v-else v-model="row.customerName" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'customerName', val)" />
      </template>
    </el-table-column>
    <!-- B: 公司代码 -->
    <el-table-column v-if="isColumnVisible('companyCode')" prop="companyCode" label="公司代码" width="90" fixed>
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__' && row.rowId !== '__verification__'"
          v-model="row.companyCode" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'companyCode', val)" />
      </template>
    </el-table-column>
    <!-- C: 款项性质（候选来自 d3NatureCategories 单一真源，与 D3-1 性质行标签同源） -->
    <el-table-column v-if="isColumnVisible('nature')" label="款项性质" width="160">
      <template #default="{ row }">
        <el-select v-if="isDataRow(row)" v-model="row.nature" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'nature', val)">
          <el-option v-for="opt in d3NatureOptions(row.nature)" :key="opt" :value="opt" />
        </el-select>
      </template>
    </el-table-column>
    <!-- D: 关联方类型（候选来自源模板 D3-2!D12:D23 数据验证） -->
    <el-table-column v-if="isColumnVisible('relationType')" label="关联方类型" width="120">
      <template #default="{ row }">
        <el-select v-if="isDataRow(row)" v-model="row.relationType" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'relationType', val)">
          <el-option v-for="opt in d3RelationTypeOptions(row.relationType)" :key="opt" :value="opt" />
        </el-select>
      </template>
    </el-table-column>
    <!-- E: 期初未审 -->
    <el-table-column v-if="isColumnVisible('priorUnadjusted')" label="期初未审(E)" width="110" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorUnadjusted" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorUnadjusted', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.priorUnadjusted) }}</span>
      </template>
    </el-table-column>
    <!-- F: 期初账项调整 -->
    <el-table-column v-if="isColumnVisible('priorAdjustment')" label="期初调整(F)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorAdjustment" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorAdjustment', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.priorAdjustment) }}</span>
      </template>
    </el-table-column>
    <!-- G: 期初重分类 -->
    <el-table-column v-if="isColumnVisible('priorReclass')" label="期初重分(G)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.priorReclass" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'priorReclass', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.priorReclass) }}</span>
      </template>
    </el-table-column>
    <!-- H: 期初审定(自动) -->
    <el-table-column v-if="isColumnVisible('priorAudited')" label="期初审定(H)" width="110" align="right">
      <template #default="{ row }">
        <GtFormulaSourceTooltip
          :expression="D3_DETAIL_FORMULA_CELLS.priorAudited.expression"
          :addr-id="D3_DETAIL_FORMULA_CELLS.priorAudited.addrId"
          plain
        >
          <span class="auto-calc amt formula-underline">{{ fmtAmount(row.priorAudited) }}</span>
        </GtFormulaSourceTooltip>
      </template>
    </el-table-column>
    <!-- 期初账龄（动态，按列设置过滤） -->
    <el-table-column v-for="band in visiblePriorBands" :key="'prior-' + band.key" :label="`${band.label}(期初)`" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.agingPrior[band.key]" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, `agingPrior.${band.key}`, val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.agingPrior?.[band.key]) }}</span>
      </template>
    </el-table-column>
    <!-- M: 借方发生 -->
    <el-table-column v-if="isColumnVisible('debit')" label="借方(M)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.debit" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'debit', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.debit) }}</span>
      </template>
    </el-table-column>
    <!-- N: 贷方发生 -->
    <el-table-column v-if="isColumnVisible('credit')" label="贷方(N)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.credit" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'credit', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.credit) }}</span>
      </template>
    </el-table-column>
    <!-- O: 期末余额(自动) -->
    <el-table-column v-if="isColumnVisible('endBalance')" label="期末余额(O)" width="110" align="right">
      <template #default="{ row }">
        <GtFormulaSourceTooltip
          :expression="D3_DETAIL_FORMULA_CELLS.endBalance.expression"
          :addr-id="D3_DETAIL_FORMULA_CELLS.endBalance.addrId"
          plain
        >
          <span class="auto-calc amt formula-underline">{{ fmtAmount(row.endBalance) }}</span>
        </GtFormulaSourceTooltip>
      </template>
    </el-table-column>
    <!-- P: 重分类调整 -->
    <el-table-column v-if="isColumnVisible('entityReclass')" label="重分类(P)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.entityReclass" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'entityReclass', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.entityReclass) }}</span>
      </template>
    </el-table-column>
    <!-- Q: 期末未审(自动) -->
    <el-table-column v-if="isColumnVisible('endUnadjusted')" label="期末未审(Q)" width="110" align="right">
      <template #default="{ row }">
        <GtFormulaSourceTooltip
          :expression="D3_DETAIL_FORMULA_CELLS.endUnadjusted.expression"
          :addr-id="D3_DETAIL_FORMULA_CELLS.endUnadjusted.addrId"
          plain
        >
          <span class="auto-calc amt formula-underline">{{ fmtAmount(row.endUnadjusted) }}</span>
        </GtFormulaSourceTooltip>
      </template>
    </el-table-column>
    <!-- R: 期末AJE -->
    <el-table-column v-if="isColumnVisible('endAje')" label="期末AJE(R)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.endAje" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'endAje', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.endAje) }}</span>
      </template>
    </el-table-column>
    <!-- S: 期末RJE -->
    <el-table-column v-if="isColumnVisible('endRje')" label="期末RJE(S)" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.endRje" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'endRje', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.endRje) }}</span>
      </template>
    </el-table-column>
    <!-- T: 期末审定(自动) -->
    <el-table-column v-if="isColumnVisible('endAudited')" label="期末审定(T)" width="110" align="right">
      <template #default="{ row }">
        <GtFormulaSourceTooltip
          :expression="D3_DETAIL_FORMULA_CELLS.endAudited.expression"
          :addr-id="D3_DETAIL_FORMULA_CELLS.endAudited.addrId"
          plain
        >
          <span class="auto-calc amt formula-underline">{{ fmtAmount(row.endAudited) }}</span>
        </GtFormulaSourceTooltip>
      </template>
    </el-table-column>
    <!-- 审定账龄（动态，按列设置过滤） -->
    <el-table-column v-for="band in visibleAuditedBands" :key="'audited-' + band.key" :label="`${band.label}(期末审定)`" width="100" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.agingAudited[band.key]" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, `agingAudited.${band.key}`, val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.agingAudited?.[band.key]) }}</span>
      </template>
    </el-table-column>
    <!-- Y: 是否发函 -->
    <el-table-column v-if="isColumnVisible('isConfirmed')" label="发函(Y)" width="70" align="center">
      <template #default="{ row }">{{ row.isConfirmed || '-' }}</template>
    </el-table-column>
    <!-- Z: 期后结转 -->
    <el-table-column v-if="isColumnVisible('postPeriodSettlement')" label="期后结转(Z)" width="110" align="right">
      <template #default="{ row }">
        <template v-if="isDataRow(row)">
          <el-input v-model.number="row.postPeriodSettlement" size="small" :disabled="isReadonly"
            @change="(val: any) => onCellChange(row.rowId, 'postPeriodSettlement', val)" />
        </template>
        <span v-else class="amt">{{ fmtAmount(row.postPeriodSettlement) }}</span>
      </template>
    </el-table-column>
    <!-- AA: 备注 -->
    <el-table-column v-if="isColumnVisible('remark')" label="备注" min-width="120">
      <template #default="{ row }">
        <el-input v-if="isDataRow(row)" v-model="row.remark" size="small" :disabled="isReadonly"
          @change="(val: string) => onCellChange(row.rowId, 'remark', val)" />
      </template>
    </el-table-column>
    <!-- 操作列 -->
    <el-table-column label="操作" width="60" fixed="right" v-if="!isReadonly">
      <template #default="{ row }">
        <el-popconfirm v-if="isDataRow(row)" title="确认删除此行？" @confirm="removeRow(row.rowId)">
          <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
        </el-popconfirm>
      </template>
    </el-table-column>
  </el-table>
  </div>

  <!-- D3-7期后结转联动提示 -->
  <el-alert
    v-if="postPeriodLinkageWarning"
    :title="postPeriodLinkageWarning"
    type="warning"
    :closable="false"
    show-icon
    style="margin: 12px 0"
  />

  <!-- 审计说明 -->
  <div class="audit-notes-section">
    <h4 class="section-header-row">
      审计说明
      <GtReviewTrigger section-id="D3-det-notes" />
    </h4>
    <div class="note-block">
      <div class="note-label">
        (1) 变动分析
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable || aiLoading"
          :loading="aiLoading"
          @click="genDetailChange"
        >🤖AI</el-button>
      </div>
      <el-input type="textarea" :rows="2" :disabled="isReadonly" placeholder="说明预收账款明细变动情况..."
        :model-value="auditNote1" @update:model-value="auditNote1 = $event" />
    </div>
    <div class="note-block">
      <div class="note-label">
        (2) 合同履约分析
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable || aiLoading"
          :loading="aiLoading"
          @click="genDetailContract"
        >🤖AI</el-button>
      </div>
      <el-input type="textarea" :rows="2" :disabled="isReadonly" placeholder="分析合同履约情况..."
        :model-value="auditNote2" @update:model-value="auditNote2 = $event" />
    </div>
    <div class="note-block">
      <div class="note-label">(3) 超期未结转说明</div>
      <el-input type="textarea" :rows="2" :disabled="isReadonly" placeholder="超期未结转的原因和处理计划..."
        :model-value="auditNote3" @update:model-value="auditNote3 = $event" />
    </div>
  </div>

  <!-- 编制提示 -->
  <details class="guidance-fold">
    <summary>📋 编制提示（CAS 1101 / CAS 14 收入）</summary>
    <p>1. 期末审定数 = 期末未审 + AJE + RJE，须与审定表（D3-1）及序时账勾稽一致；核对行「核对行」差额应为 0；</p>
    <p>2. 按款项性质区分预收销售款、合同负债等，关联方类型非「非关联方」的行需在 D3-6 进一步检查；</p>
    <p>3. 期后结转（Z列）与 D3-7 期后结转检查联动，超期未结转需在审计说明(3)中说明原因与处理计划。</p>
  </details>
</div>
</template>

<script setup lang="ts">
/**
 * D3TabDetail.vue — D3-2 明细表
 * 27列宽表 + 款项性质/关联方下拉 + 公式链自动计算 + 搜索 + 导入
 */
import { computed, ref, watch, toRef, type Ref } from 'vue'
import { useD3Detail } from '../composables/useD3Detail'
import { useD3DetailColumnPrefs } from '../composables/useD3DetailColumnPrefs'
import { useD3TabImportExport } from '../composables/useD3TabImportExport'
import { useD3AiGenerate } from '../composables/useD3AiGenerate'
import { useWorkpaperWideTable } from '../composables/useWorkpaperWideTable'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD3FormData'
import { D3_DETAIL_FORMULA_CELLS } from '../composables/useD3FormulaEngine'
import { d3NatureOptions, d3RelationTypeOptions } from '../composables/d3NatureCategories'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtFormulaSourceTooltip from '@/components/formula/GtFormulaSourceTooltip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// 父级经模板传入的是解包后的普通值（非 ref），此处重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const relatedParties = ref<string[]>([])
const auditNote1 = ref('')
const auditNote2 = ref('')
const auditNote3 = ref('')

watch(
  () => [
    allResponsesRef.value.get('D3-det-note-change')?.remark,
    allResponsesRef.value.get('D3-det-note-contract')?.remark,
    allResponsesRef.value.get('D3-det-note-longterm')?.remark,
  ],
  ([n1, n2, n3]) => {
    auditNote1.value = n1 || ''
    auditNote2.value = n2 || ''
    auditNote3.value = n3 || ''
  },
  { immediate: true },
)

watch(auditNote1, (val) => { props.debouncedSave('D3-det-note-change', { remark: val }) })
watch(auditNote2, (val) => { props.debouncedSave('D3-det-note-contract', { remark: val }) })
watch(auditNote3, (val) => { props.debouncedSave('D3-det-note-longterm', { remark: val }) })

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD3AiGenerate(wpIdRef)

const {
  rows,
  filteredRows,
  subtotalRow,
  verificationRow,
  searchQuery,
  bands,
  addRow,
  removeRow,
  updateCell,
} = useD3Detail({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  relatedParties,
})

// ─── 列显示偏好（⚙ 列设置：>15 列宽表按平台铁律提供列自定义） ──────────────
const colPrefs = useD3DetailColumnPrefs({
  bands,
  rows,
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})
const {
  allColumns: prefColumns,
  groups: prefGroups,
  getGroupColumns,
  isColumnVisible,
  toggleColumn,
  toggleGroup,
  isGroupVisible,
  isGroupPartial,
  visibleCount,
  totalCount,
  activePreset,
  applyPreset,
  presets: colPresets,
  hideEmptyColumns,
} = colPrefs

/** 账龄段可见列（避免 v-if 与 v-for 同元素：先过滤再渲染动态列） */
const visiblePriorBands = computed(() => bands.value.filter(b => isColumnVisible(`aging-prior-${b.key}`)))
const visibleAuditedBands = computed(() => bands.value.filter(b => isColumnVisible(`aging-audited-${b.key}`)))

const columnCount = computed(() => 19 + bands.value.length * 2) // 19 non-aging cols + 2 groups × N bands
const rowCount = computed(() => filteredRows.value.length)
const browseRows = filteredRows
const browseRowCount = computed(() => filteredRows.value.length)

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('customerName', '对方单位名称', 140),
  virtualTextCol('companyCode', '公司代码', 90),
  virtualTextCol('nature', '款项性质', 160),
  virtualTextCol('relationType', '关联方类型', 120),
  virtualNumCol('priorUnadjusted', '期初未审', 110, fmtAmount),
  virtualNumCol('endUnadjusted', '期末未审', 110, fmtAmount),
  virtualNumCol('endAudited', '期末审定', 110, fmtAmount),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 1400,
})

const { tableHeight: wideTableHeight, wrapperStyle, minTableWidth } = useWorkpaperWideTable({
  rowCount,
  columnCount,
  maxHeight: 600,
})

// ─── D3-7 期后结转联动 ──────────────────────────────────────────────────────
import { useD3CrossSheet } from '../composables/useD3CrossSheet'

const crossSheet = useD3CrossSheet({ allResponses: allResponsesRef })

/** 当 D3-7 有期后结转金额但 D3-2 Z列为空时，显示黄色提示 */
const postPeriodLinkageWarning = computed(() => {
  const sync = crossSheet.postPeriodSettlementSync.value
  if (sync.total === 0) return ''
  // 检查是否有 D3-7 有金额但 D3-2 Z列为空的行
  const mismatched: string[] = []
  for (const [customer, d7Amount] of Object.entries(sync.byCustomer)) {
    if (d7Amount <= 0) continue
    const detailRow = rows.value.find(r => r.customerName === customer)
    if (detailRow && (!detailRow.postPeriodSettlement || detailRow.postPeriodSettlement === 0)) {
      mismatched.push(customer)
    }
  }
  if (mismatched.length === 0) return ''
  return `D3-7期后结转检查中发现 ${mismatched.length} 个客户有贷方金额（合计 ${sync.total.toLocaleString()} 元），但D3-2期后结转列（Z列）为空：${mismatched.slice(0, 3).join('、')}${mismatched.length > 3 ? '等' : ''}`
})

// 显示行 = filteredRows + 合计行 + 核对行
const displayRows = computed(() => [...filteredRows.value, subtotalRow.value, verificationRow.value])

function isDataRow(row: any): boolean {
  return row.rowId !== '__subtotal__' && row.rowId !== '__verification__'
}

function rowClassName({ row }: { row: any }): string {
  if (row.rowId === '__subtotal__') return 'subtotal-row'
  if (row.rowId === '__verification__') return 'verification-row'
  if (row.relationType && row.relationType !== '非关联方') return 'related-party-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function genDetailChange() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('detail-change', auditNote1.value, {
    task: '预收账款明细变动分析',
    rowCount: rows.value.length,
  }, 'AI · 变动分析')
  if (text) auditNote1.value = text
}

async function genDetailContract() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('detail-contract', auditNote2.value, {
    task: '合同履约分析',
    rowCount: rows.value.length,
  }, 'AI · 合同履约分析')
  if (text) auditNote2.value = text
}

const { onExportTemplate, onExportData, onImportFile, onImportFromAuxBalance } = useD3TabImportExport(wpIdRef, 'D3-2')

// ─── 行名对齐（formula-row-name-alignment-confirmation 复盘 #4：真实入口接线）───
// 返回本表按客户名取数的行（row_key 用稳定 rowId，row_label 用客户名）。
// account_prefixes 留空 —— 由后端按 wp_code/sheet_code 从 wp_account_mapping 解析（科目定位是后端职责，红基线 3）。
function getRowNameAlignmentRows() {
  return rows.value
    .filter((r: any) => r && r.rowId && !String(r.rowId).startsWith('__') && (r.customerName || '').trim())
    .map((r: any) => ({
      row_key: String(r.rowId),
      row_label: String(r.customerName).trim(),
      account_prefixes: [] as string[],
    }))
}

defineExpose({ getRowNameAlignmentRows })
</script>

<style scoped>
.d3-detail { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.guidance-fold { margin-top: 16px; font-size: 12px; color: #606266; background: #f9fafb; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; }
.guidance-fold summary { cursor: pointer; font-weight: 600; color: #409eff; }
.guidance-fold p { margin: 6px 0 0; line-height: 1.6; }
.detail-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-actions { display: flex; gap: 8px; align-items: center; }
/* ⚙ 列设置面板 */
.col-prefs-panel { font-size: 13px; }
.col-prefs-presets { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.col-prefs-label { color: #606266; }
.col-prefs-actions { display: flex; gap: 8px; margin-bottom: 8px; }
.col-prefs-group { padding: 6px 0; border-top: 1px solid #f0f0f0; }
.col-prefs-items { display: flex; flex-wrap: wrap; gap: 4px 16px; padding: 4px 0 0 20px; }
.virtual-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.virtual-hint { margin-bottom: 0; flex: 1; }
.virtual-table { margin-bottom: 8px; }
.subtotal-label { font-weight: 700; }
.amt { text-align: right; display: inline-block; width: 100%; }
.auto-calc { background: #f5f7fa; padding: 2px 4px; border-radius: 2px; }
/* 公式列虚线下划线（tooltip 用 plain 变体，下划线由本类承载，cursor:help 随 formula-cell） */
.formula-underline { border-bottom: 1px dashed #409eff; }
.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; margin-bottom: 12px; }
.section-header-row { display: flex; align-items: center; gap: 8px; }
.note-block { margin-bottom: 12px; }
.note-label { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: var(--wp-font-size, 13px); color: #606266; }
.conclusion-actions { margin-top: 8px; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.verification-row) { background-color: #fff8e1 !important; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }
</style>
