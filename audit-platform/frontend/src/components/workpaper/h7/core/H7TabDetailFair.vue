<template>
  <div class="h7-tab-detail-fair">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：分类核对生产性生物资产明细（公允价值模式），验证各资产期末公允价值与公允价值变动损益的准确性，
        合计与 H7-1 审定表交叉勾稽一致。
      </template>
    </el-alert>

    <!-- 区段切换 -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增资产行</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="warning">公允价值模式 · 共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 基础信息 -->
    <el-table v-if="activeSegment === 'basic'" :data="displayRows" border stripe size="small" class="detail-table">
      <el-table-column prop="assetName" label="资产名称" min-width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="!row.isSubtotal && !isReadonly" v-model="row.assetName" size="small" @change="onUpdate()" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="assetType" label="类别" min-width="110">
        <template #default="{ row }">
          <el-select v-if="!row.isSubtotal && !isReadonly" v-model="row.assetType" size="small" @change="onUpdate()">
            <el-option v-for="t in ASSET_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.assetType }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" min-width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.quantity" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ row.quantity || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="fvLevel" label="公允价值层级" min-width="120">
        <template #default="{ row }">
          <el-select v-if="!row.isSubtotal && !isReadonly" v-model="row.fvLevel" size="small" @change="onUpdate()">
            <el-option v-for="l in FV_LEVELS" :key="l" :label="l" :value="l" />
          </el-select>
          <span v-else>{{ row.fvLevel }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!row.isSubtotal && !isReadonly" size="small" type="danger" link @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 公允价值变动 -->
    <el-table v-if="activeSegment === 'fv'" :data="displayRows" border stripe size="small" class="detail-table">
      <el-table-column prop="assetName" label="资产名称" min-width="150" fixed />
      <el-table-column label="期初公允价值" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.fvBegin" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.fvBegin) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期增加" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.increase" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期减少" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.decrease" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公允价值变动损益" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isSubtotal && !isReadonly" v-model="row.fvChange" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.fvChange) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末公允价值" min-width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="期末公允价值=期初+增加-减少+公允价值变动损益">{{ fmtAmt(fvEnd(row)) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 交叉验证 -->
    <el-alert v-if="crossDiff !== 0" type="warning" :closable="false" show-icon class="cross-alert">
      <template #title>交叉验证：明细期末公允价值合计 {{ fmtAmt(totalFvEnd) }} 与 H7-1 审定数差异 {{ fmtAmt(crossDiff) }}，请核对。</template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi('detail-fair')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" link @click="handleReview('H7-2-fair')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写审计说明/结论（公允价值确定依据、层级、变动合理性等）..." :disabled="isReadonly" @blur="persist('H7-2-fair-note', auditNote)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>公允价值模式明细分2区段(基础信息/公允价值变动)，行保持同步。</li>
        <li>期末公允价值=期初+本期增加-本期减少+公允价值变动损益。</li>
        <li>公允价值变动计入当期损益，不计提折旧减值。</li>
        <li>公允价值层级(L1活跃市场报价/L2可观察输入值/L3不可观察输入值)须逐项判断。</li>
        <li>合计行期末公允价值与 H7-1 审定表交叉验证；差异非零时须查明原因。</li>
        <li>新增资产行须先输入资产名称确认后创建。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabDetailFair.vue — H7-2 明细表（公允价值模式）
 *
 * 2区段(基础信息/公允价值变动)行同步 + 合计 + 与H7-1交叉验证 + 动态行。
 * 消费 useH7DetailFair(getString 种子) + api.put 持久化(remark, JSON 打包行数组)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 双计量·公允价值模式明细
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7DetailFair } from '../../composables/useH7DetailFair'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
const { getString, getNum } = useH7DetailFair(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const ASSET_TYPES = ['经济林', '薪炭林', '产畜', '役畜', '其他']
const FV_LEVELS = ['第一层次(L1)', '第二层次(L2)', '第三层次(L3)']
const segmentOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '公允价值变动', value: 'fv' },
]
const activeSegment = ref<'basic' | 'fv'>('basic')

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface FairDetailRow {
  rowId: string; assetName: string; assetType: string; quantity: number; fvLevel: string
  fvBegin: number; increase: number; decrease: number; fvChange: number
  isSubtotal?: boolean
}

function blankRow(name: string): FairDetailRow {
  return { rowId: `r${Date.now()}${Math.floor(Math.random() * 1000)}`, assetName: name, assetType: '经济林', quantity: 0, fvLevel: '第二层次(L2)', fvBegin: 0, increase: 0, decrease: 0, fvChange: 0 }
}

const rows = ref<FairDetailRow[]>([])
const auditNote = ref('')

function fvEnd(r: FairDetailRow): number { return num(r.fvBegin) + num(r.increase) - num(r.decrease) + num(r.fvChange) }

const totalFvEnd = computed(() => rows.value.reduce((s, r) => s + fvEnd(r), 0))
const subtotalRow = computed<FairDetailRow>(() => ({
  rowId: 'subtotal', assetName: '合计', assetType: '', quantity: rows.value.reduce((s, r) => s + num(r.quantity), 0), fvLevel: '',
  fvBegin: rows.value.reduce((s, r) => s + num(r.fvBegin), 0),
  increase: rows.value.reduce((s, r) => s + num(r.increase), 0),
  decrease: rows.value.reduce((s, r) => s + num(r.decrease), 0),
  fvChange: rows.value.reduce((s, r) => s + num(r.fvChange), 0),
  isSubtotal: true,
}))
const displayRows = computed(() => [...rows.value, subtotalRow.value])

const crossDiff = computed(() => {
  const adjRaw = getString('H7-1-fair')
  if (!adjRaw) return 0
  try {
    const adj = JSON.parse(adjRaw)
    const audited = num(adj.unadjusted) + num(adj.aje)
    return Number((totalFvEnd.value - audited).toFixed(2))
  } catch { return 0 }
})

async function loadOwn() {
  try {
    const list: any[] = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const m = new Map(localResponses.value)
    for (const r of (Array.isArray(list) ? list : [])) {
      if (r.item_id?.startsWith('H7-')) m.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
    }
    localResponses.value = m
  } catch { /* empty */ }
  const raw = getString('H7-2-fair-rows')
  if (raw) { try { const arr = JSON.parse(raw); if (Array.isArray(arr)) rows.value = arr } catch { /* ignore */ } }
  auditNote.value = getString('H7-2-fair-note') || ''
  void getNum
}

async function persist(itemId: string, value: any) {
  const remark = value == null ? null : (typeof value === 'string' ? value : JSON.stringify(value))
  localResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark })
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark }],
    })
  } catch { ElMessage.error('保存失败，请稍后重试') }
}

function onUpdate() { void persist('H7-2-fair-rows', rows.value) }

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '新增资产行', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(blankRow(value)); onUpdate() }
  } catch { /* cancelled */ }
}

function removeRow(rowId: string) {
  rows.value = rows.value.filter((r) => r.rowId !== rowId)
  onUpdate()
}

function handleAi(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => { void loadOwn() })
</script>

<style scoped>
.h7-tab-detail-fair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.segment-bar { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.detail-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.detail-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.cross-alert { margin-bottom: 12px; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
