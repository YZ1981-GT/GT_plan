<template>
<div class="d7-longterm">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示账龄超过1年的合同负债（科目2205），依据 CAS14 收入准则关注长期未结转的履约义务。</p>
        <p>2. 账龄超1年通常意味着履约义务长期未完成，应核查经济业务实质、合同条款及未结转原因的合理性。</p>
        <p>3. 数据可从 D7-2 明细表按账龄一键导入；"未结转原因"可借助 AI 辅助生成说明。</p>
        <p>4. 需关注至审计日的结转情况，评价是否存在应结转而未结转的收入（收入截止风险）。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实账龄超过1年合同负债未结转的原因及合理性，评价是否存在收入确认时点不当或长期挂账风险。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromD72">从D7-2导入</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" :disabled="isReadonly">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D7-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
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
      fixed
      class="virtual-table"
    />

    <!-- 8列表格 -->
    <el-table v-if="!useVirtualScroll || !browseMode" :data="rows" size="small" border>
      <el-table-column label="客户名称" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.customerName" size="small" @change="(v: string) => updateCell(row.rowId, 'customerName', v)" />
          <span v-else>
            {{ row.customerName }}
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" style="margin-left:4px" />
          </span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.endBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'endBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账龄" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.aging" size="small" @change="(v: string) => updateCell(row.rowId, 'aging', v)" />
          <span v-else>{{ row.aging }}</span>
        </template>
      </el-table-column>
      <el-table-column label="经济业务说明" width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessDescription" size="small" @change="(v: string) => updateCell(row.rowId, 'businessDescription', v)" />
          <span v-else>{{ row.businessDescription }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未结转原因" min-width="180">
        <template #default="{ row }">
          <div class="reason-cell">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => updateCell(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason }}</span>
            <el-tooltip v-if="!isReadonly" :content="aiTip" placement="top">
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="!aiAvailable || aiLoading"
                :loading="aiLoading"
                style="margin-left:4px"
                @click="genRowReason(row)"
              >🤖 AI</el-button>
            </el-tooltip>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="至审计日结转金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.auditDateTransfer" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'auditDateTransfer', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.auditDateTransfer) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="处理计划" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.plan" size="small" @change="(v: string) => updateCell(row.rowId, 'plan', v)" />
          <span v-else>{{ row.plan }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-section">
      <span>期末余额合计：<strong>{{ fmtAmt(totalRow.endBalance) }}</strong></span>
      <span>至审计日结转合计：<strong>{{ fmtAmt(totalRow.auditDateTransfer) }}</strong></span>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genAuditNote">🤖 AI辅助</el-button>
            </el-tooltip>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="对账龄超过1年合同负债的原因分析..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
        </div>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="结论..."
        />
      </div>
    </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabLongTerm.vue — 账龄1年以上 D7-5 (~250行)
 * Task: 20.1
 * Requirements: 10.1-10.8, 19.3, 20.1
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD7LongTerm } from '../composables/useD7LongTerm'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useD7AiGenerate } from '../composables/useD7AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD7ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D7-5',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const {
  rows, totalRow, addRow, removeRow, updateCell, importFromD72, auditNotes,
} = useD7LongTerm({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD7AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

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
  const text = await generateAndConfirm('analysis-note', auditNotes.value.explanation, {
    task: '超1年合同负债审计说明',
    rowCount: rows.value.length,
    endBalanceTotal: totalRow.value.endBalance,
    auditDateTransferTotal: totalRow.value.auditDateTransfer,
  }, 'AI · 审计说明')
  if (text) auditNotes.value.explanation = text
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => rows.value)
const browseRowCount = computed(() => rows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('customerName', '客户名称', 180),
  virtualTextCol('aging', '账龄', 90),
  virtualNumCol('endBalance', '期末余额', 110, fmtAmt),
  virtualNumCol('auditDateTransfer', '至审计日结转', 120, fmtAmt),
])

const {
  browseMode,
  useVirtualScroll,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 880,
})
</script>

<style scoped>
.d7-longterm { padding: 12px; }
.d7-longterm :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.d7-longterm :deep(.el-table .cell) {
  font-size: 13px !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.reason-cell { display: flex; align-items: center; }

.total-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  gap: 24px;
  font-size: 13px;
}

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
</style>
