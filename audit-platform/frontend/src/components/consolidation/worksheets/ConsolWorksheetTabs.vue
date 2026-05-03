<template>
  <div class="cw-layout">
    <!-- 左侧：表样导航 -->
    <aside class="cw-nav" :style="{ width: navWidth + 'px' }">
      <div class="cw-nav-header">
        <span class="cw-nav-title">合并工作底稿</span>
        <el-tooltip content="合并流程：基础数据→净资产归集→权益法模拟→抵消分录→汇总核查" placement="right">
          <span style="cursor:help;font-size:12px;color:#999">ⓘ</span>
        </el-tooltip>
      </div>
      <div class="cw-nav-list">
        <template v-for="group in navGroups" :key="group.key">
          <div class="cw-nav-group" @click="groupCollapsed[group.key] = !groupCollapsed[group.key]">
            <div class="cw-nav-group-left">
              <span class="cw-nav-group-num">{{ group.step }}</span>
              <span class="cw-nav-group-label">{{ group.label }}</span>
            </div>
            <div class="cw-nav-group-right">
              <span class="cw-nav-group-count">{{ group.sheets.length }}表</span>
              <span class="cw-nav-group-arrow">{{ group.collapsed ? '›' : '‹' }}</span>
            </div>
          </div>
          <template v-if="!group.collapsed">
            <div v-for="sheet in group.sheets" :key="sheet.key"
              class="cw-nav-item" :class="{ 'cw-nav-item--active': activeSheet === sheet.key }"
              @click="activeSheet = sheet.key">
              <el-icon :size="14"><component :is="sheet.icon" /></el-icon>
              <div class="cw-nav-item-text">
                <span class="cw-nav-item-label">{{ sheet.label }}</span>
                <span class="cw-nav-item-desc">{{ sheet.desc }}</span>
              </div>
              <el-tag v-if="sheet.tag" :type="sheet.tagType" size="small" effect="plain" style="flex-shrink:0">{{ sheet.tag }}</el-tag>
            </div>
          </template>
        </template>
      </div>
    </aside>
    <div class="cw-resizer" @mousedown="startResize" />
    <!-- 右侧：表样内容 -->
    <main class="cw-content">
      <SubsidiaryInfoSheet v-if="activeSheet === 'info'" v-model="data.subsidiaryInfo"
        @save="onSave('基本信息表', $event)" @open-share-change="onOpenShareChange" @open-formula="onOpenFormula" />
      <InvestmentCostSheet v-else-if="activeSheet === 'cost'" v-model="data.investmentCost"
        @save="onSave('投资明细-成本法', $event)" @open-formula="onOpenFormula" />
      <InvestmentEquitySheet v-else-if="activeSheet === 'equity_inv'" v-model="data.investmentEquity"
        @save="onSave('投资明细-权益法', $event)" @open-formula="onOpenFormula" />
      <NetAssetSheet v-else-if="activeSheet === 'net_asset'" :companies="companyColumns" v-model="data.netAsset"
        @save="onSave('净资产表', $event)" @open-formula="onOpenFormula"
        @restore-defaults="data.netAsset = buildNetAsset()" />
      <EquitySimSheet v-else-if="activeSheet === 'equity_sim'" :companies="companyColumns"
        :direct-rows="data.equitySimDirect" :indirect-sections="computedIndirectSections"
        :net-asset-data="data.netAsset"
        @save="onSave('模拟权益法', $event)" @open-formula="onOpenFormula" />
      <EliminationSheet v-else-if="activeSheet === 'elimination'" :companies="companyColumns"
        :equity-rows="data.elimEquity" :income-rows="data.elimIncome" :cross-rows="data.elimCross"
        :imported-entries="allImportedEntries"
        @save="onSave('合并抵消分录', $event)" @open-formula="onOpenFormula"
        @goto-sheet="(k: string) => activeSheet = k" />
      <CapitalReserveSheet v-else-if="activeSheet === 'capital'" :companies="companyColumns"
        v-model="data.capitalReserve" :elimination-data="elimSummaryForCapital"
        @save="onSave('资本公积变动', $event)" @open-formula="onOpenFormula" />
      <!-- 动态股比变动表 -->
      <ShareChangeSheet v-else-if="activeSheet.startsWith('share_change_')"
        :key="activeSheet"
        :change-times="activeShareChangeTimes"
        :companies="activeShareChangeCompanies"
        :all-companies="companyColumns"
        :indirect-companies="indirectCompanyList"
        @save="onShareChangeSave" @open-formula="onOpenFormula" />
      <!-- 汇总计算表 -->
      <PostElimInvestSheet v-else-if="activeSheet === 'post_invest'"
        :companies="companyColumns" :investment-cost="data.investmentCost"
        :investment-equity="data.investmentEquity" :equity-sim-direct="data.equitySimDirect"
        :elim-equity="data.elimEquity" @save="onSave('抵消后长投', $event)" @open-formula="onOpenFormula"
        @goto-sheet="(k: string) => activeSheet = k" />
      <PostElimIncomeSheet v-else-if="activeSheet === 'post_income'"
        :companies="companyColumns" :investment-cost="data.investmentCost"
        :equity-sim-direct="data.equitySimDirect" :elim-income="data.elimIncome"
        @save="onSave('抵消后投资收益', $event)"
        @goto-sheet="(k: string) => activeSheet = k" @open-formula="onOpenFormula" />
      <MinorityInterestSheet v-else-if="activeSheet === 'minority'"
        :companies="companyColumns" :net-asset-data="data.netAsset"
        :equity-sim-direct="data.equitySimDirect" :elim-equity="data.elimEquity"
        :elim-income="data.elimIncome" @save="onSave('少数股东权益损益', $event)"
        @goto-sheet="(k: string) => activeSheet = k" @open-formula="onOpenFormula" />
      <!-- 内部抵消表 -->
      <InternalArApSheet v-else-if="activeSheet === 'internal_arap'"
        :companies="companyColumns" @save="onSave('内部往来抵消', $event)" @open-formula="onOpenFormula"
        @entries-changed="(e: any[]) => internalEntries.arap = e" />
      <InternalTradeSheet v-else-if="activeSheet === 'internal_trade'"
        :companies="companyColumns" @save="onSave('内部交易抵消', $event)" @open-formula="onOpenFormula"
        @entries-changed="(e: any[]) => internalEntries.trade = e" />
      <InternalCashFlowSheet v-else-if="activeSheet === 'internal_cashflow'"
        :companies="companyColumns" @save="onSave('内部现金流抵消', $event)" @open-formula="onOpenFormula"
        @entries-changed="(e: any[]) => internalEntries.cashflow = e" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, markRaw, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { List, Coin, TrendCharts, DataBoard, SetUp, Tickets, PieChart } from '@element-plus/icons-vue'
import { getConsolScope } from '@/services/consolidationApi'
import { loadAllWorksheetData, saveWorksheetData } from '@/services/consolWorksheetDataApi'
import SubsidiaryInfoSheet from './SubsidiaryInfoSheet.vue'
import InvestmentCostSheet from './InvestmentCostSheet.vue'
import InvestmentEquitySheet from './InvestmentEquitySheet.vue'
import NetAssetSheet from './NetAssetSheet.vue'
import EquitySimSheet from './EquitySimSheet.vue'
import EliminationSheet from './EliminationSheet.vue'
import CapitalReserveSheet from './CapitalReserveSheet.vue'
import ShareChangeSheet from './ShareChangeSheet.vue'
import PostElimInvestSheet from './PostElimInvestSheet.vue'
import PostElimIncomeSheet from './PostElimIncomeSheet.vue'
import MinorityInterestSheet from './MinorityInterestSheet.vue'
import InternalArApSheet from './InternalArApSheet.vue'
import InternalTradeSheet from './InternalTradeSheet.vue'
import InternalCashFlowSheet from './InternalCashFlowSheet.vue'

interface SubsidiaryInfoRow {
  company_name: string; company_code: string; account_subject: string
  accounting_method: string; holding_type: string; indirect_holder: string; share_changed: string; change_times: number
  acquisition_date: string; merge_type: string; first_consol_date: string
  non_common_cost: number | null; non_common_ratio: number | null
  common_cost: number | null; common_ratio: number | null
  no_consol_cost: number | null; no_consol_ratio: number | null
  disposal_date: string; disposal_amount: number | null; disposal_ratio: number | null
  pre_disposal_reduce: string; pre_disposal_times: number | null
  post_disposal_reduce: string; post_disposal_times: number | null
}
interface NetAssetRow {
  seq: string; item: string; total: number | null; parent: number | null
  values: (number | null)[]; indent?: number; bold?: boolean
  isHeader?: boolean; isComputed?: boolean; section?: string
}
interface EquitySimRow {
  seq: string; step: string; direction: string; subject: string; detail: string
  total: number | null; values?: (number | null)[]; isStep?: boolean; isComputed?: boolean
}
interface IndirectSection {
  companyName: string; ratio: number; rows: EquitySimRow[]
  endLongInvest: number; endNetAssetShare: number; difference: number; diffReason: string
}
interface ElimRow {
  direction: string; subject: string; detail?: string
  total?: number | null; values?: (number | null)[]; isComputed?: boolean
}
interface CapitalReserveRow {
  item: string; total: number | null; elimAdj: number | null; parentVal: number | null
  values?: (number | null)[]; bold?: boolean; isComputed?: boolean; fromElim?: boolean; isDiff?: boolean; note?: string
}
interface NetAssetChangeRow {
  item: string; before: number | null; after: (number | null)[]
  indent?: number; bold?: boolean; isHeader?: boolean
}

const EQUITY_ITEMS = [
  '实收资本（或股本）', '其他权益工具', '资本公积', '减：库存股',
  '其他综合收益', '专项储备', '盈余公积', '△一般风险准备', '未分配利润',
]

const staticSheets = [
  { key: 'info', label: '基本信息表', desc: '子企业清单·核算方式·持股变动', icon: markRaw(List), tag: '基础', tagType: '' as const },
  { key: 'cost', label: '投资明细-成本法和公允值', desc: '期初→增加→减少→期末', icon: markRaw(Coin), tag: '基础', tagType: '' as const },
  { key: 'equity_inv', label: '投资明细-权益法', desc: '权益法长投台账', icon: markRaw(TrendCharts), tag: '基础', tagType: '' as const },
  { key: 'net_asset', label: '净资产表', desc: '净资产和损益变动·长投校对', icon: markRaw(DataBoard), tag: '核心', tagType: 'warning' as const },
  { key: 'equity_sim', label: '模拟权益法', desc: '直接持股+间接持股·9步模拟', icon: markRaw(SetUp), tag: '引擎', tagType: 'danger' as const },
  { key: 'elimination', label: '合并抵消分录', desc: '权益抵消·损益抵消·交叉持股', icon: markRaw(Tickets), tag: '输出', tagType: 'success' as const },
  { key: 'capital', label: '资本公积变动', desc: '从抵消分录提取·差异核查', icon: markRaw(PieChart), tag: '核查', tagType: 'info' as const },
  { key: 'post_invest', label: '抵消后长投明细', desc: '账面+模拟-抵消=合并列示数', icon: markRaw(DataBoard), tag: '汇总', tagType: 'success' as const },
  { key: 'post_income', label: '抵消后投资收益', desc: '红利+模拟-还原-抵消', icon: markRaw(Coin), tag: '汇总', tagType: 'success' as const },
  { key: 'minority', label: '少数股东权益损益', desc: '净资产×少数比例·超额亏损', icon: markRaw(PieChart), tag: '汇总', tagType: 'success' as const },
  { key: 'internal_arap', label: '内部往来抵消', desc: '债务方×债权方·账龄·坏账', icon: markRaw(Tickets), tag: '抵消', tagType: 'warning' as const },
  { key: 'internal_trade', label: '内部交易抵消', desc: '卖方×买方·未实现利润', icon: markRaw(Tickets), tag: '抵消', tagType: 'warning' as const },
  { key: 'internal_cashflow', label: '内部现金流抵消', desc: '按现金流量表项目配对', icon: markRaw(Tickets), tag: '抵消', tagType: 'warning' as const },
]

// 从基本信息表提取有股比变动的企业，动态生成导航项
const shareChangeSheets = computed(() => {
  const sheets: any[] = []
  const changedCompanies = data.subsidiaryInfo.filter(
    (r: SubsidiaryInfoRow) => r.share_changed === '是' && r.change_times > 0 && r.company_name
  )
  // 按变动次数分组
  for (const times of [1, 2, 3] as const) {
    const companies = changedCompanies.filter((r: SubsidiaryInfoRow) => r.change_times === times)
    if (companies.length > 0) {
      const names = companies.map((r: SubsidiaryInfoRow) => r.company_name).join('、')
      sheets.push({
        key: `share_change_${times}`,
        label: `股比变${times}次`,
        desc: names.length > 16 ? names.slice(0, 16) + '...' : names,
        icon: markRaw(TrendCharts),
        tag: `${companies.length}家`,
        tagType: 'warning' as const,
        _times: times,
        _companies: companies,
      })
    }
  }
  return sheets
})

const sheetList = computed(() => {
  const list = [...staticSheets]
  const simIdx = list.findIndex(s => s.key === 'equity_sim')
  list.splice(simIdx, 0, ...shareChangeSheets.value)
  return list
})

// ─── 树形分组导航 ─────────────────────────────────────────────────────────────
const groupCollapsed = reactive<Record<string, boolean>>({ g1: false, g2: false, g3: false, g4: true, g5: false, g6: true })

const navGroups = computed(() => [
  {
    key: 'g1', label: '基础数据', step: '1',
    collapsed: groupCollapsed.g1,
    sheets: sheetList.value.filter(s => ['info', 'cost', 'equity_inv'].includes(s.key)),
  },
  {
    key: 'g2', label: '净资产归集', step: '2',
    collapsed: groupCollapsed.g2,
    sheets: sheetList.value.filter(s => s.key === 'net_asset' || s.key.startsWith('share_change_')),
  },
  {
    key: 'g3', label: '权益法模拟', step: '3',
    collapsed: groupCollapsed.g3,
    sheets: sheetList.value.filter(s => s.key === 'equity_sim'),
  },
  {
    key: 'g4', label: '内部抵消', step: '4',
    collapsed: groupCollapsed.g4,
    sheets: sheetList.value.filter(s => ['internal_arap', 'internal_trade', 'internal_cashflow'].includes(s.key)),
  },
  {
    key: 'g5', label: '合并抵消', step: '5',
    collapsed: groupCollapsed.g5,
    sheets: sheetList.value.filter(s => ['elimination', 'capital'].includes(s.key)),
  },
  {
    key: 'g6', label: '汇总核查', step: '✓',
    collapsed: groupCollapsed.g6,
    sheets: sheetList.value.filter(s => ['post_invest', 'post_income', 'minority'].includes(s.key)),
  },
])

const activeSheet = ref('info')

// ─── 从合并范围加载子企业列表 ────────────────────────────────────────────────
const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)
const scopeCompanies = ref<{ name: string; code: string; ratio: number }[]>([])

async function loadConsolScope() {
  if (!projectId.value) return
  try {
    // 优先从合并范围获取
    const items = await getConsolScope(projectId.value, year.value)
    if (Array.isArray(items) && items.length) {
      scopeCompanies.value = items
        .filter((s: any) => s.is_included && s.company_code)
        .map((s: any) => ({
          name: s.company_name || s.company_code,
          code: s.company_code,
          ratio: Number(s.ownership_ratio) || 0,
        }))
      return
    }
  } catch { /* ignore */ }
  // 降级：从集团架构树获取直接下级
  try {
    const { getWorksheetTree } = await import('@/services/consolidationApi')
    const res = await getWorksheetTree(projectId.value)
    if (res?.tree?.children?.length) {
      scopeCompanies.value = res.tree.children.map((c: any) => ({
        name: c.company_name || c.name || c.company_code,
        code: c.company_code,
        ratio: Number(c.shareholding) || 0,
      }))
    }
  } catch { /* ignore */ }
}

onMounted(async () => {
  loadConsolScope()
  document.addEventListener('gt-formula-changed', onFormulaChanged)
  // 从后端加载已保存的工作底稿数据
  if (projectId.value) {
    try {
      const saved = await loadAllWorksheetData(projectId.value, year.value)
      if (saved.info?.rows) data.subsidiaryInfo = saved.info.rows
      if (saved.cost?.rows) data.investmentCost = saved.cost.rows
      if (saved.equity_inv?.rows) data.investmentEquity = saved.equity_inv.rows
      if (saved.net_asset?.rows) data.netAsset = saved.net_asset.rows
      if (saved.equity_sim?.rows) {
        if (saved.equity_sim.rows.direct) data.equitySimDirect = saved.equity_sim.rows.direct
        if (saved.equity_sim.rows.indirect) data.equitySimIndirect = saved.equity_sim.rows.indirect
      }
      if (saved.elimination?.rows) {
        // elimination 的 rows 可能包含 equity/income/cross
      }
      if (saved.capital?.rows) data.capitalReserve = saved.capital.rows
    } catch { /* 首次使用无数据，忽略 */ }
  }
})
onUnmounted(() => {
  document.removeEventListener('gt-formula-changed', onFormulaChanged)
})

function onFormulaChanged(_e: Event) {
  // 公式保存/应用后，重新加载合并范围数据（公式可能影响计算结果）
  ElMessage.info('公式已更新，数据同步中...')
  loadConsolScope()
  // TODO: 后续接入公式引擎后，这里触发重算各表的公式列
}

// ─── 拖拽 ─────────────────────────────────────────────────────────────────────
const navWidth = ref(260)
let rsx = 0, rsw = 0
function startResize(e: MouseEvent) {
  rsx = e.clientX; rsw = navWidth.value
  document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onResize); document.addEventListener('mouseup', stopResize)
}
function onResize(e: MouseEvent) { navWidth.value = Math.max(200, Math.min(400, rsw + (e.clientX - rsx))) }
function stopResize() {
  document.body.style.cursor = ''; document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onResize); document.removeEventListener('mouseup', stopResize)
}

// ─── 默认数据构建 ─────────────────────────────────────────────────────────────
function mkEmptyRow(): SubsidiaryInfoRow {
  return { company_name: '', company_code: '', account_subject: '', accounting_method: '',
    holding_type: '直接', indirect_holder: '', share_changed: '否', change_times: 0, acquisition_date: '', merge_type: '', first_consol_date: '',
    non_common_cost: null, non_common_ratio: null, common_cost: null, common_ratio: null,
    no_consol_cost: null, no_consol_ratio: null, disposal_date: '', disposal_amount: null, disposal_ratio: null,
    pre_disposal_reduce: '', pre_disposal_times: null, post_disposal_reduce: '', post_disposal_times: null }
}

function buildNetAsset(): NetAssetRow[] {
  const r: NetAssetRow[] = []
  const mk = (seq: string, item: string, o: Partial<NetAssetRow> = {}): NetAssetRow =>
    ({ seq, item, total: null, parent: null, values: [], ...o })
  r.push(mk('1', '所有者权益/股东权益', { isHeader: true, bold: true }))
  r.push(mk('', '期初合计：', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1 })))
  r.push(mk('', '本期增加', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1 })))
  r.push(mk('', '本期减少', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1 })))
  r.push(mk('', '期末金额', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => r.push(mk('', i, { indent: 1, isComputed: true })))
  r.push(mk('2', '利润及利润分配表', { isHeader: true, bold: true }))
  r.push(mk('', '一、期初金额', { bold: true }))
  r.push(mk('', '二、本年增减变动金额', { bold: true, isComputed: true }))
  r.push(mk('', '（一）综合收益总额', { indent: 1 }))
  r.push(mk('', '其中：当期归母净利润', { indent: 2 }))
  r.push(mk('', '（二）所有者投入和减少资本', { indent: 1, isComputed: true }))
  for (const s of ['2-1所有者投入的普通股','2-2其他权益工具持有者投入资本','2-3股份支付计入所有者权益的金额','2-4其他']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '（三）专项储备提取和使用', { indent: 1, isComputed: true }))
  for (const s of ['3-1提取专项储备','3-2使用专项储备']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '（四）利润分配', { indent: 1, isComputed: true }))
  for (const s of ['4-1提取盈余公积','4-1-1法定公积金','4-1-2任意公积金','4-1-3#储备基金','4-1-4#企业发展基金','4-1-5#利润归还投资','4-2△提取一般风险准备','4-3对所有者（或股东）的分配','4-4其他']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '（五）所有者权益内部结转', { indent: 1, isComputed: true }))
  for (const s of ['5-1资本公积转增资本（或股本）','5-2盈余公积转增资本（或股本）','5-3弥补亏损','5-4 设定受益计划变动额结转留存收益','5-5其他综合收益结转留存收益','5-6其他']) r.push(mk('', s, { indent: 2 }))
  r.push(mk('', '三、本年年末余额', { bold: true, isComputed: true }))
  r.push(mk('3', '资本公积变动表', { isHeader: true, bold: true }))
  r.push(mk('', '期初金额')); r.push(mk('', '其中：国有独享资本公积', { indent: 1 }))
  r.push(mk('', '本期变动', { isComputed: true }))
  for (const s of ['其中：资本溢价','其他资本公积','国有独享资本公积']) r.push(mk('', s, { indent: 1 }))
  r.push(mk('', '期末金额', { bold: true, isComputed: true }))
  r.push(mk('', '其中：国有独享资本公积', { indent: 1, isComputed: true }))
  return r
}

function buildEquitySim(): EquitySimRow[] {
  const r: EquitySimRow[] = []
  const mk = (seq: string, step: string, dir: string, subj: string, det = '', o: Partial<EquitySimRow> = {}): EquitySimRow =>
    ({ seq, step, direction: dir, subject: subj, detail: det, total: null, values: [], ...o })
  r.push(mk('1','期初长投模拟','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','损益调整')); r.push(mk('','','借','长期股权投资','其他权益变动'))
  r.push(mk('','','贷','年初未分配利润')); r.push(mk('','','贷','资本公积')); r.push(mk('','','贷','其他综合收益'))
  r.push(mk('','','贷','专项储备')); r.push(mk('','','贷','其他权益工具')); r.push(mk('','','贷','△一般风险准备'))
  r.push(mk('2','模拟当期长期股权投资','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','损益调整')); r.push(mk('','','借','长期股权投资','其他权益变动'))
  r.push(mk('','','贷','投资收益')); r.push(mk('','','贷','资本公积')); r.push(mk('','','贷','其他综合收益'))
  r.push(mk('','','贷','专项储备')); r.push(mk('','','贷','其他权益工具')); r.push(mk('','','贷','△一般风险准备'))
  r.push(mk('','','贷','2-3股份支付计入所有者权益的金额','（二）所有者投入和减少资本'))
  r.push(mk('','','贷','2-4其他','（二）所有者投入和减少资本'))
  r.push(mk('','','贷','4-3对所有者的分配','（四）利润分配'))
  r.push(mk('','','贷','4-4其他','（四）利润分配'))
  r.push(mk('3','还原分红影响','','','',{isStep:true}))
  r.push(mk('','','借','投资收益')); r.push(mk('','','贷','长期股权投资','损益调整'))
  r.push(mk('4','股比发生变动对享有净资产的影响','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','损益调整')); r.push(mk('','','借','长期股权投资','其他权益变动'))
  r.push(mk('','','贷','资本公积')); r.push(mk('','','贷','投资收益'))
  r.push(mk('','模拟后期末长期股权投资','','','',{isStep:true}))
  r.push(mk('','','借','长期股权投资','投资成本')); r.push(mk('','','借','长期股权投资','损益调整'))
  r.push(mk('','','借','长期股权投资','其他权益变动')); r.push(mk('','','借','长期股权投资','资产减值准备'))
  r.push(mk('','','','长期股权投资','小计',{isComputed:true}))
  return r
}

function buildElimEquity(): ElimRow[] {
  const mk = (d: string, s: string, det = ''): ElimRow => ({ direction: d, subject: s, detail: det, values: [] })
  return [mk('借','实收资本（或股本）'),mk('借','其他权益工具'),mk('借','资本公积'),mk('借','减：库存股'),
    mk('借','其他综合收益'),mk('借','专项储备'),mk('借','盈余公积'),mk('借','△一般风险准备'),mk('借','未分配利润'),
    mk('借','商誉'),mk('借','长期股权投资','减值准备'),mk('贷','长期股权投资','投资成本'),
    mk('贷','长期股权投资','损益调整'),mk('贷','长期股权投资','其他权益变动'),mk('贷','少数股东权益')]
}
function buildElimIncome(): ElimRow[] {
  const mk = (d: string, s: string, det = ''): ElimRow => ({ direction: d, subject: s, detail: det, values: [] })
  return [mk('借','年初未分配利润'),mk('借','投资收益'),mk('借','少数股权损益'),
    mk('贷','2-3股份支付计入所有者权益的金额','（二）所有者投入和减少资本'),mk('贷','2-4其他','（二）所有者投入和减少资本'),
    mk('贷','4-1提取盈余公积','（四）利润分配'),mk('贷','4-1-1法定公积金','（四）利润分配'),
    mk('贷','4-1-2任意公积金','（四）利润分配'),mk('贷','4-1-3#储备基金','（四）利润分配'),
    mk('贷','4-1-4#企业发展基金','（四）利润分配'),mk('贷','4-1-5#利润归还投资','（四）利润分配'),
    mk('贷','4-2△提取一般风险准备','（四）利润分配'),mk('贷','4-3对所有者（或股东）的分配','（四）利润分配'),
    mk('贷','4-4其他','（四）利润分配')]
}
function buildElimCross(): ElimRow[] {
  return [{direction:'借',subject:'少数股权权益',values:[]},{direction:'贷',subject:'长期股权投资',values:[]},
    {direction:'借',subject:'投资收益',values:[]},{direction:'贷',subject:'少数股权损益',values:[]}]
}
function buildCapitalReserve(): CapitalReserveRow[] {
  const mk = (item: string, o: Partial<CapitalReserveRow> = {}): CapitalReserveRow =>
    ({ item, total: null, elimAdj: null, parentVal: null, values: [], ...o })
  return [mk('期初金额',{bold:true}),mk('当期变动',{isComputed:true}),mk('+权益法模拟',{fromElim:true}),
    mk('-合并抵消数',{fromElim:true}),mk('+自身报表变动'),mk('其他'),mk('期末金额',{bold:true,isComputed:true})]
}

// ─── 数据 ─────────────────────────────────────────────────────────────────────
const data = reactive({
  subsidiaryInfo: Array.from({ length: 5 }, () => mkEmptyRow()) as SubsidiaryInfoRow[],
  investmentCost: Array.from({ length: 5 }, () => ({
    company_name:'',company_code:'',current_dividend:null,open_ratio:null,open_cost:null,open_impairment:null,open_fv:null,
    add_ratio:null,add_cost:null,add_impairment:null,add_fv:null,reduce_ratio:null,reduce_cost:null,reduce_impairment:null,reduce_fv:null,
  })) as any[],
  investmentEquity: Array.from({ length: 5 }, () => ({
    company_name:'',company_code:'',open_ratio:null,open_amount:null,open_impairment:null,
    add_ratio:null,add_cost:null,add_income_adj:null,add_oci:null,add_other_equity:null,add_other:null,add_impairment:null,
    reduce_ratio:null,reduce_cost:null,reduce_dividend:null,reduce_other:null,reduce_impairment:null,
  })) as any[],
  netAsset: buildNetAsset(),
  equitySimDirect: buildEquitySim(),
  equitySimIndirect: [] as IndirectSection[],
  elimEquity: buildElimEquity(),
  elimIncome: buildElimIncome(),
  elimCross: buildElimCross(),
  capitalReserve: buildCapitalReserve(),
})

// 子企业列：优先从合并范围树获取，降级从基本信息表获取
const companyColumns = computed(() => {
  if (scopeCompanies.value.length) return scopeCompanies.value
  return data.subsidiaryInfo.filter((r: SubsidiaryInfoRow) => r.company_name)
    .map((r: SubsidiaryInfoRow) => ({
      name: r.company_name,
      code: r.company_code,
      ratio: r.non_common_ratio || r.common_ratio || r.no_consol_ratio || 0,
    }))
})

// 间接持股企业列表
const indirectCompanyList = computed(() => {
  return data.subsidiaryInfo
    .filter((r: SubsidiaryInfoRow) => r.holding_type === '间接' && r.company_name)
    .map((r: SubsidiaryInfoRow) => ({
      name: r.company_name, code: r.company_code,
      ratio: r.non_common_ratio || r.common_ratio || r.no_consol_ratio || 0,
      indirectHolder: r.indirect_holder || '',
    }))
})

// 间接持股模拟 sections（computed，从基本信息表动态生成）
const computedIndirectSections = computed(() => {
  if (data.equitySimIndirect.length > 0) return data.equitySimIndirect
  return indirectCompanyList.value.map(c => ({
    companyName: c.name,
    ratio: c.ratio,
    indirectHolder: c.indirectHolder || '',
    rows: buildEquitySim(),
    endLongInvest: 0, endNetAssetShare: 0, difference: 0, diffReason: '',
  }))
})

const elimSummaryForCapital = computed(() => {
  const nn = (v: any) => Number(v) || 0
  const elimRow = data.elimEquity.find((r: ElimRow) => r.subject === '资本公积')
  const elimCapital = elimRow ? (elimRow.values||[]).reduce((s: number, v: number|null) => s + nn(v), 0) : 0
  // 从模拟权益法提取资本公积贷方合计
  let equitySimCapital = 0
  for (const row of data.equitySimDirect) {
    if (row.isStep) continue
    if (row.subject === '资本公积' && row.direction === '贷') {
      equitySimCapital += (row.values || []).reduce((s: number, v: any) => s + nn(v), 0)
    }
  }
  return { elimCapital, equitySimCapital }
})

// ─── 股比变动（内联表，非弹窗） ─────────────────────────────────────────────
const activeShareChangeTimes = computed(() => {
  const m = activeSheet.value.match(/share_change_(\d)/)
  return m ? (Number(m[1]) as 1|2|3) : 1
})
const activeShareChangeCompanies = computed(() => {
  const times = activeShareChangeTimes.value
  return data.subsidiaryInfo
    .filter((r: SubsidiaryInfoRow) => r.share_changed === '是' && r.change_times === times && r.company_name)
    .map((r: SubsidiaryInfoRow) => ({
      name: r.company_name, code: r.company_code,
      ratio: r.non_common_ratio || r.common_ratio || r.no_consol_ratio || 0,
      accountSubject: r.account_subject, accountingMethod: r.accounting_method,
      holdingType: r.holding_type || '直接',
    }))
})

function onOpenShareChange(row: SubsidiaryInfoRow, times: number) {
  // 直接切换到对应的股比变动表
  activeSheet.value = `share_change_${times}`
}
function onShareChangeSave(d: any) {
  const key = `share_change_${activeShareChangeTimes.value}`
  doSave(key, d)
}
async function onSave(sheet: string, payload: any) {
  const keyMap: Record<string, string> = {
    '基本信息表': 'info', '投资明细-成本法': 'cost', '投资明细-权益法': 'equity_inv',
    '净资产表': 'net_asset', '模拟权益法': 'equity_sim', '合并抵消分录': 'elimination',
    '资本公积变动': 'capital', '抵消后长投': 'post_invest', '抵消后投资收益': 'post_income',
    '少数股东权益损益': 'minority', '内部往来抵消': 'internal_arap',
    '内部交易抵消': 'internal_trade', '内部现金流抵消': 'internal_cashflow',
  }
  const key = keyMap[sheet] || sheet
  await doSave(key, payload)
  // 基本信息表保存后刷新合并范围（影响子企业列）
  if (key === 'info') loadConsolScope()
}
async function doSave(sheetKey: string, payload: any) {
  if (!projectId.value) { ElMessage.warning('项目ID缺失'); return }
  try {
    const ok = await saveWorksheetData(projectId.value, year.value, sheetKey, { rows: payload })
    if (ok) {
      ElMessage.success(`${sheetKey} 已保存`)
    } else {
      ElMessage.error(`${sheetKey} 保存失败，请检查后端服务`)
    }
  } catch (err: any) {
    ElMessage.error('保存异常：' + (err.message || '网络错误'))
  }
}

// ─── 内部抵消分录汇总 ────────────────────────────────────────────────────────
const internalEntries = reactive<{ arap: any[]; trade: any[]; cashflow: any[] }>({
  arap: [], trade: [], cashflow: [],
})

// 从模拟权益法提取权益抵消/损益抵消分录（computed，不修改 reactive 数据）
const equitySimEntries = computed(() => {
  const entries: any[] = []
  const nn = (v: any) => Number(v) || 0
  const simRows = data.equitySimDirect
  if (!simRows?.length) return entries

  // 步骤1（期初模拟）的贷方行 → 权益抵消
  const step1Idx = simRows.findIndex((r: EquitySimRow) => r.step === '期初长投模拟' && r.isStep)
  if (step1Idx >= 0) {
    for (let j = step1Idx + 1; j < simRows.length; j++) {
      const r = simRows[j]
      if (r.isStep) break
      const amt = (r.values || []).reduce((s: number, v: any) => s + nn(v), 0)
      if (amt) entries.push({ source: '权益抵消', direction: r.direction, subject: r.subject, detail: r.detail || '', amount: amt, desc: '期初模拟' })
    }
  }

  // 步骤2（当期变动）→ 损益抵消
  const step2Idx = simRows.findIndex((r: EquitySimRow) => r.step === '模拟当期长期股权投资' && r.isStep)
  if (step2Idx >= 0) {
    for (let j = step2Idx + 1; j < simRows.length; j++) {
      const r = simRows[j]
      if (r.isStep) break
      const amt = (r.values || []).reduce((s: number, v: any) => s + nn(v), 0)
      if (amt) entries.push({ source: '损益抵消', direction: r.direction, subject: r.subject, detail: r.detail || '', amount: amt, desc: '当期变动' })
    }
  }

  // 步骤3（还原分红）
  const step3Idx = simRows.findIndex((r: EquitySimRow) => r.step === '还原分红影响' && r.isStep)
  if (step3Idx >= 0) {
    for (let j = step3Idx + 1; j < simRows.length; j++) {
      const r = simRows[j]
      if (r.isStep) break
      const amt = (r.values || []).reduce((s: number, v: any) => s + nn(v), 0)
      if (amt) entries.push({ source: '损益抵消', direction: r.direction, subject: r.subject, detail: r.detail || '', amount: amt, desc: '还原分红' })
    }
  }

  return entries
})

const allImportedEntries = computed(() => [
  ...equitySimEntries.value,
  ...internalEntries.arap,
  ...internalEntries.trade,
  ...internalEntries.cashflow,
])

function onOpenFormula(sheetKey: string) {
  document.dispatchEvent(new CustomEvent('gt-open-formula-manager', { detail: { nodeKey: sheetKey } }))
}
</script>

<style scoped>
.cw-layout { display: flex; height: calc(100vh - 120px); overflow: hidden; margin: -16px; }
.cw-nav {
  flex-shrink: 0; background: #fafafa; border-right: 1px solid var(--gt-color-border-light, #e8e4f0);
  display: flex; flex-direction: column; overflow: hidden;
}
.cw-nav-header {
  padding: 16px 16px 12px; border-bottom: 1px solid var(--gt-color-border-light, #e8e4f0); flex-shrink: 0;
}
.cw-nav-title { font-size: 15px; font-weight: 700; color: #333; }
.cw-nav-list { flex: 1; overflow-y: auto; padding: 8px; }
.cw-nav-item {
  display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px 8px 18px; margin: 1px 6px;
  border-radius: 6px; cursor: pointer; transition: all 0.15s;
}
.cw-nav-item:hover { background: rgba(75,45,119,0.04); }
.cw-nav-item--active {
  background: var(--gt-color-primary-bg, #f0edf5) !important;
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}
.cw-nav-item--active .cw-nav-item-label { color: var(--gt-color-primary, #4b2d77); font-weight: 600; }
.cw-nav-item-text { flex: 1; min-width: 0; }
.cw-nav-item-label { display: block; font-size: 13px; color: #333; line-height: 1.4; }
.cw-nav-item-desc { display: block; font-size: 11px; color: #999; margin-top: 2px; }
.cw-nav-group {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; margin: 6px 6px 2px; cursor: pointer;
  background: linear-gradient(135deg, #f0edf5, #e8e4f0); border-radius: 6px;
  user-select: none; transition: background 0.15s;
}
.cw-nav-group:hover { background: linear-gradient(135deg, #e8e4f0, #ddd8e8); }
.cw-nav-group:first-child { margin-top: 2px; }
.cw-nav-group-left { display: flex; align-items: center; gap: 8px; }
.cw-nav-group-num {
  width: 20px; height: 20px; border-radius: 50%; background: #4b2d77; color: #fff;
  font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.cw-nav-group-label { font-size: 12px; font-weight: 600; color: #333; }
.cw-nav-group-right { display: flex; align-items: center; gap: 6px; }
.cw-nav-group-count { font-size: 10px; color: #999; }
.cw-nav-group-arrow { font-size: 14px; color: #999; font-weight: 700; transition: transform 0.15s; }
.cw-resizer {
  width: 4px; cursor: col-resize; background: transparent; flex-shrink: 0;
  transition: background 0.15s;
}
.cw-resizer:hover, .cw-resizer:active { background: var(--gt-color-primary-lighter, #d8d0e8); }
.cw-content { flex: 1; min-width: 0; overflow: auto; padding: 16px; background: #fff; }
</style>
