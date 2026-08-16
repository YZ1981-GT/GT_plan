<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * J2TabAdjustment — J2-3 长期应付职工薪酬调整分录汇总表
 *
 * 参照 D4-4 调整分录表范式：编制提示 + 工具栏(新增) + 借贷平衡指示 + 主表(源模板列)
 *  + 审计说明/结论卡片(AI辅助 + GtIndexChip J2-1/A13)。
 * 对齐源模板「调整分录汇总表J2-3」列：调整事项说明/类别/报表项目/科目名称/附注项目/借方调整金额/贷方调整金额/索引/备注。
 * 持久化到 checklist_responses.remark（item_id J2-3-entries/note/conclusion），复用父 GtJ2 的 saveImmediate + allResponses。
 */
import { ref, reactive, computed, inject, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { GenerateWorkpaperAiText } from '../composables/useWorkpaperScaffold'
import GtIndexChip from '../GtIndexChip.vue'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

interface RespItem { item_id: string; conclusion: string | null; remark: string | null }
const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, RespItem>
  isReadonly?: boolean
  saveImmediate?: (items: RespItem[]) => Promise<void> | void
}>()
const isReadonly = computed(() => props.isReadonly ?? false)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')

const KEY = { entries: 'J2-3-entries', note: 'J2-3-note', conclusion: 'J2-3-conclusion' }

interface AdjEntry {
  id: number
  description: string; category: string; reportItem: string
  accountName: string; noteItem: string
  debitAmount: number; creditAmount: number
  indexRef: string; remark: string
}
let seq = 1
const entries = reactive<AdjEntry[]>([])
const CATEGORY_OPTIONS = ['报表调整', '账项调整', '其他']

function n(v: unknown): number { const x = typeof v === 'number' ? v : parseFloat(String(v ?? '')); return Number.isFinite(x) ? x : 0 }
function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const totalDebit = computed(() => entries.reduce((s, e) => s + n(e.debitAmount), 0))
const totalCredit = computed(() => entries.reduce((s, e) => s + n(e.creditAmount), 0))
const isBalanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.01)
const balanceDiff = computed(() => totalDebit.value - totalCredit.value)

// ── 同步到集中登记 ────────────────────────────────────────────────────────────
const { year: auditYear } = useAuditContext()
const {
  centralStatus,
  syncing: centralSyncing,
  syncToCentral,
  refreshStatus,
} = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: auditYear,
  wpId: () => props.wpId,
  wpCode: 'J2',
  itemId: 'J2-3-entries',
  buildLineItems: () => entries.map((e) => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: entries.find((e) => e.description)?.description || 'J2 调整',
    adjustmentType: entries.every((e) => e.category === '报表调整') ? 'rje' : 'aje',
  }),
})
void refreshStatus()

function addEntry() {
  if (isReadonly.value) return
  entries.push({ id: seq++, description: '', category: '账项调整', reportItem: '长期应付职工薪酬', accountName: '', noteItem: '', debitAmount: 0, creditAmount: 0, indexRef: '', remark: '' })
  scheduleSave()
}
function removeEntry(id: number) {
  if (isReadonly.value) return
  const i = entries.findIndex(e => e.id === id)
  if (i >= 0) { entries.splice(i, 1); scheduleSave() }
}

// ── 审计说明 / 结论 ───────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
const aiLoading = ref('')

// ── 加载 / 保存 ───────────────────────────────────────────────────────────────
function load() {
  const raw = props.allResponses?.get(KEY.entries)?.remark
  let loaded: AdjEntry[] | null = null
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) loaded = p } catch { /* ignore */ } }
  if (!loaded && props.htmlData?.adjustments && Array.isArray(props.htmlData.adjustments)) {
    loaded = (props.htmlData.adjustments as Record<string, unknown>[]).map((e, i) => ({
      id: i + 1, description: String(e.description ?? ''), category: String(e.category ?? '账项调整'),
      reportItem: String(e.reportItem ?? '长期应付职工薪酬'), accountName: String(e.accountName ?? ''),
      noteItem: String(e.noteItem ?? ''), debitAmount: n(e.debitAmount), creditAmount: n(e.creditAmount),
      indexRef: String(e.indexRef ?? ''), remark: String(e.remark ?? ''),
    }))
  }
  if (loaded) {
    entries.splice(0, entries.length, ...loaded.map((e, i) => ({ ...e, id: e.id ?? i + 1 })))
    seq = Math.max(0, ...entries.map(e => e.id)) + 1
  }
  const nt = props.allResponses?.get(KEY.note)?.remark; if (nt) auditNote.value = nt
  const cc = props.allResponses?.get(KEY.conclusion)?.remark; if (cc) auditConclusion.value = cc
}

function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  props.saveImmediate([
    { item_id: KEY.entries, conclusion: null, remark: JSON.stringify(entries) },
    { item_id: KEY.note, conclusion: null, remark: auditNote.value },
    { item_id: KEY.conclusion, conclusion: null, remark: auditConclusion.value },
  ])
}

// ── AI 辅助 ───────────────────────────────────────────────────────────────────
async function aiGen(target: 'note' | 'conclusion') {
  if (isReadonly.value) return
  aiLoading.value = target
  try {
    const ctx = entries.map(e => `${e.description || '调整'}: ${e.accountName} 借${fmt(e.debitAmount)}/贷${fmt(e.creditAmount)} [${e.category}]`).join('；') || '（暂无调整分录）'
    const context: Record<string, string> = {
      科目: '2221 长期应付职工薪酬 / 设定受益计划净资产调整分录汇总表（J2-3）',
      调整分录: ctx,
      借方合计: fmt(totalDebit.value),
      贷方合计: fmt(totalCredit.value),
      借贷平衡: isBalanced.value ? '平衡' : `不平衡差异${fmt(balanceDiff.value)}`,
    }
    const existing = target === 'note' ? auditNote.value : auditConclusion.value
    const text = await generateAiText({ section: `j2-3-${target}`, context, existingContent: existing })
    if (!text) ElMessage.warning('AI 未生成内容，请稍后重试')
    else { if (target === 'note') auditNote.value = text; else auditConclusion.value = text; scheduleSave() }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j2-tab-adjustment">
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：汇总设定受益计划相关的审计调整分录（AJE/RJE），核验调整依据、借贷科目与金额的准确性及借贷平衡，确保调整正确传导至审定表（J2-1）与报表。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="doc-title">长期应付职工薪酬调整分录汇总表</h3>
      <GtIndexChip value="wp:J2-1" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ entries.length }} 笔</el-tag>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 汇总本底稿形成的审计调整分录，区分"报表调整"(RJE，仅影响报表列报的重分类)与"账项调整"(AJE，涉及科目余额)。</p>
        <p>2. 每笔调整须借贷平衡（借方合计=贷方合计），不平衡时无法确认。</p>
        <p>3. 注明调整事项说明、报表项目、科目名称、附注项目及索引来源。</p>
        <p>4. 调整后金额传导至审定表（J2-1）审定数列，并回写试算平衡表科目 2221；可推送至 A13 错报汇总表。</p>
        <p>5. 【注：本底稿适用于调整分录较多、较复杂的项目，且仅列示与本报表项目相关的审计调整。项目组可根据项目实际情况选择是否使用该底稿。】</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addEntry">+ 新增调整分录</el-button>
      </div>
      <div class="toolbar-right">
        <span class="balance-item">借方合计：<strong>{{ fmt(totalDebit) }}</strong></span>
        <span class="balance-item">贷方合计：<strong>{{ fmt(totalCredit) }}</strong></span>
        <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
        <el-tag v-else type="danger" size="small">不平衡 差异{{ fmt(balanceDiff) }}</el-tag>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || entries.length === 0"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
          @click="syncToCentral"
        >
          同步到集中登记
        </el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >
          集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
        </el-tag>
      </div>
    </div>

    <!-- 主表 -->
    <el-table :data="entries" border size="small" class="wp-table" style="width: 100%">
      <el-table-column type="index" label="序号" width="56" align="center" />
      <el-table-column label="调整事项说明" min-width="200">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="调整事项说明" @change="scheduleSave" />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="120">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.category" size="small" @change="scheduleSave">
            <el-option v-for="o in CATEGORY_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.reportItem" size="small" @change="scheduleSave" />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.accountName" size="small" placeholder="如 2221-设定受益计划" @change="scheduleSave" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.noteItem" size="small" @change="scheduleSave" />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="130" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" v-model="row.debitAmount" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方调整金额" width="130" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" v-model="row.creditAmount" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="90" align="center">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="scheduleSave" />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="scheduleSave" />
          <span v-else>{{ row.remark || '' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
        <template #default="{ row }"><el-button type="danger" link size="small" @click="removeEntry(row.id)">删</el-button></template>
      </el-table-column>
      <template #empty><span class="empty-hint">暂无调整分录。点击"新增调整分录"添加与本报表项目相关的审计调整。</span></template>
    </el-table>

    <!-- 审计说明与结论卡片 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:J2-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:A13" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <el-button size="small" type="primary" plain :loading="aiLoading === 'note'" :disabled="isReadonly" @click="aiGen('note')">🤖 AI辅助</el-button>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          placeholder="请输入审计说明（汇总设定受益计划相关调整事项的原因与影响）..." @change="scheduleSave" />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <el-button size="small" type="primary" plain :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="aiGen('conclusion')">🤖 AI辅助</el-button>
        </div>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
          placeholder="请输入审计结论..." @change="scheduleSave" />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.j2-tab-adjustment { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.doc-title { font-size: 15px; font-weight: 600; margin: 0; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; }
.toolbar-right { display: flex; gap: 12px; align-items: center; font-size: 13px; color: #606266; }
.balance-item strong { color: #303133; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.wp-table :deep(.el-input-number) { width: 100%; }
.wp-table :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
.empty-hint { font-size: 12px; color: #909399; }
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
