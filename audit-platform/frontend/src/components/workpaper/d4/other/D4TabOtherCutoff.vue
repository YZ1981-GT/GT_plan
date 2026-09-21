<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabOtherCutoff — D4-36 其他业务收入截止性测试
 *
 * 双向截止测试合一组件：
 * (一)账到单据：记账凭证→发货单，凭证日期≤截止且发货日期>截止 = 跨期×
 * (二)单据到账：发货单→记账凭证，发货日期≤截止且凭证日期>截止 = 跨期×
 * 截止日期可配 + 自动跨期判断 + AI + 双模式 + 导入导出
 * 预留cutoff-test-auto-sampling对接接口
 */
import { ref, computed, inject, watch, onBeforeUnmount, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import { isCrossPeriodForward, isCrossPeriodBackward, calcCrossPeriodDays } from '../../composables/useD4FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'
import { useD4InspectionWriteback } from '../../composables/useD4InspectionWriteback'
import { d4_36Candidates, D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME } from '../../composables/d4OtherGroupPushPredicates'
import { eventBus } from '@/utils/eventBus'
// D4-36 双向回写：统一走 useD4SyncMode（dedicated sync sheet，sheetKey=d436-managed，
// 同 entry gt-d4-operating-revenue；后端 phase5_d4_other_cutoff_sheet 作为 sibling sheet
// 并入 phase5_d4_revenue_detail，adapter d4.revenue_detail）——与 D4-34 同架构（双区 dict store）。
import GtEntrySyncCapabilityNotice from '../../sync/GtEntrySyncCapabilityNotice.vue'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import { useD4SyncMode, D4_SYNC_ENTRY_ID } from '../composables/useD4SyncMode'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Types ───────────────────────────────────────────────────────────
interface CutoffRow {
  id: string
  voucherDate: string; voucherNo: string; voucherProduct: string; voucherQty: string; voucherAmount: number | string
  docDate: string; docNo: string; docProduct: string; docQty: string; docAmount: number | string
  isCrossing: string  // √(正常) / ×(跨期)
}

const cutoffDate = ref('202X-12-31')
const daysBefore = ref(0)
const daysAfter = ref(0)
const amountThreshold = ref(0)
const forwardRows = ref<CutoffRow[]>([])  // 账到单据
const backwardRows = ref<CutoffRow[]>([]) // 单据到账
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(): CutoffRow { return { id: `ct-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, voucherDate: '', voucherNo: '', voucherProduct: '', voucherQty: '', voucherAmount: '', docDate: '', docNo: '', docProduct: '', docQty: '', docAmount: '', isCrossing: '' } }

// 自动判断跨期 —— 走引擎方向化纯函数（forward/backward 语义相反，单一真源）
function autoJudgeForward(row: CutoffRow) {
  // 账到单据：凭证在截止日或之前 且 单据在截止日之后 → 跨期×
  if (!row.voucherDate || !row.docDate || cutoffDate.value.startsWith('202X')) return
  row.isCrossing = isCrossPeriodForward(row.voucherDate, row.docDate, cutoffDate.value) ? '×' : '√'
}
function autoJudgeBackward(row: CutoffRow) {
  // 单据到账：单据在截止日或之前 且 凭证在截止日之后 → 跨期×
  if (!row.voucherDate || !row.docDate || cutoffDate.value.startsWith('202X')) return
  row.isCrossing = isCrossPeriodBackward(row.docDate, row.voucherDate, cutoffDate.value) ? '×' : '√'
}

function loadData() {
  const r = props.allResponses.get('D4-36-data')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (p) { forwardRows.value = p.forward || []; backwardRows.value = p.backward || []; cutoffDate.value = p.cutoffDate || '202X-12-31'; daysBefore.value = p.daysBefore || 0; daysAfter.value = p.daysAfter || 0; amountThreshold.value = p.amountThreshold || 0; return } } catch {} }
  forwardRows.value = []; backwardRows.value = []
}
function loadNote() { auditNote.value = props.allResponses.get('D4-36-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-36-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-36-data')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-36-note')?.remark, loadNote, { immediate: true })

function addForward() { if (props.isReadonly) return; forwardRows.value.push(createRow()); persistAll() }
function addBackward() { if (props.isReadonly) return; backwardRows.value.push(createRow()); persistAll() }
function removeForward(id: string) { if (props.isReadonly) return; forwardRows.value = forwardRows.value.filter(r => r.id !== id); persistAll() }
function removeBackward(id: string) { if (props.isReadonly) return; backwardRows.value = backwardRows.value.filter(r => r.id !== id); persistAll() }

function updateForward(id: string, field: keyof CutoffRow, value: any) { if (props.isReadonly) return; const row = forwardRows.value.find(r => r.id === id); if (!row) return; (row as any)[field] = value; autoJudgeForward(row); persistAll() }
function updateBackward(id: string, field: keyof CutoffRow, value: any) { if (props.isReadonly) return; const row = backwardRows.value.find(r => r.id === id); if (!row) return; (row as any)[field] = value; autoJudgeBackward(row); persistAll() }
function updateCutoffDate(v: string) { if (props.isReadonly) return; cutoffDate.value = v; forwardRows.value.forEach(r => autoJudgeForward(r)); backwardRows.value.forEach(r => autoJudgeBackward(r)); persistAll() }

// Stats
const forwardCrossingCount = computed(() => forwardRows.value.filter(r => r.isCrossing === '×').length)
const backwardCrossingCount = computed(() => backwardRows.value.filter(r => r.isCrossing === '×').length)

function persistAll() {
  props.allResponses.set('D4-36-data', { item_id: 'D4-36-data', conclusion: null, remark: JSON.stringify({ forward: forwardRows.value, backward: backwardRows.value, cutoffDate: cutoffDate.value, daysBefore: daysBefore.value, daysAfter: daysAfter.value, amountThreshold: amountThreshold.value }) })
  props.allResponses.set('D4-36-note', { item_id: 'D4-36-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-36-conclusion', { item_id: 'D4-36-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-36-data','D4-36-note','D4-36-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
// 同步 flush：立即派发待存改动（清 debounce），供 bridge.flushHtml 在 readStoreProjection 前落库。
function flushPendingSave() {
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
  const keys = ['D4-36-data','D4-36-note','D4-36-conclusion']
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushPendingSave() } })

// ─── D4-36 sync bridge（统一走 useD4SyncMode，见其文件头注释） ─────────
const { syncBridge, descriptor: syncOoDescriptor, editorMode, modeOptions, syncStateTag } = useD4SyncMode({
  sheetKey: 'd436-managed',
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  isReadonly: toRef(props, 'isReadonly'),
  views: ['表格视图'],
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_SYNC_ENTRY_ID })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: 'd436-managed' }
  },
  reloadHtml: async () => { if (reloadWorkpaperData) await reloadWorkpaperData() },
})
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于其他业务收入截止性测试(D4-36)结果生成审计说明', forwardCount: forwardRows.value.length, backwardCount: backwardRows.value.length, forwardCrossing: forwardCrossingCount.value, backwardCrossing: backwardCrossingCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于截止性测试结果生成审计结论', noteText: auditNote.value, forwardCrossing: forwardCrossingCount.value, backwardCrossing: backwardCrossingCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function rowClass({ row }: { row: CutoffRow }) { return row.isCrossing === '×' ? 'row-crossing' : '' }

// ─── A13 错报推送（科目 6051；forward 取 docAmount / backward 取 voucherAmount；带方向+跨期天数）──
const { pushToA13 } = useD4InspectionWriteback({
  wpCode: 'D4-36',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
// 给判据补跨期天数（凭证↔单据日期绝对天数，走引擎）
function withDays(rows: CutoffRow[]) {
  return rows.map(r => ({
    voucherNo: r.voucherNo, voucherAmount: r.voucherAmount,
    docNo: r.docNo, docAmount: r.docAmount, isCrossing: r.isCrossing,
    crossPeriodDays: (r.voucherDate && r.docDate) ? calcCrossPeriodDays(r.voucherDate, r.docDate) : undefined,
  }))
}
const pushableCount = computed(
  () => d4_36Candidates(withDays(forwardRows.value) as any, withDays(backwardRows.value) as any).length,
)
function pushCrossPeriodToA13() {
  if (props.isReadonly) return
  const cands = d4_36Candidates(withDays(forwardRows.value) as any, withDays(backwardRows.value) as any)
  if (!cands.length) { ElMessage.info('无跨期疑点，无需推送'); return }
  const items = cands.map(c => ({
    voucherNo: c.voucherNo,
    amount: c.refAmount ?? 0, // 取证金额是参考，人工认定
    description: c.description,
    indexRef: c.indexRef,
  }))
  pushToA13(items, D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME)
}

// ─── 公式管理（打开平台全局公式管理中心，定位到本底稿 D4-36；同 E1 范式）───────────
// 平台唯一一套公式：wp_formula 表权威存储，后端权威执行 + CAS + 审计；
// 支持跨底稿 TB()/WP()/ROW() 取数联动与表内 SUM_ROW()/IF() 运算校对。
function openFormulaManager() {
  eventBus.emit('open-formula-manager', { nodeKey: 'wp_d4_36' })
}
</script>

<template>
<div class="d4-other-cutoff">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-button size="small" type="warning" plain :disabled="isReadonly||pushableCount===0" @click="pushCrossPeriodToA13" title="把跨期疑点推送到 A13 未更正错报汇总（方向+跨期天数，人工认定金额）">推送跨期至 A13{{ pushableCount ? `（${pushableCount}）` : '' }}</el-button><el-button size="small" @click="openFormulaManager" title="打开平台公式管理中心（唯一一套公式，支持跨底稿取数联动与表内校对）">ƒx 公式管理</el-button><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu>
    <el-dropdown-item disabled class="dropdown-group-label">— (一)账到单据 —</el-dropdown-item>
    <el-dropdown-item @click="exportTemplate('D4-36-forward')">导出模板</el-dropdown-item>
    <el-dropdown-item @click="exportData('D4-36-forward')">导出数据</el-dropdown-item>
    <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-36-forward',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item>
    <el-dropdown-item disabled class="dropdown-group-label">— (二)单据到账 —</el-dropdown-item>
    <el-dropdown-item @click="exportTemplate('D4-36-backward')">导出模板</el-dropdown-item>
    <el-dropdown-item @click="exportData('D4-36-backward')">导出数据</el-dropdown-item>
    <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-36-backward',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item>
  </el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-36" :context-project-id="projectId" /><el-tag :type="syncStateTag.type" size="small" class="sync-state-tag">{{ syncStateTag.text }}</el-tag><GtEntrySyncCapabilityNotice entry-id="xlsx/gt-d4-operating-revenue" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-36-cutoff')">💬 复核</el-button></div></div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 截止日期配置 + 抽样参数 -->
    <div class="cutoff-config">
      <div class="config-row">
        <span class="config-label">截止日期：</span>
        <el-input :model-value="cutoffDate" size="small" style="width:140px" :disabled="isReadonly" placeholder="YYYY-MM-DD" @input="(v:string)=>updateCutoffDate(v)" />
      </div>
      <div class="config-row">
        <span class="config-label">抽样范围：</span>
        <span class="config-text">报表日前</span>
        <el-input-number :model-value="daysBefore" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:60px" @change="(v:any)=>{daysBefore=v??0;persistAll()}" />
        <span class="config-text">天、后</span>
        <el-input-number :model-value="daysAfter" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:60px" @change="(v:any)=>{daysAfter=v??0;persistAll()}" />
        <span class="config-text">天，且金额大于</span>
        <el-input-number :model-value="amountThreshold" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100px" @change="(v:any)=>{amountThreshold=v??0;persistAll()}" />
        <span class="config-text">元</span>
      </div>
      <div class="config-hint">（凭证日期/发货日期与截止日期比较判断跨期；抽样范围用于后续从序时账自动提取样本）</div>
    </div>

    <!-- 统计横幅 -->
    <div class="stats-bar">
      <span class="stat-item">账到单据：<strong>{{ forwardRows.length }}笔</strong></span>
      <span class="stat-item" :class="{ warn: forwardCrossingCount > 0 }">跨期：<strong>{{ forwardCrossingCount }}笔</strong></span>
      <span class="stat-item">单据到账：<strong>{{ backwardRows.length }}笔</strong></span>
      <span class="stat-item" :class="{ warn: backwardCrossingCount > 0 }">跨期：<strong>{{ backwardCrossingCount }}笔</strong></span>
    </div>

    <!-- ═══ (一) 账到单据 ═══ -->
    <div class="block-section forward-block">
      <div class="block-header"><span class="block-title">（一）账到单据</span><span class="block-hint">记账凭证 → 发货单/验收单/出库单</span><el-button size="small" :disabled="isReadonly" @click="addForward"><el-icon :size="12"><Plus /></el-icon> 添加</el-button></div>
      <el-table :data="forwardRows" border stripe size="small" class="cutoff-table" :row-class-name="rowClass">
        <el-table-column label="记账凭证" align="center" class-name="col-voucher">
          <el-table-column label="日期" min-width="90"><template #default="{ row }"><el-input v-model="row.voucherDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateForward(row.id,'voucherDate',row.voucherDate)" /></template></el-table-column>
          <el-table-column label="编号" min-width="80"><template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="updateForward(row.id,'voucherNo',row.voucherNo)" /></template></el-table-column>
          <el-table-column label="品名" min-width="80"><template #default="{ row }"><el-input v-model="row.voucherProduct" size="small" :disabled="isReadonly" @change="updateForward(row.id,'voucherProduct',row.voucherProduct)" /></template></el-table-column>
          <el-table-column label="数量" width="60"><template #default="{ row }"><el-input v-model="row.voucherQty" size="small" :disabled="isReadonly" @change="updateForward(row.id,'voucherQty',row.voucherQty)" /></template></el-table-column>
          <el-table-column label="金额" min-width="90" align="right"><template #default="{ row }"><WpAmountInput v-model="row.voucherAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateForward(row.id,'voucherAmount',row.voucherAmount)" /></template></el-table-column>
        </el-table-column>
        <el-table-column label="发货单（或验收单、出库单等）" align="center" class-name="col-doc">
          <el-table-column label="日期" min-width="90"><template #default="{ row }"><el-input v-model="row.docDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateForward(row.id,'docDate',row.docDate)" /></template></el-table-column>
          <el-table-column label="编号" min-width="80"><template #default="{ row }"><el-input v-model="row.docNo" size="small" :disabled="isReadonly" @change="updateForward(row.id,'docNo',row.docNo)" /></template></el-table-column>
          <el-table-column label="品名" min-width="80"><template #default="{ row }"><el-input v-model="row.docProduct" size="small" :disabled="isReadonly" @change="updateForward(row.id,'docProduct',row.docProduct)" /></template></el-table-column>
          <el-table-column label="数量" width="60"><template #default="{ row }"><el-input v-model="row.docQty" size="small" :disabled="isReadonly" @change="updateForward(row.id,'docQty',row.docQty)" /></template></el-table-column>
          <el-table-column label="金额" min-width="90" align="right"><template #default="{ row }"><WpAmountInput v-model="row.docAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateForward(row.id,'docAmount',row.docAmount)" /></template></el-table-column>
        </el-table-column>
        <el-table-column label="是否跨期" width="65" align="center"><template #default="{ row }"><span :class="['crossing-badge', row.isCrossing==='×'?'crossing-bad':'crossing-ok']">{{ row.isCrossing || '—' }}</span></template></el-table-column>
        <el-table-column width="35" align="center"><template #default="{ row }"><el-popconfirm title="删除？" @confirm="removeForward(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">×</el-button></template></el-popconfirm></template></el-table-column>
      </el-table>
      <div class="cutoff-date-line">截止日期：{{ cutoffDate }}</div>
    </div>

    <!-- ═══ (二) 单据到账 ═══ -->
    <div class="block-section backward-block">
      <div class="block-header"><span class="block-title">（二）单据到账</span><span class="block-hint">发货单/验收单/出库单 → 记账凭证</span><el-button size="small" :disabled="isReadonly" @click="addBackward"><el-icon :size="12"><Plus /></el-icon> 添加</el-button></div>
      <el-table :data="backwardRows" border stripe size="small" class="cutoff-table" :row-class-name="rowClass">
        <el-table-column label="发货单（或验收单、出库单等）" align="center" class-name="col-doc">
          <el-table-column label="日期" min-width="90"><template #default="{ row }"><el-input v-model="row.docDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateBackward(row.id,'docDate',row.docDate)" /></template></el-table-column>
          <el-table-column label="编号" min-width="80"><template #default="{ row }"><el-input v-model="row.docNo" size="small" :disabled="isReadonly" @change="updateBackward(row.id,'docNo',row.docNo)" /></template></el-table-column>
          <el-table-column label="品名" min-width="80"><template #default="{ row }"><el-input v-model="row.docProduct" size="small" :disabled="isReadonly" @change="updateBackward(row.id,'docProduct',row.docProduct)" /></template></el-table-column>
          <el-table-column label="数量" width="60"><template #default="{ row }"><el-input v-model="row.docQty" size="small" :disabled="isReadonly" @change="updateBackward(row.id,'docQty',row.docQty)" /></template></el-table-column>
          <el-table-column label="金额" min-width="90" align="right"><template #default="{ row }"><WpAmountInput v-model="row.docAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateBackward(row.id,'docAmount',row.docAmount)" /></template></el-table-column>
        </el-table-column>
        <el-table-column label="记账凭证" align="center" class-name="col-voucher">
          <el-table-column label="日期" min-width="90"><template #default="{ row }"><el-input v-model="row.voucherDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateBackward(row.id,'voucherDate',row.voucherDate)" /></template></el-table-column>
          <el-table-column label="编号" min-width="80"><template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="updateBackward(row.id,'voucherNo',row.voucherNo)" /></template></el-table-column>
          <el-table-column label="品名" min-width="80"><template #default="{ row }"><el-input v-model="row.voucherProduct" size="small" :disabled="isReadonly" @change="updateBackward(row.id,'voucherProduct',row.voucherProduct)" /></template></el-table-column>
          <el-table-column label="数量" width="60"><template #default="{ row }"><el-input v-model="row.voucherQty" size="small" :disabled="isReadonly" @change="updateBackward(row.id,'voucherQty',row.voucherQty)" /></template></el-table-column>
          <el-table-column label="金额" min-width="90" align="right"><template #default="{ row }"><WpAmountInput v-model="row.voucherAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateBackward(row.id,'voucherAmount',row.voucherAmount)" /></template></el-table-column>
        </el-table-column>
        <el-table-column label="是否跨期" width="65" align="center"><template #default="{ row }"><span :class="['crossing-badge', row.isCrossing==='×'?'crossing-bad':'crossing-ok']">{{ row.isCrossing || '—' }}</span></template></el-table-column>
        <el-table-column width="35" align="center"><template #default="{ row }"><el-popconfirm title="删除？" @confirm="removeBackward(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">×</el-button></template></el-popconfirm></template></el-table-column>
      </el-table>
      <div class="cutoff-date-line">截止日期：{{ cutoffDate }}</div>
    </div>

    <!-- 红字提示 -->
    <details class="tips-collapse"><summary class="tips-summary">⚠️ 截止测试提示</summary><ol class="tips-list">
      <li>本表适用于对"以发货单为确认收入时点"的被审计单位的截止测试，项目组在使用模板时，请根据企业的收入确认政策做出调整。</li>
      <li>如果存在跨期嫌疑风险较高或前所检查样本中发现有跨期的，应扩大测试期间和样本，甚至可以考虑将截止测试期间延长至审计报告日。同时考虑是否存在内控缺陷。</li>
    </ol></details>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录截止测试中发现的跨期情况" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断其他业务收入截止是否正确" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <!-- 在线编辑：平台 sync bridge（dedicated sync sheet，非裸 GtOnlyOfficeSheet） -->
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor="syncOoDescriptor" :bridge="syncBridge" /><div v-else class="oo-loading">正在打开 D4-36 同步编辑器…</div></div></template>
</div>
</template>

<style scoped>
.d4-other-cutoff{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
:deep(.dropdown-group-label) { font-size: 12px; color: #909399; cursor: default; }
.cutoff-config{display:flex;flex-direction:column;gap:8px;margin-bottom:12px;padding:10px 14px;background:#fdf6ec;border-radius:6px;border:1px solid #faecd8}.config-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.config-label{font-size: var(--wp-font-size, 13px);font-weight:500;color:#e6a23c;min-width:70px}.config-text{font-size:12px;color:#606266}.config-hint{font-size:11px;color:#909399;margin-top:2px}
.stats-bar{display:flex;gap:20px;margin-bottom:16px;padding:8px 14px;background:linear-gradient(135deg,#f8f9fe,#f0f4ff);border-radius:6px;border:1px solid #e4e7ed;font-size: var(--wp-font-size, 13px);color:#606266}.stat-item strong{color:#303133;margin-left:4px}.stat-item.warn{color:#f56c6c}.stat-item.warn strong{color:#f56c6c}
.block-section{margin-bottom:20px;border:1px solid #ebeef5;border-radius:8px;padding:14px 16px}
.forward-block{border-left:3px solid #409eff}
.backward-block{border-left:3px solid #67c23a}
.block-header{display:flex;align-items:center;gap:12px;margin-bottom:10px}.block-title{font-size:14px;font-weight:600;color:#303133}.block-hint{font-size:12px;color:#909399}
.cutoff-table{font-size: var(--wp-font-size, 13px)}.cutoff-table :deep(.el-table__cell){padding:5px 4px}.cutoff-table :deep(.col-voucher .el-table__cell){background-color:#f0f5ff !important}.cutoff-table :deep(.col-doc .el-table__cell){background-color:#f0faf0 !important}.cutoff-table :deep(.row-crossing td){background-color:#fef0f0 !important}
.cutoff-date-line{margin-top:8px;text-align:center;font-size:12px;color:#909399;padding:4px;border-top:1px dashed #e4e7ed}
.crossing-badge{font-weight:700;font-size:14px}.crossing-ok{color:#67c23a}.crossing-bad{color:#f56c6c}
.tips-collapse{margin-bottom:16px;border-radius:6px;border:1px solid #fde2e2;border-left:3px solid #f56c6c;background:#fef0f0}.tips-summary{cursor:pointer;padding:8px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#f56c6c}.tips-list{margin:8px 14px 12px;padding-left:18px;font-size:12px;color:#606266;line-height:2}
.audit-opinion-card{margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
