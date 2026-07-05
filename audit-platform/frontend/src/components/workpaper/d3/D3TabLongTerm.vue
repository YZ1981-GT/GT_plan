<template>
<div class="d3-long-term">
  <!-- 工具栏 -->
  <div class="lt-toolbar">
    <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
    <el-button size="small" :disabled="isReadonly" @click="doImport">从D3-2导入</el-button>
    <GtReviewTrigger section-id="D3-lt-header" />
    <el-button-group size="small" style="margin-left: auto">
      <el-button @click="onExportTemplate">导出模板</el-button>
      <el-button @click="onExportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button>导入数据</el-button>
      </el-upload>
    </el-button-group>
  </div>

  <!-- 8列表格 -->
  <el-table :data="tableData" size="small" border stripe>
    <el-table-column label="对方单位名称" width="160">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-label">合计</span>
        </template>
        <template v-else>
          <el-input v-model="row.customerName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell(row.rowId, 'customerName', val)" />
          <GtIndexChip target="D3-2" :label="row.customerName" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="期末余额" width="120" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.endBalance) }}</span>
        </template>
        <template v-else>
          <el-input v-model.number="row.endBalance" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell(row.rowId, 'endBalance', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="账龄" width="100">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.aging" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'aging', val)" />
      </template>
    </el-table-column>
    <el-table-column label="经济业务说明" min-width="140">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.businessDescription" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'businessDescription', val)" />
      </template>
    </el-table-column>
    <el-table-column label="未结转原因" min-width="160">
      <template #default="{ row }">
        <template v-if="row.rowId !== '__subtotal__'">
          <div class="reason-cell">
            <el-input v-model="row.reason" size="small" :disabled="isReadonly"
              @change="(val: string) => updateCell(row.rowId, 'reason', val)" />
            <el-button
              size="small"
              :disabled="isReadonly || !aiAvailable || aiLoading"
              :loading="aiLoading"
              @click="genRowReason(row)"
            >🤖</el-button>
          </div>
        </template>
      </template>
    </el-table-column>
    <el-table-column label="结转金额" width="120" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.settlementAmount) }}</span>
        </template>
        <template v-else>
          <el-input v-model.number="row.settlementAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell(row.rowId, 'settlementAmount', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="处理计划" width="120">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.plan" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'plan', val)" />
      </template>
    </el-table-column>
    <el-table-column label="备注" width="100">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.remark" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'remark', val)" />
      </template>
    </el-table-column>
    <!-- 操作 -->
    <el-table-column label="操作" width="60" v-if="!isReadonly">
      <template #default="{ row }">
        <el-popconfirm v-if="row.rowId !== '__subtotal__'" title="确认删除？" @confirm="removeRow(row.rowId)">
          <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
        </el-popconfirm>
      </template>
    </el-table-column>
  </el-table>

  <!-- 审计说明 + 结论 -->
  <div class="audit-notes-section">
    <h4 class="section-header-row">
      审计说明
      <el-button
        size="small"
        :disabled="isReadonly || !aiAvailable || aiLoading"
        :loading="aiLoading"
        @click="genAuditNote"
      >🤖AI</el-button>
    </h4>
    <el-input
      v-model="auditNote"
      type="textarea"
      :rows="3"
      :disabled="isReadonly"
      placeholder="对超1年预收账款未结转原因的审计说明..."
    />
    <h4 style="margin-top: 16px">审计结论</h4>
    <el-input
      v-model="conclusion"
      type="textarea"
      :rows="2"
      :disabled="isReadonly"
      placeholder="审计结论..."
    />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D3TabLongTerm.vue — D3-5 账龄1年以上检查表
 * 8列表 + 从D3-2导入 + AI建议 + GtIndexChip
 */
import { computed, type Ref } from 'vue'
import { useD3LongTerm } from '../composables/useD3LongTerm'
import { useD3TabImportExport } from '../composables/useD3TabImportExport'
import { useD3AiGenerate } from '../composables/useD3AiGenerate'
import type { useD3CrossSheet } from '../composables/useD3CrossSheet'
import type { ChecklistResponse } from '../composables/useD3FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: boolean
  crossSheet: ReturnType<typeof useD3CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const {
  rows,
  subtotalRow,
  auditNote,
  conclusion,
  addRow,
  removeRow,
  updateCell,
  importFromCrossSheet,
} = useD3LongTerm({
  allResponses: props.allResponses,
  wpId: props.wpId,
  projectId: props.projectId,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD3AiGenerate(props.wpId)

async function genRowReason(row: { rowId: string; customerName: string; endBalance: number; aging: string; reason: string }) {
  if (props.isReadonly) return
  const text = await generateAndConfirm('longterm-reason', row.reason, {
    customerName: row.customerName,
    endBalance: row.endBalance,
    aging: row.aging,
  }, `AI · 未结转原因 — ${row.customerName || '该行'}`)
  if (text) updateCell(row.rowId, 'reason', text)
}

async function genAuditNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('analysis-note', auditNote.value, {
    task: '超1年预收账款审计说明',
    rowCount: rows.value.length,
  }, 'AI · 审计说明')
  if (text) auditNote.value = text
}

// Append subtotal row for display
const tableData = computed(() => [
  ...rows.value,
  { rowId: '__subtotal__', customerName: '合计', endBalance: 0, aging: '', businessDescription: '', reason: '', settlementAmount: 0, plan: '', remark: '' },
])

function doImport() {
  const longTermRows = props.crossSheet.longTermRows.value
  importFromCrossSheet(longTermRows)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

const { onExportTemplate, onExportData, onImportFile } = useD3TabImportExport(props.wpId, 'D3-5')
</script>

<style scoped>
.d3-long-term { padding: 16px; }
.lt-toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.reason-cell { display: flex; gap: 4px; align-items: center; }
.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; margin-bottom: 8px; }
.section-header-row { display: flex; align-items: center; gap: 8px; }
.note-label { display: flex; gap: 8px; }
</style>
