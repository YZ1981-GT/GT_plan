<template>
  <div class="g12-hedge" data-testid="g12-hedge-detail">
    <div class="toolbar">
      <h3>G12-2 套期关系明细</h3>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="hd.addRow()">+ 新增</el-button>
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-2" :disabled="isReadonly" @imported="emit('imported')" />
      <el-tag size="small" type="info">共 {{ hd.rows.value.length }} 行</el-tag>
      <GtReviewTrigger section-id="G12-2-hedge-detail" />
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="核对套期关系的正式指定文档（套期类型、被套期项目、套期工具、套期比率），测算套期无效部分并与 G12-4 公允价值测试交叉验证，评价套期有效性结论。"
    />

    <el-alert v-if="crossMismatches.length" type="warning" :closable="false" class="cross-alert" data-testid="g12-hedge-fv-cross-bar">
      <template #title>G12-4 交叉验证差异（{{ crossMismatches.length }} 处）</template>
      <div v-for="m in crossMismatches.slice(0, 3)" :key="`${m.hedgeRelationId}-${m.field}`" class="cross-line">
        {{ m.hedgeRelationId }} · {{ m.field === 'instrumentFVChange' ? '工具FV变动' : '项目FV变动' }}：
        G12-2={{ m.hedgeValue.toFixed(2) }} vs G12-4={{ m.fvTestValue.toFixed(2) }}（差 {{ m.variance.toFixed(2) }}）
      </div>
      <span v-if="crossMismatches.length > 3">…另有 {{ crossMismatches.length - 3 }} 处</span>
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-4"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-4'))"
      />
    </el-alert>
    <el-alert
      v-else-if="hasFvTestData"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g12-hedge-fv-cross-ok"
    >
      G12-2 与 G12-4 公允价值测试一致
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-4"
        :prevent-navigate="true"
        :validate="false"
        class="ok-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-4'))"
      />
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G12-2" /></span>
        <el-tag size="small" type="info">共 {{ hd.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-segmented v-model="activeTab" :options="tabOptions" size="small" />

    <el-table :data="hd.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="480"
      :row-class-name="rowClassName">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="套期关系编号" prop="hedgeRelationId" width="110" fixed />

      <!-- Tab1: 关系指定（10列区） -->
      <template v-if="activeTab === 'designation'">
        <el-table-column label="套期类型" width="130">
          <template #default="{ row }">
            <el-select v-model="row.hedgeType" size="small" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'hedgeType', v)">
              <el-option v-for="t in hd.G12_HEDGE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="被套期项目" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.hedgedItem" size="small" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'hedgedItem', v)" />
          </template>
        </el-table-column>
        <el-table-column label="套期工具" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.hedgingInstrument" size="small" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'hedgingInstrument', v)" />
          </template>
        </el-table-column>
        <el-table-column label="指定日期" width="110">
          <template #default="{ row }">
            <el-input v-model="row.designationDate" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'designationDate', v)" />
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="110">
          <template #default="{ row }">
            <el-input v-model="row.maturityDate" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'maturityDate', v)" />
          </template>
        </el-table-column>
        <el-table-column label="被套期风险" width="110">
          <template #default="{ row }">
            <el-input v-model="row.hedgedRisk" size="small" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'hedgedRisk', v)" />
          </template>
        </el-table-column>
        <el-table-column label="套期比率" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.hedgeRatio" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => hd.updateCell(row.rowId, 'hedgeRatio', v)" />
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
              @change="(v: string) => hd.updateCell(row.rowId, 'indexRef', v)" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'remark', v)" />
          </template>
        </el-table-column>
      </template>

      <!-- Tab2: FV与结论（5列区 + 公式列） -->
      <template v-else>
        <el-table-column label="工具FV变动" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.instrumentFVChange" size="small" :controls="false" :disabled="isReadonly"
              :class="{ 'fv-mismatch': hasMismatch(row.hedgeRelationId, 'instrumentFVChange') }"
              style="width:100%" @change="(v: number) => hd.updateCell(row.rowId, 'instrumentFVChange', v)" />
          </template>
        </el-table-column>
        <el-table-column label="被套期FV变动" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.itemFVChange" size="small" :controls="false" :disabled="isReadonly"
              :class="{ 'fv-mismatch': hasMismatch(row.hedgeRelationId, 'itemFVChange') }"
              style="width:100%" @change="(v: number) => hd.updateCell(row.rowId, 'itemFVChange', v)" />
          </template>
        </el-table-column>
        <el-table-column label="无效部分" width="100" align="right">
          <template #default="{ row }"><span class="formula" title="套期无效部分 = |套期工具FV变动 − 被套期项目FV变动|">{{ row.ineffectiveness.toFixed(2) }}</span></template>
        </el-table-column>
        <el-table-column label="计入损益" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.profitLossAmount" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => hd.updateCell(row.rowId, 'profitLossAmount', v)" />
          </template>
        </el-table-column>
        <el-table-column label="有效性结论" width="110">
          <template #default="{ row }">
            <el-select v-model="row.effectivenessConclusion" size="small" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'effectivenessConclusion', v)">
              <el-option v-for="o in hd.G12_EFFECTIVENESS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="100">
          <template #default="{ row }"><GtIndexChip v-if="row.indexRef" :value="row.indexRef" /></template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly"
              @change="(v: string) => hd.updateCell(row.rowId, 'remark', v)" />
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="hd.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <span>工具FV合计：{{ hd.totals.value.instrumentFVChange.toFixed(2) }}</span>
      <span>项目FV合计：{{ hd.totals.value.itemFVChange.toFixed(2) }}</span>
      <span>无效部分合计：{{ hd.totals.value.ineffectiveness.toFixed(2) }}</span>
      <span>计入损益合计：{{ hd.totals.value.profitLossAmount.toFixed(2) }}</span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：套期指定文档核对、套期有效性测算与 G12-4 交叉验证结果。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论：套期关系指定是否合规、有效性评价结论。"
        @change="saveAuditConclusion" />
    </el-card>

    <details class="methodology-hint">
      <summary>📋 编制提示（CAS24 套期会计）</summary>
      <p>套期会计三要素：经济关系 + 信用风险主导 + 套期比率。「关系指定」区段录入正式指定信息，「FV与结论」区段录入公允价值变动并测算无效部分（计入损益）。工具/项目 FV 变动须与 G12-4 公允价值测试一致，否则触发交叉验证告警。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, onMounted } from 'vue'
import { useG12HedgeDetail } from '../../composables/useG12HedgeDetail'
import { findG12FvCrossMismatches, hasG12FvTestData } from '../../composables/useG12CrossValidate'
import { resolveG12SheetLabel } from '../../composables/g12SheetLabels'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const activeTab = ref<'designation' | 'fv'>('designation')
const tabOptions = [
  { label: '关系指定', value: 'designation' },
  { label: 'FV与结论', value: 'fv' },
]

const hd = useG12HedgeDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const NOTE_KEY = 'G12-hedge-detail-audit-note'
const CONCLUSION_KEY = 'G12-hedge-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const crossMismatches = computed(() =>
  findG12FvCrossMismatches(hd.rows.value, props.allResponses),
)

const hasFvTestData = computed(() => hasG12FvTestData(props.allResponses))

function hasMismatch(id: string, field: 'instrumentFVChange' | 'itemFVChange'): boolean {
  return crossMismatches.value.some((m) => m.hedgeRelationId === id && m.field === field)
}

function rowClassName({ row }: { row: { hedgeRelationId: string } }): string {
  return crossMismatches.value.some((m) => m.hedgeRelationId === row.hedgeRelationId) ? 'g12-cross-warn' : ''
}
</script>

<style scoped>
.g12-hedge { padding: 12px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.audit-objective { margin-bottom: 8px; }
.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.cross-alert { margin-bottom: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.warn-chip, .ok-chip { margin-left: 8px; }
.cross-line { font-size: 12px; }
.formula { border-bottom: 1px dashed #909399; background: #fafafa; cursor: help; display: inline-block; width: 100%; }
.totals { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 10px; padding: 8px 12px; background: #fafafa; border-radius: 4px; font-size: 12px; font-weight: 500; }
:deep(.g12-cross-warn) { background: #fdf6ec !important; }
:deep(.fv-mismatch .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
</style>
