<template>
  <div class="h9-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>租赁负债审定表：科目2205（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）。负债类期末=期初+贷方-借方；备抵类期末=期初+借方-贷方。审定数=未审+AJE+RJE。净额=原值-未确认融资费用。</p>
    </div>

    <!-- 区块1: 租赁负债原值（贷方/负债类） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、租赁负债原值（科目2205，贷方/负债类）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddLiabilityRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'adjudication-liability')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'adjudication-liability')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="liabilityRows" border size="small" class="formula-table" show-summary :summary-method="getLiabilitySummary">
        <el-table-column prop="name" label="项目（合同类型）" min-width="140">
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
        <el-table-column prop="creditAmount" label="贷方发生(增加)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'creditAmount', v)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitAmount" label="借方发生(减少)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'debitAmount', v)" />
            <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：期初+贷方-借方（负债类贷方科目）">{{ fmtAmt(row.endBalance) }}</span>
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

    <!-- 区块2: 未确认融资费用（借方/负债备抵类） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、未确认融资费用（借方/负债备抵类）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddUnearnedRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'adjudication-unearned')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'adjudication-unearned')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="unearnedRows" border size="small" class="formula-table" show-summary :summary-method="getUnearnedSummary">
        <el-table-column prop="name" label="项目（合同类型）" min-width="140">
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
        <el-table-column prop="debitAmount" label="借方发生(增加)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'debitAmount', v)" />
            <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditAmount" label="贷方发生(摊销确认)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'creditAmount', v)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：期初+借方-贷方（借方/负债备抵类）">{{ fmtAmt(row.endBalance) }}</span>
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

    <!-- 三、租赁负债净额 -->
    <el-card shadow="never" class="net-card">
      <div class="net-row">
        <span class="net-label">三、租赁负债净额（原值 - 未确认融资费用）</span>
        <span class="net-value">{{ fmtAmt(netAudited) }} 元</span>
      </div>
    </el-card>

    <!-- H8-H9 联动校验区域 -->
    <el-card shadow="never" class="linkage-card">
      <template #header>
        <div class="section-title">
          <span>H8-H9 联动校验（CAS21）</span>
        </div>
      </template>
      <div class="linkage-content">
        <div class="linkage-formula">
          <span class="formula-label">核心公式：</span>
          <span>H9初始确认 ≈ H8初始计量 - 初始直接费用 + 租赁激励（±1元容差）</span>
        </div>
        <div class="linkage-status" :class="h8Linkage.isConsistent ? 'linkage-ok' : 'linkage-error'">
          <el-icon v-if="h8Linkage.isConsistent" :size="14"><svg viewBox="0 0 1024 1024" width="14"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.7l-210.6 292a31.8 31.8 0 01-51.7 0l-109.8-152a8 8 0 016.5-12.7h46.2c10.3 0 19.9 5 25.9 13.3l63.5 87.8 164.4-228c6-8.3 15.6-13.3 25.9-13.3h46.2a8 8 0 016.5 12.7z" fill="currentColor"/></svg></el-icon>
          <el-icon v-else :size="14"><svg viewBox="0 0 1024 1024" width="14"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm165.4 618.2l-66-.3L512 563.4l-99.3 118.4-66.1.3c-4.4 0-8-3.5-8-8 0-1.9.7-3.7 1.9-5.2l130.1-155L340.5 359a8.3 8.3 0 01-1.9-5.2c0-4.4 3.6-8 8-8l66.1.3L512 464.6l99.3-118.4 66-.3c4.4 0 8 3.5 8 8 0 1.9-.7 3.7-1.9 5.2L553.5 514l130 155c1.2 1.5 1.9 3.3 1.9 5.2 0 4.4-3.6 8-8 8z" fill="currentColor"/></svg></el-icon>
          <span>{{ h8Linkage.message }}</span>
          <span v-if="!h8Linkage.isConsistent && h8Linkage.diff !== 0" class="diff-badge">
            差额：{{ h8Linkage.diff > 0 ? '+' : '' }}{{ h8Linkage.diff.toFixed(2) }}元
          </span>
        </div>
      </div>
    </el-card>

    <!-- TB回写 -->
    <div v-if="!isReadonly" class="writeback-area">
      <el-button type="primary" @click="handleWriteback" :loading="writebackLoading">
        审定数回写TB（2205租赁负债 + 未确认融资费用）
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
        <li>租赁负债为贷方科目（负债类），期末=期初+贷方-借方</li>
        <li>未确认融资费用为借方科目（负债备抵类），期末=期初+借方-贷方</li>
        <li>净额=租赁负债原值-未确认融资费用</li>
        <li>CAS21联动：H9初始确认≈H8初始计量-直接费用+激励（±1元容差）</li>
        <li>审定数=未审数+AJE+RJE</li>
        <li>回写TB后自动发布 substantive:adjudicated 事件</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabAdjudication.vue — H9-1 审定表（负债类双区块+H8联动校验+TB回写）
 *
 * 三段结构：
 * 一、租赁负债原值（贷方/负债类，期末=期初+贷方-借方）
 * 二、未确认融资费用（借方/负债备抵类，期末=期初+借方-贷方）
 * 三、租赁负债净额（原值-未确认融资费用）
 *
 * + H8-H9 联动校验区（CAS21：H9初始≈H8初始-直接费用+激励，±1元容差）
 * + TB回写（2205+未确认融资费用）
 * + 审计说明/结论
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 4.2
 * Requirements: 2.1-2.8, 8.1-8.4
 */
import { ref, toRef, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useH9Adjudication, type H9AdjudicationRow } from '../../composables/useH9Adjudication'
import { useH9CrossSheet } from '../../composables/useH9CrossSheet'

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
  (e: 'navigate-sheet', sheetName: string): void
}>()

const writebackLoading = ref(false)
const auditNoteLocal = ref('')
const auditConclusionLocal = ref('')

const allResponsesRef = toRef(props, 'allResponses')

const {
  liabilityRows, unearnedRows,
  liabilitySubtotal, unearnedSubtotal, netAudited,
  updateCell, addRow, deleteRow,
  publishAdjudicated, saveNote, saveConclusion,
  auditNote, auditConclusion,
} = useH9Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
  onSave: (itemId, value) => emit('save', itemId, value),
  onWritebackTB: async (liability, unearned) => {
    emit('save', 'H9-1-liability-audited', liability)
    emit('save', 'H9-1-unearned-audited', unearned)
  },
})

const { h9VsH8Linkage } = useH9CrossSheet(allResponsesRef)
const h8Linkage = computed(() => h9VsH8Linkage.value)

// Sync local text refs
watch(auditNote, (v) => { auditNoteLocal.value = v }, { immediate: true })
watch(auditConclusion, (v) => { auditConclusionLocal.value = v }, { immediate: true })

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCellChange(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function handleAddLiabilityRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同类型名称', '新增负债行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：房屋租赁/设备租赁',
  })
  if (value) addRow(value, 'liability')
}

async function handleAddUnearnedRow() {
  const { value } = await ElMessageBox.prompt('请输入融资费用类型名称', '新增未确认融资费用行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：房屋租赁/设备租赁',
  })
  if (value) addRow(value, 'unearned')
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

async function handleWriteback() {
  writebackLoading.value = true
  try {
    // Call TB writeback API for 2205 租赁负债 (贷方/负债类)
    await http.put(`/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '2205',
      audited_amount: liabilitySubtotal.value.audited,
    })
    // Call TB writeback API for 未确认融资费用 (借方/负债备抵类)
    await http.put(`/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '1802',
      audited_amount: unearnedSubtotal.value.audited,
    })
    // Publish adjudicated event (dispatches 'substantive:adjudicated')
    await publishAdjudicated()
    ElMessage.success('审定数已回写TB（2205租赁负债 + 未确认融资费用）')
  } catch {
    ElMessage.warning('审定数回写失败，请手动确认试算表数据')
  } finally {
    writebackLoading.value = false
  }
}

function handleSaveNote() { saveNote(auditNoteLocal.value) }
function handleSaveConclusion() { saveConclusion(auditConclusionLocal.value) }

function getLiabilitySummary({ columns }: { columns: any[]; data: H9AdjudicationRow[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '负债原值合计'
    const s = liabilitySubtotal.value
    const map: Record<number, number> = {
      1: s.beginBalance, 2: s.creditAmount, 3: s.debitAmount,
      4: s.endBalance, 5: s.unadjusted, 6: s.aje, 7: s.rje, 8: s.audited,
    }
    return map[idx] !== undefined ? fmtAmt(map[idx]) : ''
  })
}

function getUnearnedSummary({ columns }: { columns: any[]; data: H9AdjudicationRow[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '融资费用合计'
    const s = unearnedSubtotal.value
    const map: Record<number, number> = {
      1: s.beginBalance, 2: s.debitAmount, 3: s.creditAmount,
      4: s.endBalance, 5: s.unadjusted, 6: s.aje, 7: s.rje, 8: s.audited,
    }
    return map[idx] !== undefined ? fmtAmt(map[idx]) : ''
  })
}
</script>

<style scoped>
.h9-tab-adjudication { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

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

.compile-hint {
  margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary);
  cursor: pointer; padding: 8px 12px; border-radius: 6px; background: #fafafa;
}
.compile-hint summary { font-weight: 600; margin-bottom: 6px; }
.compile-hint ul { padding-left: 18px; margin: 4px 0; line-height: 1.8; }
</style>
