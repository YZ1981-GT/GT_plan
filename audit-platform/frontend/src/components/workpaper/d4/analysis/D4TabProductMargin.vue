<script setup lang="ts">
/**
 * D4TabProductMargin — D4-8 重要产品/服务毛利率分析表
 *
 * 对齐源模板真实结构（openpyxl实读 D4-6至D4-11.xlsx "产品毛利率分析D4-8"）：
 * 一、审计目标（3条固定）
 * 二、审计过程（AI辅助填充）
 * 主表（按产品×12月）：
 *   本期数: A月份(1-12) B销量 C平均单价 D金额(收入) E销量(成本) F平均单位成本 G金额(成本)
 *          H毛利=D-G I毛利率=IF(D=0,0,H/D)
 *   上期数: J销量 K平均单价 L金额(收入) M销量(成本) N平均单位成本 O金额(成本)
 *          P毛利=L-O Q毛利率=IF(L=0,0,P/L)
 *   变动分析: R平均单价=(C-K)/K S单位成本=(F-N)/N T主营业务收入=(D-L)/L
 *            U主营业务成本=(G-O)/O V毛利=(H-P)/P W毛利率=I-Q
 *   X备注
 *   合计行: SUM(1~12月)
 *   同行业A/B企业、行业平均水平
 * 三、审计说明
 * 四、审计结论
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 审计目标（固定文本） ─────────────────────────────────────────────
const auditObjectives = [
  '1. 利润表中记录的营业收入已发生，且与被审计单位有关；',
  '2. 所有应当记录的营业收入均已记录；',
  '3. 与营业收入有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。',
]

// ─── 审计过程（AI可填充） ─────────────────────────────────────────────
const auditProcess = ref('')
function loadAuditProcess() {
  auditProcess.value = props.allResponses.get('D4-8-audit-process')?.remark || ''
}

watch(() => props.allResponses.get('D4-8-audit-process')?.remark, () => loadAuditProcess(), { immediate: true })

function updateAuditProcess(val: string) {
  if (props.isReadonly) return
  auditProcess.value = val
  persist('D4-8-audit-process', val)
}

// ─── 产品数据结构 ────────────────────────────────────────────────────
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

interface MonthRow {
  revQty: number    // B 销量(收入)
  revPrice: number  // C 平均单价
  revAmt: number    // D 金额(收入)
  costQty: number   // E 销量(成本)
  costPrice: number // F 平均单位成本
  costAmt: number   // G 金额(成本)
}

interface IndustryRow {
  name: string
  revQty: number; revPrice: number; revAmt: number
  costQty: number; costPrice: number; costAmt: number
}

interface ProductData {
  name: string
  months: MonthRow[]       // 本期12月
  priorMonths: MonthRow[]  // 上期12月
  industry: IndustryRow[]  // 同行业对比（3行：A企业/B企业/行业平均）
}

function emptyMonth(): MonthRow {
  return { revQty: 0, revPrice: 0, revAmt: 0, costQty: 0, costPrice: 0, costAmt: 0 }
}

function defaultIndustry(): IndustryRow[] {
  return [
    { name: '同行业A企业', revQty: 0, revPrice: 0, revAmt: 0, costQty: 0, costPrice: 0, costAmt: 0 },
    { name: '同行业B企业', revQty: 0, revPrice: 0, revAmt: 0, costQty: 0, costPrice: 0, costAmt: 0 },
    { name: '行业平均水平', revQty: 0, revPrice: 0, revAmt: 0, costQty: 0, costPrice: 0, costAmt: 0 },
  ]
}

function defaultProduct(name = ''): ProductData {
  return {
    name,
    months: Array.from({ length: 12 }, emptyMonth),
    priorMonths: Array.from({ length: 12 }, emptyMonth),
    industry: defaultIndustry(),
  }
}


// ─── 产品列表 ────────────────────────────────────────────────────────
const products = ref<ProductData[]>([])
const activeProductIdx = ref(0)

function loadProducts() {
  const resp = props.allResponses.get('D4-8-products')
  if (resp?.remark) {
    try {
      const p = JSON.parse(resp.remark)
      if (Array.isArray(p) && p.length) {
        products.value = p.map((item: any) => ({
          name: item.name || '',
          months: (item.months || []).map((m: any) => ({ ...emptyMonth(), ...m })),
          priorMonths: (item.priorMonths || []).map((m: any) => ({ ...emptyMonth(), ...m })),
          industry: (Array.isArray(item.industry) && item.industry.length)
            ? item.industry.map((r: any) => ({ ...defaultIndustry()[0], ...r }))
            : defaultIndustry(),
        }))
        // 保证每个产品本期/上期各 12 个月
        products.value.forEach((pr) => {
          while (pr.months.length < 12) pr.months.push(emptyMonth())
          while (pr.priorMonths.length < 12) pr.priorMonths.push(emptyMonth())
        })
        activeProductIdx.value = 0
        return
      }
    } catch { /* ignore */ }
  }
  products.value = [defaultProduct('产品A')]
  activeProductIdx.value = 0
}
watch(() => props.allResponses.get('D4-8-products')?.remark, () => loadProducts(), { immediate: true })

const activeProduct = computed(() => products.value[activeProductIdx.value] || defaultProduct())

function addProduct() {
  if (props.isReadonly) return
  const idx = products.value.length + 1
  products.value.push(defaultProduct(`产品${String.fromCharCode(64 + idx)}`))
  activeProductIdx.value = products.value.length - 1
  persistProducts()
}

function removeProduct() {
  if (props.isReadonly || products.value.length <= 1) return
  ElMessageBox.confirm(`确定删除「${activeProduct.value.name || '未命名产品'}」？`, '确认', { type: 'warning' })
    .then(() => {
      products.value.splice(activeProductIdx.value, 1)
      if (activeProductIdx.value >= products.value.length) activeProductIdx.value = products.value.length - 1
      persistProducts()
    })
    .catch(() => {})
}

function updateProduct() {
  if (props.isReadonly) return
  persistProducts()
}

function persistProducts() {
  props.allResponses.set('D4-8-products', { item_id: 'D4-8-products', conclusion: null, remark: JSON.stringify(products.value) })
  debounceSave()
}


// ─── 计算列（当前选中产品） ──────────────────────────────────────────
interface ComputedMonthRow {
  month: string
  revQty: number; revPrice: number; revAmt: number
  costQty: number; costPrice: number; costAmt: number
  profit: number; margin: number
  pRevQty: number; pRevPrice: number; pRevAmt: number
  pCostQty: number; pCostPrice: number; pCostAmt: number
  pProfit: number; pMargin: number
  chgPrice: number | null; chgUnitCost: number | null
  chgRevenue: number | null; chgCost: number | null
  chgProfit: number | null; chgMargin: number
}

const computedMonths = computed<ComputedMonthRow[]>(() => {
  const prod = activeProduct.value
  return prod.months.map((m, i) => {
    const pm = prod.priorMonths[i] || emptyMonth()
    const profit = m.revAmt - m.costAmt
    const margin = m.revAmt === 0 ? 0 : profit / m.revAmt
    const pProfit = pm.revAmt - pm.costAmt
    const pMargin = pm.revAmt === 0 ? 0 : pProfit / pm.revAmt
    return {
      month: MONTHS[i],
      revQty: m.revQty, revPrice: m.revPrice, revAmt: m.revAmt,
      costQty: m.costQty, costPrice: m.costPrice, costAmt: m.costAmt,
      profit, margin,
      pRevQty: pm.revQty, pRevPrice: pm.revPrice, pRevAmt: pm.revAmt,
      pCostQty: pm.costQty, pCostPrice: pm.costPrice, pCostAmt: pm.costAmt,
      pProfit, pMargin,
      chgPrice: pm.revPrice === 0 ? null : (m.revPrice - pm.revPrice) / pm.revPrice,
      chgUnitCost: pm.costPrice === 0 ? null : (m.costPrice - pm.costPrice) / pm.costPrice,
      chgRevenue: pm.revAmt === 0 ? null : (m.revAmt - pm.revAmt) / pm.revAmt,
      chgCost: pm.costAmt === 0 ? null : (m.costAmt - pm.costAmt) / pm.costAmt,
      chgProfit: pProfit === 0 ? null : (profit - pProfit) / Math.abs(pProfit),
      chgMargin: margin - pMargin,
    }
  })
})


// 合计行
const totals = computed(() => {
  const prod = activeProduct.value
  const sumCur = prod.months.reduce((acc, m) => ({
    revQty: acc.revQty + m.revQty, revAmt: acc.revAmt + m.revAmt,
    costQty: acc.costQty + m.costQty, costAmt: acc.costAmt + m.costAmt,
  }), { revQty: 0, revAmt: 0, costQty: 0, costAmt: 0 })
  const sumPrior = prod.priorMonths.reduce((acc, m) => ({
    revQty: acc.revQty + m.revQty, revAmt: acc.revAmt + m.revAmt,
    costQty: acc.costQty + m.costQty, costAmt: acc.costAmt + m.costAmt,
  }), { revQty: 0, revAmt: 0, costQty: 0, costAmt: 0 })

  const curAvgPrice = sumCur.revQty === 0 ? 0 : sumCur.revAmt / sumCur.revQty
  const curAvgCost = sumCur.costQty === 0 ? 0 : sumCur.costAmt / sumCur.costQty
  const curProfit = sumCur.revAmt - sumCur.costAmt
  const curMargin = sumCur.revAmt === 0 ? 0 : curProfit / sumCur.revAmt

  const priorAvgPrice = sumPrior.revQty === 0 ? 0 : sumPrior.revAmt / sumPrior.revQty
  const priorAvgCost = sumPrior.costQty === 0 ? 0 : sumPrior.costAmt / sumPrior.costQty
  const priorProfit = sumPrior.revAmt - sumPrior.costAmt
  const priorMargin = sumPrior.revAmt === 0 ? 0 : priorProfit / sumPrior.revAmt

  return {
    ...sumCur, curAvgPrice, curAvgCost, curProfit, curMargin,
    pRevQty: sumPrior.revQty, pRevAmt: sumPrior.revAmt,
    pCostQty: sumPrior.costQty, pCostAmt: sumPrior.costAmt,
    priorAvgPrice, priorAvgCost, priorProfit, priorMargin,
    chgPrice: priorAvgPrice === 0 ? null : (curAvgPrice - priorAvgPrice) / priorAvgPrice,
    chgUnitCost: priorAvgCost === 0 ? null : (curAvgCost - priorAvgCost) / priorAvgCost,
    chgRevenue: sumPrior.revAmt === 0 ? null : (sumCur.revAmt - sumPrior.revAmt) / sumPrior.revAmt,
    chgCost: sumPrior.costAmt === 0 ? null : (sumCur.costAmt - sumPrior.costAmt) / sumPrior.costAmt,
    chgProfit: priorProfit === 0 ? null : (curProfit - priorProfit) / Math.abs(priorProfit),
    chgMargin: curMargin - priorMargin,
  }
})

// 同行业对比计算
interface IndustryComputed {
  name: string
  revQty: number; revPrice: number; revAmt: number
  costQty: number; costPrice: number; costAmt: number
  profit: number; margin: number
}
const computedIndustry = computed<IndustryComputed[]>(() => {
  return activeProduct.value.industry.map(ind => {
    const profit = ind.revAmt - ind.costAmt
    const margin = ind.revAmt === 0 ? 0 : profit / ind.revAmt
    return { ...ind, profit, margin }
  })
})


// ─── 审计说明 / 审计结论 ──────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
function loadNoteConclusion() {
  auditNote.value = props.allResponses.get('D4-8-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-8-conclusion')?.remark || ''
}
watch(() => props.allResponses.get('D4-8-note')?.remark, () => loadNoteConclusion(), { immediate: true })

function updateNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persist('D4-8-note', val) }
function updateConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persist('D4-8-conclusion', val) }

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
    const ctx = `审计目标：${auditObjectives.join(' ')}\n产品毛利率分析表按单个产品逐月分析本期/上期的销量、单价、收入、成本、毛利及毛利率变动情况，并与同行业对比。请生成D4-8重要产品/服务毛利率分析表的审计过程描述。`
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
    const prodSummaries = products.value.map(p => {
      const sums = p.months.reduce((a, m) => ({ rev: a.rev + m.revAmt, cost: a.cost + m.costAmt }), { rev: 0, cost: 0 })
      const margin = sums.rev === 0 ? 0 : (sums.rev - sums.cost) / sums.rev
      const pSums = p.priorMonths.reduce((a, m) => ({ rev: a.rev + m.revAmt, cost: a.cost + m.costAmt }), { rev: 0, cost: 0 })
      const pMargin = pSums.rev === 0 ? 0 : (pSums.rev - pSums.cost) / pSums.rev
      return `${p.name || '未命名'}: 本期毛利率=${fmtPercent(margin)}, 上期=${fmtPercent(pMargin)}, 变动=${fmtPercent(margin - pMargin)}`
    }).join('\n')
    const text = await callD4Ai('analysis-note', `重要产品/服务毛利率分析:\n${prodSummaries}`)
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
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n产品数量：${products.value.length}个\n综合毛利率变动：${fmtPercent(totals.value.chgMargin)}`
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
function handleExportTemplate() { exportTemplate('D4-8' as any) }
function handleExportData() { exportData('D4-8' as any) }
function handleImportUpload(file: File): boolean {
  importData('D4-8' as any, file).then((result) => {
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
  const keys = ['D4-8-audit-process', 'D4-8-products', 'D4-8-note', 'D4-8-conclusion']
  const items = keys.map(k => props.allResponses.get(k)).filter(Boolean)
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
}
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
</script>



<template>
  <div class="d4-product-margin">
    <!-- 一、审计目标 -->
    <section class="sec">
      <h4 class="sec-title">一、审计目标</h4>
      <div class="objective-list">
        <p v-for="(obj, i) in auditObjectives" :key="i" class="objective-item">{{ obj }}</p>
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
        placeholder="1.了解公司各重要产品或服务的销量、单价、成本及毛利变化情况是否符合行业和市场同期趋势。2.逐月分析各产品毛利率波动的合理性，与同行业可比公司进行对比分析。"
        @input="(v: string) => updateAuditProcess(v)"
      />
    </section>

    <!-- 产品选择器 + 工具栏 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">重要产品/服务毛利率分析</h4>
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
          <GtIndexChip value="wp:D4-7" :context-project-id="projectId" />
          <GtIndexChip value="wp:D4-2" :context-project-id="projectId" />
        </div>
      </div>

      <!-- 产品切换栏 -->
      <div class="product-selector">
        <el-select v-model="activeProductIdx" size="small" style="min-width: 160px">
          <el-option v-for="(p, idx) in products" :key="idx" :value="idx"
            :label="p.name || `产品${idx + 1}`" />
        </el-select>
        <el-input v-model="activeProduct.name" size="small" placeholder="产品名称"
          style="width: 160px" :disabled="isReadonly" @input="updateProduct" />
        <el-tooltip content="批量数据建议：先点「导入导出 ▾ → 导出模板」，在Excel中填写后导入更快" placement="top" :show-after="300">
          <el-button size="small" :disabled="isReadonly" @click="addProduct">+ 增行</el-button>
        </el-tooltip>
        <el-button size="small" type="danger" plain :disabled="isReadonly || products.length <= 1"
          @click="removeProduct">删除当前产品</el-button>
      </div>


      <!-- 月度明细表 -->
      <div class="monthly-table-wrap">
        <table class="monthly-table" border="1" cellpadding="0" cellspacing="0">
          <thead>
            <tr>
              <th rowspan="2" class="col-month">月份</th>
              <th colspan="6" class="group-cur">本期数</th>
              <th colspan="2" class="group-formula">本期计算</th>
              <th colspan="6" class="group-prior">上期数</th>
              <th colspan="2" class="group-formula">上期计算</th>
              <th colspan="6" class="group-change">变动分析</th>
            </tr>
            <tr>
              <!-- 本期数 -->
              <th class="col-num">销量</th>
              <th class="col-num">平均单价</th>
              <th class="col-amt">
                <el-tooltip content="数据来源: 序时账科目6001按月/按产品汇总" placement="top" :show-after="200">
                  <span class="has-formula">金额(收入)</span>
                </el-tooltip>
              </th>
              <th class="col-num">销量(成本)</th>
              <th class="col-num">单位成本</th>
              <th class="col-amt">
                <el-tooltip content="数据来源: 序时账科目6401按月/按产品汇总" placement="top" :show-after="200">
                  <span class="has-formula">金额(成本)</span>
                </el-tooltip>
              </th>
              <!-- 本期计算 -->
              <th class="col-formula">
                <el-tooltip content="公式: H=D-G (收入-成本)" placement="top" :show-after="200">
                  <span class="has-formula">毛利</span>
                </el-tooltip>
              </th>
              <th class="col-formula">
                <el-tooltip content="公式: I=IF(D=0,0,H/D)" placement="top" :show-after="200">
                  <span class="has-formula">毛利率</span>
                </el-tooltip>
              </th>
              <!-- 上期数 -->
              <th class="col-num">销量</th>
              <th class="col-num">平均单价</th>
              <th class="col-amt">金额(收入)</th>
              <th class="col-num">销量(成本)</th>
              <th class="col-num">单位成本</th>
              <th class="col-amt">金额(成本)</th>
              <!-- 上期计算 -->
              <th class="col-formula">
                <el-tooltip content="公式: P=L-O" placement="top" :show-after="200">
                  <span class="has-formula">毛利</span>
                </el-tooltip>
              </th>
              <th class="col-formula">
                <el-tooltip content="公式: Q=IF(L=0,0,P/L)" placement="top" :show-after="200">
                  <span class="has-formula">毛利率</span>
                </el-tooltip>
              </th>
              <!-- 变动分析 -->
              <th class="col-change">
                <el-tooltip content="公式: R=(C-K)/K" placement="top" :show-after="200">
                  <span class="has-formula">平均单价</span>
                </el-tooltip>
              </th>
              <th class="col-change">
                <el-tooltip content="公式: S=(F-N)/N" placement="top" :show-after="200">
                  <span class="has-formula">单位成本</span>
                </el-tooltip>
              </th>
              <th class="col-change">
                <el-tooltip content="公式: T=(D-L)/L" placement="top" :show-after="200">
                  <span class="has-formula">收入</span>
                </el-tooltip>
              </th>
              <th class="col-change">
                <el-tooltip content="公式: U=(G-O)/O" placement="top" :show-after="200">
                  <span class="has-formula">成本</span>
                </el-tooltip>
              </th>
              <th class="col-change">
                <el-tooltip content="公式: V=(H-P)/|P|" placement="top" :show-after="200">
                  <span class="has-formula">毛利</span>
                </el-tooltip>
              </th>
              <th class="col-change">
                <el-tooltip content="公式: W=I-Q" placement="top" :show-after="200">
                  <span class="has-formula">毛利率</span>
                </el-tooltip>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in computedMonths" :key="idx">
              <td class="cell-month">{{ row.month }}</td>
              <!-- 本期手填 -->
              <td class="cell-input"><el-input-number v-model="activeProduct.months[idx].revQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.months[idx].revPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.months[idx].revAmt" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.months[idx].costQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.months[idx].costPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.months[idx].costAmt" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <!-- 本期计算 -->
              <td class="cell-computed">
                <el-tooltip :content="`毛利 = ${fmtAmt(row.revAmt)} - ${fmtAmt(row.costAmt)}`" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtAmt(row.profit) }}</span>
                </el-tooltip>
              </td>
              <td class="cell-computed">
                <el-tooltip content="IF(收入=0,0,毛利/收入)" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtPercent(row.margin) }}</span>
                </el-tooltip>
              </td>
              <!-- 上期手填 -->
              <td class="cell-input"><el-input-number v-model="activeProduct.priorMonths[idx].revQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.priorMonths[idx].revPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.priorMonths[idx].revAmt" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.priorMonths[idx].costQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.priorMonths[idx].costPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.priorMonths[idx].costAmt" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <!-- 上期计算 -->
              <td class="cell-computed">
                <el-tooltip :content="`毛利 = ${fmtAmt(row.pRevAmt)} - ${fmtAmt(row.pCostAmt)}`" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtAmt(row.pProfit) }}</span>
                </el-tooltip>
              </td>
              <td class="cell-computed">
                <el-tooltip content="IF(收入=0,0,毛利/收入)" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtPercent(row.pMargin) }}</span>
                </el-tooltip>
              </td>
              <!-- 变动分析 -->
              <td class="cell-computed" :class="{ 'val-exceed': row.chgPrice != null && Math.abs(row.chgPrice) > 0.2 }">
                <span class="has-formula">{{ fmtPercent(row.chgPrice) }}</span>
              </td>
              <td class="cell-computed" :class="{ 'val-exceed': row.chgUnitCost != null && Math.abs(row.chgUnitCost) > 0.2 }">
                <span class="has-formula">{{ fmtPercent(row.chgUnitCost) }}</span>
              </td>
              <td class="cell-computed" :class="{ 'val-exceed': row.chgRevenue != null && Math.abs(row.chgRevenue) > 0.3 }">
                <span class="has-formula">{{ fmtPercent(row.chgRevenue) }}</span>
              </td>
              <td class="cell-computed" :class="{ 'val-exceed': row.chgCost != null && Math.abs(row.chgCost) > 0.3 }">
                <span class="has-formula">{{ fmtPercent(row.chgCost) }}</span>
              </td>
              <td class="cell-computed" :class="{ 'val-exceed': row.chgProfit != null && Math.abs(row.chgProfit) > 0.3 }">
                <span class="has-formula">{{ fmtPercent(row.chgProfit) }}</span>
              </td>
              <td class="cell-computed" :class="{ 'val-exceed': Math.abs(row.chgMargin) > 0.05 }">
                <span class="has-formula">{{ fmtPercent(row.chgMargin) }}</span>
              </td>
            </tr>

            <!-- 合计行 -->
            <tr class="row-total">
              <td class="cell-month"><strong>合计</strong></td>
              <td class="cell-computed">{{ fmtAmt(totals.revQty) }}</td>
              <td class="cell-computed"><el-tooltip content="合计收入/合计销量" placement="top" :show-after="200"><span class="has-formula">{{ fmtAmt(totals.curAvgPrice) }}</span></el-tooltip></td>
              <td class="cell-computed">{{ fmtAmt(totals.revAmt) }}</td>
              <td class="cell-computed">{{ fmtAmt(totals.costQty) }}</td>
              <td class="cell-computed"><el-tooltip content="合计成本/合计成本销量" placement="top" :show-after="200"><span class="has-formula">{{ fmtAmt(totals.curAvgCost) }}</span></el-tooltip></td>
              <td class="cell-computed">{{ fmtAmt(totals.costAmt) }}</td>
              <td class="cell-computed"><span class="has-formula">{{ fmtAmt(totals.curProfit) }}</span></td>
              <td class="cell-computed"><span class="has-formula">{{ fmtPercent(totals.curMargin) }}</span></td>
              <td class="cell-computed">{{ fmtAmt(totals.pRevQty) }}</td>
              <td class="cell-computed"><span class="has-formula">{{ fmtAmt(totals.priorAvgPrice) }}</span></td>
              <td class="cell-computed">{{ fmtAmt(totals.pRevAmt) }}</td>
              <td class="cell-computed">{{ fmtAmt(totals.pCostQty) }}</td>
              <td class="cell-computed"><span class="has-formula">{{ fmtAmt(totals.priorAvgCost) }}</span></td>
              <td class="cell-computed">{{ fmtAmt(totals.pCostAmt) }}</td>
              <td class="cell-computed"><span class="has-formula">{{ fmtAmt(totals.priorProfit) }}</span></td>
              <td class="cell-computed"><span class="has-formula">{{ fmtPercent(totals.priorMargin) }}</span></td>
              <td class="cell-computed" :class="{ 'val-exceed': totals.chgPrice != null && Math.abs(totals.chgPrice) > 0.2 }"><span class="has-formula">{{ fmtPercent(totals.chgPrice) }}</span></td>
              <td class="cell-computed" :class="{ 'val-exceed': totals.chgUnitCost != null && Math.abs(totals.chgUnitCost) > 0.2 }"><span class="has-formula">{{ fmtPercent(totals.chgUnitCost) }}</span></td>
              <td class="cell-computed" :class="{ 'val-exceed': totals.chgRevenue != null && Math.abs(totals.chgRevenue) > 0.3 }"><span class="has-formula">{{ fmtPercent(totals.chgRevenue) }}</span></td>
              <td class="cell-computed" :class="{ 'val-exceed': totals.chgCost != null && Math.abs(totals.chgCost) > 0.3 }"><span class="has-formula">{{ fmtPercent(totals.chgCost) }}</span></td>
              <td class="cell-computed" :class="{ 'val-exceed': totals.chgProfit != null && Math.abs(totals.chgProfit) > 0.3 }"><span class="has-formula">{{ fmtPercent(totals.chgProfit) }}</span></td>
              <td class="cell-computed" :class="{ 'val-exceed': Math.abs(totals.chgMargin) > 0.05 }"><span class="has-formula">{{ fmtPercent(totals.chgMargin) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>


      <!-- 同行业对比 -->
      <div class="industry-section">
        <h5 class="sub-title">同行业对比</h5>
        <table class="industry-table" border="1" cellpadding="0" cellspacing="0">
          <thead>
            <tr>
              <th class="col-name">企业/水平</th>
              <th>销量</th>
              <th>平均单价</th>
              <th>收入金额</th>
              <th>销量(成本)</th>
              <th>单位成本</th>
              <th>成本金额</th>
              <th><el-tooltip content="公式: 收入-成本" placement="top" :show-after="200"><span class="has-formula">毛利</span></el-tooltip></th>
              <th><el-tooltip content="公式: IF(收入=0,0,毛利/收入)" placement="top" :show-after="200"><span class="has-formula">毛利率</span></el-tooltip></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(ind, idx) in computedIndustry" :key="idx">
              <td class="cell-name">{{ ind.name }}</td>
              <td class="cell-input"><el-input-number v-model="activeProduct.industry[idx].revQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.industry[idx].revPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.industry[idx].revAmt" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.industry[idx].costQty" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.industry[idx].costPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-input"><el-input-number v-model="activeProduct.industry[idx].costAmt" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateProduct" /></td>
              <td class="cell-computed">
                <el-tooltip content="收入-成本" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtAmt(ind.profit) }}</span>
                </el-tooltip>
              </td>
              <td class="cell-computed">
                <el-tooltip content="IF(收入=0,0,毛利/收入)" placement="top" :show-after="200">
                  <span class="has-formula">{{ fmtPercent(ind.margin) }}</span>
                </el-tooltip>
              </td>
            </tr>
            <!-- 本产品合计对比行 -->
            <tr class="row-total">
              <td class="cell-name"><strong>本产品合计</strong></td>
              <td class="cell-computed">{{ fmtAmt(totals.revQty) }}</td>
              <td class="cell-computed"><span class="has-formula">{{ fmtAmt(totals.curAvgPrice) }}</span></td>
              <td class="cell-computed">{{ fmtAmt(totals.revAmt) }}</td>
              <td class="cell-computed">{{ fmtAmt(totals.costQty) }}</td>
              <td class="cell-computed"><span class="has-formula">{{ fmtAmt(totals.curAvgCost) }}</span></td>
              <td class="cell-computed">{{ fmtAmt(totals.costAmt) }}</td>
              <td class="cell-computed"><span class="has-formula">{{ fmtAmt(totals.curProfit) }}</span></td>
              <td class="cell-computed"><span class="has-formula">{{ fmtPercent(totals.curMargin) }}</span></td>
            </tr>
          </tbody>
        </table>
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
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-8-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="4" :model-value="auditNote" :disabled="isReadonly"
        placeholder="1.毛利率变动异常原因分析；2.XX产品单价变动异常，采用审计抽样方法检查该类型产品单价变动的合理性，判断销售给关联方或关系密切的重要客户的产品价格是否合理，有无以低价或高价结算的方法，相互之间有无转移利润的现象，见<产品销售价格分析D4-11>。"
        @input="(v: string) => updateNote(v)" />
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
        <p>1. 本表按重要产品/服务逐个分析，每个产品单独分析12个月的销量、单价、收入、成本、毛利及毛利率。</p>
        <p>2. 除分析主要产品和服务之外，还需要考虑被审计单位是否有联产品和副产品产出；如有，应同时分析联产品和副产品的毛利变化情况。</p>
        <p>3. 对于IPO、上市公司等审计业务，还需要考虑产品毛利率与同行业可比公司的对比分析。</p>
        <p>4. 关注各月毛利率波动的合理性，如存在显著异常需进一步分析原因并记录于审计说明中。</p>
      </div>
    </details>
  </div>
</template>



<style scoped>
.d4-product-margin { padding: 16px; }
.sec { margin-bottom: 20px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 8px; }
.sec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sec-actions { display: flex; gap: 8px; align-items: center; }
.objective-list { padding: 10px 14px; background: #f5f7fa; border-radius: 6px; }
.objective-item { margin: 0 0 4px; font-size: var(--wp-font-size, 13px); color: #303133; line-height: 1.7; }
.objective-item:last-child { margin-bottom: 0; }

/* 产品选择器 */
.product-selector { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }

/* 月度明细表 */
.monthly-table-wrap { overflow-x: auto; margin-bottom: 16px; }
.monthly-table { width: 100%; border-collapse: collapse; font-size: var(--wp-font-size, 13px); white-space: nowrap; }
.monthly-table th, .monthly-table td { border: 1px solid #dcdfe6; padding: 4px 5px; text-align: center; }
.monthly-table th { background: #f5f7fa; font-weight: 600; font-size: 12px; }
.group-cur { background: #ecf5ff; }
.group-prior { background: #f0f9eb; }
.group-formula { background: #fdf6ec; }
.group-change { background: #fef0f0; }
.col-month { min-width: 40px; }
.col-num { min-width: 68px; }
.col-amt { min-width: 88px; }
.col-formula { min-width: 72px; }
.col-change { min-width: 68px; }
.cell-month { font-weight: 500; background: #fafafa; }
.cell-input { padding: 2px; }
.cell-computed { background: #fafafa; font-size: var(--wp-font-size, 13px); text-align: right; padding-right: 6px; }
.row-total td { background: #f5f7fa; font-weight: 600; }
.num-cell { width: 100%; }
.num-cell :deep(.el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); padding: 0 4px; }
.has-formula { border-bottom: 1px dashed #909399; cursor: help; }
.val-exceed { color: #f56c6c; font-weight: 600; }

/* 同行业对比 */
.industry-section { margin-top: 16px; }
.sub-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; margin: 0 0 8px; }
.industry-table { width: 100%; border-collapse: collapse; font-size: var(--wp-font-size, 13px); white-space: nowrap; }
.industry-table th, .industry-table td { border: 1px solid #dcdfe6; padding: 4px 6px; text-align: center; }
.industry-table th { background: #f5f7fa; font-weight: 600; font-size: 12px; }
.col-name { min-width: 100px; text-align: left; }
.cell-name { text-align: left; font-weight: 500; padding-left: 8px; }

/* 编制提示折叠 */
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #f0f7ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { font-size: var(--wp-font-size, 13px); font-weight: 500; cursor: pointer; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.8; }
.guidance-content p { margin: 0 0 4px; }
</style>
