<template>
  <div class="h7-tab-stocktake-check">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：通过双向抽盘（账面→实物测存在、实物→账面测完整）核对生产性生物资产账面数量/金额与实际状况，比对账面/企业盘点/审计抽盘三数量，识别盘盈盘亏及状况异常，评价资产计价与减值影响（CAS 5 / CAS 1311 参照适用）。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('navigate-sheet', 'H7-8')">← H7-8</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H7-10')">H7-10 →</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H7-9" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button v-if="!isReadonly" size="small" @click="onDraftConclusion">起草结论</el-button>
        <el-button size="small" type="default" link @click="handleReview('H7-9')">💬 复核</el-button>
      </div>
    </div>

    <ItemAttachment
      v-if="projectId && wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-key="H7-9"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.mp4,.mov"
    />

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <div>
            <span>（一）账面→实物（存在性）</span>
            <el-tag v-if="b2fVariance > 0" size="small" type="danger" class="ml-tag">{{ b2fVariance }} 行差异</el-tag>
            <el-tag v-else-if="b2fH1.length" size="small" type="success" class="ml-tag">无差异</el-tag>
          </div>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow('bookToFloor')">+ 明细行</el-button>
          </div>
        </div>
      </template>
      <H1CheckDirectionTable
        :rows="b2fH1"
        :is-readonly="!!isReadonly"
        empty-text="暂无「账面→实物」明细"
        @update="onRowUpdate"
        @remove="removeRow"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <div>
            <span>（二）实物→账面（完整性）</span>
            <el-tag v-if="f2bVariance > 0" size="small" type="danger" class="ml-tag">{{ f2bVariance }} 行差异</el-tag>
            <el-tag v-else-if="f2bH1.length" size="small" type="success" class="ml-tag">无差异</el-tag>
          </div>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow('floorToBook')">+ 明细行</el-button>
          </div>
        </div>
      </template>
      <H1CheckDirectionTable
        :rows="f2bH1"
        :is-readonly="!!isReadonly"
        empty-text="暂无「实物→账面」明细；完整性测试不可省略"
        @update="onRowUpdate"
        @remove="removeRow"
      />
    </el-card>

    <!-- 生物资产补充字段（类别 / 标识核对），不改变 H1 表列结构 -->
    <el-card v-if="rows.length" shadow="never" class="block-card">
      <template #header>
        <div class="section-title"><span>补充：类别与标识核对</span></div>
      </template>
      <el-table :data="rows" border stripe size="small" max-height="280" class="check-table">
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="direction" label="方向" width="110" align="center">
          <template #default="{ row }">
            {{ row.direction === 'floorToBook' ? '实物→账面' : '账面→实物' }}
          </template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.category" size="small" @change="persistRows">
              <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="identityCheck" label="标识核对" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.identityCheck" size="small" style="width:90px" @change="persistRows">
              <el-option label="一致" value="一致" />
              <el-option label="不一致" value="不一致" />
            </el-select>
            <el-tag v-else :type="row.identityCheck === '一致' ? 'success' : 'danger'" size="small">{{ row.identityCheck || '-' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="summary-bar">
      <span>账实相符：<b>{{ stat.match }}</b></span>
      <span>盘盈：<b class="text-warn">{{ stat.surplus }}</b></span>
      <span>盘亏：<b :class="{ 'text-danger': stat.deficit > 0 }">{{ stat.deficit }}</b></span>
      <span>标识不一致：<b :class="{ 'text-danger': stat.identityMismatch > 0 }">{{ stat.identityMismatch }}</b></span>
      <span>相符率：<b>{{ stat.matchRate.toFixed(1) }}%</b></span>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="记录本表审计程序的实施情况、核对过程与发现。" @blur="persist('H7-9-note', auditNote)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-9-conclusion', auditConclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>双向抽盘：账面→实物测存在性，实物→账面测完整性。</li>
        <li>三数量：账面数量、企业盘点数量、审计抽盘数量；旧「实际数量」已映射为抽盘数量。</li>
        <li>标识（耳标/树牌）不一致可能表明资产存在性或权属问题，应进一步核实。</li>
        <li>完成后汇入 H7-10 监盘小结。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import H1CheckDirectionTable from '../../h1/stocktake/H1CheckDirectionTable.vue'
import { useH7Stocktake } from '../../composables/useH7Stocktake'
import {
  normalizeDirection,
  deriveResultFromQty,
  calcRowDiffs,
  type StocktakeDirection,
  type StocktakeCheckRow as H1Row,
} from '../../composables/h1StocktakeCheckModel'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const stk = useH7Stocktake(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const CATEGORY_OPTIONS = ['经济林木', '产畜', '产蛋/产奶禽畜', '水产养殖', '其他']

interface Row {
  rowId: string
  name: string
  category: string
  unit: string
  direction: StocktakeDirection
  bookQty: number
  /** 兼容旧字段：读时归一到 sampleQty，写时双写 */
  actualQty: number
  sampleQty: number
  clientCountQty: number
  bookAmount: number
  unitPrice: number
  assetNo: string
  qualityStatus: string
  identityCheck: string
  result: string
  diffReason: string
  remark: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function normalize(raw: any): Row {
  const sampleQty = _num(raw.sampleQty ?? raw.actualQty)
  const bookQty = _num(raw.bookQty)
  let result = String(raw.result ?? '')
  if (!result && (bookQty > 0 || sampleQty > 0)) {
    result = deriveResultFromQty(sampleQty, bookQty)
  }
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    name: String(raw.name ?? ''),
    category: String(raw.category ?? ''),
    unit: String(raw.unit ?? ''),
    direction: normalizeDirection(raw.direction),
    bookQty,
    actualQty: _num(raw.actualQty ?? sampleQty),
    sampleQty,
    clientCountQty: _num(raw.clientCountQty),
    bookAmount: _num(raw.bookAmount),
    unitPrice: _num(raw.unitPrice),
    assetNo: String(raw.assetNo ?? ''),
    qualityStatus: String(raw.qualityStatus ?? ''),
    identityCheck: String(raw.identityCheck ?? ''),
    result,
    diffReason: String(raw.diffReason ?? ''),
    remark: String(raw.remark ?? ''),
  }
}

function syncQty(row: Row): void {
  row.actualQty = row.sampleQty
  if (row.bookQty > 0 || row.sampleQty > 0 || row.clientCountQty > 0) {
    row.result = deriveResultFromQty(row.sampleQty, row.bookQty)
  }
}

function toH1(r: Row): H1Row {
  return {
    rowId: r.rowId,
    seq: 0,
    direction: r.direction,
    name: r.name,
    assetNo: r.assetNo,
    location: '',
    spec: '',
    unit: r.unit,
    unitPrice: r.unitPrice,
    bookQty: r.bookQty,
    bookAmount: r.bookAmount,
    clientCountQty: r.clientCountQty,
    sampleQty: r.sampleQty,
    qualityStatus: r.qualityStatus,
    result: r.result,
    diffReason: r.diffReason,
    diffAmount: 0,
    suggestion: '',
    checker: '',
    remark: r.remark,
    bookCost: r.bookAmount,
    bookNetValue: 0,
    actualStatus: r.qualityStatus || '',
    photoUrl: '',
    nameplateCheck: r.identityCheck,
    quantityCheck: Math.abs(r.sampleQty - r.bookQty) < 0.001 ? '一致' : '不一致',
    conditionAssess: '',
  }
}

const b2fH1 = computed(() => rows.value.filter((r) => r.direction === 'bookToFloor').map(toH1))
const f2bH1 = computed(() => rows.value.filter((r) => r.direction === 'floorToBook').map(toH1))
const b2fVariance = computed(() => b2fH1.value.filter((r) => calcRowDiffs(r).hasVariance).length)
const f2bVariance = computed(() => f2bH1.value.filter((r) => calcRowDiffs(r).hasVariance).length)

const stat = computed(() => {
  const s = { match: 0, surplus: 0, deficit: 0, identityMismatch: 0, matchRate: 0 }
  for (const r of rows.value) {
    if (r.result === '账实相符') s.match++
    else if (r.result === '盘盈') s.surplus++
    else if (r.result === '盘亏') s.deficit++
    if (r.identityCheck === '不一致') s.identityMismatch++
  }
  s.matchRate = rows.value.length ? (s.match / rows.value.length) * 100 : 0
  return s
})

function seed(): void {
  const raw = stk.getString('H7-9-rows')
  if (raw) {
    try {
      const p = JSON.parse(raw)
      if (Array.isArray(p)) rows.value = p.map(normalize)
    } catch { /* ignore */ }
  }
  auditNote.value = stk.getString('H7-9-note') || ''
  auditConclusion.value = stk.getString('H7-9-conclusion') || ''
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-9-rows', rows.value) }

function onRowUpdate(rowId: string, patch: Partial<H1Row>): void {
  const row = rows.value.find((r) => r.rowId === rowId)
  if (!row) return
  if (patch.name != null) row.name = patch.name
  if (patch.assetNo != null) row.assetNo = patch.assetNo
  if (patch.unit != null) row.unit = patch.unit
  if (patch.unitPrice != null) row.unitPrice = _num(patch.unitPrice)
  if (patch.bookQty != null) row.bookQty = _num(patch.bookQty)
  if (patch.bookAmount != null) row.bookAmount = _num(patch.bookAmount)
  if (patch.clientCountQty != null) row.clientCountQty = _num(patch.clientCountQty)
  if (patch.sampleQty != null) row.sampleQty = _num(patch.sampleQty)
  if (patch.qualityStatus != null) row.qualityStatus = patch.qualityStatus
  if (patch.diffReason != null) row.diffReason = patch.diffReason
  if (patch.remark != null) row.remark = patch.remark
  if (patch.nameplateCheck != null) row.identityCheck = patch.nameplateCheck
  syncQty(row)
  persistRows()
}

async function handleAddRow(direction: StocktakeDirection): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入生物资产名称', '新增盘点项', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (name) {
      rows.value.push(normalize({ name, direction }))
      persistRows()
    }
  } catch { /* cancelled */ }
}

function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}

function onDraftConclusion(): void {
  if (props.isReadonly) return
  const s = stat.value
  const lines = [
    `本次生产性生物资产抽盘共检查 ${rows.value.length} 项（账面→实物 ${b2fH1.value.length}、实物→账面 ${f2bH1.value.length}）。`,
    `账实相符 ${s.match} 项，相符率 ${s.matchRate.toFixed(1)}%；盘盈 ${s.surplus}、盘亏 ${s.deficit}；标识不一致 ${s.identityMismatch} 项。`,
  ]
  if (rows.value.length === 0) {
    lines.push('尚未录入抽盘明细，本节审计目标尚待执行后结论。')
  } else if (s.deficit > 0 || s.identityMismatch > 0) {
    lines.push('存在盘亏或标识不符，已在检查表记录原因；需关注计价与减值影响，并汇入 H7-10。')
  } else {
    lines.push('双向抽盘未发现重大账实不符；存在性与完整性认定可获合理保证。详见 H7-8/H7-10。')
  }
  auditConclusion.value = lines.join('\n')
  persist('H7-9-conclusion', auditConclusion.value)
}

function handleReview(id: string): void { openReviewDialog(id) }
</script>

<style scoped>
.h7-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; }
.note-card, .block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.ml-tag { margin-left: 8px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.text-warn { color: var(--el-color-warning); }
.text-danger { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-bottom: 12px; background: var(--el-fill-color-light); border-radius: 4px; flex-wrap: wrap; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
