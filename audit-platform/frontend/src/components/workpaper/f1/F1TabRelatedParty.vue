<template>
<div class="d3-related-party">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表列示关联方预付账款（科目1123），逐户填列关联关系、发生额与期末余额。</p>
      <p>2. 期末余额自动计算（期末=期初+借方-贷方，灰底列不可手工编辑）。</p>
      <p>3. 关注关联方预付是否具有商业实质、定价是否公允，警惕通过预付款变相资金占用。</p>
      <p>4. 关联方及其交易须在附注充分披露，结论应与 F1-1 审定表、附注勾稽一致。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核实关联方预付账款的真实性与完整性，评估交易的商业实质与定价公允性，确认关联方关系及交易披露的充分性。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加关联方</el-button>
      <el-button size="small" :disabled="isReadonly" @click="doImport">从F1-2导入</el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('F1-6')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('F1-6')">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing"
                :before-upload="(file: any) => handleImport(file, 'F1-6')">
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:F1-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>
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
          <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
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
    <el-table-column label="期末余额" width="110" align="right" class-name="auto-calc-col">
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

  <!-- 审计说明区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
          <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
        </div>
      </div>
    </template>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计说明</span>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对关联方预付账款的分析说明..."
      />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计结论</span>
        <div class="opinion-actions">
          <el-button size="small" @click="openReview">💬</el-button>
        </div>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="审计结论..."
      />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabRelatedParty.vue — F1-6 关联方检查表
 * 10列表 + 行内公式(期末=期初+贷方-借方) + 从F1-2导入 + 复核
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useF1RelatedParty } from '../composables/useF1RelatedParty'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

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
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
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
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: toRef(props, 'wpId') as Ref<string> })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-related-party { padding: 16px; }
.d3-related-party :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.d3-related-party :deep(.el-table .cell) { font-size: 13px !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.auto-calc { color: #909399; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
