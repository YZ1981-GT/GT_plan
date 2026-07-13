<template>
  <div class="g1-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">G1-3 交易性金融资产调整分录</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">新增分录</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-3-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实交易性金融资产（科目1501）审计调整分录（AJE）与重分类分录（RJE）的完整、准确与借贷平衡，确认调整依据充分、账务处理恰当。"
      class="objective-alert"
    />

    <el-table :data="rows" border size="small" max-height="500">
      <el-table-column prop="seq" label="序号" width="60">
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="分录类型" width="100">
        <template #default="{ row }">
          <el-select v-model="row.entryType" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { entryType: row.entryType })">
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="日期" width="140">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly"
            @change="updateRow(row.id, { date: row.date })" />
        </template>
      </el-table-column>
      <el-table-column label="摘要" width="180">
        <template #default="{ row }">
          <el-input v-model="row.summary" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { summary: row.summary })" />
        </template>
      </el-table-column>
      <el-table-column label="科目代码" width="110">
        <template #default="{ row }">
          <el-input v-model="row.accountCode" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { accountCode: row.accountCode })" />
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="150">
        <template #default="{ row }">
          <el-input v-model="row.accountName" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { accountName: row.accountName })" />
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.debit" size="small" :controls="false" :disabled="isReadonly" style="width: 100%"
            @change="updateRow(row.id, { debit: row.debit })" />
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.credit" size="small" :controls="false" :disabled="isReadonly" style="width: 100%"
            @change="updateRow(row.id, { credit: row.credit })" />
        </template>
      </el-table-column>
      <el-table-column label="编制人" width="100">
        <template #default="{ row }">
          <el-input v-model="row.preparer" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { preparer: row.preparer })" />
        </template>
      </el-table-column>
      <el-table-column label="备注" width="140">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { remark: row.remark })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡校验 -->
    <div class="balance-bar" :class="{ 'balance-ok': balanced, 'balance-bad': !balanced }">
      <span>借方合计：{{ totalDebit.toLocaleString() }}</span>
      <span>贷方合计：{{ totalCredit.toLocaleString() }}</span>
      <span v-if="balanced" class="balance-flag">✓ 借贷平衡</span>
      <span v-else class="balance-flag">✗ 借贷不平衡，差额：{{ balanceDiff.toLocaleString() }}</span>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：（1）调整分录的编制依据及事项说明；（2）AJE/RJE 对科目1501及相关损益的影响。" />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="对调整分录的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>AJE=审计调整分录，RJE=重分类调整分录，需分别录入。</li>
        <li>每张凭证借贷方金额必须相等，底部实时校验借贷平衡。</li>
        <li>交易性金融资产科目代码为 1501，公允价值变动损益计入投资收益/公允价值变动损益。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, watch } from 'vue'
import { isDebitCreditBalanced, parseNum } from '../../composables/useG1TraFinFormulaEngine'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const DATA_KEY = 'G1-3-rows'
const CONCLUSION_KEY = 'G1-3-conclusion'

interface AdjustmentRow {
  id: string
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debit: number
  credit: number
  preparer: string
  remark: string
}

function emptyRow(id: string): AdjustmentRow {
  return {
    id,
    entryType: 'AJE',
    date: '',
    summary: '',
    accountCode: '',
    accountName: '',
    debit: 0,
    credit: 0,
    preparer: '',
    remark: '',
  }
}

function loadRows(): AdjustmentRow[] {
  const raw = props.allResponses.get(DATA_KEY)?.conclusion
  if (!raw) return [emptyRow('1')]
  try {
    const parsed = JSON.parse(raw) as AdjustmentRow[]
    return Array.isArray(parsed) && parsed.length ? parsed : [emptyRow('1')]
  } catch {
    return [emptyRow('1')]
  }
}

const rows = ref<AdjustmentRow[]>(loadRows())
const conclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.conclusion ?? '')

const AUDIT_NOTE_KEY = 'G1-3-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const totalDebit = computed(() => rows.value.reduce((s, r) => s + parseNum(r.debit), 0))
const totalCredit = computed(() => rows.value.reduce((s, r) => s + parseNum(r.credit), 0))
const balanced = computed(() =>
  isDebitCreditBalanced(
    rows.value.map((r) => parseNum(r.debit)),
    rows.value.map((r) => parseNum(r.credit)),
  ),
)
const balanceDiff = computed(() => totalDebit.value - totalCredit.value)

function persist() {
  if (props.isReadonly) return
  props.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
}

function updateRow(id: string, patch: Partial<AdjustmentRow>) {
  if (props.isReadonly) return
  rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
  persist()
}

function addRow() {
  if (props.isReadonly) return
  rows.value = [...rows.value, emptyRow(`row-${Date.now()}`)]
  persist()
}

function removeRow(id: string) {
  if (props.isReadonly || rows.value.length <= 1) return
  rows.value = rows.value.filter((r) => r.id !== id)
  persist()
}

watch(conclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { conclusion: v })
})
</script>

<style scoped>
.g1-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-adjustment :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-adjustment :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.balance-bar { display: flex; gap: 24px; align-items: center; margin: 14px 0; padding: 8px 12px; border-radius: 4px; }
.balance-ok { background: #f0f9eb; color: #67c23a; }
.balance-bad { background: #fef0f0; color: #f56c6c; }
.balance-flag { font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
