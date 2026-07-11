<template>
  <div class="h8-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>使用权资产审定表：科目1901（借方/资产类）+ 累计折旧（贷方/备抵类）。原值期末=期初+借-贷；折旧期末=期初+贷-借。审定数=未审+AJE+RJE。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-1" />
      <el-tag size="small" type="info">共 {{ costRows.length + accDepRows.length }} 行</el-tag>
    </div>

    <!-- 区块1: 使用权资产-原值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>使用权资产-原值（科目1901）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddCostRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'adjudication-cost')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'adjudication-cost')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="costRows" border size="small" class="formula-table" show-summary :summary-method="getCostSummary">
        <el-table-column prop="name" label="项目（租赁类型）" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCellChange(row.rowId, 'name', row.name)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'beginBalance', v)" />
            <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitAmount" label="借方发生" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'debitAmount', v)" />
            <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditAmount" label="贷方发生" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'creditAmount', v)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：期初+借方-贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.unadjusted" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'unadjusted', v)" />
            <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'aje', v)" />
            <span v-else>{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'rje', v)" />
            <span v-else>{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区块2: 累计折旧 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>累计折旧（备抵类，贷方）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddDepRow">+ 新增行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="accDepRows" border size="small" class="formula-table" show-summary :summary-method="getDepSummary">
        <el-table-column prop="name" label="项目（租赁类型）" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCellChange(row.rowId, 'name', row.name)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'beginBalance', v)" />
            <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitAmount" label="借方发生" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'debitAmount', v)" />
            <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditAmount" label="贷方发生" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'creditAmount', v)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：期初+贷方-借方（备抵类）">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.unadjusted" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'unadjusted', v)" />
            <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'aje', v)" />
            <span v-else>{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'rje', v)" />
            <span v-else>{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 净值合计 -->
    <el-card shadow="never" class="net-card">
      <div class="net-row">
        <span class="net-label">使用权资产净值（原值 - 累计折旧）</span>
        <span class="net-value">{{ fmtAmt(netAudited) }} 元</span>
      </div>
    </el-card>

    <!-- H9联动校验区域 -->
    <el-card shadow="never" class="linkage-card">
      <template #header>
        <div class="section-title">
          <span>H8-H9 联动校验（CAS21）</span>
        </div>
      </template>
      <div class="linkage-content">
        <div class="linkage-formula">
          <span class="formula-label">核心公式：</span>
          <span>使用权资产初始计量 = H9租赁负债初始确认 + 初始直接费用 - 租赁激励</span>
        </div>
        <div
          class="linkage-status"
          :class="h9Linkage.isConsistent ? 'linkage-ok' : 'linkage-error'"
        >
          <el-icon v-if="h9Linkage.isConsistent"><svg viewBox="0 0 1024 1024" width="14"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.7l-210.6 292a31.8 31.8 0 01-51.7 0l-109.8-152a8 8 0 016.5-12.7h46.2c10.3 0 19.9 5 25.9 13.3l63.5 87.8 164.4-228c6-8.3 15.6-13.3 25.9-13.3h46.2a8 8 0 016.5 12.7z" fill="currentColor"/></svg></el-icon>
          <span>{{ h9Linkage.message }}</span>
          <span v-if="!h9Linkage.isConsistent && h9Linkage.diff !== 0" class="diff-badge">
            差额：{{ h9Linkage.diff > 0 ? '+' : '' }}{{ h9Linkage.diff.toFixed(2) }}元
          </span>
        </div>
      </div>
    </el-card>

    <!-- TB回写 -->
    <div v-if="!isReadonly" class="writeback-area">
      <el-button type="primary" @click="handleWriteback" :loading="writebackLoading">
        审定数回写TB（1901+累计折旧）
      </el-button>
    </div>

    <!-- 审计说明+结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'adjudication-note')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'adjudication-note')">复核</el-button>
          </div>
        </div>
      </template>
      <el-form label-position="top" size="small">
        <el-form-item label="审计说明">
          <el-input type="textarea" :autosize="{ minRows: 3 }" v-model="auditNoteLocal"
            :readonly="isReadonly" @change="handleSaveNote" placeholder="请输入审计说明..." />
        </el-form-item>
        <el-form-item label="审计结论">
          <el-input type="textarea" :autosize="{ minRows: 2 }" v-model="auditConclusionLocal"
            :readonly="isReadonly" @change="handleSaveConclusion" placeholder="请输入审计结论..." />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>使用权资产原值（1901）为借方资产类：期末=期初+借方-贷方</li>
        <li>累计折旧为备抵类（贷方）：期末=期初+贷方-借方</li>
        <li>审定数=未审数+AJE+RJE；净值=原值审定数-累计折旧审定数</li>
        <li>核心公式（CAS21）：初始计量=H9租赁负债初始确认+初始直接费用-租赁激励</li>
        <li>审定完成后点击"审定数回写TB"，同步至试算表科目1901及累计折旧</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabAdjudication.vue — H8-1 审定表（双区块51公式+H9联动校验+TB回写）
 * Spec: Task 4.2 | Requirements: 2.1-2.8, 11.1-11.4
 */
import { ref, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8Adjudication, type H8AdjudicationRow } from '../../composables/useH8Adjudication'
import { useH8CrossSheet } from '../../composables/useH8CrossSheet'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'writeback-tb', costAudited: number, depAudited: number): void
}>()

const writebackLoading = ref(false)
const auditNoteLocal = ref('')
const auditConclusionLocal = ref('')

const allResponsesRef = toRef(props, 'allResponses')

const {
  costRows, accDepRows, costSubtotal, accDepSubtotal, netAudited,
  updateCell, addRow, deleteRow, publishAdjudicated, saveNote, saveConclusion, auditNote, auditConclusion,
} = useH8Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
  onSave: (itemId, value) => emit('save', itemId, value),
  onWritebackTB: async (cost, dep) => {
    emit('writeback-tb', cost, dep)
  },
})

const { h8VsH9Linkage } = useH8CrossSheet(allResponsesRef)
const h9Linkage = computed(() => h8VsH9Linkage.value)

// Sync local text refs
auditNoteLocal.value = auditNote.value
auditConclusionLocal.value = auditConclusion.value

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCellChange(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function handleAddCostRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁类型名称', '新增原值行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：房屋租赁',
  })
  if (value) addRow(value, 'cost')
}

async function handleAddDepRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁类型名称', '新增折旧行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：房屋租赁',
  })
  if (value) addRow(value, 'accDep')
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

async function handleWriteback() {
  writebackLoading.value = true
  try {
    await publishAdjudicated()
  } finally {
    writebackLoading.value = false
  }
}

function handleSaveNote() { saveNote(auditNoteLocal.value) }
function handleSaveConclusion() { saveConclusion(auditConclusionLocal.value) }

function getCostSummary({ columns, data }: { columns: any[]; data: H8AdjudicationRow[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '原值小计'
    const s = costSubtotal.value
    const map: Record<number, number> = { 1: s.beginBalance, 2: s.debitAmount, 3: s.creditAmount, 4: s.endBalance, 5: s.unadjusted, 6: s.aje, 7: s.rje, 8: s.audited }
    return map[idx] !== undefined ? fmtAmt(map[idx]) : ''
  })
}

function getDepSummary({ columns, data }: { columns: any[]; data: H8AdjudicationRow[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '折旧小计'
    const s = accDepSubtotal.value
    const map: Record<number, number> = { 1: s.beginBalance, 2: s.debitAmount, 3: s.creditAmount, 4: s.endBalance, 5: s.unadjusted, 6: s.aje, 7: s.rje, 8: s.audited }
    return map[idx] !== undefined ? fmtAmt(map[idx]) : ''
  })
}
</script>

<style scoped>
.h8-tab-adjudication { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.block-card { margin-bottom: 16px; }
.formula-table { font-size: 13px; }
.formula-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }

.net-card { margin-bottom: 16px; }
.net-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; }
.net-label { font-weight: 600; }
.net-value { font-size: 18px; font-weight: 700; color: var(--el-color-primary); }

.linkage-card { margin-bottom: 16px; }
.linkage-content { padding: 4px 0; }
.linkage-formula { margin-bottom: 10px; font-size: 12px; color: var(--el-text-color-secondary); }
.formula-label { font-weight: 600; }
.linkage-status { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 6px; }
.linkage-ok { background: #f0f9eb; color: #67c23a; }
.linkage-error { background: #fef0f0; color: #f56c6c; }
.diff-badge { font-weight: 700; margin-left: 8px; }

.writeback-area { margin-bottom: 16px; text-align: right; }
.note-card { margin-bottom: 16px; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
