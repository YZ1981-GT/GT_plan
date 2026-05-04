<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>股比变动{{ changeTimes }}次 — 净资产变动与权益法模拟</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', `consol_share_change_${changeTimes}`)">ƒx 公式</el-button>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="exportData">📤 导出数据</el-button>
        <el-button size="small" @click="fileInputRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" @click="$emit('save', allData)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>📋 共 <b>{{ companies.length }}</b> 家企业发生{{ changeTimes }}次股比变动。
        每家展示三栏：❶净资产变动（变动前→变动后）❷直接持股权益法模拟 ❸间接持股权益法模拟。
        模拟后长投小计将<b style="color:#e6a23c">自动回填</b>到模拟权益法主表。</span>
    </div>

    <!-- 每家企业独立区块 -->
    <div v-for="(comp, ci) in companies" :key="comp.code || ci" class="sc-company-block">
      <div class="sc-company-header">
        <span class="sc-company-idx">{{ ci + 1 }}</span>
        <span class="sc-company-name">{{ comp.name }}</span>
        <el-tag size="small" effect="plain" round>持股 {{ comp.ratio }}%</el-tag>
        <el-tag v-if="comp.accountSubject" size="small" type="info" effect="plain" round>{{ comp.accountSubject }}</el-tag>
        <span style="flex:1" />
        <span style="font-size:11px;color:#999">模拟后长投小计：</span>
        <span style="font-size:14px;font-weight:700;color:#4b2d77">{{ fmt(getEndInvest(ci)) }}</span>
      </div>

      <div class="sc-three-col">
        <!-- 第1栏：净资产变动 -->
        <div class="sc-col" :class="{ 'sc-col--collapsed': colCollapsed[`${ci}_na`] }">
          <div class="sc-col-title" @click="colCollapsed[`${ci}_na`] = !colCollapsed[`${ci}_na`]" style="cursor:pointer">
            <span>{{ colCollapsed[`${ci}_na`] ? '▶' : '▼' }} 📊 {{ comp.name }} — 净资产变动</span>
          </div>
          <el-table v-show="!colCollapsed[`${ci}_na`]" :data="companyData[ci]?.naRows || []" border size="small" class="sc-table" max-height="500"
            :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="naRowClass">
            <el-table-column prop="item" label="项目" width="180" fixed show-overflow-tooltip>
              <template #default="{ row }">
                <span :style="{ paddingLeft: (row.indent || 0) * 10 + 'px', fontWeight: row.bold ? 700 : 400 }">{{ row.item }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动前" width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.isComputed" class="sc-computed">{{ fmt(row.vals[0]) }}</span>
                <el-input-number v-else-if="!row.isHeader" v-model="row.vals[0]" size="small" :precision="2" :controls="false" style="width:100%" />
              </template>
            </el-table-column>
            <el-table-column v-for="t in changeTimes" :key="'na'+t"
              :label="changeTimes === 1 ? '变动后' : `第${t}次变动后`" width="110" align="right">
              <template #default="{ row }">
                <span v-if="row.isComputed" class="sc-computed">{{ fmt(row.vals[t]) }}</span>
                <el-input-number v-else-if="!row.isHeader" v-model="row.vals[t]" size="small" :precision="2" :controls="false" style="width:100%" />
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 拖拽分隔线 1-2 -->
        <div class="sc-resizer" @mousedown="startResize($event, ci, 0)"><div class="sc-resizer-bar"></div></div>

        <!-- 第2栏：直接持股权益法模拟 -->
        <div class="sc-col" :class="{ 'sc-col--collapsed': colCollapsed[`${ci}_direct`] }">
          <div class="sc-col-title" @click="colCollapsed[`${ci}_direct`] = !colCollapsed[`${ci}_direct`]" style="cursor:pointer">
            <span>{{ colCollapsed[`${ci}_direct`] ? '▶' : '▼' }} 🔄 {{ comp.name }} — 直接持股权益法模拟 ({{ comp.ratio }}%)</span>
          </div>
          <el-table v-show="!colCollapsed[`${ci}_direct`]" :data="companyData[ci]?.simRows || []" border size="small" class="sc-table" max-height="500"
            :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="simRowClass">
            <el-table-column prop="subject" label="科目" width="140" fixed show-overflow-tooltip>
              <template #default="{ row }">
                <span :style="{ fontWeight: row.isSection ? 700 : 400, color: row.isSection ? '#4b2d77' : '' }">{{ row.subject }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="明细" width="120" show-overflow-tooltip />
            <el-table-column label="变动前" align="center">
              <el-table-column label="借" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection" />
                  <span v-else-if="row.isRatio" class="sc-ratio-val">
                    <el-input-number v-model="row.dc[0]" size="small" :precision="6" :controls="false" style="width:80px" /><span style="color:#999;font-size:10px">%</span>
                  </span>
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[0]) }}</span>
                  <el-input-number v-else v-model="row.dc[0]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
              <el-table-column label="贷" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection || row.isRatio" />
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[1]) }}</span>
                  <el-input-number v-else v-model="row.dc[1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column v-for="t in changeTimes" :key="'sim'+t"
              :label="changeTimes === 1 ? '变动后' : `第${t}次变动后`" align="center">
              <el-table-column label="借" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection" />
                  <span v-else-if="row.isRatio" class="sc-ratio-val">
                    <el-input-number v-model="row.dc[t * 2]" size="small" :precision="6" :controls="false" style="width:80px" /><span style="color:#999;font-size:10px">%</span>
                  </span>
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[t * 2]) }}</span>
                  <el-input-number v-else v-model="row.dc[t * 2]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
              <el-table-column label="贷" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection || row.isRatio" />
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[t * 2 + 1]) }}</span>
                  <el-input-number v-else v-model="row.dc[t * 2 + 1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
            </el-table-column>
          </el-table>
        </div>

        <!-- 第3栏：间接持股权益法模拟（动态，可能多个） -->
        <template v-for="(indComp, ici) in indirectList" :key="'ind'+ici">
          <!-- 拖拽分隔线 2-3 -->
          <div class="sc-resizer" @mousedown="startResize($event, ci, ici + 1)"><div class="sc-resizer-bar"></div></div>
          <div class="sc-col" :class="{ 'sc-col--collapsed': colCollapsed[`${ci}_ind_${ici}`] }">
            <div class="sc-col-title sc-col-title--indirect" @click="colCollapsed[`${ci}_ind_${ici}`] = !colCollapsed[`${ci}_ind_${ici}`]" style="cursor:pointer">
              <span>{{ colCollapsed[`${ci}_ind_${ici}`] ? '▶' : '▼' }} 🔗 {{ indComp.name }} — 间接持股 {{ indComp.ratio }}%{{ indComp.indirectHolder ? '（通过' + indComp.indirectHolder + '）' : '' }}</span>
            </div>
          <el-table v-show="!colCollapsed[`${ci}_ind_${ici}`]" :data="getIndirectSimRows(ci, ici)" border size="small" class="sc-table" max-height="500"
            :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="simRowClass">
            <el-table-column prop="subject" label="科目" width="140" fixed show-overflow-tooltip>
              <template #default="{ row }">
                <span :style="{ fontWeight: row.isSection ? 700 : 400, color: row.isSection ? '#1a5fb4' : '' }">{{ row.subject }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="明细" width="120" show-overflow-tooltip />
            <el-table-column label="变动前" align="center">
              <el-table-column label="借" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection" />
                  <span v-else-if="row.isRatio" class="sc-ratio-val">
                    <el-input-number v-model="row.dc[0]" size="small" :precision="6" :controls="false" style="width:80px" /><span style="color:#999;font-size:10px">%</span>
                  </span>
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[0]) }}</span>
                  <el-input-number v-else v-model="row.dc[0]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
              <el-table-column label="贷" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection || row.isRatio" />
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[1]) }}</span>
                  <el-input-number v-else v-model="row.dc[1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column v-for="t in changeTimes" :key="'isim'+t"
              :label="changeTimes === 1 ? '变动后' : `第${t}次变动后`" align="center">
              <el-table-column label="借" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection" />
                  <span v-else-if="row.isRatio" class="sc-ratio-val">
                    <el-input-number v-model="row.dc[t * 2]" size="small" :precision="6" :controls="false" style="width:80px" /><span style="color:#999;font-size:10px">%</span>
                  </span>
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[t * 2]) }}</span>
                  <el-input-number v-else v-model="row.dc[t * 2]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
              <el-table-column label="贷" width="100" align="right">
                <template #default="{ row }">
                  <span v-if="row.isSection || row.isRatio" />
                  <span v-else-if="row.isSubtotal" class="sc-auto-val">{{ fmt(row.dc[t * 2 + 1]) }}</span>
                  <el-input-number v-else v-model="row.dc[t * 2 + 1]" size="small" :precision="2" :controls="false" style="width:100%" />
                </template>
              </el-table-column>
            </el-table-column>
          </el-table>
          </div>
        </template>
      </div>
    </div>

    <el-empty v-if="!companies.length" description="没有符合条件的企业（需在基本信息表设置股比变动并填写变动次数）" />
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

const EQUITY_ITEMS = ['实收资本（或股本）','其他权益工具','资本公积','减：库存股','其他综合收益','专项储备','盈余公积','△一般风险准备','未分配利润']

interface CompanyInfo { name: string; code: string; ratio: number; accountSubject?: string; accountingMethod?: string; holdingType?: string }
interface NARow { item: string; vals: (number | null)[]; indent?: number; bold?: boolean; isHeader?: boolean; isComputed?: boolean }
interface SimRow { subject: string; detail: string; dc: (number | null)[]; isSection?: boolean; isSubtotal?: boolean; isRatio?: boolean }

const props = defineProps<{
  changeTimes: 1 | 2 | 3
  companies: CompanyInfo[]
  allCompanies: { name: string; code?: string; ratio: number }[]
  indirectCompanies?: { name: string; code?: string; ratio: number; indirectHolder?: string }[]
}>()

const _emit = defineEmits<{
  (e: 'save', data: any): void
  (e: 'open-formula', key: string): void
}>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const colCount = computed(() => props.changeTimes + 1)
const dcCount = computed(() => colCount.value * 2)
const n = (v: any) => Number(v) || 0
const colCollapsed = reactive<Record<string, boolean>>({})

// ─── 拖拽分隔线 ─────────────────────────────────────────────────────────────
let resizeTarget: HTMLElement | null = null
let resizeStartX = 0
let resizeStartW = 0

function startResize(e: MouseEvent, _ci: number, _colIdx: number) {
  const el = (e.target as HTMLElement).closest('.sc-resizer')
  const prev = el?.previousElementSibling as HTMLElement
  if (!prev) return
  resizeTarget = prev
  resizeStartX = e.clientX
  resizeStartW = prev.offsetWidth
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}
function onResize(e: MouseEvent) {
  if (!resizeTarget) return
  const w = Math.max(250, resizeStartW + (e.clientX - resizeStartX))
  resizeTarget.style.width = w + 'px'
  resizeTarget.style.flexShrink = '0'
}
function stopResize() {
  resizeTarget = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
}

// 间接持股企业列表
const indirectList = computed(() => props.indirectCompanies || [])

// ─── 数据结构 ────────────────────────────────────────────────────────────────

const SIM_STRUCTURE: { s: string; d: string; sec?: boolean; sub?: boolean; ratio?: boolean }[] = [
  { s: '1.基础信息', d: '', sec: true },
  { s: '持股比例', d: '', ratio: true },
  { s: '2.权益法模拟', d: '', sec: true },
  { s: '2.1 期初模拟', d: '', sub: true },
  { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
  { s: '年初未分配利润', d: '' }, { s: '资本公积', d: '' }, { s: '其他综合收益', d: '' },
  { s: '专项储备', d: '' }, { s: '其他权益工具', d: '' }, { s: '△一般风险准备', d: '' },
  { s: '2.2 当期变动', d: '', sub: true },
  { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
  { s: '投资收益', d: '' }, { s: '资本公积', d: '' }, { s: '其他综合收益', d: '' },
  { s: '专项储备', d: '' }, { s: '其他权益工具', d: '' }, { s: '△一般风险准备', d: '' },
  { s: '2-3股份支付', d: '（二）所有者投入和减少资本' }, { s: '2-4其他', d: '（二）所有者投入和减少资本' },
  { s: '4-3对所有者的分配', d: '（四）利润分配' }, { s: '4-4其他', d: '（四）利润分配' },
  { s: '3.分红影响', d: '', sub: true },
  { s: '投资收益', d: '' }, { s: '长期股权投资', d: '损益调整' },
  { s: '4.股比变动影响', d: '', sub: true },
  { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
  { s: '资本公积', d: '' }, { s: '投资收益', d: '' },
  { s: '模拟后长投', d: '', sec: true },
  { s: '长期股权投资', d: '投资成本' }, { s: '长期股权投资', d: '损益调整' },
  { s: '长期股权投资', d: '其他权益变动' }, { s: '长期股权投资', d: '减值准备' },
  { s: '长期股权投资', d: '小计', sub: true },
]

function buildNARows(): NARow[] {
  const rows: NARow[] = []
  const mk = (item: string, opts: Partial<NARow> = {}): NARow =>
    ({ item, vals: new Array(colCount.value).fill(null), ...opts })
  rows.push(mk('所有者权益/股东权益', { isHeader: true, bold: true }))
  rows.push(mk('期初合计：', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  rows.push(mk('本期增加', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  rows.push(mk('本期减少', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  rows.push(mk('期末金额', { bold: true, isComputed: true }))
  EQUITY_ITEMS.forEach(i => rows.push(mk(i, { indent: 1 })))
  return rows
}

function buildSimRows(): SimRow[] {
  return SIM_STRUCTURE.map(r => ({
    subject: r.s, detail: r.d, dc: new Array(dcCount.value).fill(null),
    isSection: r.sec || false, isSubtotal: r.sub || false, isRatio: r.ratio || false,
  }))
}

// ─── 直接持股数据（每家企业一组） ────────────────────────────────────────────
const companyData = reactive<{ naRows: NARow[]; simRows: SimRow[] }[]>([])

// setup 阶段同步初始化
for (let ci = 0; ci < props.companies.length; ci++) {
  const cd = { naRows: buildNARows(), simRows: buildSimRows() }
  // 自动填充持股比例：变动前=当前比例，变动后默认0
  const ratioRow = cd.simRows.find(r => r.isRatio)
  if (ratioRow) {
    ratioRow.dc[0] = props.companies[ci].ratio
    // 变动后各列的借方也填0（用户可修改）
    for (let t = 1; t <= props.changeTimes; t++) {
      if (ratioRow.dc[t * 2] == null) ratioRow.dc[t * 2] = 0
    }
  }
  companyData.push(cd)
}

// props 变化时同步
watch(() => props.companies, (comps) => {
  while (companyData.length < comps.length) {
    const cd = { naRows: buildNARows(), simRows: buildSimRows() }
    const ratioRow = cd.simRows.find(r => r.isRatio)
    if (ratioRow) {
      ratioRow.dc[0] = comps[companyData.length]?.ratio ?? 0
      for (let t = 1; t <= props.changeTimes; t++) {
        if (ratioRow.dc[t * 2] == null) ratioRow.dc[t * 2] = 0
      }
    }
    companyData.push(cd)
  }
  companyData.length = comps.length
}, { deep: true })

// ─── 间接持股数据 ────────────────────────────────────────────────────────────
const indirectSimData = reactive<Record<string, SimRow[]>>({})

function getIndirectSimRows(ci: number, ici: number): SimRow[] {
  const key = `${ci}_${ici}`
  if (!indirectSimData[key]) {
    indirectSimData[key] = buildSimRows()
    const indComp = indirectList.value[ici]
    if (indComp) {
      const ratioRow = indirectSimData[key].find(r => r.isRatio)
      if (ratioRow) {
        ratioRow.dc[0] = indComp.ratio
        // 变动后各列默认0
        for (let t = 1; t <= props.changeTimes; t++) {
          if (ratioRow.dc[t * 2] == null) ratioRow.dc[t * 2] = 0
        }
      }
    }
  }
  return indirectSimData[key]
}

// ─── 自动计算 ────────────────────────────────────────────────────────────────

// 净资产汇总行自动求和
watch(companyData, () => {
  for (const cd of companyData) {
    for (let i = 0; i < cd.naRows.length; i++) {
      const row = cd.naRows[i]
      if (!row.isComputed || !row.bold || row.isHeader) continue
      const sums = new Array(colCount.value).fill(0)
      for (let j = i + 1; j < cd.naRows.length; j++) {
        const child = cd.naRows[j]
        if (child.bold || child.isHeader || (child.indent || 0) === 0) break
        if (child.isComputed) continue
        for (let k = 0; k < colCount.value; k++) sums[k] += n(child.vals[k])
      }
      for (let k = 0; k < colCount.value; k++) row.vals[k] = sums[k]
    }
    // 直接持股模拟小计行自动求和
    calcSimSubtotals(cd.simRows)
  }
}, { deep: true })

// 间接持股模拟小计行自动求和
watch(indirectSimData, () => {
  for (const key of Object.keys(indirectSimData)) {
    calcSimSubtotals(indirectSimData[key])
  }
}, { deep: true })

function calcSimSubtotals(rows: SimRow[]) {
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i]
    if (!row.isSubtotal) continue
    const sums = new Array(dcCount.value).fill(0)
    for (let j = i + 1; j < rows.length; j++) {
      const child = rows[j]
      if (child.isSection || child.isSubtotal) break
      for (let k = 0; k < dcCount.value; k++) sums[k] += n(child.dc[k])
    }
    for (let k = 0; k < dcCount.value; k++) row.dc[k] = sums[k]
  }
}

// ─── 回填数据 ────────────────────────────────────────────────────────────────
function getEndInvest(ci: number): number {
  const cd = companyData[ci]
  if (!cd) return 0
  const lastD = props.changeTimes * 2, lastC = lastD + 1
  const row = cd.simRows.find(r => r.subject === '长期股权投资' && r.detail === '小计')
  return row ? n(row.dc[lastD]) - n(row.dc[lastC]) : 0
}

const allData = computed(() => companyData.map((cd, i) => ({
  company: props.companies[i], naRows: cd.naRows, simRows: cd.simRows,
  indirectSimData: Object.fromEntries(Object.entries(indirectSimData).filter(([k]) => k.startsWith(`${i}_`))),
  endInvestTotal: getEndInvest(i),
})))

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

// ─── 导出辅助 ────────────────────────────────────────────────────────────────
function buildSimHeaders(): string[] {
  return ['科目','明细','变动前借','变动前贷',...Array.from({length:props.changeTimes},(_,i)=>{
    const l = props.changeTimes===1?'变动后':`第${i+1}次变动后`; return[l+'借',l+'贷']
  }).flat()]
}
function buildNaHeaders(): string[] {
  return ['项目','变动前',...Array.from({length:props.changeTimes},(_,i)=>props.changeTimes===1?'变动后':`第${i+1}次变动后`)]
}

// ─── 导出模板 ────────────────────────────────────────────────────────────────
async function exportTemplate() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const instr = [[`股比变动${props.changeTimes}次 — 填写说明`],[],
    ['1. 每家企业有三类工作表：净资产、直接持股模拟、间接持股模拟'],
    ['2. 按项目名/科目+明细匹配导入'],
    ['3. 紫色行为自动计算行无需填写'],
    [`4. 共${colCount.value}列：变动前 + ${props.changeTimes}次变动后`],
    ['5. 间接持股企业需在基本信息表中设置持股类型为间接'],
  ]
  const wsI = XLSX.utils.aoa_to_sheet(instr); wsI['!cols']=[{wch:60}]
  XLSX.utils.book_append_sheet(wb, wsI, '填写说明')
  const naH = buildNaHeaders(); const sH = buildSimHeaders()
  for (let ci = 0; ci < props.companies.length; ci++) {
    const comp = props.companies[ci]; const cd = companyData[ci]; if (!cd) continue
    // 净资产表
    const naD = cd.naRows.map(r => [r.item,...(r.vals||[]).map(v=>v??'')])
    const wsN = XLSX.utils.aoa_to_sheet([naH,...naD]); wsN['!cols']=naH.map(()=>({wch:16}))
    XLSX.utils.book_append_sheet(wb, wsN, `${comp.name}-净资产`.substring(0,31))
    // 直接持股模拟
    const sD = cd.simRows.map(r => [r.subject,r.detail,...(r.dc||[]).map(v=>v??'')])
    const wsS = XLSX.utils.aoa_to_sheet([sH,...sD]); wsS['!cols']=sH.map(()=>({wch:14}))
    XLSX.utils.book_append_sheet(wb, wsS, `${comp.name}-直接模拟`.substring(0,31))
  }
  // 间接持股模拟
  for (let ici = 0; ici < indirectList.value.length; ici++) {
    const indComp = indirectList.value[ici]
    for (let ci = 0; ci < props.companies.length; ci++) {
      const rows = getIndirectSimRows(ci, ici)
      const iD = rows.map(r => [r.subject,r.detail,...(r.dc||[]).map(v=>v??'')])
      const wsI2 = XLSX.utils.aoa_to_sheet([sH,...iD]); wsI2['!cols']=sH.map(()=>({wch:14}))
      XLSX.utils.book_append_sheet(wb, wsI2, `${indComp.name}-间接模拟`.substring(0,31))
    }
  }
  XLSX.writeFile(wb, `股比变动${props.changeTimes}次_模板.xlsx`)
  ElMessage.success('模板已导出，含净资产+直接模拟+间接模拟工作表')
}

// ─── 导出数据 ────────────────────────────────────────────────────────────────
async function exportData() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const naH = buildNaHeaders(); const sH = buildSimHeaders()
  for (let ci = 0; ci < props.companies.length; ci++) {
    const comp = props.companies[ci]; const cd = companyData[ci]; if (!cd) continue
    const naD = cd.naRows.map(r => [r.item,...(r.vals||[]).map(v=>v??'')])
    const wsN = XLSX.utils.aoa_to_sheet([naH,...naD]); wsN['!cols']=naH.map(()=>({wch:16}))
    XLSX.utils.book_append_sheet(wb, wsN, `${comp.name}-净资产`.substring(0,31))
    const sD = cd.simRows.map(r => [r.subject,r.detail,...(r.dc||[]).map(v=>v??'')])
    const wsS = XLSX.utils.aoa_to_sheet([sH,...sD]); wsS['!cols']=sH.map(()=>({wch:14}))
    XLSX.utils.book_append_sheet(wb, wsS, `${comp.name}-直接模拟`.substring(0,31))
  }
  for (let ici = 0; ici < indirectList.value.length; ici++) {
    const indComp = indirectList.value[ici]
    for (let ci = 0; ci < props.companies.length; ci++) {
      const rows = getIndirectSimRows(ci, ici)
      const iD = rows.map(r => [r.subject,r.detail,...(r.dc||[]).map(v=>v??'')])
      const wsI2 = XLSX.utils.aoa_to_sheet([sH,...iD]); wsI2['!cols']=sH.map(()=>({wch:14}))
      XLSX.utils.book_append_sheet(wb, wsI2, `${indComp.name}-间接模拟`.substring(0,31))
    }
  }
  XLSX.writeFile(wb, `股比变动${props.changeTimes}次_数据.xlsx`); ElMessage.success('数据已导出')
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  try {
    const XLSX = await import('xlsx'); const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    let matched = 0
    for (let ci = 0; ci < props.companies.length; ci++) {
      const comp = props.companies[ci]; const cd = companyData[ci]; if (!cd) continue
      const naSheet = wb.SheetNames.find(sn => sn.includes(comp.name) && sn.includes('净资产'))
      if (naSheet) {
        const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[naSheet], { header: 1 })
        for (let i = 1; i < json.length; i++) {
          const r = json[i]; const item = String(r?.[0]||'').trim(); if (!item) continue
          const target = cd.naRows.find(row => row.item === item)
          if (!target || target.isHeader || target.isComputed) continue
          for (let k = 0; k < colCount.value; k++) { if (r[1+k] != null && r[1+k] !== '') target.vals[k] = Number(r[1+k]) || null }
          matched++
        }
      }
      // 直接持股模拟
      const simSheet = wb.SheetNames.find(sn => sn.includes(comp.name) && (sn.includes('直接模拟') || (sn.includes('模拟') && !sn.includes('间接'))))
      if (simSheet) {
        const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[simSheet], { header: 1 })
        for (let i = 1; i < json.length; i++) {
          const r = json[i]; const subj = String(r?.[0]||'').trim(); if (!subj) continue
          const det = String(r?.[1]||'').trim()
          const target = cd.simRows.find(row => row.subject === subj && row.detail === det)
          if (!target || target.isSection) continue
          for (let k = 0; k < dcCount.value; k++) { if (r[2+k] != null && r[2+k] !== '') target.dc[k] = Number(r[2+k]) || null }
          matched++
        }
      }
    }
    // 间接持股模拟导入
    for (let ici = 0; ici < indirectList.value.length; ici++) {
      const indComp = indirectList.value[ici]
      const indSheet = wb.SheetNames.find(sn => sn.includes(indComp.name) && sn.includes('间接模拟'))
      if (indSheet) {
        for (let ci = 0; ci < props.companies.length; ci++) {
          const rows = getIndirectSimRows(ci, ici)
          const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[indSheet], { header: 1 })
          for (let i = 1; i < json.length; i++) {
            const r = json[i]; const subj = String(r?.[0]||'').trim(); if (!subj) continue
            const det = String(r?.[1]||'').trim()
            const target = rows.find(row => row.subject === subj && row.detail === det)
            if (!target || target.isSection) continue
            for (let k = 0; k < dcCount.value; k++) { if (r[2+k] != null && r[2+k] !== '') target.dc[k] = Number(r[2+k]) || null }
            matched++
          }
        }
      }
    }
    ElMessage.success(`已导入，匹配 ${matched} 行`)
  } catch (err: any) { ElMessage.error('解析失败：' + (err.message || '')) }
  finally { if (fileInputRef.value) fileInputRef.value.value = '' }
}

// ─── 样式函数 ────────────────────────────────────────────────────────────────
const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '2px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }
function naRowClass({ row }: any) { return row.isHeader ? 'sc-row-header' : row.bold ? 'sc-row-bold' : '' }
function simRowClass({ row }: any) {
  if (row.isSection) return 'sc-row-section'
  if (row.isSubtotal) return 'sc-row-subtotal'
  if (row.isRatio) return 'sc-row-ratio'
  return ''
}

function onEsc(e: KeyboardEvent) { if (e.key === 'Escape' && isFullscreen.value) isFullscreen.value = false }
onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; white-space: nowrap; }
.ws-sheet-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-tip b { color: #4b2d77; }

.sc-company-block { margin-bottom: 20px; border: 1px solid #e8e4f0; border-radius: 8px; overflow: hidden; }
.sc-company-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; background: linear-gradient(135deg, #4b2d77 0%, #7c5caa 100%);
}
.sc-company-idx { width: 24px; height: 24px; border-radius: 50%; background: rgba(255,255,255,0.2); color: #fff; font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.sc-company-name { font-size: 14px; font-weight: 700; color: #fff; }
.sc-company-header :deep(.el-tag) { border-color: rgba(255,255,255,0.3); color: #fff; background: rgba(255,255,255,0.15); }

.sc-three-col { display: flex; gap: 0; overflow-x: auto; padding: 12px; }
.sc-col { flex-shrink: 0; min-width: 250px; }
.sc-col--collapsed { min-width: 0 !important; width: auto !important; }
.sc-col--collapsed .sc-col-title { margin-bottom: 0; }

/* 拖拽分隔线 */
.sc-resizer {
  width: 8px; flex-shrink: 0; cursor: col-resize; display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.sc-resizer:hover { background: rgba(75,45,119,0.06); }
.sc-resizer-bar {
  width: 3px; height: 40px; background: #d8d0e8; border-radius: 2px; transition: all 0.2s;
}
.sc-resizer:hover .sc-resizer-bar { height: 80px; background: #4b2d77; }
.sc-col-title { font-size: 12px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 5px 10px; background: #f8f6fb; border-radius: 4px; }
.sc-col-title--indirect { background: #edf3fb; color: #1a5fb4; }

.sc-computed { color: #4b2d77; font-weight: 500; }
.sc-auto-val { display: block; text-align: right; padding: 0 4px; color: #4b2d77; font-weight: 600; font-size: 11px; background: #faf8fd; border-radius: 2px; }
.sc-ratio-val { display: flex; align-items: center; justify-content: center; color: #4b2d77; font-weight: 700; font-size: 12px; }
.sc-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.sc-table :deep(.sc-row-header td) { background: #f8f6fb !important; font-weight: 600; }
.sc-table :deep(.sc-row-bold td) { font-weight: 600; }
.sc-table :deep(.sc-row-section td) { background: #f0edf5 !important; font-weight: 600; color: #4b2d77; }
.sc-table :deep(.sc-row-subtotal td) { background: #faf8fd !important; font-weight: 600; }
.sc-table :deep(.sc-row-ratio td) { background: #f8f6fb !important; font-weight: 600; color: #4b2d77; }
</style>
