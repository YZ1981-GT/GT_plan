<template>
  <div class="h9-tab-detail">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实租赁负债各合同期末余额、本期偿还与利息费用（实际利率法）计算准确、完整，确认与 H8 使用权资产及摊销表的勾稽关系符合 CAS21。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第26条：租赁负债按实际利率法后续计量，期末=期初-偿还(借方)+利息(贷方)。22列按3区段Tab展示，与H8使用权资产合同一一对应。</p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="ledgerPulling" @click="handleLedgerPull">
          📥 从序时账取数
        </el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H9-2" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 区段切换 + 工具栏 -->
    <div class="segment-bar">
      <el-segmented v-model="activeTab" :options="tabOptions" size="default" />
      <div class="bar-actions">
        <el-dropdown v-if="!isReadonly" trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRow">+ 新增合同</el-button>
        <el-button size="small" @click="$emit('open-review', 'detail')">复核</el-button>
      </div>
    </div>

    <!-- 区段1: 基础+变动 (A~E列 + O~R) -->
    <el-table
      v-if="activeTab === '负债变动'"
      :data="rows"
      border
      size="small"
      class="detail-table"
      show-summary
      :summary-method="getSummaryMovement"
    >
      <el-table-column prop="lessor" label="出租方" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.lessor" size="small" @change="onCell(row.rowId, 'lessor', row.lessor)" />
          <span v-else>{{ row.lessor }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="contractNo" label="合同号" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" @change="onCell(row.rowId, 'contractNo', row.contractNo)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="H8" width="60" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="row.contractNo" value="H8-2" :context-project-id="props.projectId"
            context="H8使用权资产对应合同" @click="emit('navigate-sheet', 'H8-2')" :prevent-navigate="true" />
        </template>
      </el-table-column>
      <el-table-column prop="assetDesc" label="承租资产" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.assetDesc" size="small" @change="onCell(row.rowId, 'assetDesc', row.assetDesc)" />
          <span v-else>{{ row.assetDesc }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="ibrRate" label="IBR利率(%)" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.ibrRate" :controls="false" :precision="2" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'ibrRate', v)" />
          <span v-else>{{ row.ibrRate ? row.ibrRate.toFixed(2) + '%' : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="leaseTerm" label="租赁期(月)" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.leaseTerm" :controls="false" :min="0" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'leaseTerm', v)" />
          <span v-else>{{ row.leaseTerm || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="beginBalance" label="B:期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'beginBalance', v)" />
          <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="repayment" label="C:本期偿还(借)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.repayment" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'repayment', v)" />
          <span v-else>{{ fmtAmt(row.repayment) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="interestAccrued" label="D:本期利息(贷)" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.interestAccrued" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'interestAccrued', v)" />
          <span v-else>{{ fmtAmt(row.interestAccrued) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="E:期末余额" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：E=B-C+D（负债贷方：期初-偿还+利息）">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleDelete(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段2: 审定调整 (F~N列) -->
    <el-table
      v-if="activeTab === '审定调整'"
      :data="rows"
      border
      size="small"
      class="detail-table"
      show-summary
      :summary-method="getSummaryAdjustment"
    >
      <el-table-column prop="lessor" label="出租方" width="120" />
      <el-table-column prop="contractNo" label="合同号" width="110" />
      <el-table-column prop="beginAje" label="F:期初AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.beginAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'beginAje', v)" />
          <span v-else>{{ fmtAmt(row.beginAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="repayAje" label="G:偿还AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.repayAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'repayAje', v)" />
          <span v-else>{{ fmtAmt(row.repayAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="interestAje" label="H:利息AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.interestAje" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'interestAje', v)" />
          <span v-else>{{ fmtAmt(row.interestAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="I:审定期初" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：I=B+F">{{ fmtAmt(row.auditedBegin) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="J:审定偿还" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：J=C+G">{{ fmtAmt(row.auditedRepay) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="K:审定利息" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：K=D+H">{{ fmtAmt(row.auditedInterest) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="L:审定期末" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：L=I-J+K">{{ fmtAmt(row.auditedEnd) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="reclassification" label="M:重分类" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.reclassification" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'reclassification', v)" />
          <span v-else>{{ fmtAmt(row.reclassification) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="N:最终审定" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：N=L-M">{{ fmtAmt(row.finalAudited) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段3: 到期分析+关联方+发函+期后 -->
    <el-table
      v-if="activeTab === '到期与关联'"
      :data="rows"
      border
      size="small"
      class="detail-table"
    >
      <el-table-column prop="lessor" label="出租方" width="120" />
      <el-table-column prop="contractNo" label="合同号" width="110" />
      <el-table-column label="N:最终审定" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmt(row.finalAudited) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="dueWithin1Y" label="O:1年以内" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.dueWithin1Y" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'dueWithin1Y', v)" />
          <span v-else>{{ fmtAmt(row.dueWithin1Y) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="due1To2Y" label="P:1-2年" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.due1To2Y" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'due1To2Y', v)" />
          <span v-else>{{ fmtAmt(row.due1To2Y) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="due2To3Y" label="Q:2-3年" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.due2To3Y" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'due2To3Y', v)" />
          <span v-else>{{ fmtAmt(row.due2To3Y) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="dueOver3Y" label="R:3年以上" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.dueOver3Y" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'dueOver3Y', v)" />
          <span v-else>{{ fmtAmt(row.dueOver3Y) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="到期合计vs审定" width="120" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span
            class="formula-value"
            :class="{ 'maturity-mismatch': Math.abs((row.dueWithin1Y + row.due1To2Y + row.due2To3Y + row.dueOver3Y) - row.finalAudited) > 1 }"
            :title="'四档合计应等于最终审定 N'"
          >
            {{ fmtAmt(row.dueWithin1Y + row.due1To2Y + row.due2To3Y + row.dueOver3Y) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="isRelatedParty" label="S:关联方" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="!isReadonly" :type="row.isRelatedParty === '是' ? 'danger' : 'info'" size="small"
            style="cursor: pointer" @click="toggleRelated(row)">
            {{ row.isRelatedParty }}
          </el-tag>
          <el-tag v-else :type="row.isRelatedParty === '是' ? 'danger' : 'info'" size="small">
            {{ row.isRelatedParty }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="isConfirmed" label="T:发函" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="!isReadonly" :type="row.isConfirmed === '是' ? 'success' : 'info'" size="small"
            style="cursor: pointer" @click="toggleConfirmed(row)">
            {{ row.isConfirmed }}
          </el-tag>
          <el-tag v-else :type="row.isConfirmed === '是' ? 'success' : 'info'" size="small">
            {{ row.isConfirmed }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计统计栏 -->
    <div class="stat-bar">
      <span>合同总数：{{ rows.length }}</span>
      <span>期初合计：{{ fmtAmt(totalRow.beginBalance) }}元</span>
      <span>审定期末合计：{{ fmtAmt(totalRow.auditedEnd) }}元</span>
      <span>最终审定合计：{{ fmtAmt(totalRow.finalAudited) }}元</span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-header">
          <span>审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="对租赁负债明细的审计说明..."
        :readonly="isReadonly"
        @change="onSaveNote('H9-2-audit-note', auditNote)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="note-header">
          <span>审计结论</span>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="对租赁负债明细表的审计结论..."
        :readonly="isReadonly"
        @change="onSaveNote('H9-2-audit-conclusion', auditConclusion)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <ul>
        <li>租赁负债为负债类贷方科目：期末余额 E = 期初 B − 本期偿还 C（借方）+ 本期利息 D（贷方）</li>
        <li>IBR 增量借款利率按 CAS21 应采用承租人在类似期限、类似担保下的借款利率</li>
        <li>各合同应与 H8 使用权资产逐一对应（点 H8 索引跳转核对初始确认勾稽）</li>
        <li>本期利息费用应与 H9 摊销表 Σ 各期利息一致（±1 元容差）</li>
        <li>审定期末 L = 审定期初 I − 审定偿还 J + 审定利息 K；最终审定 N = L − 重分类 M</li>
        <li>到期日分析 O~R 四档合计应等于最终审定 N（支撑附注流动性披露）</li>
        <li>关联方租赁需在 H9-6 单独评价公允性，并在附注中披露</li>
        <li>初始确认及未确认融资费用摊销计算过程参见使用权资产底稿 H8-4/H8-5/H8-6/H8-7</li>
      </ul>
    </details>

    <!-- 隐藏文件上传(导入) -->
    <input ref="importFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileImport" />
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabDetail.vue — H9-2 租赁负债明细表（22列 3区段Tab）
 *
 * 按合同列示租赁负债变动（负债贷方科目：期末=期初-偿还+利息）
 * 3区段Tab切换行同步：①负债变动(基础+B~E) ②审定调整(F~N) ③到期与关联(S/T)
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 4.3
 * Requirements: 3.1-3.6
 */
import { ref, toRef, inject } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useH9Detail, type H9DetailRow } from '../../composables/useH9Detail'
import { useH9ImportExport } from '../../composables/useH9ImportExport'
import { fetchH9LedgerByLessor } from '../../composables/h9LedgerPull'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── 区段Tab ─────────────────────────────────────────────────────────────────
const tabOptions = ['负债变动', '审定调整', '到期与关联']
const activeTab = ref('负债变动')

// ─── Composable ──────────────────────────────────────────────────────────────
const {
  rows, totalRow,
  addRow, deleteRow, updateCell,
} = useH9Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const h9ReloadAll = inject<() => Promise<void>>('h9ReloadAll', async () => {})

const {
  exportTemplate, exportData, importData,
} = useH9ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'H9-2',
  onImported: async () => { await h9ReloadAll() },
})

// ─── 审计说明/结论 ───────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')

// 从 allResponses 加载文本
function loadNotes() {
  const noteItem = props.allResponses.get('H9-2-audit-note')
  auditNote.value = noteItem?.remark ?? noteItem?.conclusion ?? ''
  const conclusionItem = props.allResponses.get('H9-2-audit-conclusion')
  auditConclusion.value = conclusionItem?.remark ?? conclusionItem?.conclusion ?? ''
}
loadNotes()

function onSaveNote(itemId: string, value: string) {
  emit('save', itemId, value)
}

// ─── Actions ─────────────────────────────────────────────────────────────────
function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCell(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入出租方名称', '新增明细行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：XX房地产开发有限公司',
  })
  if (value) addRow(value)
}

// ─── 从序时账取数（科目2205按出租方聚合） ─────────────────────────────────
const ledgerPulling = ref(false)

async function handleLedgerPull() {
  if (props.isReadonly || !props.projectId) return
  ledgerPulling.value = true
  try {
    const year = props.year || new Date().getFullYear()
    const ledgerRows = await fetchH9LedgerByLessor(props.projectId, year)
    if (!ledgerRows.length) {
      ElMessage.info('序时账中未找到科目2205的租赁相关分录，请确认试算表已导入')
      return
    }
    const summary = `共找到 ${ledgerRows.length} 个出租方的租赁发生额数据（偿还/利息），是否合并到明细表？\n（仅填充空值，不覆盖已有数据）`
    await ElMessageBox.confirm(summary, '从序时账取数', {
      confirmButtonText: '合并', cancelButtonText: '取消', type: 'info',
    })
    const merged = mergeH9LedgerRows(rows.value, ledgerRows)
    // 逐行通过 addRow/updateCell 方式合并（新行 addRow，已有行 updateCell）
    for (const lr of ledgerRows) {
      const nameKey = lr.lessor.trim().toLowerCase()
      const existing = rows.value.find(r => String(r.lessor || '').trim().toLowerCase() === nameKey)
      if (existing) {
        // 仅填空值
        if (!existing.repayment && lr.repayment) updateCell(existing.rowId, 'repayment', lr.repayment)
        if (!existing.interestAccrued && lr.interestAccrued) updateCell(existing.rowId, 'interestAccrued', lr.interestAccrued)
      } else {
        // 新增行后设置字段
        addRow(lr.lessor)
        const newRow = rows.value[rows.value.length - 1]
        if (newRow && lr.repayment) updateCell(newRow.rowId, 'repayment', lr.repayment)
        if (newRow && lr.interestAccrued) updateCell(newRow.rowId, 'interestAccrued', lr.interestAccrued)
      }
    }
    ElMessage.success(`已从序时账合并 ${ledgerRows.length} 个出租方数据`)
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.warning('从序时账取数失败，请稍后重试')
    }
  } finally {
    ledgerPulling.value = false
  }
}

function handleDelete(rowId: string) {
  deleteRow(rowId)
}

function toggleRelated(row: H9DetailRow) {
  const newVal = row.isRelatedParty === '是' ? '否' : '是'
  updateCell(row.rowId, 'isRelatedParty', newVal)
}

function toggleConfirmed(row: H9DetailRow) {
  const newVal = row.isConfirmed === '是' ? '否' : '是'
  updateCell(row.rowId, 'isConfirmed', newVal)
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
const importFileRef = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string) {
  switch (command) {
    case 'export-template': exportTemplate(['H9-2']); break
    case 'export-data': exportData(['H9-2']); break
    case 'import-data': importFileRef.value?.click(); break
  }
}

async function handleFileImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await importData(file)
  // Reset input
  if (importFileRef.value) importFileRef.value.value = ''
}

// ─── Summary methods ─────────────────────────────────────────────────────────
function getSummaryMovement({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return `合计（${rows.value.length}笔）`
    if (idx === 6) return fmtAmt(totalRow.value.beginBalance)
    if (idx === 7) return fmtAmt(totalRow.value.repayment)
    if (idx === 8) return fmtAmt(totalRow.value.interestAccrued)
    if (idx === 9) return fmtAmt(totalRow.value.endBalance)
    return ''
  })
}

function getSummaryAdjustment({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 5) return fmtAmt(totalRow.value.auditedBegin)
    if (idx === 6) return fmtAmt(totalRow.value.auditedRepay)
    if (idx === 7) return fmtAmt(totalRow.value.auditedInterest)
    if (idx === 8) return fmtAmt(totalRow.value.auditedEnd)
    if (idx === 10) return fmtAmt(totalRow.value.finalAudited)
    return ''
  })
}
</script>

<style scoped>
.h9-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.guidance-details {
  margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-details ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

.segment-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.bar-actions { display: flex; gap: 6px; align-items: center; }

.detail-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.detail-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }
.maturity-mismatch { color: #f56c6c !important; font-weight: 700; }

.stat-bar {
  display: flex; gap: 24px; padding: 10px 0; font-size: 12px;
  color: var(--el-text-color-secondary); border-top: 1px solid var(--el-border-color-lighter);
  margin-bottom: 16px;
}

.audit-note-card { margin-bottom: 12px; }
.note-header { display: flex; align-items: center; justify-content: space-between; }
</style>
