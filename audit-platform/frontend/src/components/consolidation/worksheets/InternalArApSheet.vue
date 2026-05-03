<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>内部往来抵消表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="emitArap('open-formula', 'consol_internal_arap')">ƒx 公式</el-button>
        <el-button size="small" type="primary" @click="addRow">+ 新增</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="emitArap('save', rows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>内部往来余额抵消。本方金额应等于对方金额，差异需说明。坏账按账龄明细记录，合并时冲回。账龄段从项目设置中统一引用。</span>
    </div>

    <!-- 账龄段设置 -->
    <div class="ws-aging-bar" v-show="!isFullscreen">
      <span style="font-size:12px;color:#666;margin-right:8px">账龄段：</span>
      <el-radio-group v-model="agingPreset" size="small" @change="onAgingPresetChange">
        <el-radio-button value="3year">3年段</el-radio-button>
        <el-radio-button value="5year">5年段</el-radio-button>
        <el-radio-button value="custom">自定义</el-radio-button>
      </el-radio-group>
      <span style="font-size:11px;color:#999;margin-left:8px">{{ agingSegments.map(a => a.name).join(' / ') }}</span>
    </div>

    <el-table :data="rows" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 80px)' : 'calc(100vh - 320px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      @selection-change="sel => selectedRows = sel">
      <el-table-column type="selection" width="36" fixed align="center" />
      <el-table-column type="index" label="序号" width="50" fixed align="center" class-name="ws-col-index" />

      <!-- 本方 -->
      <el-table-column label="本方" align="center">
        <el-table-column prop="localCompany" label="单位" width="130">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.localCompany" size="small" style="width:100%" placeholder="选择" filterable>
                <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="localSubject" label="科目" width="120">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.localSubject" size="small" style="width:100%" placeholder="科目" filterable allow-create>
                <el-option v-for="s in subjectOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="localDetail" label="明细" width="110">
          <template #default="{ row }"><el-input v-model="row.localDetail" size="small" placeholder="明细" /></template>
        </el-table-column>
        <el-table-column prop="localAmount" label="金额" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.localAmount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="localImpairment" label="坏账准备" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.localImpairment" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="localAging" label="账龄" width="100">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.localAging" size="small" style="width:100%" placeholder="账龄">
                <el-option v-for="a in agingSegments" :key="a.name" :label="a.name" :value="a.name" />
              </el-select>
            </div>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 对方 -->
      <el-table-column label="对方" align="center">
        <el-table-column prop="remoteCompany" label="单位" width="130">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.remoteCompany" size="small" style="width:100%" placeholder="选择" filterable>
                <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="remoteSubject" label="科目" width="120">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.remoteSubject" size="small" style="width:100%" placeholder="科目" filterable allow-create>
                <el-option v-for="s in subjectOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="remoteDetail" label="明细" width="110">
          <template #default="{ row }"><el-input v-model="row.remoteDetail" size="small" placeholder="明细" /></template>
        </el-table-column>
        <el-table-column prop="remoteAmount" label="金额" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.remoteAmount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="remoteImpairment" label="坏账准备" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.remoteImpairment" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="remoteAging" label="账龄" width="100">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.remoteAging" size="small" style="width:100%" placeholder="账龄">
                <el-option v-for="a in agingSegments" :key="a.name" :label="a.name" :value="a.name" />
              </el-select>
            </div>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 差异与核查 -->
      <el-table-column label="差异" width="110" align="right">
        <template #default="{ row }">
          <span :class="n(row.localAmount) - n(row.remoteAmount) !== 0 ? 'ws-diff-warn' : 'ws-computed'">
            {{ fmt(n(row.localAmount) - n(row.remoteAmount)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="diffReason" label="差异原因" width="140">
        <template #default="{ row }"><el-input v-model="row.diffReason" size="small" placeholder="原因" /></template>
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessageBox } from 'element-plus'

interface CompanyCol { name: string; code?: string; ratio: number }
interface AgingSegment { name: string; startMonth: number; endMonth: number; impairmentRate: number }
interface ArApRow {
  localCompany: string; localSubject: string; localDetail: string; localAmount: number|null; localImpairment: number|null; localAging: string
  remoteCompany: string; remoteSubject: string; remoteDetail: string; remoteAmount: number|null; remoteImpairment: number|null; remoteAging: string
  diffReason: string
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
const n = (v: any) => Number(v) || 0

const allCompanyOptions = computed(() => [
  { name: '母公司', code: 'parent' },
  ...props.companies.map(c => ({ name: c.name, code: c.code || '' })),
])

const subjectOptions = ['应收账款', '其他应收款', '预付账款', '应收票据', '长期应收款', '应付账款', '其他应付款', '预收账款', '应付票据']

// ─── 账龄段 ───────────────────────────────────────────────────────────────────
const agingPreset = ref<'3year'|'5year'|'custom'>('3year')
const AGING_3YEAR: AgingSegment[] = [
  { name: '1年以内', startMonth: 0, endMonth: 12, impairmentRate: 5 },
  { name: '1-2年', startMonth: 12, endMonth: 24, impairmentRate: 10 },
  { name: '2-3年', startMonth: 24, endMonth: 36, impairmentRate: 30 },
  { name: '3年以上', startMonth: 36, endMonth: 999, impairmentRate: 50 },
]
const AGING_5YEAR: AgingSegment[] = [
  { name: '1年以内', startMonth: 0, endMonth: 12, impairmentRate: 5 },
  { name: '1-2年', startMonth: 12, endMonth: 24, impairmentRate: 10 },
  { name: '2-3年', startMonth: 24, endMonth: 36, impairmentRate: 20 },
  { name: '3-4年', startMonth: 36, endMonth: 48, impairmentRate: 40 },
  { name: '4-5年', startMonth: 48, endMonth: 60, impairmentRate: 60 },
  { name: '5年以上', startMonth: 60, endMonth: 999, impairmentRate: 80 },
]
const customAging = reactive<AgingSegment[]>([...AGING_3YEAR])
const agingSegments = computed(() => {
  if (agingPreset.value === '3year') return AGING_3YEAR
  if (agingPreset.value === '5year') return AGING_5YEAR
  return customAging
})
function onAgingPresetChange(val: string) {
  if (val === 'custom') { customAging.length = 0; customAging.push(...AGING_3YEAR) }
}

// ─── 数据行 ───────────────────────────────────────────────────────────────────
const rows = reactive<ArApRow[]>([mkEmpty(), mkEmpty(), mkEmpty()])

function mkEmpty(): ArApRow {
  return {
    localCompany: '', localSubject: '', localDetail: '', localAmount: null, localImpairment: null, localAging: '',
    remoteCompany: '', remoteSubject: '', remoteDetail: '', remoteAmount: null, remoteImpairment: null, remoteAging: '',
    diffReason: '',
  }
}
function addRow() { rows.push(mkEmpty()) }
async function batchDelete() {
  if (!selectedRows.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除 ${selectedRows.value.length} 条？`, '删除确认', { type: 'warning' })
    const del = new Set(selectedRows.value)
    const remaining = rows.filter(r => !del.has(r))
    rows.length = 0; rows.push(...remaining); selectedRows.value = []
  } catch {}
}

// ─── 自动生成抵消分录 ────────────────────────────────────────────────────────
const generatedEntries = computed(() => {
  const entries: { direction: string; subject: string; amount: number; desc: string }[] = []
  // 按本方科目+对方科目配对汇总
  const pairMap = new Map<string, { localTotal: number; remoteTotal: number; localImp: number; remoteImp: number }>()
  for (const row of rows) {
    if (!row.localSubject && !row.remoteSubject) continue
    if (!row.localAmount && !row.remoteAmount) continue
    const key = `${row.localSubject}|${row.remoteSubject}`
    if (!pairMap.has(key)) pairMap.set(key, { localTotal: 0, remoteTotal: 0, localImp: 0, remoteImp: 0 })
    const m = pairMap.get(key)!
    m.localTotal += n(row.localAmount)
    m.remoteTotal += n(row.remoteAmount)
    m.localImp += n(row.localImpairment)
    m.remoteImp += n(row.remoteImpairment)
  }
  for (const [key, vals] of pairMap) {
    const [localSubj, remoteSubj] = key.split('|')
    const amount = Math.min(vals.localTotal, vals.remoteTotal)
    if (amount > 0) {
      entries.push({ direction: '借', subject: localSubj || remoteSubj, amount, desc: `内部往来抵消` })
      entries.push({ direction: '贷', subject: remoteSubj || localSubj, amount, desc: `内部往来抵消` })
    }
    const totalImp = vals.localImp + vals.remoteImp
    if (totalImp > 0) {
      entries.push({ direction: '借', subject: '坏账准备', amount: totalImp, desc: `冲回内部往来坏账` })
      entries.push({ direction: '贷', subject: '信用减值损失', amount: totalImp, desc: `冲回内部往来坏账` })
    }
  }
  return entries
})

watch(generatedEntries, (entries) => {
  emitArap('entries-changed', entries.map(e => ({ ...e, source: '内部往来' })))
}, { immediate: true })

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '2px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }

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
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
</style>
