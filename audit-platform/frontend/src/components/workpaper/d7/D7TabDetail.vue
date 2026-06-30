<template>
<div class="d7-detail">
  <!-- 双模式切换 -->
  <div class="mode-toolbar">
    <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
  </div>

  <template v-if="viewMode === 'structured'">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-input v-model="searchFilter" placeholder="搜索单位名称/合同名称..." size="small" style="width:240px" clearable />
      <div class="toolbar-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">添加客户</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
        <el-button size="small" :disabled="true">导出空模板</el-button>
        <el-button size="small" :disabled="true">导入数据</el-button>
      </div>
    </div>

    <!-- 27列明细表 -->
    <el-table
      :data="displayRows"
      size="small"
      border
      max-height="600"
      :row-class-name="({ row }: any) => detailRowClassName(row)"
      style="width:100%"
    >
      <!-- 固定列 -->
      <el-table-column prop="contractName" label="合同名称" width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="isDataRow(row) && !isReadonly" :model-value="row.contractName" size="small" @change="(v: string) => updateCell(row.rowId, 'contractName', v)" />
          <span v-else class="label-bold">{{ row.contractName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="companyName" label="单位名称" width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="isDataRow(row) && !isReadonly" :model-value="row.companyName" size="small" @change="(v: string) => updateCell(row.rowId, 'companyName', v)" />
          <span v-else>{{ row.companyName }}</span>
        </template>
      </el-table-column>

      <!-- 类型(款项性质) -->
      <el-table-column label="类型(款项性质)" width="140">
        <template #default="{ row }">
          <el-select v-if="isDataRow(row) && !isReadonly" :model-value="row.natureType" size="small" placeholder="请选择" @change="(v: string) => updateCell(row.rowId, 'natureType', v)">
            <el-option v-for="t in NATURE_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.natureType }}</span>
        </template>
      </el-table-column>

      <!-- 关联关系 -->
      <el-table-column label="关联关系" width="140">
        <template #default="{ row }">
          <el-select v-if="isDataRow(row) && !isReadonly" :model-value="row.relatedPartyType" size="small" placeholder="请选择" @change="(v: string) => updateCell(row.rowId, 'relatedPartyType', v)">
            <el-option v-for="t in RELATED_PARTY_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.relatedPartyType }}</span>
        </template>
      </el-table-column>

      <!-- 期初 -->
      <el-table-column label="期初未审" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.priorUnadjusted" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初AJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.priorAje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初RJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.priorRje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorRje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初审定" width="110" align="right">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.priorAudited) }}</span></template>
      </el-table-column>

      <!-- 期初账龄 -->
      <el-table-column label="1年以内" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.priorAging1" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAging1', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorAging1) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="1~2年" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.priorAging2" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAging2', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorAging2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="2~3年" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.priorAging3" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAging3', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorAging3) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="3年以上" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.priorAging4" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAging4', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorAging4) }}</span>
        </template>
      </el-table-column>

      <!-- 借贷发生 -->
      <el-table-column label="借方发生" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方发生" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 期末 -->
      <el-table-column label="期末余额" width="110" align="right">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.endBalance) }}</span></template>
      </el-table-column>
      <el-table-column label="重分类" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.entityReclass" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'entityReclass', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.entityReclass) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末未审" width="110" align="right">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.endUnadjusted) }}</span></template>
      </el-table-column>
      <el-table-column label="期末AJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.endAje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endAje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末RJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.endRje" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endRje', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末审定" width="110" align="right">
        <template #default="{ row }"><span class="auto-calc">{{ fmtAmt(row.endAudited) }}</span></template>
      </el-table-column>

      <!-- 期末账龄 -->
      <el-table-column label="1年以内" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.endAging1" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endAging1', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endAging1) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="1~2年" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.endAging2" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endAging2', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endAging2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="2~3年" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.endAging3" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endAging3', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endAging3) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="3年以上" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="isDataRow(row) && !isReadonly" :model-value="row.endAging4" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endAging4', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endAging4) }}</span>
        </template>
      </el-table-column>

      <!-- 其他 -->
      <el-table-column label="期后结转" width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmt(row.postTransfer) }}</span></template>
      </el-table-column>
      <el-table-column label="是否发函" width="80" align="center">
        <template #default="{ row }"><span>{{ row.isConfirmed || '-' }}</span></template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column v-if="!isReadonly" label="" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-popconfirm v-if="isDataRow(row)" title="确认删除？" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>
      <div class="note-item">
        <label>期末变动分析：</label>
        <el-input v-model="detailNotes.explanation" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="分析合同负债明细本期增减变动原因..." />
      </div>
      <div class="note-item">
        <label>合同履行情况：</label>
        <el-input v-model="detailNotes.contract" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="说明主要合同的履约进度及收入确认情况..." />
      </div>
      <div class="note-item">
        <label>超1年原因：<GtIndexChip wp-code="D7-5" label="→D7-5" /></label>
        <el-input v-model="detailNotes.longTerm" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="账龄超过1年的合同负债未结转原因..." />
      </div>
    </div>

    <!-- 审计结论 -->
    <div class="audit-conclusion-section">
      <h4>审计结论</h4>
      <el-input v-model="detailNotes.conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="对合同负债明细的总结性结论..." />
      <div class="note-actions">
        <el-button size="small" :disabled="true">🤖AI</el-button>
        <el-button size="small" @click="openReviewDialog('D7-2-note-conclusion')">💬复核</el-button>
      </div>
    </div>
  </template>

  <div v-else class="oo-mode-placeholder">
    <el-empty description="OnlyOffice 在线编辑模式（待OO服务就绪后启用）" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabDetail.vue — 明细表 D7-2 (~400行), 27列横向滚动
 * Task: 17.1
 * Requirements: 5.1-5.12, 6.1-6.7, 7.1-7.5, 17.2, 19.3, 20.1, 22.1-22.5
 */
import { ref, computed, watch, inject, type Ref } from 'vue'
import { useD7Detail, NATURE_TYPES, RELATED_PARTY_TYPES, type DetailRow } from '../composables/useD7Detail'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  rows, totalRow, addRow, removeRow, updateCell, importFromAuxBalance, searchFilter, filteredRows,
} = useD7Detail({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

// Display rows: filtered data + total row
const displayRows = computed(() => [...filteredRows.value, totalRow.value])

function isDataRow(row: DetailRow): boolean {
  return !row.rowId.startsWith('__')
}

function detailRowClassName({ row }: { row: DetailRow }): string {
  if (row.rowId.startsWith('__')) return 'total-row'
  if (row.relatedPartyType && row.relatedPartyType !== '非关联方' && row.relatedPartyType !== '') return 'related-party-row'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// Audit notes for detail tab
const detailNotes = ref({ explanation: '', contract: '', longTerm: '', conclusion: '' })

watch(() => props.allResponses.value, (map) => {
  detailNotes.value.explanation = map.get('D7-2-note-explanation')?.remark || ''
  detailNotes.value.contract = map.get('D7-2-note-contract')?.remark || ''
  detailNotes.value.longTerm = map.get('D7-2-note-longterm')?.remark || ''
  detailNotes.value.conclusion = map.get('D7-2-note-conclusion')?.remark || ''
}, { immediate: true })

watch(() => detailNotes.value.explanation, v => props.debouncedSave('D7-2-note-explanation', { remark: v }))
watch(() => detailNotes.value.contract, v => props.debouncedSave('D7-2-note-contract', { remark: v }))
watch(() => detailNotes.value.longTerm, v => props.debouncedSave('D7-2-note-longterm', { remark: v }))
watch(() => detailNotes.value.conclusion, v => props.debouncedSave('D7-2-note-conclusion', { remark: v }))
</script>

<style scoped>
.d7-detail { padding: 16px; }
.mode-toolbar { margin-bottom: 12px; }
.oo-mode-placeholder { padding: 40px 0; }

.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-actions { display: flex; gap: 8px; }

.auto-calc { background: #f5f7fa; padding: 2px 4px; border-radius: 2px; color: #909399; font-size: 12px; }
.label-bold { font-weight: 700; }

:deep(.total-row) { background-color: #fafafa !important; font-weight: 600; }
:deep(.related-party-row) { background-color: #fdf6ec !important; }

.audit-notes-section, .audit-conclusion-section { margin-top: 20px; }
.audit-notes-section h4, .audit-conclusion-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.note-item { margin-bottom: 12px; }
.note-item label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #606266; margin-bottom: 4px; }
.note-actions { display: flex; gap: 8px; margin-top: 6px; }
</style>
