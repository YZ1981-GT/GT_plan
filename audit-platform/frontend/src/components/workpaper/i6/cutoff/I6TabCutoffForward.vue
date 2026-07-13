<template>
  <div class="i6-cutoff-forward">
    <div class="section-header">
      <span class="section-title">I6-5 截止测试（账簿→单据）</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：从账簿记录出发核对研发费用原始单据日期（期末±5天），验证研发费用（6602）是否记录在正确会计期间，识别跨期交易。"
      class="objective-alert"
    />

    <div class="methodology-context">
      <p>正向截止测试：从账簿记录出发，核对原始单据日期（期末±5天）。验证研发费用是否记录在正确的会计期间。跨期交易以红色高亮标记。</p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I6-5" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>
    <div class="stats-card">
      <div class="stat-item"><span class="stat-label">样本总数</span><span class="stat-value">{{ rows.length }}</span></div>
      <div class="stat-item"><span class="stat-label">跨期笔数</span><span class="stat-value stat-danger">{{ crossCount }}</span></div>
      <div class="stat-item"><span class="stat-label">跨期金额</span><span class="stat-value stat-danger">{{ fmtAmount(crossAmount) }}</span></div>
    </div>

    <el-table :data="rows" border size="small" class="cutoff-table" max-height="460" :row-class-name="rowClassName">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="amount" label="金额" min-width="110" align="right">
        <template #default="{ row, $index }"><el-input-number v-if="!isReadonly" v-model="row.amount" size="small" :controls="false" @change="onRowChange($index)" /><span v-else>{{ fmtAmount(row.amount) }}</span></template>
      </el-table-column>
      <el-table-column prop="expenseType" label="费用类型" min-width="100">
        <template #default="{ row, $index }"><el-input v-if="!isReadonly" v-model="row.expenseType" size="small" @change="onRowChange($index)" /><span v-else>{{ row.expenseType }}</span></template>
      </el-table-column>
      <el-table-column prop="recordDate" label="记账日期" min-width="130">
        <template #default="{ row, $index }"><el-date-picker v-if="!isReadonly" v-model="row.recordDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="onRowChange($index)" /><span v-else>{{ row.recordDate }}</span></template>
      </el-table-column>
      <el-table-column prop="documentDate" label="单据日期" min-width="130">
        <template #default="{ row, $index }"><el-date-picker v-if="!isReadonly" v-model="row.documentDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="onRowChange($index)" /><span v-else>{{ row.documentDate }}</span></template>
      </el-table-column>
      <el-table-column prop="recordPeriod" label="记账期间" min-width="90">
        <template #default="{ row, $index }"><el-input v-if="!isReadonly" v-model="row.recordPeriod" size="small" @change="onRowChange($index)" /><span v-else>{{ row.recordPeriod }}</span></template>
      </el-table-column>
      <el-table-column prop="belongPeriod" label="归属期间" min-width="90">
        <template #default="{ row, $index }"><el-input v-if="!isReadonly" v-model="row.belongPeriod" size="small" @change="onRowChange($index)" /><span v-else>{{ row.belongPeriod }}</span></template>
      </el-table-column>
      <el-table-column label="是否跨期" width="85" align="center">
        <template #default="{ row }"><el-tag :type="row.isCrossPeriod ? 'danger' : 'success'" size="small">{{ row.isCrossPeriod ? '跨期' : '正常' }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="conclusion" label="结论" min-width="80">
        <template #default="{ row, $index }"><el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="onRowChange($index)" /><span v-else>{{ row.conclusion || '-' }}</span></template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="55" fixed="right" align="center">
        <template #default="{ $index }"><el-button size="small" type="danger" text @click="removeRow($index)">删</el-button></template>
      </el-table-column>
    </el-table>

    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="addRow">+ 新增</el-button>
      <el-button size="small" type="warning" plain @click="handleAutoSampling">一键从序时账提取样本</el-button>
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="summary-card audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="请填写审计说明（正向截止测试样本选取、跨期交易分析等）..." @blur="onAuditNoteBlur" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="summary-card audit-note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="请填写审计结论（研发费用截止正确，无重大跨期错报）..." @blur="onAuditConclusionBlur" />
    </el-card>

    <details class="guidance-details compile-hint"><summary>编制提示</summary><ul>
      <li>正向截止：从账簿出发核对单据日期</li>
      <li>跨期判定：记账期间≠归属期间则为跨期</li>
      <li>"一键提取"自动从序时账±5天采样</li>
      <li>跨期行红色高亮</li>
    </ul></details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ 'save': [itemId: string, value: any] }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

interface CutoffRow { rowId: string; amount: number; expenseType: string; recordDate: string; documentDate: string; recordPeriod: string; belongPeriod: string; isCrossPeriod: boolean; conclusion: string }

const ITEM_ID = 'I6-5-rows'
const NOTE_KEY = 'I6-5-audit-note'
const CONCLUSION_KEY = 'I6-5-audit-conclusion'
const rows = ref<CutoffRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

const crossCount = computed(() => rows.value.filter((r) => r.isCrossPeriod).length)
const crossAmount = computed(() => rows.value.filter((r) => r.isCrossPeriod).reduce((s, r) => s + (r.amount || 0), 0))

function _load(): void {
  auditNote.value = _str(NOTE_KEY)
  auditConclusion.value = _str(CONCLUSION_KEY)
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? (typeof item === 'string' ? item : null)
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) { rows.value = p; _recalcCross(); return } } catch { /* */ } }
  rows.value = []
}
function _str(id: string): string { const item = props.allResponses.get(id); return (item?.remark ?? (typeof item === 'string' ? item : '')) as string }
watch(() => props.allResponses, () => _load(), { immediate: true })

function _recalcCross(): void {
  for (const row of rows.value) { row.isCrossPeriod = !!(row.recordPeriod && row.belongPeriod && row.recordPeriod !== row.belongPeriod) }
}
function _persist(): void { emit('save', ITEM_ID, JSON.stringify(rows.value)) }

function addRow(): void {
  rows.value.push({ rowId: `row-${Date.now().toString(36)}`, amount: 0, expenseType: '', recordDate: '', documentDate: '', recordPeriod: '', belongPeriod: '', isCrossPeriod: false, conclusion: '' })
}
function removeRow(idx: number): void { rows.value.splice(idx, 1); _persist() }
function onRowChange(_idx: number): void { _recalcCross(); _persist() }

function handleSave(): void { _persist(); ElMessage.success('正向截止测试已保存') }
function onAuditNoteBlur(): void { if (props.isReadonly) return; emit('save', NOTE_KEY, auditNote.value) }
function onAuditConclusionBlur(): void { if (props.isReadonly) return; emit('save', CONCLUSION_KEY, auditConclusion.value) }

async function handleAutoSampling(): Promise<void> {
  try {
    const res = await http.get(`/api/projects/${props.projectId}/cutoff-sampling`, { params: { direction: 'forward', account_prefix: '6602', days: 5 }, _silent: true } as any)
    const samples = res.data?.data ?? res.data
    if (Array.isArray(samples) && samples.length > 0) {
      rows.value = samples.map((s: any) => ({
        rowId: `row-${Math.random().toString(36).slice(2, 10)}`, amount: Number(s.amount) || 0, expenseType: s.expense_type ?? s.summary ?? '',
        recordDate: s.record_date ?? '', documentDate: s.document_date ?? '', recordPeriod: s.record_period ?? '', belongPeriod: s.belong_period ?? '',
        isCrossPeriod: (s.record_period ?? '') !== (s.belong_period ?? ''), conclusion: '',
      }))
      _persist(); ElMessage.success(`已提取 ${rows.value.length} 条样本`)
    } else { ElMessage.info('未找到符合条件的样本') }
  } catch { ElMessage.warning('自动提取失败，请手工录入') }
}

function handleReview(): void { openReviewDialog('I6-5 截止(账→单据)') }
function rowClassName({ row }: { row: CutoffRow }): string { return row.isCrossPeriod ? 'cross-period-row' : '' }
function fmtAmount(v: number | null | undefined): string { if (v == null || Math.abs(v) < 0.005) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.i6-cutoff-forward { font-size: var(--wp-font-size, 13px); padding: 16px; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.stats-card { display: flex; gap: 24px; padding: 12px 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 14px; }
.stat-item { display: flex; flex-direction: column; align-items: center; }
.stat-label { font-size: 12px; color: #6b7280; }
.stat-value { font-size: 18px; font-weight: 700; color: #1f2937; }
.stat-danger { color: #dc2626; }
.cutoff-table { font-size: var(--wp-font-size, 13px); }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
.summary-card { margin-top: 16px; }
:deep(.cross-period-row) { background-color: #fef2f2 !important; }
:deep(.cross-period-row:hover > td) { background-color: #fee2e2 !important; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
