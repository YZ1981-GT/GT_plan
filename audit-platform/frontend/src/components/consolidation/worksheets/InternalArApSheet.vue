<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>内部往来抵消表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="emitArap('open-formula', 'consol_internal_arap')">ƒx 公式</el-button>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="exportData">📤 导出数据</el-button>
        <el-button size="small" @click="fileInputRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" type="primary" @click="addRow">+ 新增</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="emitArap('save', rows)">💾 保存</el-button>
        <el-button size="small" type="success" @click="runReconcile">🔍 逐笔核对</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>📋 <b>内部往来抵消</b>：每行一笔往来（本方↔对方），账龄段横向展开。❶先确认账龄段设置（3年段/5年段/自定义）❷导出模板按格式填写 ❸导入后自动追加。
        <b>请先确认账龄段后再导出模板</b>，列结构与账龄段一致。底部自动生成抵消分录（往来抵消+坏账冲回），汇总到合并抵消分录表。</span>
    </div>

    <!-- 账龄段选择 -->
    <div class="ws-aging-bar" v-show="!isFullscreen">
      <span style="font-size:12px;color:#666;margin-right:8px">账龄段：</span>
      <el-radio-group v-model="agingPreset" size="small">
        <el-radio-button value="3year">3年段</el-radio-button>
        <el-radio-button value="5year">5年段</el-radio-button>
        <el-radio-button value="custom">自定义</el-radio-button>
      </el-radio-group>
      <el-button v-if="agingPreset === 'custom'" size="small" style="margin-left:8px" @click="showAgingDialog = true">✏️ 编辑账龄段</el-button>
      <span style="font-size:11px;color:#999;margin-left:8px">{{ agingSegments.map(a => a.name).join(' / ') }}</span>
    </div>

    <!-- 主表格 -->
    <el-table :data="rows" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 340px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      @selection-change="(_sel: any[]) => selectedRows = _sel">
      <el-table-column type="selection" width="36" fixed align="center" />
      <el-table-column type="index" label="序号" width="50" fixed align="center" class-name="ws-col-index" />
      <!-- 本方基本信息 -->
      <el-table-column label="本方" align="center">
        <el-table-column prop="localCompany" label="单位" width="120">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.localCompany" size="small" style="width:100%" placeholder="选择" filterable>
                <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="localSubject" label="科目" width="110">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.localSubject" size="small" style="width:100%" placeholder="科目" filterable allow-create>
                <el-option v-for="s in subjectOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="localDetail" label="明细" width="100">
          <template #default="{ row }"><el-input v-model="row.localDetail" size="small" placeholder="明细" /></template>
        </el-table-column>
        <!-- 本方原值按账龄 -->
        <el-table-column v-for="(ag, ai) in agingSegments" :key="'la'+ai" :label="ag.name" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.localAmounts[ai]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="原值合计" width="110" align="right">
          <template #default="{ row }"><span class="ws-auto-cell" style="color:#4b2d77;font-weight:600">{{ fmt(sumArr(row.localAmounts)) }}</span></template>
        </el-table-column>
        <!-- 本方坏账按账龄 -->
        <el-table-column v-for="(ag, ai) in agingSegments" :key="'li'+ai" :label="'坏账-'+ag.name" width="90" align="right">
          <template #default="{ row }"><el-input-number v-model="row.localImpairments[ai]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="坏账合计" width="100" align="right">
          <template #default="{ row }"><span class="ws-auto-cell" style="color:#e6a23c;font-weight:600">{{ fmt(sumArr(row.localImpairments)) }}</span></template>
        </el-table-column>
      </el-table-column>
      <!-- 对方基本信息 -->
      <el-table-column label="对方" align="center">
        <el-table-column prop="remoteCompany" label="单位" width="120">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.remoteCompany" size="small" style="width:100%" placeholder="选择" filterable>
                <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="remoteSubject" label="科目" width="110">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.remoteSubject" size="small" style="width:100%" placeholder="科目" filterable allow-create>
                <el-option v-for="s in subjectOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="remoteDetail" label="明细" width="100">
          <template #default="{ row }"><el-input v-model="row.remoteDetail" size="small" placeholder="明细" /></template>
        </el-table-column>
        <el-table-column v-for="(ag, ai) in agingSegments" :key="'ra'+ai" :label="ag.name" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.remoteAmounts[ai]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="原值合计" width="110" align="right">
          <template #default="{ row }"><span class="ws-auto-cell" style="color:#4b2d77;font-weight:600">{{ fmt(sumArr(row.remoteAmounts)) }}</span></template>
        </el-table-column>
        <el-table-column v-for="(ag, ai) in agingSegments" :key="'ri'+ai" :label="'坏账-'+ag.name" width="90" align="right">
          <template #default="{ row }"><el-input-number v-model="row.remoteImpairments[ai]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="坏账合计" width="100" align="right">
          <template #default="{ row }"><span class="ws-auto-cell" style="color:#e6a23c;font-weight:600">{{ fmt(sumArr(row.remoteImpairments)) }}</span></template>
        </el-table-column>
      </el-table-column>
      <!-- 差异 -->
      <el-table-column label="差异" width="110" align="right">
        <template #default="{ row }">
          <span :class="sumArr(row.localAmounts) - sumArr(row.remoteAmounts) !== 0 ? 'ws-diff-warn' : 'ws-computed'">
            {{ fmt(sumArr(row.localAmounts) - sumArr(row.remoteAmounts)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="diffReason" label="差异原因" width="130">
        <template #default="{ row }"><el-input v-model="row.diffReason" size="small" placeholder="原因" /></template>
      </el-table-column>
      <el-table-column label="核对" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row._reconcileStatus === 'matched'" type="success" size="small" effect="plain">✓</el-tag>
          <el-tooltip v-else-if="row._reconcileStatus === 'diff'" :content="`差异: ${fmt(row._reconcileDiff)}${row._impairmentDiff ? '，坏账差异: ' + fmt(row._impairmentDiff) : ''}`" placement="left">
            <el-tag type="warning" size="small" effect="plain">≠</el-tag>
          </el-tooltip>
          <span v-else style="color:#ccc">—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 抵消分录预览 -->
    <div class="ws-section" style="margin-top:12px">
      <div class="ws-section-title">自动生成的抵消分录</div>
      <el-table :data="generatedEntries" border size="small" class="ws-table" max-height="200"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷" width="50" align="center">
          <template #default="{ row }"><el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="科目" width="160" />
        <el-table-column prop="amount" label="金额" width="140" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column prop="desc" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />

    <!-- 核对结果摘要 -->
    <div v-if="showReconcileResult" class="ws-section" style="margin-top:8px">
      <div class="ws-section-title">🔍 逐笔核对结果</div>
      <div style="display:flex;gap:16px;padding:8px 12px;font-size:13px;background:#f8f7fc;border-radius:6px">
        <span>总笔数：<b>{{ reconcileStats.total }}</b></span>
        <span style="color:#28a745">一致：<b>{{ reconcileStats.matched }}</b></span>
        <span style="color:#e6a23c">有差异：<b>{{ reconcileStats.diffCount }}</b></span>
        <span v-if="reconcileStats.total > 0" style="color:#999">
          核对率：<b>{{ Math.round(reconcileStats.matched / reconcileStats.total * 100) }}%</b>
        </span>
      </div>
    </div>

    <!-- 自定义账龄段弹窗 -->
    <el-dialog v-model="showAgingDialog" title="自定义账龄段" width="500px" append-to-body>
      <el-alert type="info" :closable="false" style="margin-bottom:12px">
        <template #title>设置账龄分段，所有使用账龄的底稿将统一引用此设置。</template>
      </el-alert>
      <el-table :data="editingAging" border size="small">
        <el-table-column type="index" label="#" width="40" />
        <el-table-column label="段名" min-width="120">
          <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
        </el-table-column>
        <el-table-column label="起始月" width="80">
          <template #default="{ row }"><el-input-number v-model="row.startMonth" size="small" :min="0" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="结束月" width="80">
          <template #default="{ row }"><el-input-number v-model="row.endMonth" size="small" :min="0" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="坏账比例%" width="90">
          <template #default="{ row }"><el-input-number v-model="row.impairmentRate" size="small" :min="0" :max="100" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="editingAging.splice($index, 1)">删</el-button></template>
        </el-table-column>
      </el-table>
      <el-button size="small" style="margin-top:6px" @click="editingAging.push({ name: '', startMonth: 0, endMonth: 12, impairmentRate: 5 })">+ 新增段</el-button>
      <template #footer>
        <el-button @click="showAgingDialog = false">取消</el-button>
        <el-button type="primary" @click="applyCustomAging">确认应用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'

interface CompanyCol { name: string; code?: string; ratio: number }
interface AgingSegment { name: string; startMonth: number; endMonth: number; impairmentRate: number }
interface ArApRow {
  localCompany: string; localSubject: string; localDetail: string
  localAmounts: (number|null)[]; localImpairments: (number|null)[]
  remoteCompany: string; remoteSubject: string; remoteDetail: string
  remoteAmounts: (number|null)[]; remoteImpairments: (number|null)[]
  diffReason: string
  _reconcileStatus?: string; _reconcileDiff?: number; _impairmentDiff?: number
}

const props = defineProps<{ companies: CompanyCol[] }>()
const emitArap = defineEmits<{
  (e: 'save', data: ArApRow[]): void
  (e: 'open-formula', key: string): void
  (e: 'entries-changed', entries: any[]): void
}>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement|null>(null)
const selectedRows = ref<ArApRow[]>([])
const showAgingDialog = ref(false)
const fileInputRef = ref<HTMLInputElement|null>(null)

const allCompanyOptions = computed(() => [
  { name: '母公司', code: 'parent' },
  ...props.companies.map(c => ({ name: c.name, code: c.code || '' })),
])
const subjectOptions = ['应收账款', '其他应收款', '预付账款', '应收票据', '长期应收款', '应付账款', '其他应付款', '预收账款', '应付票据']

// ─── 账龄段 ───────────────────────────────────────────────────────────────────
const agingPreset = ref<'3year'|'5year'|'custom'>('3year')
const AGING_3: AgingSegment[] = [
  { name: '1年以内', startMonth: 0, endMonth: 12, impairmentRate: 5 },
  { name: '1-2年', startMonth: 12, endMonth: 24, impairmentRate: 10 },
  { name: '2-3年', startMonth: 24, endMonth: 36, impairmentRate: 30 },
  { name: '3年以上', startMonth: 36, endMonth: 999, impairmentRate: 50 },
]
const AGING_5: AgingSegment[] = [
  { name: '1年以内', startMonth: 0, endMonth: 12, impairmentRate: 5 },
  { name: '1-2年', startMonth: 12, endMonth: 24, impairmentRate: 10 },
  { name: '2-3年', startMonth: 24, endMonth: 36, impairmentRate: 20 },
  { name: '3-4年', startMonth: 36, endMonth: 48, impairmentRate: 40 },
  { name: '4-5年', startMonth: 48, endMonth: 60, impairmentRate: 60 },
  { name: '5年以上', startMonth: 60, endMonth: 999, impairmentRate: 80 },
]
const customAging = reactive<AgingSegment[]>([...AGING_3])
const editingAging = reactive<AgingSegment[]>([])
const agingSegments = computed(() => {
  if (agingPreset.value === '3year') return AGING_3
  if (agingPreset.value === '5year') return AGING_5
  return customAging
})
const agingCount = computed(() => agingSegments.value.length)

// 打开自定义弹窗时复制当前段
watch(showAgingDialog, (v) => {
  if (v) { editingAging.length = 0; editingAging.push(...customAging.map(a => ({ ...a }))) }
})

function applyCustomAging() {
  if (!editingAging.length) { ElMessage.warning('至少需要一个账龄段'); return }
  customAging.length = 0; customAging.push(...editingAging.map(a => ({ ...a })))
  agingPreset.value = 'custom'
  // 调整所有行的数组长度
  for (const row of rows) {
    resizeArr(row.localAmounts, agingCount.value)
    resizeArr(row.localImpairments, agingCount.value)
    resizeArr(row.remoteAmounts, agingCount.value)
    resizeArr(row.remoteImpairments, agingCount.value)
  }
  showAgingDialog.value = false
  ElMessage.success('账龄段已更新')
}

function resizeArr(arr: (number|null)[], len: number) {
  while (arr.length < len) arr.push(null)
  arr.length = len
}

// ─── 数据行 ───────────────────────────────────────────────────────────────────
const rows = reactive<ArApRow[]>([mkEmpty(), mkEmpty(), mkEmpty()])

function mkEmpty(): ArApRow {
  const len = agingCount.value
  return {
    localCompany: '', localSubject: '', localDetail: '',
    localAmounts: new Array(len).fill(null), localImpairments: new Array(len).fill(null),
    remoteCompany: '', remoteSubject: '', remoteDetail: '',
    remoteAmounts: new Array(len).fill(null), remoteImpairments: new Array(len).fill(null),
    diffReason: '',
  }
}

function addRow() {
  const newRow = mkEmpty()
  if (selectedRows.value.length > 0) {
    const last = selectedRows.value[selectedRows.value.length - 1]
    const idx = rows.indexOf(last)
    if (idx >= 0) { rows.splice(idx + 1, 0, newRow); return }
  }
  rows.push(newRow)
}

async function batchDelete() {
  if (!selectedRows.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除 ${selectedRows.value.length} 条？`, '删除确认', { type: 'warning' })
    const del = new Set(selectedRows.value)
    const remaining = rows.filter(r => !del.has(r))
    rows.length = 0; rows.push(...remaining); selectedRows.value = []
  } catch {}
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────
const n = (v: any) => Number(v) || 0
function sumArr(arr: (number|null)[]): number { return arr.reduce((s: number, v) => s + n(v), 0) }
function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

// ─── 逐笔核对 ────────────────────────────────────────────────────────────────
const showReconcileResult = ref(false)
const reconcileStats = reactive({ total: 0, matched: 0, diffCount: 0, unmatchedLocal: 0, unmatchedRemote: 0 })

function runReconcile() {
  // 按 本方单位+对方单位+科目 分组，逐笔比对金额
  let matched = 0, diffCount = 0, unmatchedLocal = 0, unmatchedRemote = 0

  // 构建对方视角的索引：remoteCompany+remoteSubject → rows[]
  const remoteIndex = new Map<string, any[]>()
  for (const row of rows) {
    if (!row.remoteCompany || !row.remoteSubject) continue
    const key = `${row.remoteCompany}|${row.remoteSubject}|${row.localCompany}`
    if (!remoteIndex.has(key)) remoteIndex.set(key, [])
    remoteIndex.get(key)!.push(row)
  }

  const usedRemote = new Set<any>()

  for (const row of rows) {
    if (!row.localCompany || !row.localSubject) {
      row._reconcileStatus = ''
      continue
    }
    const localTotal = sumArr(row.localAmounts)
    const remoteTotal = sumArr(row.remoteAmounts)

    if (localTotal === 0 && remoteTotal === 0) {
      row._reconcileStatus = ''
      continue
    }

    // 差异 = 本方 - 对方
    const diff = Math.round((localTotal - remoteTotal) * 100) / 100
    if (Math.abs(diff) < 0.01) {
      row._reconcileStatus = 'matched'
      matched++
    } else {
      row._reconcileStatus = 'diff'
      row._reconcileDiff = diff
      diffCount++
    }

    // 检查坏账差异
    const localImpTotal = sumArr(row.localImpairments)
    const remoteImpTotal = sumArr(row.remoteImpairments)
    row._impairmentDiff = Math.round((localImpTotal - remoteImpTotal) * 100) / 100
  }

  reconcileStats.total = rows.filter(r => r.localCompany || r.remoteCompany).length
  reconcileStats.matched = matched
  reconcileStats.diffCount = diffCount
  reconcileStats.unmatchedLocal = unmatchedLocal
  reconcileStats.unmatchedRemote = unmatchedRemote
  showReconcileResult.value = true
  ElMessage.success(`核对完成：${matched} 笔一致，${diffCount} 笔有差异`)
}

// ─── 自动生成抵消分录 ────────────────────────────────────────────────────────
const generatedEntries = computed(() => {
  const entries: any[] = []
  const pairMap = new Map<string, { local: number; remote: number; localImp: number; remoteImp: number; localByAging: number[]; remoteByAging: number[] }>()
  for (const row of rows) {
    if (!row.localSubject && !row.remoteSubject) continue
    const key = `${row.localSubject}|${row.remoteSubject}`
    if (!pairMap.has(key)) pairMap.set(key, { local: 0, remote: 0, localImp: 0, remoteImp: 0, localByAging: agingSegments.value.map(() => 0), remoteByAging: agingSegments.value.map(() => 0) })
    const m = pairMap.get(key)!
    m.local += sumArr(row.localAmounts)
    m.remote += sumArr(row.remoteAmounts)
    m.localImp += sumArr(row.localImpairments)
    m.remoteImp += sumArr(row.remoteImpairments)
    // 按账龄段累加
    for (let i = 0; i < agingSegments.value.length; i++) {
      m.localByAging[i] += n(row.localAmounts[i])
      m.remoteByAging[i] += n(row.remoteAmounts[i])
    }
  }
  for (const [key, vals] of pairMap) {
    const [localSubj, remoteSubj] = key.split('|')
    const amount = Math.min(vals.local, vals.remote)
    if (amount > 0) {
      // 往来抵消分录
      entries.push({ direction: '借', subject: localSubj || remoteSubj, amount, desc: `内部往来抵消（本方${fmt(vals.local)} / 对方${fmt(vals.remote)}）` })
      entries.push({ direction: '贷', subject: remoteSubj || localSubj, amount, desc: `内部往来抵消` })
    }
    // 坏账准备冲回（本方+对方的坏账都要冲回）
    if (vals.localImp > 0) {
      entries.push({ direction: '借', subject: '坏账准备', amount: vals.localImp, desc: `冲回本方坏账（${localSubj}）` })
      entries.push({ direction: '贷', subject: '信用减值损失', amount: vals.localImp, desc: `冲回本方坏账` })
    }
    if (vals.remoteImp > 0) {
      entries.push({ direction: '借', subject: '坏账准备', amount: vals.remoteImp, desc: `冲回对方坏账（${remoteSubj}）` })
      entries.push({ direction: '贷', subject: '信用减值损失', amount: vals.remoteImp, desc: `冲回对方坏账` })
    }
    // 差异提示
    const diff = Math.round((vals.local - vals.remote) * 100) / 100
    if (Math.abs(diff) > 0.01) {
      entries.push({ direction: '—', subject: '⚠️ 差异', amount: diff, desc: `${localSubj}↔${remoteSubj} 未抵消差异` })
    }
  }
  return entries
})

watch(generatedEntries, (entries) => {
  emitArap('entries-changed', entries.map(e => ({ ...e, source: '内部往来' })))
}, { immediate: true })

const headerStyle = { background: '#f0edf5', fontSize: '10px', color: '#333', padding: '2px 0' }
const cellStyle = { padding: '2px 3px', fontSize: '11px' }

// ─── 导出模板 / 导入 ──────────────────────────────────────────────────────────
async function exportTemplate() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const agNames = agingSegments.value.map(a => a.name)
  const headers = ['本方单位','本方科目','本方明细',
    ...agNames.map(a => '本方-'+a), '本方原值合计', ...agNames.map(a => '本方坏账-'+a), '本方坏账合计',
    '对方单位','对方科目','对方明细',
    ...agNames.map(a => '对方-'+a), '对方原值合计', ...agNames.map(a => '对方坏账-'+a), '对方坏账合计',
    '差异','差异原因']
  const dataRows = rows.map(r => [
    r.localCompany, r.localSubject, r.localDetail,
    ...r.localAmounts.map(v => v ?? ''), sumArr(r.localAmounts) || '',
    ...r.localImpairments.map(v => v ?? ''), sumArr(r.localImpairments) || '',
    r.remoteCompany, r.remoteSubject, r.remoteDetail,
    ...r.remoteAmounts.map(v => v ?? ''), sumArr(r.remoteAmounts) || '',
    ...r.remoteImpairments.map(v => v ?? ''), sumArr(r.remoteImpairments) || '',
    sumArr(r.localAmounts) - sumArr(r.remoteAmounts) || '', r.diffReason,
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map(() => ({ wch: 14 }))
  XLSX.utils.book_append_sheet(wb, ws, '数据填写')
  XLSX.writeFile(wb, '内部往来抵消_模板.xlsx'); ElMessage.success('模板已导出')
}

async function exportData() {
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const agNames = agingSegments.value.map(a => a.name)
  const headers = ['本方单位', '本方科目', '本方明细',
    ...agNames.map(a => '本方-' + a), '本方原值合计', ...agNames.map(a => '本方坏账-' + a), '本方坏账合计',
    '对方单位', '对方科目', '对方明细',
    ...agNames.map(a => '对方-' + a), '对方原值合计', ...agNames.map(a => '对方坏账-' + a), '对方坏账合计',
    '差异', '差异原因']
  const dataRows = rows.filter(r => r.localCompany || r.remoteCompany).map(r => [
    r.localCompany, r.localSubject, r.localDetail,
    ...r.localAmounts.map(v => v ?? ''), sumArr(r.localAmounts) || '',
    ...r.localImpairments.map(v => v ?? ''), sumArr(r.localImpairments) || '',
    r.remoteCompany, r.remoteSubject, r.remoteDetail,
    ...r.remoteAmounts.map(v => v ?? ''), sumArr(r.remoteAmounts) || '',
    ...r.remoteImpairments.map(v => v ?? ''), sumArr(r.remoteImpairments) || '',
    sumArr(r.localAmounts) - sumArr(r.remoteAmounts) || '', r.diffReason,
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map(() => ({ wch: 14 }))
  XLSX.utils.book_append_sheet(wb, ws, '内部往来抵消')
  XLSX.writeFile(wb, '内部往来抵消_数据.xlsx')
  ElMessage.success('数据已导出')
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  try {
    const XLSX = await import('xlsx'); const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const sn = wb.SheetNames.find(n => n === '数据填写') || wb.SheetNames[wb.SheetNames.length - 1]
    const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1 })
    const ac = agingCount.value
    let imported = 0
    for (let i = 1; i < json.length; i++) {
      const r = json[i]; if (!r?.[0]) continue
      const p = (idx: number) => r[idx] != null && r[idx] !== '' ? Number(r[idx]) : null
      const localAmts: (number|null)[] = []; for (let k = 0; k < ac; k++) localAmts.push(p(3 + k))
      const localImps: (number|null)[] = []; for (let k = 0; k < ac; k++) localImps.push(p(3 + ac + 1 + k))
      const remoteBase = 3 + ac * 2 + 2 + 3
      const remoteAmts: (number|null)[] = []; for (let k = 0; k < ac; k++) remoteAmts.push(p(remoteBase + k))
      const remoteImps: (number|null)[] = []; for (let k = 0; k < ac; k++) remoteImps.push(p(remoteBase + ac + 1 + k))
      rows.push({
        localCompany: String(r[0] || ''), localSubject: String(r[1] || ''), localDetail: String(r[2] || ''),
        localAmounts: localAmts, localImpairments: localImps,
        remoteCompany: String(r[remoteBase - 3] || ''), remoteSubject: String(r[remoteBase - 2] || ''), remoteDetail: String(r[remoteBase - 1] || ''),
        remoteAmounts: remoteAmts, remoteImpairments: remoteImps,
        diffReason: String(r[r.length - 1] || ''),
      })
      imported++
    }
    ElMessage.success(`已导入 ${imported} 条`)
  } catch (err: any) { ElMessage.error('解析失败：' + (err.message || '')) }
  finally { if (fileInputRef.value) fileInputRef.value.value = '' }
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
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 8px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-aging-bar { display: flex; align-items: center; margin-bottom: 10px; }
.ws-section { margin-bottom: 16px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: #e6a23c !important; font-weight: 700 !important; }
.ws-auto-cell { background: #faf8fd; padding: 2px 4px; border-radius: 2px; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
</style>
