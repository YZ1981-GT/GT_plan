<script setup lang="ts">
/**
 * D4TabMarginMonthly — D4-7 主营业务收入毛利率分析表
 *
 * 对齐源模板真实结构（openpyxl实读 D4-6至D4-11.xlsx "毛利率分析表D4-7"）：
 * 一、审计目标（固定文本）
 * 二、审计过程（AI辅助填充）
 * （一）月度毛利分析（4行固定×16列：1~12月+合计+上期+变动比例）
 *   - 主营业务收入（手填12月+上期，合计=SUM(1~12月)，变动=(合计-上期)/上期）
 *   - 主营业务成本（同上）
 *   - 毛利=收入-成本（全自动）
 *   - 毛利率=毛利/收入（全自动）
 * （二）按产品毛利分析（动态产品行×22列）
 *   本期: A产品名称 B数量 C平均单价=D/B D主营业务收入 E结构比=D/$D合计
 *         F单位成本=G/B G主营业务成本 H毛利=D-G I毛利率=IF(D=0,0,H/D)
 *   上期: J数量 K平均单价=L/J L主营业务收入 M结构比=L/$L合计
 *         N单位成本=O/J O主营业务成本 P毛利=L-O Q毛利率=IF(L=0,0,P/L)
 *   变动: R平均单价=(C-K)/K S单位成本=(F-N)/N T主营业务收入=(D-L)/L
 *         U主营业务成本=(G-O)/O V毛利率=I-Q
 *   W备注
 * 三、审计说明
 * 四、审计结论
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// 双模式（结构化视图 / 在线编辑）
const editorMode = ref<'structured' | 'onlyoffice'>('structured')
const ooHealthy = ref(false)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
])
async function checkOoHealth() {
  try {
    const res = await http.get(`/api/workpapers/onlyoffice/health`, { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()

// ─── 审计目标（固定文本） ─────────────────────────────────────────────
const auditObjective = '利润表中记录的营业收入已发生，且与被审计单位有关。'

// ─── 审计过程（AI可填充） ─────────────────────────────────────────────
const auditProcess = ref('')
function loadAuditProcess() {
  auditProcess.value = props.allResponses.get('D4-7-audit-process')?.remark || ''
}
watch(() => props.allResponses.get('D4-7-audit-process')?.remark, () => loadAuditProcess(), { immediate: true })

function updateAuditProcess(val: string) {
  if (props.isReadonly) return
  auditProcess.value = val
  persist('D4-7-audit-process', val)
}

// ─── （一）月度毛利分析 ──────────────────────────────────────────────
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

interface MonthlyData {
  revenue: number[]  // 12月收入
  cost: number[]     // 12月成本
  priorRevenue: number  // 上期收入合计
  priorCost: number     // 上期成本合计
}

const monthly = ref<MonthlyData>({
  revenue: new Array(12).fill(0),
  cost: new Array(12).fill(0),
  priorRevenue: 0,
  priorCost: 0,
})

function loadMonthly() {
  const resp = props.allResponses.get('D4-7-monthly')
  if (resp?.remark) {
    try { const p = JSON.parse(resp.remark); if (p && typeof p === 'object') { monthly.value = { revenue: p.revenue || new Array(12).fill(0), cost: p.cost || new Array(12).fill(0), priorRevenue: p.priorRevenue || 0, priorCost: p.priorCost || 0 }; return } } catch {}
  }
  monthly.value = { revenue: new Array(12).fill(0), cost: new Array(12).fill(0), priorRevenue: 0, priorCost: 0 }
}
watch(() => props.allResponses.get('D4-7-monthly')?.remark, () => loadMonthly(), { immediate: true })

// 计算列
const revenueTotal = computed(() => monthly.value.revenue.reduce((s, v) => s + v, 0))
const costTotal = computed(() => monthly.value.cost.reduce((s, v) => s + v, 0))
const profitMonths = computed(() => monthly.value.revenue.map((r, i) => r - monthly.value.cost[i]))
const profitTotal = computed(() => revenueTotal.value - costTotal.value)
const priorProfit = computed(() => monthly.value.priorRevenue - monthly.value.priorCost)
const marginMonths = computed(() => monthly.value.revenue.map((r, i) => r === 0 ? 0 : (r - monthly.value.cost[i]) / r))
const marginTotal = computed(() => revenueTotal.value === 0 ? 0 : profitTotal.value / revenueTotal.value)
const marginPrior = computed(() => monthly.value.priorRevenue === 0 ? 0 : priorProfit.value / monthly.value.priorRevenue)
// 变动比例
const revenueChange = computed(() => monthly.value.priorRevenue === 0 ? null : (revenueTotal.value - monthly.value.priorRevenue) / monthly.value.priorRevenue)
const costChange = computed(() => monthly.value.priorCost === 0 ? null : (costTotal.value - monthly.value.priorCost) / monthly.value.priorCost)
const profitChange = computed(() => priorProfit.value === 0 ? null : (profitTotal.value - priorProfit.value) / Math.abs(priorProfit.value))

function updateRevenue(idx: number, val: number) {
  if (props.isReadonly) return
  monthly.value.revenue[idx] = val
  persistMonthly()
}
function updateCost(idx: number, val: number) {
  if (props.isReadonly) return
  monthly.value.cost[idx] = val
  persistMonthly()
}
function updatePriorRevenue(val: number) { if (props.isReadonly) return; monthly.value.priorRevenue = val; persistMonthly() }
function updatePriorCost(val: number) { if (props.isReadonly) return; monthly.value.priorCost = val; persistMonthly() }

function persistMonthly() {
  props.allResponses.set('D4-7-monthly', { item_id: 'D4-7-monthly', conclusion: null, remark: JSON.stringify(monthly.value) })
  debounceSave()
}

// ─── （二）按产品毛利分析 ────────────────────────────────────────────
interface ProductRow {
  name: string
  // 本期：手填 B数量 D收入 G成本; 其余自动
  curQty: number
  curRevenue: number
  curCost: number
  // 上期：手填 J数量 L收入 O成本
  priorQty: number
  priorRevenue: number
  priorCost: number
  // 备注
  remark: string
}

const products = ref<ProductRow[]>([])

function loadProducts() {
  const resp = props.allResponses.get('D4-7-products')
  if (resp?.remark) {
    try { const p = JSON.parse(resp.remark); if (Array.isArray(p) && p.length) { products.value = p; return } } catch {}
  }
  products.value = []
}
watch(() => props.allResponses.get('D4-7-products')?.remark, () => loadProducts(), { immediate: true })


// 产品表合计（用于结构比分母 $D$26 / $L$26）
const totalCurRevenue = computed(() => products.value.reduce((s, r) => s + (r.curRevenue || 0), 0))
const totalPriorRevenue = computed(() => products.value.reduce((s, r) => s + (r.priorRevenue || 0), 0))

// 产品行计算列
interface ProductComputed extends ProductRow {
  curAvgPrice: number    // C=D/B
  curStructure: number   // E=D/$D合计
  curUnitCost: number    // F=G/B
  curProfit: number      // H=D-G
  curMargin: number      // I=IF(D=0,0,H/D)
  priorAvgPrice: number  // K=L/J
  priorStructure: number // M=L/$L合计
  priorUnitCost: number  // N=O/J
  priorProfit: number    // P=L-O
  priorMargin: number    // Q=IF(L=0,0,P/L)
  chgAvgPrice: number | null  // R=(C-K)/K
  chgUnitCost: number | null  // S=(F-N)/N
  chgRevenue: number | null   // T=(D-L)/L
  chgCost: number | null      // U=(G-O)/O
  chgMargin: number           // V=I-Q
}

const computedProducts = computed<ProductComputed[]>(() => {
  const totCurRev = totalCurRevenue.value
  const totPriorRev = totalPriorRevenue.value
  return products.value.map(r => {
    const curAvgPrice = r.curQty === 0 ? 0 : r.curRevenue / r.curQty
    const curStructure = totCurRev === 0 ? 0 : r.curRevenue / totCurRev
    const curUnitCost = r.curQty === 0 ? 0 : r.curCost / r.curQty
    const curProfit = r.curRevenue - r.curCost
    const curMargin = r.curRevenue === 0 ? 0 : curProfit / r.curRevenue
    const priorAvgPrice = r.priorQty === 0 ? 0 : r.priorRevenue / r.priorQty
    const priorStructure = totPriorRev === 0 ? 0 : r.priorRevenue / totPriorRev
    const priorUnitCost = r.priorQty === 0 ? 0 : r.priorCost / r.priorQty
    const priorProfit = r.priorRevenue - r.priorCost
    const priorMargin = r.priorRevenue === 0 ? 0 : priorProfit / r.priorRevenue
    const chgAvgPrice = priorAvgPrice === 0 ? null : (curAvgPrice - priorAvgPrice) / priorAvgPrice
    const chgUnitCost = priorUnitCost === 0 ? null : (curUnitCost - priorUnitCost) / priorUnitCost
    const chgRevenue = r.priorRevenue === 0 ? null : (r.curRevenue - r.priorRevenue) / r.priorRevenue
    const chgCost = r.priorCost === 0 ? null : (r.curCost - r.priorCost) / r.priorCost
    const chgMargin = curMargin - priorMargin
    return { ...r, curAvgPrice, curStructure, curUnitCost, curProfit, curMargin, priorAvgPrice, priorStructure, priorUnitCost, priorProfit, priorMargin, chgAvgPrice, chgUnitCost, chgRevenue, chgCost, chgMargin }
  })
})

// 合计行
const productTotals = computed(() => {
  const rows = computedProducts.value
  const sumB = rows.reduce((s, r) => s + r.curQty, 0)
  const sumD = totalCurRevenue.value
  const sumG = rows.reduce((s, r) => s + r.curCost, 0)
  const sumH = sumD - sumG
  const sumI = sumD === 0 ? 0 : sumH / sumD
  const sumJ = rows.reduce((s, r) => s + r.priorQty, 0)
  const sumL = totalPriorRevenue.value
  const sumO = rows.reduce((s, r) => s + r.priorCost, 0)
  const sumP = sumL - sumO
  const sumQ = sumL === 0 ? 0 : sumP / sumL
  const avgC = sumB === 0 ? 0 : sumD / sumB
  const avgF = sumB === 0 ? 0 : sumG / sumB
  const avgK = sumJ === 0 ? 0 : sumL / sumJ
  const avgN = sumJ === 0 ? 0 : sumO / sumJ
  return {
    sumB, avgC, sumD, sumG, sumH, sumI, avgF,
    sumJ, avgK, sumL, sumO, sumP, sumQ, avgN,
    chgAvgPrice: avgK === 0 ? null : (avgC - avgK) / avgK,
    chgUnitCost: avgN === 0 ? null : (avgF - avgN) / avgN,
    chgRevenue: sumL === 0 ? null : (sumD - sumL) / sumL,
    chgCost: sumO === 0 ? null : (sumG - sumO) / sumO,
    chgMargin: sumI - sumQ,
  }
})

function addProduct() {
  if (props.isReadonly) return
  products.value.push({ name: '', curQty: 0, curRevenue: 0, curCost: 0, priorQty: 0, priorRevenue: 0, priorCost: 0, remark: '' })
  persistProducts()
}
function removeProduct(idx: number) {
  if (props.isReadonly) return
  products.value.splice(idx, 1)
  persistProducts()
}
function updateProduct() {
  if (props.isReadonly) return
  persistProducts()
}
function persistProducts() {
  props.allResponses.set('D4-7-products', { item_id: 'D4-7-products', conclusion: null, remark: JSON.stringify(products.value) })
  debounceSave()
}

// ─── 审计说明 / 审计结论 ──────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
function loadNoteConclusion() {
  auditNote.value = props.allResponses.get('D4-7-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-7-conclusion')?.remark || ''
}
watch(() => props.allResponses.get('D4-7-note')?.remark, () => loadNoteConclusion(), { immediate: true })

function updateNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persist('D4-7-note', val) }
function updateConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persist('D4-7-conclusion', val) }

// ─── 格式化 ──────────────────────────────────────────────────────────
function fmtAmt(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPercent(val: number | null): string {
  if (val == null) return '-'
  return (val * 100).toFixed(2) + '%'
}

// ─── AI辅助 ──────────────────────────────────────────────────────────
const aiAvailable = ref(false)
const aiLoadingKey = ref<string | null>(null)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

async function callD4Ai(section: string, existing: string): Promise<string> {
  const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
    section, existingContent: existing, relatedContext: {},
  }, { _silent: true } as any)
  return res.data?.data?.content ?? res.data?.content ?? ''
}

async function generateAuditProcess() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'process'
  try {
    const ctx = `审计目标：${auditObjective}\n毛利率分析表包含月度毛利分析（12月收入/成本/毛利/毛利率）和按产品毛利分析（本期/上期/变动）。请生成D4-7毛利率分析表的审计过程描述，说明了解公司各月毛利、收入构成及变化情况，与行业和市场同期对比分析的具体步骤。`
    const text = await callD4Ai('analysis-note', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计过程', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateAuditProcess(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const monthlyCtx = `月度毛利率: ${marginMonths.value.map((m, i) => `${i+1}月=${fmtPercent(m)}`).join(', ')}, 全年=${fmtPercent(marginTotal.value)}, 上期=${fmtPercent(marginPrior.value)}`
    const productCtx = computedProducts.value.map(r => `${r.name||'未命名'}: 本期毛利率=${fmtPercent(r.curMargin)}, 上期=${fmtPercent(r.priorMargin)}, 变动=${fmtPercent(r.chgMargin)}`).join('\n')
    const text = await callD4Ai('analysis-note', `${monthlyCtx}\n\n按产品:\n${productCtx}`)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const abnormals = computedProducts.value.filter(r => Math.abs(r.chgMargin) > 0.05)
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n异常产品：${abnormals.length ? abnormals.map(r => `${r.name}毛利率变动${fmtPercent(r.chgMargin)}`).join('、') : '无'}\n综合毛利率变动：${fmtPercent(marginTotal.value - marginPrior.value)}`
    const text = await callD4Ai('adj-conclusion', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

// ─── 导入导出 ────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
})
function handleExportTemplate() { exportTemplate('D4-7' as any) }
function handleExportData() { exportData('D4-7' as any) }
function handleImportUpload(file: File): boolean {
  importData('D4-7' as any, file).then((result) => {
    if (result && result.rowCount > 0) loadProducts()
  })
  return false
}

// ─── 持久化 ──────────────────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function persist(itemId: string, value: string) {
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value })
  debounceSave()
}
function debounceSave() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
}
function flushSave() {
  const keys = ['D4-7-audit-process', 'D4-7-monthly', 'D4-7-products', 'D4-7-note', 'D4-7-conclusion']
  const items = keys.map(k => props.allResponses.get(k)).filter(Boolean)
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
}
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
</script>


<template>
  <div class="d4-margin">

    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === 'structured'">    <!-- 一、审计目标 -->
    <section class="sec">
      <h4 class="sec-title">一、审计目标</h4>
      <div class="objective-list">
        <p class="objective-item">{{ auditObjective }}</p>
      </div>
    </section>

    <!-- 二、审计过程 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">二、审计过程</h4>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain
            :loading="aiLoadingKey === 'process'"
            :disabled="isReadonly || !aiAvailable"
            @click="generateAuditProcess">🤖 AI辅助</el-button>
        </el-tooltip>
      </div>
      <el-input
        type="textarea" :rows="3"
        :model-value="auditProcess" :disabled="isReadonly"
        placeholder="1.了解公司各月毛利、收入的构成及变化情况是否符合行业和市场同期的变化情况。了解公司的产品或服务价格、销量及变动趋势，了解市场上具有代表性企业的价格信息和趋势、行业协会发布的统计数据，并进行比较，确定是否存在显著异常"
        @input="(v: string) => updateAuditProcess(v)"
      />
    </section>

    <!-- （一）月度毛利分析 -->
    <section class="sec">
      <h4 class="sec-title">（一）月度毛利分析</h4>
      <div class="monthly-table-wrap">
        <table class="monthly-table" border="1" cellpadding="0" cellspacing="0">
          <thead>
            <tr>
              <th class="col-label">月份</th>
              <th v-for="m in MONTHS" :key="m" class="col-month">{{ m }}</th>
              <th class="col-total">合计</th>
              <th class="col-prior">上期</th>
              <th class="col-change">变动比例</th>
            </tr>
          </thead>
          <tbody>
            <!-- 主营业务收入 -->
            <tr>
              <td class="row-label">
                <el-tooltip content="数据来源: 序时账(tb_ledger)科目6001按月汇总，或从D4-2主营明细各月合计取数" placement="right" :show-after="200">
                  <span class="has-formula">主营业务收入</span>
                </el-tooltip>
              </td>
              <td v-for="(_, idx) in 12" :key="'r'+idx" class="cell-input">
                <el-input-number v-model="monthly.revenue[idx]" :controls="false" size="small"
                  :disabled="isReadonly" :precision="2" class="num-cell"
                  @change="() => updateRevenue(idx, monthly.revenue[idx])" />
              </td>
              <td class="cell-computed">{{ fmtAmt(revenueTotal) }}</td>
              <td class="cell-input">
                <el-input-number v-model="monthly.priorRevenue" :controls="false" size="small"
                  :disabled="isReadonly" :precision="2" class="num-cell"
                  @change="() => updatePriorRevenue(monthly.priorRevenue)" />
              </td>
              <td class="cell-computed" :class="{ 'val-exceed': revenueChange != null && Math.abs(revenueChange) > 0.3 }">
                <el-tooltip content="公式: (合计-上期)/上期" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtPercent(revenueChange) }}</span>
                </el-tooltip>
              </td>
            </tr>
            <!-- 主营业务成本 -->
            <tr>
              <td class="row-label">
                <el-tooltip content="数据来源: 序时账(tb_ledger)科目6401按月汇总，或从成本明细表各月合计取数" placement="right" :show-after="200">
                  <span class="has-formula">主营业务成本</span>
                </el-tooltip>
              </td>
              <td v-for="(_, idx) in 12" :key="'c'+idx" class="cell-input">
                <el-input-number v-model="monthly.cost[idx]" :controls="false" size="small"
                  :disabled="isReadonly" :precision="2" class="num-cell"
                  @change="() => updateCost(idx, monthly.cost[idx])" />
              </td>
              <td class="cell-computed">{{ fmtAmt(costTotal) }}</td>
              <td class="cell-input">
                <el-input-number v-model="monthly.priorCost" :controls="false" size="small"
                  :disabled="isReadonly" :precision="2" class="num-cell"
                  @change="() => updatePriorCost(monthly.priorCost)" />
              </td>
              <td class="cell-computed" :class="{ 'val-exceed': costChange != null && Math.abs(costChange) > 0.3 }">
                <el-tooltip content="公式: (合计-上期)/上期" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtPercent(costChange) }}</span>
                </el-tooltip>
              </td>
            </tr>
            <!-- 毛利 = 收入 - 成本 -->
            <tr class="row-auto">
              <td class="row-label">毛利</td>
              <td v-for="(_, idx) in 12" :key="'p'+idx" class="cell-computed">
                <el-tooltip :content="`公式: 收入-成本 = ${fmtAmt(monthly.revenue[idx])}-${fmtAmt(monthly.cost[idx])}`" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtAmt(profitMonths[idx]) }}</span>
                </el-tooltip>
              </td>
              <td class="cell-computed">{{ fmtAmt(profitTotal) }}</td>
              <td class="cell-computed">{{ fmtAmt(priorProfit) }}</td>
              <td class="cell-computed" :class="{ 'val-exceed': profitChange != null && Math.abs(profitChange) > 0.3 }">
                <el-tooltip content="公式: (合计毛利-上期毛利)/|上期毛利|" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtPercent(profitChange) }}</span>
                </el-tooltip>
              </td>
            </tr>
            <!-- 毛利率 = 毛利/收入 -->
            <tr class="row-auto">
              <td class="row-label">毛利率</td>
              <td v-for="(_, idx) in 12" :key="'m'+idx" class="cell-computed">
                <el-tooltip :content="`公式: 毛利/收入`" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtPercent(marginMonths[idx]) }}</span>
                </el-tooltip>
              </td>
              <td class="cell-computed">{{ fmtPercent(marginTotal) }}</td>
              <td class="cell-computed">{{ fmtPercent(marginPrior) }}</td>
              <td class="cell-computed"></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- （二）按产品毛利分析 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">（二）按产品毛利分析</h4>
        <div class="sec-actions">
          <el-dropdown size="small" trigger="click" :disabled="isReadonly">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImportUpload" :disabled="importing">
                    <span>{{ importing ? '导入中...' : '导入数据' }}</span>
                  </el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tooltip content="批量数据建议：先点「导入导出 ▾ → 导出模板」，在Excel中填写后导入更快" placement="top" :show-after="300">
            <el-button size="small" :disabled="isReadonly" @click="addProduct">+ 增行</el-button>
          </el-tooltip>
          <GtIndexChip value="wp:D4-2" :context-project-id="projectId" />
          <GtIndexChip value="wp:D4-8" :context-project-id="projectId" />
        </div>
      </div>

      <div class="product-table-wrap">
        <el-table :data="computedProducts" border class="product-table" max-height="480"
          :header-cell-style="{ fontSize: '13px', fontWeight: '600', background: '#f5f7fa', textAlign: 'center' }">
          <!-- 产品名称 -->
          <el-table-column label="产品名称" min-width="110" fixed>
            <template #default="{ row, $index }">
              <el-input v-model="row.name" size="small" :disabled="isReadonly" placeholder="产品" @input="updateProduct" />
            </template>
          </el-table-column>
          <!-- 本期 -->
          <el-table-column label="本期" align="center">
            <el-table-column label="数量" width="80" align="right">
              <template #default="{ row }"><el-input-number v-model="row.curQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></template>
            </el-table-column>
            <el-table-column label="平均单价" width="90" align="right">
              <template #default="{ row }"><el-tooltip content="公式: 收入/数量" placement="top" :show-after="200"><span class="has-formula">{{ fmtAmt(row.curAvgPrice) }}</span></el-tooltip></template>
            </el-table-column>
            <el-table-column label="主营业务收入" width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.curRevenue" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></template>
            </el-table-column>
            <el-table-column label="结构比" width="75" align="right">
              <template #default="{ row }"><el-tooltip content="公式: 收入/合计收入" placement="top" :show-after="200"><span class="has-formula">{{ fmtPercent(row.curStructure) }}</span></el-tooltip></template>
            </el-table-column>
            <el-table-column label="单位成本" width="90" align="right">
              <template #default="{ row }"><el-tooltip content="公式: 成本/数量" placement="top" :show-after="200"><span class="has-formula">{{ fmtAmt(row.curUnitCost) }}</span></el-tooltip></template>
            </el-table-column>
            <el-table-column label="主营业务成本" width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.curCost" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></template>
            </el-table-column>
            <el-table-column label="毛利" width="90" align="right">
              <template #default="{ row }"><el-tooltip content="公式: 收入-成本" placement="top" :show-after="200"><span class="has-formula">{{ fmtAmt(row.curProfit) }}</span></el-tooltip></template>
            </el-table-column>
            <el-table-column label="毛利率" width="75" align="right">
              <template #default="{ row }"><el-tooltip content="公式: IF(收入=0,0,毛利/收入)" placement="top" :show-after="200"><span class="has-formula">{{ fmtPercent(row.curMargin) }}</span></el-tooltip></template>
            </el-table-column>
          </el-table-column>
          <!-- 上期 -->
          <el-table-column label="上期" align="center">
            <el-table-column label="数量" width="80" align="right">
              <template #default="{ row }"><el-input-number v-model="row.priorQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></template>
            </el-table-column>
            <el-table-column label="平均单价" width="90" align="right">
              <template #default="{ row }"><span class="has-formula">{{ fmtAmt(row.priorAvgPrice) }}</span></template>
            </el-table-column>
            <el-table-column label="主营业务收入" width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.priorRevenue" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></template>
            </el-table-column>
            <el-table-column label="结构比" width="75" align="right">
              <template #default="{ row }"><span class="has-formula">{{ fmtPercent(row.priorStructure) }}</span></template>
            </el-table-column>
            <el-table-column label="单位成本" width="90" align="right">
              <template #default="{ row }"><span class="has-formula">{{ fmtAmt(row.priorUnitCost) }}</span></template>
            </el-table-column>
            <el-table-column label="主营业务成本" width="110" align="right">
              <template #default="{ row }"><el-input-number v-model="row.priorCost" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></template>
            </el-table-column>
            <el-table-column label="毛利" width="90" align="right">
              <template #default="{ row }"><span class="has-formula">{{ fmtAmt(row.priorProfit) }}</span></template>
            </el-table-column>
            <el-table-column label="毛利率" width="75" align="right">
              <template #default="{ row }"><span class="has-formula">{{ fmtPercent(row.priorMargin) }}</span></template>
            </el-table-column>
          </el-table-column>
          <!-- 变动比例 -->
          <el-table-column label="变动比例" align="center">
            <el-table-column label="平均单价" width="85" align="right">
              <template #default="{ row }"><span :class="{ 'val-exceed': row.chgAvgPrice != null && Math.abs(row.chgAvgPrice) > 0.2 }">{{ fmtPercent(row.chgAvgPrice) }}</span></template>
            </el-table-column>
            <el-table-column label="单位成本" width="85" align="right">
              <template #default="{ row }"><span :class="{ 'val-exceed': row.chgUnitCost != null && Math.abs(row.chgUnitCost) > 0.2 }">{{ fmtPercent(row.chgUnitCost) }}</span></template>
            </el-table-column>
            <el-table-column label="主营业务收入" width="100" align="right">
              <template #default="{ row }"><span :class="{ 'val-exceed': row.chgRevenue != null && Math.abs(row.chgRevenue) > 0.3 }">{{ fmtPercent(row.chgRevenue) }}</span></template>
            </el-table-column>
            <el-table-column label="主营业务成本" width="100" align="right">
              <template #default="{ row }"><span :class="{ 'val-exceed': row.chgCost != null && Math.abs(row.chgCost) > 0.3 }">{{ fmtPercent(row.chgCost) }}</span></template>
            </el-table-column>
            <el-table-column label="毛利率" width="85" align="right">
              <template #default="{ row }"><span :class="{ 'val-exceed': Math.abs(row.chgMargin) > 0.05, 'has-formula': true }">{{ fmtPercent(row.chgMargin) }}</span></template>
            </el-table-column>
          </el-table-column>
          <!-- 备注 -->
          <el-table-column label="备注" min-width="100">
            <template #default="{ row }"><el-input v-model="row.remark" size="small" :disabled="isReadonly" placeholder="" @input="updateProduct" /></template>
          </el-table-column>
          <!-- 操作 -->
          <el-table-column v-if="!isReadonly" label="" width="40" fixed="right">
            <template #default="{ $index }">
              <el-button size="small" type="danger" text @click="removeProduct($index)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
        <!-- 合计行 -->
        <div v-if="products.length > 0" class="totals-row">
          <span class="totals-label">合计</span>
          <span class="totals-item">本期收入: {{ fmtAmt(productTotals.sumD) }}</span>
          <span class="totals-item">本期成本: {{ fmtAmt(productTotals.sumG) }}</span>
          <span class="totals-item">本期毛利率: {{ fmtPercent(productTotals.sumI) }}</span>
          <span class="totals-item">上期毛利率: {{ fmtPercent(productTotals.sumQ) }}</span>
          <span class="totals-item" :class="{ 'val-exceed': Math.abs(productTotals.chgMargin) > 0.05 }">毛利率变动: {{ fmtPercent(productTotals.chgMargin) }}</span>
        </div>
      </div>
    </section>

    <!-- 三、审计说明 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">三、审计说明</h4>
        <div class="sec-actions">
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'"
              :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button>
          </el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-7-note')">💬</el-button>
        </div>
      </div>
      <p class="guidance-hint">1.毛利率变动异常原因：</p>
      <p class="guidance-hint">2.XX产品单价变动异常，采用审计抽样方法检查该类型产品单价变动的合理性，判断销售给关联方或关系密切的重要客户的产品价格是否合理，有无以低价或高价结算的方法，相互之间有无转移利润的现象，见&lt;产品销售价格分析D4-11&gt;。</p>
      <el-input type="textarea" :rows="4" :model-value="auditNote" :disabled="isReadonly"
        placeholder="请输入毛利率分析审计说明..." @input="(v: string) => updateNote(v)" />
    </section>

    <!-- 四、审计结论 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">四、审计结论</h4>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'"
            :disabled="isReadonly || !aiAvailable" @click="generateConclusion">🤖 AI辅助</el-button>
        </el-tooltip>
      </div>
      <el-input type="textarea" :rows="3" :model-value="auditConclusion" :disabled="isReadonly"
        placeholder="请输入审计结论..." @input="(v: string) => updateConclusion(v)" />
    </section>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>提示：除分析主要产品和服务之外，还需要考虑被审计单位是否有联产品和副产品产出；如有，应同时分析联产品和副产品的毛利变化情况。</p>
        <p>对于IPO、上市公司等审计业务，还需要考虑产品毛利率与同行业可比公司的对比分析。</p>
      </div>
    </details>
  
    </template>

    <!-- OnlyOffice 在线编辑 -->
    <template v-else>
      <div style="min-height: 600px; height: calc(100vh - 280px);">
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          sheet-name="毛利率分析表D4-7"
          :readonly="isReadonly"
        />
      </div>
    </template>
  </div>
</template>


<style scoped>
.d4-margin { padding: 16px; }
.sec { margin-bottom: 20px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 8px; }
.sec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sec-actions { display: flex; gap: 8px; align-items: center; }
.objective-list { padding: 10px 14px; background: #f5f7fa; border-radius: 6px; }
.objective-item { margin: 0; font-size: 13px; color: #303133; line-height: 1.7; }

/* 月度毛利表 */
.monthly-table-wrap { overflow-x: auto; }
.monthly-table { width: 100%; border-collapse: collapse; font-size: 13px; white-space: nowrap; }
.monthly-table th, .monthly-table td { border: 1px solid #dcdfe6; padding: 4px 6px; text-align: center; }
.monthly-table th { background: #f5f7fa; font-weight: 600; }
.col-label { min-width: 100px; text-align: left; }
.col-month { min-width: 72px; }
.col-total { min-width: 90px; background: #fafafa; }
.col-prior { min-width: 90px; }
.col-change { min-width: 80px; }
.row-label { text-align: left; font-weight: 500; white-space: nowrap; padding-left: 8px; }
.cell-input { padding: 2px; }
.cell-computed { background: #fafafa; font-size: 13px; text-align: right; padding-right: 6px; }
.row-auto td { background: #f9fafb; }
.num-cell { width: 100%; }
.num-cell :deep(.el-input__inner) { text-align: right; font-size: 13px; padding: 0 4px; }
.has-formula { border-bottom: 1px dashed #909399; cursor: help; }
.val-exceed { color: #f56c6c; font-weight: 600; }

/* 产品表 */
.product-table-wrap { margin-top: 8px; }
.product-table { font-size: 13px; }
.product-table :deep(.el-table__cell) { font-size: 13px; padding: 4px 0; }
.totals-row { display: flex; gap: 16px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; margin-top: 8px; font-size: 13px; flex-wrap: wrap; }
.totals-label { font-weight: 600; }
.totals-item { color: #606266; }

/* 审计说明提示 */
.guidance-hint { font-size: 12px; color: #909399; margin: 0 0 4px; line-height: 1.6; }

/* 编制提示折叠 */
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #f0f7ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { font-size: 13px; font-weight: 500; cursor: pointer; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.8; }
.guidance-content p { margin: 0 0 4px; }

.mode-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
