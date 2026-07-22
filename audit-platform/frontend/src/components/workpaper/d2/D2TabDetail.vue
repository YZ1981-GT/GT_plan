<script setup lang="ts">
/**
 * D2TabDetail — 明细表D2-2 (39列宽表)
 * 横向滚动, 固定前2列, 关联方橙色背景, 搜索过滤, 虚拟滚动>30行
 */
import { computed, h, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD2Detail, type DetailRow } from '../composables/useD2Detail'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useVirtualTable, type VirtualColumn } from '@/composables/useVirtualTable'
import type { AgingBand } from '@/composables/useAgingConfig'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  relatedParties: string[]
  bsDate?: string
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-2',
)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.rowId || row?.seq || 'unknown'
  openReviewDialog(`D2-detail-${rowKey}-${field}`)
}

const {
  rows,
  filteredRows,
  totalRow,
  searchQuery,
  addRow,
  removeRow,
  updateCell,
  useVirtualScroll,
  importFromAuxBalance,
  importPostPaymentFromLedger,
  bands,
} = useD2Detail({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  relatedParties: toRef(props, 'relatedParties') as Ref<string[]>,
  bsDate: toRef(props, 'bsDate') as Ref<string>,
})

const browseMode = ref(true)
const tableWidth = ref(1200)
const editPageSize = 50
const editCurrentPage = ref(1)
const pagedRows = computed(() => {
  if (!useVirtualScroll.value || browseMode.value) return filteredRows.value
  const start = (editCurrentPage.value - 1) * editPageSize
  return filteredRows.value.slice(start, start + editPageSize)
})

const virtualColumns = computed<VirtualColumn[]>(() => {
  const fmt = (v: unknown) => displayPrefs.fmtAmount(Number(v) || 0)
  const numCol = (key: keyof DetailRow, title: string, w = 110): VirtualColumn => ({
    key: String(key),
    dataKey: String(key),
    title,
    width: w,
    align: 'right',
    cellRenderer: ({ cellData }) => h('span', {}, fmt(cellData)),
  })
  return [
    { key: 'seq', dataKey: 'seq', title: '序号', width: 60, align: 'center' },
    { key: 'customerName', dataKey: 'customerName', title: '客户名称', width: 160 },
    { key: 'companyCode', dataKey: 'companyCode', title: '公司代码', width: 90 },
    { key: 'relationType', dataKey: 'relationType', title: '关联方类型', width: 120 },
    numCol('priorAudited', '期初审定', 110),
    numCol('currentUnadjusted', '期末未审', 110),
    numCol('currentAudited', '期末审定', 110),
    { key: 'creditRiskClassification', dataKey: 'creditRiskClassification', title: '信用风险组合', width: 130 },
    {
      key: 'isConfirmation',
      dataKey: 'isConfirmation',
      title: '函证',
      width: 60,
      align: 'center',
      cellRenderer: ({ cellData }) => h('span', {}, cellData ? '是' : '-'),
    },
  ]
})

const { rowEventHandlers } = useVirtualTable({
  rows: filteredRows,
  columns: virtualColumns,
  width: tableWidth,
  height: 560,
  onRowDblclick: () => { browseMode.value = false },
})

const RELATION_OPTIONS = ['非关联方', '控股股东', '实际控制人', '其他关联方']
const CREDIT_RISK_OPTIONS = ['单项计提', '账龄组合', '客户类型组合']

const { generateAndConfirm, aiAvailable } = useD2AiGenerate(toRef(props, 'wpId'))
const importing = ref(false)
const detailNote = ref('')

function loadDetailNote(): void {
  detailNote.value = props.allResponses.get('D2-detail-audit-note')?.remark || ''
}
loadDetailNote()

async function handleImportFromAux(): Promise<void> {
  if (props.isReadonly) return
  importing.value = true
  try {
    const result = await importFromAuxBalance(props.projectId)
    ElMessage.success(`导入完成：新增 ${result.added} 行，更新 ${result.updated} 行`)
  } catch {
    ElMessage.error('从余额表导入失败')
  } finally {
    importing.value = false
  }
}

const fetchingPostPayment = ref(false)
async function handleImportPostPayment(): Promise<void> {
  if (props.isReadonly) return
  fetchingPostPayment.value = true
  try {
    await importPostPaymentFromLedger()
  } finally {
    fetchingPostPayment.value = false
  }
}

function saveDetailNote(): void {
  props.allResponses.set('D2-detail-audit-note', { item_id: 'D2-detail-audit-note', conclusion: null, remark: detailNote.value })
  window.dispatchEvent(new CustomEvent('d2:save-items', {
    detail: { items: [{ item_id: 'D2-detail-audit-note', conclusion: null, remark: detailNote.value }] },
  }))
}

async function onAiDetailNote(): Promise<void> {
  const content = await generateAndConfirm('detail-note', detailNote.value, {
    rowCount: rows.value.length,
    totalAudited: totalRow.value.currentAudited,
  }, 'AI 生成明细表说明')
  if (content) {
    detailNote.value = content
    saveDetailNote()
  }
}

function getRowClassName({ row }: { row: DetailRow }): string {
  if (row.relationType && row.relationType !== '非关联方') return 'related-party-row'
  return ''
}

function handleEdit(row: DetailRow, field: string, value: any) {
  if (props.isReadonly) return
  updateCell(row.rowId, field, value)
}
</script>

<template>
  <div class="d2-tab-detail">
    <div class="tab-header">
      <h4>应收账款明细表 D2-2</h4>
      <GtReviewTrigger section-id="D2-detail-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>核实应收账款客户明细的完整性与准确性，按账龄/信用风险组合归集，驱动审定表 SUMIF 汇总与 ECL 计提。</p>
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
        <el-button size="small" type="success" :disabled="isReadonly" :loading="importing" @click="handleImportFromAux">
          从余额表导入
        </el-button>
        <el-tooltip content="从次年序时账取基准日后 1122 贷方收款，按客户归集填入期后回款（函证替代程序）" placement="top">
          <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="fetchingPostPayment" @click="handleImportPostPayment">
            取期后回款
          </el-button>
        </el-tooltip>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
          添加客户
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="searchQuery"
          placeholder="搜索客户名称..."
          size="small"
          clearable
          style="width: 200px"
        />
      </div>
    </div>

    <!-- 虚拟滚动：速览 / 编辑切换 -->
    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ filteredRows.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
      </el-alert>
      <el-button size="small" @click="browseMode = !browseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>

    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="filteredRows"
      :width="tableWidth"
      :height="560"
      :row-height="36"
      :header-height="40"
      :row-event-handlers="rowEventHandlers"
      fixed
      class="virtual-table"
    />

    <!-- 主表（编辑模式或 ≤30 行） -->
    <el-table
      v-else
      :data="pagedRows"
      border
      stripe
      size="small"
      :row-class-name="getRowClassName"
      :max-height="600"
      style="width: 100%"
    >
      <el-table-column label="序号" width="68" fixed>
        <template #default="{ $index, row }">
          {{ $index + 1 }}<GtReviewDot row-prefix="D2-detail" :row-key="row.rowId" />
        </template>
      </el-table-column>
      <el-table-column prop="customerName" label="客户名称" width="160" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.customerName"
            size="small"
            @update:model-value="(v: string) => handleEdit(row, 'customerName', v)"
          />
          <span v-else>{{ row.customerName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公司代码" width="90" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.companyCode"
            size="small"
            @change="(v: string) => handleEdit(row, 'companyCode', v)"
          />
          <span v-else>{{ row.companyCode || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 关联方类型 -->
      <el-table-column label="关联方类型" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.relationType"
            size="small"
            @change="(v: string) => handleEdit(row, 'relationType', v)"
          >
            <el-option v-for="opt in RELATION_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.relationType }}</span>
        </template>
      </el-table-column>

      <!-- 期初 -->
      <el-table-column label="期初未审" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorUnadjusted) }}</template>
      </el-table-column>
      <el-table-column label="期初AJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorAje) }}</template>
      </el-table-column>
      <el-table-column label="期初RJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorRje) }}</template>
      </el-table-column>
      <el-table-column label="期初审定" width="110" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600">{{ displayPrefs.fmtAmount(row.priorAudited) }}</span>
        </template>
      </el-table-column>

      <!-- 期初审定账龄 -->
      <el-table-column label="期初审定账龄" align="center">
        <el-table-column v-for="band in bands" :key="'p-' + band.key" :label="band.label" width="95" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.agingPrior?.[band.key] ?? 0) }}</template>
        </el-table-column>
      </el-table-column>

      <!-- 本期发生 -->
      <el-table-column label="借方发生" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.debitOccurrence) }}</template>
      </el-table-column>
      <el-table-column label="贷方发生" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.creditOccurrence) }}</template>
      </el-table-column>
      <el-table-column label="期末余额" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.endBalance) }}</template>
      </el-table-column>
      <el-table-column label="重分类" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.reclassification) }}</template>
      </el-table-column>

      <!-- 期末未审 -->
      <el-table-column label="期末未审" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentUnadjusted) }}</template>
      </el-table-column>

      <!-- 期末未审账龄 -->
      <el-table-column label="期末未审账龄" align="center">
        <el-table-column v-for="band in bands" :key="'c-' + band.key" :label="band.label" width="95" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.agingCurrent?.[band.key] ?? 0) }}</template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末AJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentAje) }}</template>
      </el-table-column>
      <el-table-column label="期末RJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentRje) }}</template>
      </el-table-column>
      <el-table-column label="期末审定" width="110" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
        </template>
      </el-table-column>

      <!-- 期末审定账龄 -->
      <el-table-column label="期末审定账龄" align="center">
        <el-table-column v-for="band in bands" :key="'a-' + band.key" :label="band.label" width="95" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.agingAudited?.[band.key] ?? 0"
              :controls="false"
              size="small"
              class="aging-input"
              @change="(v: number) => handleEdit(row, `agingAudited.${band.key}`, v ?? 0)"
            />
            <span v-else class="audited-aging">{{ displayPrefs.fmtAmount(row.agingAudited?.[band.key] ?? 0) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 信用风险组合方式 -->
      <el-table-column label="信用风险组合方式" width="160">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.creditRiskClassification"
            size="small"
            @change="(v: string) => handleEdit(row, 'creditRiskClassification', v)"
          >
            <el-option v-for="opt in CREDIT_RISK_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.creditRiskClassification }}</span>
        </template>
      </el-table-column>

      <el-table-column label="组合名称" width="110">
        <template #default="{ row }">{{ row.groupName || '-' }}</template>
      </el-table-column>
      <el-table-column label="函证" width="60" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.isConfirmation"
            :class="{ 'confirmation-auto': (row as any)._confirmationAutoMarked }"
            type="success"
            size="small"
          >是</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>

      <!-- 期后回款（可编辑 / 一键取数） -->
      <el-table-column label="期后回款" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.postPayment"
            :controls="false"
            :precision="2"
            size="small"
            style="width: 118px"
            @change="(v: number | undefined) => handleEdit(row, 'postPayment', v ?? 0)"
          />
          <span v-else>{{ displayPrefs.fmtAmount(row.postPayment) }}</span>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="70" fixed="right" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑模式分页 -->
    <div v-if="useVirtualScroll && !browseMode && filteredRows.length > editPageSize" class="edit-pagination">
      <el-pagination
        v-model:current-page="editCurrentPage"
        :page-size="editPageSize"
        :total="filteredRows.length"
        layout="prev, pager, next, jumper, ->, total"
        small
      />
    </div>

    <!-- 合计行 -->
    <div class="total-bar">
      <span class="total-label">合计</span>
      <span class="total-value">期初审定: {{ displayPrefs.fmtAmount(totalRow.priorAudited as number) }}</span>
      <span class="total-value">期末审定: {{ displayPrefs.fmtAmount(totalRow.currentAudited as number) }}</span>
      <span class="total-value">期后回款: {{ displayPrefs.fmtAmount(totalRow.postPayment as number) }}</span>
    </div>
    <!-- 审计说明 -->
    <div class="audit-note-block">
      <div class="audit-note-header">
        <span>审计说明</span>
        <GtReviewTrigger section-id="D2-detail-audit-note" />
        <el-button v-if="aiAvailable && !isReadonly" size="small" text type="primary" @click="onAiDetailNote">🤖 AI生成</el-button>
      </div>
      <el-input
        v-model="detailNote"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="明细表编制说明..."
        @change="saveDetailNote"
      />
    </div>
  </div>
</template>

<style scoped>
.d2-tab-detail { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(p) { margin: 0; font-size: var(--wp-font-size, 13px); line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.toolbar-right { display: flex; align-items: center; }
.virtual-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.virtual-hint { margin-bottom: 0; flex: 1; }
.virtual-table { margin-bottom: 8px; }
.edit-pagination { margin: 8px 0; display: flex; justify-content: center; }
:deep(.related-party-row) { background-color: #fff7e6 !important; }
.aging-input { width: 100%; }
.total-bar {
  display: flex; gap: 24px; align-items: center;
  padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.total-label { font-weight: 600; }
.total-value { color: #606266; }
.audited-aging { background: #e6f7ff; padding: 1px 4px; border-radius: 2px; }
.confirmation-auto { background: #b7eb8f !important; border-color: #52c41a !important; color: #135200 !important; }
.audit-note-block { margin-top: 16px; }
.audit-note-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-weight: 600; font-size: var(--wp-font-size, 13px); }
</style>
