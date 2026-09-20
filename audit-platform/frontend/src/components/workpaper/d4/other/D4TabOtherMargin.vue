<script setup lang="ts">
/**
 * D4TabOtherMargin — D4-33 其他业务毛利率分析表
 *
 * 固定16行(12月+合计+上年数+变动额+变动比例) × 动态业务类型列(每类3子列:收入/成本/毛利率)
 * 毛利率=(收入-成本)/收入 自动计算；合计=12月之和；变动额=合计-上年；变动比例=变动额/上年
 * 双模式 + AI + 导入导出
 */
import { ref, computed, inject, watch, onBeforeUnmount, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import { parseNum, calcGrossMarginRate, calcSubtotal, calcChangeRate } from '../../composables/useD4FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'
import { useD4InspectionWriteback } from '../../composables/useD4InspectionWriteback'
import { d4_33Candidates, D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME } from '../../composables/d4OtherGroupPushPredicates'
import { eventBus } from '@/utils/eventBus'
// D4-33 双向回写：子组件自管 sync bridge（dedicated sync sheet，sheetKey=d433-managed，
// 同 entry gt-d4-operating-revenue；后端 phase5_d4_other_margin_sheet 作为**静态受管区** sibling
// sheet 并入 phase5_d4_revenue_detail，adapter d4.revenue_detail）——引擎静态 cell 路径
// （spec workpaper-sync-static-cell-sheet-writeback，非 legacy 裸 GtOnlyOfficeSheet）。
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from '../../sync/useWorkpaperSyncBridge'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import { capabilityForEntry } from '../../sync/workpaperSyncCapability'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── 公式管理（打开平台全局公式管理中心，定位到本底稿 D4-33）───────────────────
// 由顶层挂载的全局 FormulaManagerDialog 响应 `open-formula-manager`（同 E1 范式）。
// 平台唯一一套公式：wp_formula 表权威存储，后端权威执行 + CAS + 审计；
// 支持跨底稿 TB()/WP()/ROW() 取数联动与表内 SUM_ROW()/IF() 运算校对。
function openFormulaManager() {
  eventBus.emit('open-formula-manager', { nodeKey: 'wp_d4_33' })
}
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

interface BizType { id: string; name: string }
interface MonthEntry { revenue: number | string; cost: number | string }
interface StoreData { bizTypes: BizType[]; months: Record<string, MonthEntry[]>; priorYear: Record<string, MonthEntry> }

const MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
const store = ref<StoreData>({ bizTypes: [], months: {}, priorYear: {} })
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// 数值解析走引擎单一真源；毛利率 = 引擎 calcGrossMarginRate（小数比率）× 100 展示（DEC-2 百分比口径，*100 仅格式化非改口径）
const pn = parseNum
function fmtMargin(rev: number, cost: number): string { if (!rev) return '—'; return (calcGrossMarginRate(rev, cost) * 100).toFixed(2) + '%' }
function fmtAmt(v: number): string { return v ? v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—' }

// 获取某业务类型某月数据
function getMonth(bizId: string, monthIdx: number): MonthEntry { return store.value.months[bizId]?.[monthIdx] || { revenue: '', cost: '' } }
function getPrior(bizId: string): MonthEntry { return store.value.priorYear[bizId] || { revenue: '', cost: '' } }

// 合计（12月之和）走引擎 calcSubtotal
function getTotal(bizId: string, field: 'revenue' | 'cost'): number {
  const arr = store.value.months[bizId] || []
  return calcSubtotal(arr.map(m => pn(m[field])))
}

function loadData() {
  const r = props.allResponses.get('D4-33-data')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (p?.bizTypes) { store.value = p; return } } catch {} }
  // 默认预填3个业务类型（对齐源模板）
  const defaultTypes: BizType[] = [
    { id: 'biz-rent-fixed', name: '出租固定资产' },
    { id: 'biz-rent-intangible', name: '出租无形资产' },
    { id: 'biz-sell-material', name: '销售材料' },
  ]
  const months: Record<string, MonthEntry[]> = {}
  const priorYear: Record<string, MonthEntry> = {}
  for (const t of defaultTypes) {
    months[t.id] = Array.from({ length: 12 }, () => ({ revenue: '', cost: '' }))
    priorYear[t.id] = { revenue: '', cost: '' }
  }
  store.value = { bizTypes: defaultTypes, months, priorYear }
}
function loadNote() { auditNote.value = props.allResponses.get('D4-33-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-33-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-33-data')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-33-note')?.remark, loadNote, { immediate: true })

async function addBizType() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入业务类型名称', '添加其他业务类型', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' })
    if (value?.trim()) {
      const id = `biz-${Date.now().toString(36)}`
      store.value.bizTypes.push({ id, name: value.trim() })
      store.value.months[id] = Array.from({ length: 12 }, () => ({ revenue: '', cost: '' }))
      store.value.priorYear[id] = { revenue: '', cost: '' }
      persistAll()
    }
  } catch {}
}
function removeBizType(id: string) {
  if (props.isReadonly) return
  store.value.bizTypes = store.value.bizTypes.filter(b => b.id !== id)
  delete store.value.months[id]
  delete store.value.priorYear[id]
  persistAll()
}

function updateMonth(bizId: string, monthIdx: number, field: 'revenue' | 'cost', value: any) {
  if (props.isReadonly) return
  if (!store.value.months[bizId]) store.value.months[bizId] = Array.from({ length: 12 }, () => ({ revenue: '', cost: '' }))
  store.value.months[bizId][monthIdx][field] = value
  persistAll()
}
function updatePrior(bizId: string, field: 'revenue' | 'cost', value: any) {
  if (props.isReadonly) return
  if (!store.value.priorYear[bizId]) store.value.priorYear[bizId] = { revenue: '', cost: '' }
  store.value.priorYear[bizId][field] = value
  persistAll()
}

function persistAll() {
  props.allResponses.set('D4-33-data', { item_id: 'D4-33-data', conclusion: null, remark: JSON.stringify(store.value) })
  props.allResponses.set('D4-33-note', { item_id: 'D4-33-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-33-conclusion', { item_id: 'D4-33-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-33-data','D4-33-note','D4-33-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
// 立即 flush（清 debounce + 同步 dispatch），供 sync bridge 切到在线编辑前把 html 侧落库。
function flushPendingSave() {
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
  const keys = ['D4-33-data', 'D4-33-note', 'D4-33-conclusion']
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } }))
}
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-33-data','D4-33-note','D4-33-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

// ─── 双模式 sync bridge（D4-33 其他业务毛利率，dedicated 静态受管区 sync sheet）──────────
const D4_33_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_33_SHEET_KEY = 'd433-managed'
const modeOptions = ['表格视图', '在线编辑']
const ooHealthy = ref(false)
async function checkOoHealth() {
  try { const r = await http.get('/api/onlyoffice/health', { _silent: true } as any); ooHealthy.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' } catch { ooHealthy.value = false }
}
checkOoHealth()
const syncSwitching = ref(false)
const syncBridge = useWorkpaperSyncBridge({
  entryId: ref(D4_33_ENTRY),
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey: ref(D4_33_SHEET_KEY),
  capability: capabilityForEntry(D4_33_ENTRY),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_33_ENTRY })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_33_SHEET_KEY }
  },
  reloadHtml: async () => { if (reloadWorkpaperData) await reloadWorkpaperData() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(
  () => syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const editorMode = computed<string>({
  get: () => (syncBridge.mode.value === 'oo' ? '在线编辑' : '表格视图'),
  set: (v: string) => { void switchMode(v === '在线编辑' ? 'onlyoffice' : 'structured') },
})
async function switchMode(target: 'structured' | 'onlyoffice'): Promise<void> {
  const cur = syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'structured'
  if (target === cur) return
  if (target === 'onlyoffice') {
    if (props.isReadonly || !ooHealthy.value) return
    syncSwitching.value = true
    try { await syncBridge.switchToOnlyOffice() } finally { syncSwitching.value = false }
    return
  }
  syncSwitching.value = true
  try { await syncBridge.switchToHtml() } finally { syncSwitching.value = false }
}
// fail-visible：同步失败以中文 tag 显式呈现，不静默吞。
const syncStateTag = computed(() => {
  const st = String(syncBridge.state.value)
  if (syncBusy.value) return { text: '同步中…', type: 'info' as const }
  if (syncBridge.dirty?.value) {
    return syncBridge.mode.value === 'oo'
      ? { text: 'excel 侧有未同步改动', type: 'warning' as const }
      : { text: 'html 侧有未同步改动', type: 'warning' as const }
  }
  if (st.includes('error') || String(syncBridge.lastError?.value || '')) {
    return { text: '同步失败，请重试', type: 'danger' as const }
  }
  return { text: syncBridge.mode.value === 'oo' ? 'Excel 在线编辑' : '表格视图', type: 'success' as const }
})
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于其他业务毛利率分析(D4-33)生成审计说明', bizTypeCount: store.value.bizTypes.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于毛利率分析结果生成审计结论', noteText: auditNote.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

// ─── A13 错报推送（科目 6051；毛利率分析=定性项，金额与方向由人工认定，不推 0）──────
const { pushToA13 } = useD4InspectionWriteback({
  wpCode: 'D4-33',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
// 每业务类型的合计毛利率(%) + 同比变动率(%)
function bizStats() {
  return store.value.bizTypes.map(b => {
    const curRev = getTotal(b.id, 'revenue'); const curCost = getTotal(b.id, 'cost')
    const priorRev = pn(getPrior(b.id).revenue); const priorCost = pn(getPrior(b.id).cost)
    const marginPct = calcGrossMarginRate(curRev, curCost) * 100
    const priorMarginPct = calcGrossMarginRate(priorRev, priorCost) * 100
    const cr = calcChangeRate(marginPct, priorMarginPct) // 毛利率同比变动率
    return { name: b.name, marginPct, changeRatePct: (cr === '' || cr === 'N/A') ? null : cr * 100 }
  })
}
const pushableCount = computed(() => d4_33Candidates(bizStats()).length)
async function pushMarginAnomaliesToA13() {
  if (props.isReadonly) return
  const cands = d4_33Candidates(bizStats())
  if (!cands.length) { ElMessage.info('无毛利率异常，无需推送'); return }
  // 定性项：逐条由人工认定错报金额（不自动推 amount:0）
  const items: { amount: number; description: string; indexRef: string }[] = []
  for (const c of cands) {
    try {
      const { value } = await ElMessageBox.prompt(
        `${c.description}\n\n请认定该项对应的错报金额（元）；如仅为定性关注、暂无法量化，请填 0 并在 A13 说明。`,
        'A13 错报金额认定', { confirmButtonText: '确认', cancelButtonText: '跳过此项', inputValue: '' },
      )
      items.push({ amount: parseNum(value), description: c.description, indexRef: c.indexRef })
    } catch { /* 跳过此项 */ }
  }
  if (!items.length) { ElMessage.info('未认定任何金额，已取消推送'); return }
  pushToA13(items, D4_OTHER_ACCOUNT_CODE, D4_OTHER_ACCOUNT_NAME)
}
</script>

<template>
<div class="d4-other-margin">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-button size="small" type="warning" plain :disabled="isReadonly||pushableCount===0" @click="pushMarginAnomaliesToA13" title="把毛利率异常推送到 A13（定性项，金额由人工逐条认定）">推送异常至 A13{{ pushableCount ? `（${pushableCount}）` : '' }}</el-button><el-button size="small" @click="openFormulaManager" title="打开平台公式管理中心（唯一一套公式，支持跨底稿取数联动与表内校对）">ƒx 公式管理</el-button><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-33')">导出模板</el-dropdown-item><el-dropdown-item @click="exportData('D4-33')">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-33',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-3" :context-project-id="projectId" /><el-tag :type="syncStateTag.type" size="small" class="sync-state-tag">{{ syncStateTag.text }}</el-tag><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-33-margin')">💬 复核</el-button></div></div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 业务类型管理 -->
    <div class="biz-management">
      <span class="biz-label">业务类型：</span>
      <el-tag v-for="biz in store.bizTypes" :key="biz.id" closable :disable-transitions="false" :disabled="isReadonly" @close="removeBizType(biz.id)" size="default" type="info">{{ biz.name }}</el-tag>
      <el-button size="small" :disabled="isReadonly" @click="addBizType"><el-icon :size="14"><Plus /></el-icon> 添加</el-button>
    </div>

    <!-- 矩阵表格（横向滚动） -->
    <div class="table-wrapper" v-if="store.bizTypes.length">
      <table class="margin-table" border="1">
        <thead>
          <tr class="header-row-1">
            <th rowspan="2" class="col-month">月份</th>
            <th colspan="3" class="col-total">合计</th>
            <th v-for="biz in store.bizTypes" :key="biz.id" colspan="3" class="col-biz">{{ biz.name }}</th>
          </tr>
          <tr class="header-row-2">
            <th>收入</th><th>成本</th><th title="(收入 − 成本) / 收入 × 100%（自动计算）">毛利率 ƒx</th>
            <template v-for="biz in store.bizTypes" :key="biz.id+'h'"><th>收入</th><th>成本</th><th title="(收入 − 成本) / 收入 × 100%（自动计算）">毛利率 ƒx</th></template>
          </tr>
        </thead>
        <tbody>
          <!-- 12月 -->
          <tr v-for="(m, mIdx) in MONTHS" :key="mIdx">
            <td class="col-month">{{ m }}</td>
            <!-- 合计列（自动汇总所有业务类型） -->
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).revenue), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).cost), 0)) }}</td>
            <td class="auto-cell margin-cell">{{ fmtMargin(store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).revenue), 0), store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).cost), 0)) }}</td>
            <!-- 各业务类型 -->
            <template v-for="biz in store.bizTypes" :key="biz.id+mIdx">
              <td><input type="number" :value="getMonth(biz.id, mIdx).revenue || ''" :disabled="isReadonly" @change="(e: any) => updateMonth(biz.id, mIdx, 'revenue', e.target.value)" /></td>
              <td><input type="number" :value="getMonth(biz.id, mIdx).cost || ''" :disabled="isReadonly" @change="(e: any) => updateMonth(biz.id, mIdx, 'cost', e.target.value)" /></td>
              <td class="auto-cell margin-cell">{{ fmtMargin(pn(getMonth(biz.id, mIdx).revenue), pn(getMonth(biz.id, mIdx).cost)) }}</td>
            </template>
          </tr>
          <!-- 合计行 -->
          <tr class="summary-row">
            <td class="col-month">合计</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'revenue'), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'cost'), 0)) }}</td>
            <td class="auto-cell margin-cell">{{ fmtMargin(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'revenue'), 0), store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'cost'), 0)) }}</td>
            <template v-for="biz in store.bizTypes" :key="biz.id+'t'">
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'revenue')) }}</td>
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'cost')) }}</td>
              <td class="auto-cell margin-cell">{{ fmtMargin(getTotal(biz.id, 'revenue'), getTotal(biz.id, 'cost')) }}</td>
            </template>
          </tr>
          <!-- 上年数 -->
          <tr class="prior-row">
            <td class="col-month">上年数</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).revenue), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).cost), 0)) }}</td>
            <td class="auto-cell margin-cell">{{ fmtMargin(store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).revenue), 0), store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).cost), 0)) }}</td>
            <template v-for="biz in store.bizTypes" :key="biz.id+'p'">
              <td><input type="number" :value="getPrior(biz.id).revenue || ''" :disabled="isReadonly" @change="(e: any) => updatePrior(biz.id, 'revenue', e.target.value)" /></td>
              <td><input type="number" :value="getPrior(biz.id).cost || ''" :disabled="isReadonly" @change="(e: any) => updatePrior(biz.id, 'cost', e.target.value)" /></td>
              <td class="auto-cell margin-cell">{{ fmtMargin(pn(getPrior(biz.id).revenue), pn(getPrior(biz.id).cost)) }}</td>
            </template>
          </tr>
          <!-- 变动额 -->
          <tr class="delta-row">
            <td class="col-month">变动额</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'revenue'), 0) - store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).revenue), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'cost'), 0) - store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).cost), 0)) }}</td>
            <td class="auto-cell margin-cell">—</td>
            <template v-for="biz in store.bizTypes" :key="biz.id+'d'">
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'revenue') - pn(getPrior(biz.id).revenue)) }}</td>
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'cost') - pn(getPrior(biz.id).cost)) }}</td>
              <td class="auto-cell margin-cell">—</td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <el-empty v-else description="请先添加业务类型" :image-size="60"><el-button type="primary" :disabled="isReadonly" @click="addBizType"><el-icon :size="14"><Plus /></el-icon> 添加业务类型</el-button></el-empty>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="分析各业务类型毛利率变动的合理性" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断其他业务收入毛利率是否合理" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <!-- 在线编辑：平台 sync bridge（dedicated 静态受管区 sync sheet，非裸 GtOnlyOfficeSheet） -->
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor="syncOoDescriptor" :bridge="syncBridge" /><div v-else class="oo-loading">正在打开 D4-33 同步编辑器…</div></div></template>
</div>
</template>

<style scoped>
.d4-other-margin{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.biz-management{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px;padding:8px 14px;background:#faf5ff;border-radius:6px;border:1px solid #e8d5f5}.biz-label{font-size:12px;color:#9b59b6;font-weight:500}
.table-wrapper{overflow-x:auto;margin-bottom:24px;border-radius:6px;border:1px solid #ebeef5}
.margin-table{width:100%;border-collapse:collapse;font-size: var(--wp-font-size, 13px);min-width:600px}
.margin-table th,.margin-table td{padding:6px 8px;border:1px solid #ebeef5;text-align:center;white-space:nowrap}
.margin-table thead{background:#f5f7fa}
.header-row-1 th{font-weight:600;font-size: var(--wp-font-size, 13px)}
.header-row-2 th{font-size:12px;font-weight:400;color:#606266}
.col-month{font-weight:500;background:#fafbfc;min-width:50px;text-align:center}
.col-total{background:#f0faf0;color:#303133}
.col-biz{background:#f0f5ff;color:#303133}
/* 自动计算列：对齐平台蓝本 .auto-calc-col（灰底 + 虚线下划线提示为公式派生值） */
.auto-cell{color:#909399;background:#fafafa;border-bottom:1px dashed #dcdfe6}
.margin-cell{font-weight:500}
.summary-row td{background:#f0f9eb !important;font-weight:600}
.prior-row td{background:#fdf6ec !important}
.delta-row td{background:#f0f5ff !important}
.margin-table input{width:80px;border:1px solid #dcdfe6;border-radius:3px;padding:2px 6px;font-size: var(--wp-font-size, 13px);text-align:right;outline:none}
.margin-table input:focus{border-color:#409eff}
.margin-table input:disabled{background:#f5f7fa;color:#909399;border-color:#ebeef5}
.audit-opinion-card{margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
:deep(.el-empty){padding:32px 0}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
