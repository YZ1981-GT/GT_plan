<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>模拟权益法调整表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <span class="ws-btn-sep"></span>
        <el-button size="small" @click="$emit('open-formula', 'consol_equity_sim')">ƒx 公式</el-button>
        <span class="ws-btn-sep"></span>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="exportData">📤 导出数据</el-button>
        <el-button size="small" @click="fileInputRef?.click()">📤 导入Excel</el-button>
        <span class="ws-btn-sep"></span>
        <el-button size="small" type="primary" @click="addDirectRow">+ 新增行</el-button>
        <el-button size="small" type="danger" :disabled="!selectedDirectRows.length" @click="batchDeleteDirect">
          删除{{ selectedDirectRows.length ? `(${selectedDirectRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="restoreDirectDefaults" title="恢复默认行结构">🔄 还原</el-button>
        <span class="ws-btn-sep"></span>
        <el-button size="small" @click="$emit('save', { direct: directRows, indirect: indirectSections })">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>📋 <b>模拟权益法</b>：4步模拟流程 ❶期初长投模拟（从上年底稿或手动输入）→ ❷当期变动模拟（从净资产表按比例提取）→ ❸还原分红影响 → ❹股比变动影响。
        期末=期初+增加-减少。底部比对区自动校验"模拟后长投 vs 按比例享有净资产"差异。
        有股比变动的企业请先到对应的"股比变动N次"表填写，模拟结果会自动回填。</span>
    </div>

    <!-- 1. 直接长期股权投资权益法模拟 -->
    <div class="ws-section">
      <div class="ws-section-title">1. 直接长期股权投资权益法模拟</div>
      <el-table :data="directTableData" border size="small" class="ws-table"
        :max-height="isFullscreen ? 'calc(100vh - 200px)' : '500'"
        :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName"
        @selection-change="sel => selectedDirectRows = sel.filter((r: any) => !r._isRatioRow)">
        <el-table-column type="selection" width="36" fixed align="center" :selectable="(row: any) => !row._isRatioRow" />
        <el-table-column prop="seq" label="序号" width="50" fixed align="center" class-name="ws-col-index" />
        <el-table-column prop="step" label="步骤" width="160" fixed show-overflow-tooltip>
          <template #default="{ row }"><span :style="{ fontWeight: row.isStep ? 700 : 400 }">{{ row.step }}</span></template>
        </el-table-column>
        <el-table-column prop="direction" label="借贷" width="60" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.direction" :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row._isRatioRow" style="font-weight:600;color:#4b2d77">期末持股比例</span>
            <span v-else>{{ row.subject }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="二级明细" width="140" show-overflow-tooltip />
        <el-table-column prop="total" label="合计" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row._isRatioRow"></span>
            <span v-else-if="!row.isStep" class="ws-auto-cell" style="display:block;text-align:right;padding:0 4px;font-size:11px;color:#4b2d77;font-weight:500">
              {{ fmt(rowTotal(row)) }}
            </span>
          </template>
        </el-table-column>
        <!-- 动态子企业列 -->
        <el-table-column v-for="(c, ci) in companies" :key="c.code || ci" align="center" min-width="120">
          <template #header>
            <div style="text-align:center;line-height:1.3">
              <div style="font-weight:600">{{ c.name }}</div>
              <div style="color:#4b2d77;font-size:10px">持股比例 {{ c.ratio }}%</div>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="row._isRatioRow" style="font-weight:600;color:#4b2d77;font-size:12px">{{ c.ratio }}%</span>
            <el-input-number v-else-if="!row.isStep && row.values"
              v-model="row.values[ci]" size="small" :precision="2" :controls="false"
              style="width:100%" :class="{ 'ws-auto-cell': row.isComputed }" />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 比对区：模拟后长投 vs 按比例享有净资产 -->
    <div class="ws-section">
      <div class="ws-section-title">比对：模拟后期末长投 vs 按比例享有净资产</div>
      <div v-if="!companies.length" class="ws-empty-hint">
        请先在"基本信息表"中填写子企业名称，或确保合并范围已配置，子企业列将自动生成。
      </div>
      <el-table v-else :data="compareRows" border size="small" class="ws-table"
        :header-cell-style="headerStyle" :cell-style="compareCellStyle">
        <el-table-column prop="label" label="项目" width="260" fixed show-overflow-tooltip />
        <el-table-column v-for="(c, ci) in companies" :key="'cmp'+ci" align="right" min-width="130">
          <template #header>
            <div style="text-align:center;line-height:1.3">
              <div style="font-weight:600">{{ c.name }}</div>
              <div style="color:#4b2d77;font-size:10px">{{ c.ratio }}%</div>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="row.key === 'ratio'" style="font-weight:600;color:#4b2d77">{{ c.ratio }}%</span>
            <span v-else-if="row.key === 'diff'" :class="n(row.values?.[ci]) !== 0 ? 'ws-diff-warn' : 'ws-computed'">{{ fmt(row.values?.[ci]) }}</span>
            <span v-else-if="row.key === 'reason'">
              <el-input v-model="diffReasons[ci]" size="small" placeholder="差异原因" />
            </span>
            <el-input-number v-else-if="row.editable" v-model="row.values[ci]" size="small" :precision="2" :controls="false" style="width:100%" />
            <span v-else :class="calcCls(row.values?.[ci])">{{ fmt(row.values?.[ci]) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 2. 间接/交叉持股 -->
    <div v-for="(section, si) in indirectSections" :key="si" class="ws-section">
      <div class="ws-section-title">2. 间接/交叉持股权益法模拟 — {{ section.companyName }} <small style="color:#999;margin-left:8px">{{ section.ratio }}%</small></div>
      <el-table :data="section.rows" border size="small" class="ws-table" max-height="400"
        :header-cell-style="headerStyle" :cell-style="cellStyle" :row-class-name="rowClassName">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="step" label="步骤" width="160" show-overflow-tooltip>
          <template #default="{ row }"><span :style="{ fontWeight: row.isStep ? 700 : 400 }">{{ row.step }}</span></template>
        </el-table-column>
        <el-table-column prop="direction" label="借贷" width="60" align="center">
          <template #default="{ row }"><el-tag v-if="row.direction" :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="160" show-overflow-tooltip />
        <el-table-column prop="detail" label="二级明细" width="140" show-overflow-tooltip />
        <el-table-column prop="total" label="金额" width="120" align="right">
          <template #default="{ row }">
            <span v-if="!row.isStep" class="ws-auto-cell" style="display:block;text-align:right;padding:0 4px;font-size:11px;color:#4b2d77;font-weight:500">
              {{ fmt(n(row.total)) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    <el-dialog v-model="importVisible" title="导入模拟权益法数据" width="600px" append-to-body>
      <el-alert type="warning" :closable="false" style="margin-bottom:12px">
        <template #title><span>按"项目+二级明细"匹配导入，读取<b>"数据填写"</b>工作表。</span></template>
      </el-alert>
      <p v-if="importCount > 0" style="font-size:13px;color:#666">匹配到 <b style="color:#4b2d77">{{ importCount }}</b> 行</p>
      <el-empty v-else description="未解析到有效数据" :image-size="60" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!importCount" @click="confirmImport">确认导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

interface CompanyCol { name: string; code?: string; ratio: number }
interface EquitySimRow {
  seq: string; step: string; direction: string; subject: string; detail: string
  total: number | null; values?: (number | null)[]; isStep?: boolean; isComputed?: boolean
}
interface IndirectSection {
  companyName: string; ratio: number; rows: EquitySimRow[]
  endLongInvest: number; endNetAssetShare: number; difference: number; diffReason: string
}

const props = defineProps<{
  companies: CompanyCol[]
  directRows: EquitySimRow[]
  indirectSections: IndirectSection[]
  netAssetData?: any[]  // 净资产表数据，用于自动提取期末值
}>()
defineEmits<{
  (e: 'save', data: { direct: EquitySimRow[]; indirect: IndirectSection[] }): void
  (e: 'open-formula', sheetKey: string): void
}>()

const companies = computed(() => props.companies)
const directRows = ref([...props.directRows])
const indirectSections = ref([...props.indirectSections])

// 在直接持股表格数据前插入持股比例行
const directTableData = computed(() => {
  const ratioRow: any = {
    _isRatioRow: true, seq: '', step: '', direction: '', subject: '期末持股比例', detail: '',
    total: null, values: companies.value.map(c => null), isStep: false, isComputed: false,
  }
  return [ratioRow, ...directRows.value]
})
const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const importVisible = ref(false)
const importCount = ref(0)
const importMap = ref<Map<string, any>>(new Map())
const diffReasons = reactive<string[]>([])
const selectedDirectRows = ref<any[]>([])

function addDirectRow() {
  const newRow: EquitySimRow = { seq: '', step: '', direction: '', subject: '', detail: '', total: null, values: [] }
  if (selectedDirectRows.value.length > 0) {
    const last = selectedDirectRows.value[selectedDirectRows.value.length - 1]
    const idx = directRows.value.indexOf(last)
    if (idx >= 0) { directRows.value.splice(idx + 1, 0, newRow); return }
  }
  directRows.value.push(newRow)
}

async function batchDeleteDirect() {
  if (!selectedDirectRows.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除 ${selectedDirectRows.value.length} 行？删除后可点击"还原"恢复。`, '删除确认', { type: 'warning' })
    const del = new Set(selectedDirectRows.value)
    directRows.value = directRows.value.filter(r => !del.has(r))
    selectedDirectRows.value = []
  } catch {}
}

async function restoreDirectDefaults() {
  try {
    await ElMessageBox.confirm('确定恢复默认行结构？当前数据将被重置。', '还原确认', { type: 'warning' })
    // 重建默认行
    const SIM_STRUCTURE = [
      { s: '1.基础信息', d: '', sec: true }, { s: '持股比例', d: '', sec: true },
      { s: '2.权益法模拟', d: '', sec: true }, { s: '2.1 期初模拟', d: '', sec: true },
      { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
      { s: '年初未分配利润', d: '' }, { s: '资本公积', d: '' }, { s: '其他综合收益', d: '' },
      { s: '专项储备', d: '' }, { s: '其他权益工具', d: '' }, { s: '△一般风险准备', d: '' },
      { s: '2.2 当期变动', d: '', sec: true },
      { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
      { s: '投资收益', d: '' }, { s: '资本公积', d: '' }, { s: '其他综合收益', d: '' },
      { s: '专项储备', d: '' }, { s: '其他权益工具', d: '' }, { s: '△一般风险准备', d: '' },
      { s: '2-3股份支付', d: '（二）所有者投入和减少资本' }, { s: '2-4其他', d: '（二）所有者投入和减少资本' },
      { s: '4-3对所有者的分配', d: '（四）利润分配' }, { s: '4-4其他', d: '（四）利润分配' },
      { s: '3.分红影响', d: '', sec: true },
      { s: '投资收益', d: '' }, { s: '长期股权投资', d: '损益调整' },
      { s: '4.股比变动影响', d: '', sec: true },
      { s: '长期股权投资', d: '损益调整' }, { s: '长期股权投资', d: '其他权益变动' },
      { s: '资本公积', d: '' }, { s: '投资收益', d: '' },
      { s: '模拟后长投', d: '', sec: true },
      { s: '长期股权投资', d: '投资成本' }, { s: '长期股权投资', d: '损益调整' },
      { s: '长期股权投资', d: '其他权益变动' }, { s: '长期股权投资', d: '减值准备' },
      { s: '长期股权投资', d: '小计' },
    ]
    directRows.value = SIM_STRUCTURE.map(r => ({
      seq: '', step: r.sec ? r.s : '', direction: '', subject: r.sec ? '' : r.s, detail: r.d,
      total: null, values: [], isStep: r.sec, isComputed: r.d === '小计',
    }))
    ElMessage.success('已恢复默认行结构')
  } catch {}
}

watch(() => props.directRows, (v) => { directRows.value = [...v] }, { deep: true })
watch(() => props.indirectSections, (v) => { indirectSections.value = [...v] }, { deep: true })

// 同步 total 字段（在 watch 中而非渲染函数中）
watch(directRows, (rows) => {
  for (const row of rows) {
    if (row.isStep || !row.values || !row.values.length) continue
    row.total = row.values.reduce((s: number, v: any) => s + n(v), 0)
  }
}, { deep: true })

const n = (v: any) => Number(v) || 0

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function calcCls(v: any) { return Number(v) === 0 ? 'ws-computed ws-zero' : 'ws-computed' }

// 合计 = 各子企业列之和（纯计算，不修改 row）
function rowTotal(row: any): number {
  if (!row.values || !row.values.length) return n(row.total)
  return row.values.reduce((s: number, v: any) => s + n(v), 0)
}

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }
function compareCellStyle({ row }: any) {
  const base: any = { padding: '4px 8px', fontSize: '12px' }
  if (row.key === 'diff') { base.fontWeight = '700' }
  if (row.key === 'end_invest' || row.key === 'net_asset_share') { base.background = '#f8f6fb' }
  return base
}
function rowClassName({ row }: { row: any }) {
  if (row._isRatioRow) return 'ws-row-ratio'
  if (row.isStep) return 'ws-row-step'
  return ''
}

// ─── 比对行：模拟后长投 vs 按比例享有净资产 ──────────────────────────────────
const endNetAssets = reactive<(number | null)[]>([])

// 自动从净资产表提取期末值
watch(() => props.netAssetData, (data) => {
  if (!data?.length) return
  // 找到"期末金额"行（bold + isComputed + item 包含"期末"）
  const endRow = data.find((r: any) => r.item === '期末金额' && r.bold && r.isComputed)
  if (endRow?.values) {
    for (let i = 0; i < companies.value.length; i++) {
      endNetAssets[i] = endRow.values[i] != null ? Number(endRow.values[i]) || 0 : null
    }
  }
}, { deep: true, immediate: true })

const compareRows = computed(() => {
  const compLen = companies.value.length
  // 确保 endNetAssets 长度和 companies 一致
  while (endNetAssets.length < compLen) endNetAssets.push(null)

  // 找到"模拟后期末长期股权投资"步骤下的"小计"行
  const endInvestRow = directRows.value.find(r => r.isComputed && r.detail === '小计')
  const endInvestVals = endInvestRow?.values || new Array(compLen).fill(0)

  // 按比例享有净资产 = 期末净资产 × 持股比例 / 100
  const shareVals = companies.value.map((c, i) => {
    const na = n(endNetAssets[i])
    return na ? Math.round(na * c.ratio) / 100 : 0
  })

  const diffVals = companies.value.map((_, i) => n(shareVals[i]) - n(endInvestVals[i]))

  return [
    { key: 'ratio', label: '期末持股比例', values: companies.value.map(() => null) },
    { key: 'end_invest', label: '模拟后期末长投小计', values: endInvestVals },
    { key: 'net_asset', label: '各家期末净资产', values: endNetAssets, editable: true },
    { key: 'net_asset_share', label: '期末净资产 × 持股比例', values: shareVals },
    { key: 'diff', label: '差异金额（按比例享有 - 长投）', values: diffVals },
    { key: 'reason', label: '差异原因（简要注明）', values: new Array(compLen).fill('') },
  ]
})

// ─── 导出模板 ─────────────────────────────────────────────────────────────────
async function exportTemplate() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const instr = [['模拟权益法调整表 — 填写说明'],[],['⚠ 重要提示：'],
    ['1. 在"数据填写"工作表填写，不要修改sheet名称'],
    ['2. 步骤行（紫色背景）为分组标题，无需填写'],
    ['3. 按"项目+二级明细"匹配导入，不要修改项目列文字'],
    ['4. 期初模拟数据可从上年底稿获取或手动输入'],
    ['5. 期末=期初+增加-减少，系统自动计算']]
  const wsI = XLSX.utils.aoa_to_sheet(instr); wsI['!cols']=[{wch:60}]
  XLSX.utils.book_append_sheet(wb, wsI, '填写说明')
  // 持股比例行 + 表头 + 数据
  const ratioRow = ['','','','期末持股比例','', '', ...companies.value.map(c => `${c.ratio}%`)]
  const headers = ['序号','步骤','借贷','项目','二级明细','合计',...companies.value.map(c => c.name)]
  const dataRows = directRows.value.map(r => [r.seq, r.step, r.direction, r.subject, r.detail, r.total ?? '',
    ...(r.values || []).map(v => v ?? '')])
  const wsD = XLSX.utils.aoa_to_sheet([ratioRow, headers, ...dataRows])
  wsD['!cols'] = [{wch:5},{wch:22},{wch:8},{wch:18},{wch:18},{wch:14},...companies.value.map(()=>({wch:14}))]
  XLSX.utils.book_append_sheet(wb, wsD, '数据填写')
  XLSX.writeFile(wb, '模拟权益法调整表_模板.xlsx'); ElMessage.success('模板已导出')
}

async function exportData() {
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = ['序号', '步骤', '借贷', '项目', '二级明细', '合计', ...companies.value.map(c => c.name)]
  const dataRows = directRows.value.map(r => [
    r.seq, r.step, r.direction, r.subject, r.detail, r.total ?? '',
    ...(r.values || []).map(v => v ?? '')
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = [{ wch: 5 }, { wch: 22 }, { wch: 8 }, { wch: 18 }, { wch: 18 }, { wch: 14 }, ...companies.value.map(() => ({ wch: 14 }))]
  XLSX.utils.book_append_sheet(wb, ws, '模拟权益法')
  XLSX.writeFile(wb, '模拟权益法_数据.xlsx')
  ElMessage.success('数据已导出')
}

// ─── 导入 ─────────────────────────────────────────────────────────────────────
async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  try {
    const XLSX = await import('xlsx'); const wb = XLSX.read(await file.arrayBuffer(), {type:'array'})
    const sn = wb.SheetNames.find(n => n === '数据填写') || wb.SheetNames[wb.SheetNames.length - 1]
    const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[sn], {header:1})
    const parsed = new Map<string, any>()
    // 跳过持股比例行和表头行（前2行）
    for (let i = 2; i < json.length; i++) {
      const r = json[i]; if (!r?.[3]) continue
      const key = `${String(r[3]).trim()}|${String(r[4]||'').trim()}`
      parsed.set(key, { total: r[5], values: r.slice(6) })
    }
    importMap.value = parsed; importCount.value = parsed.size; importVisible.value = true
  } catch (err: any) { ElMessage.error('解析失败：' + (err.message || '')) }
  finally { if (fileInputRef.value) fileInputRef.value.value = '' }
}

function confirmImport() {
  let count = 0
  for (const row of directRows.value) {
    if (row.isStep) continue
    const key = `${row.subject}|${row.detail}`
    const entry = importMap.value.get(key)
    if (!entry) continue
    if (entry.total != null && entry.total !== '') row.total = Number(entry.total) || null
    if (entry.values && row.values) {
      for (let k = 0; k < row.values.length; k++) {
        if (entry.values[k] != null && entry.values[k] !== '') row.values[k] = Number(entry.values[k]) || null
      }
    }
    count++
  }
  importVisible.value = false; ElMessage.success(`已导入 ${count} 行`); importMap.value = new Map()
}

function onEsc(e: KeyboardEvent) { if (e.key === 'Escape' && isFullscreen.value) isFullscreen.value = false }
onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-tip b { color: #4b2d77; }
.ws-section { margin-bottom: 20px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-zero { color: #c0c4cc !important; font-weight: 400 !important; }
.ws-diff-warn { color: #e6a23c !important; font-weight: 700 !important; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.ws-auto-cell .el-input__inner) { color: #4b2d77; font-weight: 500; background: #faf8fd; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
.ws-table :deep(.ws-row-step td) { background: #f8f6fb !important; font-weight: 600; }
.ws-table :deep(.ws-row-ratio td) { background: #f0edf5 !important; font-weight: 600; }
.ws-empty-hint {
  padding: 16px 20px; background: #fdf6ec; border: 1px solid #faecd8; border-radius: 6px;
  font-size: 13px; color: #8a6d3b; text-align: center;
}
.ws-btn-sep { width: 1px; height: 18px; background: #ddd; margin: 0 2px; flex-shrink: 0; }
</style>
