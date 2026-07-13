<template>
  <div class="h7-tab-stocktake-check">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：通过现场监盘核对生产性生物资产的账面数量/金额与实际状况，识别盘盈盘亏及资产存在性、状况异常，评价资产计价与减值影响（CAS 5 / CAS 1311 参照适用）。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-9" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>
            H7-9 盘点检查表（{{ rows.length }} 项）
            <GtIndexChip value="wp:H7-10" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H7-9')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border stripe size="small" max-height="500" class="check-table">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="name" label="生物资产名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persistRows" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.category" size="small" @change="persistRows">
              <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unit" label="单位" width="70">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unit" size="small" placeholder="头/株/尾" @change="persistRows" />
            <span v-else>{{ row.unit }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookQty" label="账面数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookQty" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtNum(row.bookQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actualQty" label="实际数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.actualQty" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtNum(row.actualQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数量差异" width="100" align="right">
          <template #default="{ row }">
            <span class="calc-cell" :class="{ 'has-diff': qtyDiff(row) !== 0 }" title="=实际数量-账面数量">{{ fmtNum(qtyDiff(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAmount" label="账面金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookAmount" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="identityCheck" label="标识核对" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.identityCheck" size="small" style="width:80px" @change="persistRows">
              <el-option label="一致" value="一致" />
              <el-option label="不一致" value="不一致" />
            </el-select>
            <el-tag v-else :type="row.identityCheck === '一致' ? 'success' : 'danger'" size="small">{{ row.identityCheck || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="盘点结果" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.result" size="small" style="width:92px" @change="persistRows">
              <el-option label="账实相符" value="账实相符" />
              <el-option label="盘盈" value="盘盈" />
              <el-option label="盘亏" value="盘亏" />
            </el-select>
            <el-tag v-else :type="resultTag(row.result)" size="small">{{ row.result || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="diffReason" label="差异原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.diffReason" size="small" @change="persistRows" />
            <span v-else>{{ row.diffReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>账实相符：<b>{{ stat.match }}</b></span>
        <span>盘盈：<b class="text-warn">{{ stat.surplus }}</b></span>
        <span>盘亏：<b :class="{ 'text-danger': stat.deficit > 0 }">{{ stat.deficit }}</b></span>
        <span>标识不一致：<b :class="{ 'text-danger': stat.identityMismatch > 0 }">{{ stat.identityMismatch }}</b></span>
        <span>相符率：<b>{{ stat.matchRate.toFixed(1) }}%</b></span>
      </div>
    </el-card>

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
        <li>数量差异 = 实际数量 − 账面数量；差异 ≠ 0 时红色高亮。</li>
        <li>盘点结果三选一：账实相符 / 盘盈 / 盘亏；盘亏需附差异原因及建议处理方式。</li>
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
import { useH7Stocktake } from '../../composables/useH7Stocktake'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
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
  bookQty: number
  actualQty: number
  bookAmount: number
  identityCheck: string
  result: string
  diffReason: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function qtyDiff(r: Row): number { return (Number(r.actualQty) || 0) - (Number(r.bookQty) || 0) }

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

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    name: raw.name ?? '',
    category: raw.category ?? '',
    unit: raw.unit ?? '',
    bookQty: Number(raw.bookQty) || 0,
    actualQty: Number(raw.actualQty) || 0,
    bookAmount: Number(raw.bookAmount) || 0,
    identityCheck: raw.identityCheck ?? '',
    result: raw.result ?? '',
    diffReason: raw.diffReason ?? '',
  }
}

function seed(): void {
  const raw = stk.getString('H7-9-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = stk.getString('H7-9-note') || ''
  auditConclusion.value = stk.getString('H7-9-conclusion') || ''
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-9-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入生物资产名称', '新增盘点项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (name) { rows.value.push(normalize({ name })); persistRows() }
  } catch { /* cancelled */ }
}
function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}
function resultTag(r: string): 'success' | 'warning' | 'danger' | 'info' {
  if (r === '账实相符') return 'success'
  if (r === '盘盈') return 'warning'
  if (r === '盘亏') return 'danger'
  return 'info'
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtNum(v: number | null | undefined): string { return v == null ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function fmtAmt(v: number | null | undefined): string { return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h7-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.note-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; background: var(--el-fill-color-light); border-bottom: 1px dashed var(--el-border-color); cursor: help; display: inline-block; width: 100%; text-align: right; }
.calc-cell.has-diff { color: var(--el-color-danger); font-weight: 600; }
.text-warn { color: var(--el-color-warning); }
.text-danger { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
