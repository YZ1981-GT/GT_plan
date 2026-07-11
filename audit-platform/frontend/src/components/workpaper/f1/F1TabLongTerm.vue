<template>
<div class="d3-long-term">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表检查账龄超过1年的预付账款（科目1123），逐户列示未结转原因与处理计划。</p>
      <p>2. 长期挂账应分析款项性质：是否仍具商业实质、能否形成资产或已具备结转/退款条件。</p>
      <p>3. 无法收回或对方已注销/失联的，应评估减值并考虑转入其他应收款或计提坏账。</p>
      <p>4. 数据可从 F1-2 明细表按账龄一键导入，结论应与 F1-1 审定表账龄区块勾稽一致。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：核查账龄超过1年的预付账款长期挂账原因，评估其可收回性与列报恰当性，识别减值及重分类迹象。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="doImport">从F1-2导入</el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('F1-5')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('F1-5')">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload :show-file-list="false" accept=".xlsx" :disabled="isReadonly || importing"
                :before-upload="(file: any) => handleImport(file, 'F1-5')">
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
          <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
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
        <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.reason" size="small" :disabled="isReadonly"
          @change="(val: string) => updateCell(row.rowId, 'reason', val)" />
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
        placeholder="对超1年预付账款未结转原因的审计说明..."
      />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计结论</span>
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
 * F1TabLongTerm.vue — F1-5 账龄1年以上检查表
 * 8列表 + 从F1-2导入 + AI建议 + GtIndexChip
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useF1LongTerm } from '../composables/useF1LongTerm'
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

const {
  rows,
  subtotalRow,
  auditNote,
  conclusion,
  addRow,
  removeRow,
  updateCell,
  importFromCrossSheet,
} = useF1LongTerm({
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

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

// ─── 导入导出（D4 模式） ─────────────────────────────────────────────────────
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: toRef(props, 'wpId') as Ref<string> })

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}
</script>

<style scoped>
.d3-long-term { padding: 16px; }
.d3-long-term :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.d3-long-term :deep(.el-table .cell) { font-size: 13px !important; }

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
</style>
