<template>
<div class="d3-related-party">
  <!-- 工具栏 -->
  <div class="rp-toolbar">
    <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加关联方</el-button>
    <el-button size="small" :disabled="isReadonly" @click="doImport">从F1-2导入</el-button>
    <el-button-group size="small" style="margin-left: auto">
      <el-button @click="exportTemplate('F1-6')">导出模板</el-button>
      <el-button @click="exportData('F1-6')">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing" :before-upload="(file: any) => handleImport(file, 'F1-6')">
        <el-button>导入数据</el-button>
      </el-upload>
    </el-button-group>
  </div>

  <!-- 10列表格 -->
  <el-table :data="tableData" size="small" border stripe>
    <el-table-column label="关联方名称" width="140">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-label">合计</span>
        </template>
        <template v-else>
          <el-input v-model="row.partyName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell(row.rowId, 'partyName', val)" />
          <GtIndexChip target="F1-2" :label="row.partyName" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="关联关系" width="120">
      <template #default="{ row }">
        <el-select v-if="row.rowId !== '__subtotal__'" v-model="row.relationship" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'relationship', val)">
          <el-option value="母公司" />
          <el-option value="子公司" />
          <el-option value="联营企业" />
          <el-option value="合营企业" />
          <el-option value="关键管理人员" />
          <el-option value="其他关联方" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column label="期初余额" width="110" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.priorBalance) }}</span>
        </template>
        <template v-else>
          <el-input v-model.number="row.priorBalance" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell(row.rowId, 'priorBalance', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="借方发生" width="110" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.debit) }}</span>
        </template>
        <template v-else>
          <el-input v-model.number="row.debit" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell(row.rowId, 'debit', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="贷方发生" width="110" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.credit) }}</span>
        </template>
        <template v-else>
          <el-input v-model.number="row.credit" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell(row.rowId, 'credit', val)" />
        </template>
      </template>
    </el-table-column>
    <el-table-column label="期末余额" width="110" align="right">
      <template #default="{ row }">
        <template v-if="row.rowId === '__subtotal__'">
          <span class="subtotal-val">{{ fmtAmount(subtotalRow.endBalance) }}</span>
        </template>
        <template v-else>
          <span class="auto-calc">{{ fmtAmount(row.endBalance) }}</span>
        </template>
      </template>
    </el-table-column>
    <el-table-column label="发生时间及账龄" width="130">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.agingDescription" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'agingDescription', val)" />
      </template>
    </el-table-column>
    <el-table-column label="款项性质" width="120">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.natureDescription" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'natureDescription', val)" />
      </template>
    </el-table-column>
    <el-table-column label="索引" width="70">
      <template #default="{ row }">
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.indexRef" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'indexRef', val)" />
      </template>
    </el-table-column>
    <el-table-column label="备注" min-width="100">
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

  <!-- 审计说明 + 结论 + 复核 -->
  <div class="audit-notes-section">
    <h4>审计说明</h4>
    <el-input
      v-model="auditNote"
      type="textarea"
      :rows="3"
      :disabled="isReadonly"
      placeholder="对关联方预付账款的分析说明..."
    />
    <h4 style="margin-top: 16px">审计结论</h4>
    <el-input
      v-model="conclusion"
      type="textarea"
      :rows="2"
      :disabled="isReadonly"
      placeholder="审计结论..."
    />
    <div class="conclusion-actions">
      <el-button size="small" @click="openReview">💬 复核</el-button>
    </div>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabRelatedParty.vue — F1-6 关联方检查表
 * 10列表 + 行内公式(期末=期初+贷方-借方) + 从F1-2导入 + 复核
 */
import { computed, inject, type Ref } from 'vue'
import { useF1RelatedParty } from '../composables/useF1RelatedParty'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  rows,
  subtotalRow,
  auditNote,
  conclusion,
  addRow,
  removeRow,
  updateCell,
  importFromCrossSheet,
} = useF1RelatedParty({
  allResponses: props.allResponses,
  wpId: props.wpId,
  projectId: props.projectId,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const tableData = computed(() => [
  ...rows.value,
  { rowId: '__subtotal__', partyName: '合计', relationship: '', priorBalance: 0, debit: 0, credit: 0, endBalance: 0, agingDescription: '', natureDescription: '', indexRef: '', remark: '' },
])

function doImport() {
  const rpRows = props.crossSheet.relatedPartyRows.value
  importFromCrossSheet(rpRows)
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function openReview() {
  openReviewDialog('F1-rp-conclusion')
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: props.wpId })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-related-party { padding: 16px; }
.rp-toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; }
.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; margin-bottom: 8px; }
.conclusion-actions { margin-top: 8px; }
</style>
