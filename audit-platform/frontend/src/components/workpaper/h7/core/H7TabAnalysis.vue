<template>
  <div class="h7-tab-analysis">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：通过分析性程序评价生产性生物资产各分类的期间变动合理性，
        识别原值/净值/折旧率异常波动（超30%），并取得管理层解释。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增分类行</el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-5" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 摘要指标 -->
    <div class="summary-row">
      <div class="summary-item"><span class="label">本期原值合计</span><span class="value">{{ fmtAmt(totalCurrentCost) }}</span></div>
      <div class="summary-item"><span class="label">本期净值合计</span><span class="value">{{ fmtAmt(totalCurrentNet) }}</span></div>
      <div class="summary-item"><span class="label">综合折旧率</span><span class="value">{{ overallDepRate.toFixed(2) }}%</span></div>
    </div>

    <!-- 重大变动预警 -->
    <el-alert v-if="abnormalCount > 0" type="warning" :closable="false" show-icon class="warn-alert">
      <template #title>{{ abnormalCount }} 项原值变动率超30%，请关注并说明原因。</template>
    </el-alert>

    <el-table :data="rows" border stripe size="small" class="analysis-table">
      <el-table-column prop="category" label="资产分类" min-width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.category" size="small" @change="onUpdate()" />
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期原值" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.priorCost" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.priorCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期原值" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.currentCost" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.currentCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原值变动率" min-width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ abnormal: Math.abs(costChangeRate(row)) > 30 }" title="变动率=(本期-上期)/上期×100">{{ costChangeRate(row).toFixed(2) }}%</span>
        </template>
      </el-table-column>
      <el-table-column label="累计折旧" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.accDep" :controls="false" size="small" class="amt-input" @change="onUpdate()" />
          <span v-else class="amount-cell">{{ fmtAmt(row.accDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="折旧率" min-width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="折旧率=累计折旧/本期原值×100">{{ depRate(row).toFixed(2) }}%</span>
        </template>
      </el-table-column>
      <el-table-column label="本期净值" min-width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="净值=本期原值-累计折旧">{{ fmtAmt(netVal(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="explanation" label="变动原因" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.explanation" size="small" @change="onUpdate()" />
          <span v-else>{{ row.explanation }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>分析性程序结论</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-5')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="分析性程序结论..." :disabled="isReadonly" @blur="persist('H7-5-conclusion', conclusion)" />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="记录分析性程序的实施情况、异常波动分析与结论。" @blur="persist('H7-5-note', auditNote)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>对比上期评价各分类生产性生物资产原值/净值变动合理性。</li>
        <li>变动率异常项(绝对值>30%)须取得管理层解释并记录。</li>
        <li>折旧率应符合各类生物资产的经济寿命与折旧政策。</li>
        <li>关注畜禽存栏变动、经济林更新改造、自然灾害损失等对余额的影响。</li>
        <li>新增分类行须先输入分类名称确认后创建。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabAnalysis.vue — H7-5 分析表
 *
 * 分类变动率/折旧率分析 + 摘要指标 + 异常预警(>30%) + 动态行。
 * 消费 useH7Analysis(getString 种子) + api.put 持久化(remark, JSON 打包行数组)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 分析性程序
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Analysis } from '../../composables/useH7Analysis'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
const { getString, getNum } = useH7Analysis(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface AnalysisRow { rowId: string; category: string; priorCost: number; currentCost: number; accDep: number; explanation: string }
function blankRow(cat: string): AnalysisRow {
  return { rowId: `a${Date.now()}${Math.floor(Math.random() * 1000)}`, category: cat, priorCost: 0, currentCost: 0, accDep: 0, explanation: '' }
}

const rows = ref<AnalysisRow[]>([])
const conclusion = ref('')
const auditNote = ref('')

function costChangeRate(r: AnalysisRow): number { return num(r.priorCost) === 0 ? 0 : ((num(r.currentCost) - num(r.priorCost)) / num(r.priorCost)) * 100 }
function depRate(r: AnalysisRow): number { return num(r.currentCost) === 0 ? 0 : (num(r.accDep) / num(r.currentCost)) * 100 }
function netVal(r: AnalysisRow): number { return num(r.currentCost) - num(r.accDep) }

const totalCurrentCost = computed(() => rows.value.reduce((s, r) => s + num(r.currentCost), 0))
const totalCurrentNet = computed(() => rows.value.reduce((s, r) => s + netVal(r), 0))
const overallDepRate = computed(() => totalCurrentCost.value === 0 ? 0 : (rows.value.reduce((s, r) => s + num(r.accDep), 0) / totalCurrentCost.value) * 100)
const abnormalCount = computed(() => rows.value.filter((r) => Math.abs(costChangeRate(r)) > 30).length)

async function loadOwn() {
  try {
    const list: any[] = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const m = new Map(localResponses.value)
    for (const r of (Array.isArray(list) ? list : [])) {
      if (r.item_id?.startsWith('H7-')) m.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
    }
    localResponses.value = m
  } catch { /* empty */ }
  const raw = getString('H7-5-rows')
  if (raw) { try { const arr = JSON.parse(raw); if (Array.isArray(arr)) rows.value = arr } catch { /* ignore */ } }
  conclusion.value = getString('H7-5-conclusion') || ''
  auditNote.value = getString('H7-5-note') || ''
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

function onUpdate() { void persist('H7-5-rows', rows.value) }

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产分类名称', '新增分类行', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(blankRow(value)); onUpdate() }
  } catch { /* cancelled */ }
}

function removeRow(rowId: string) {
  rows.value = rows.value.filter((r) => r.rowId !== rowId)
  onUpdate()
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => { void loadOwn() })
</script>

<style scoped>
.h7-tab-analysis { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.summary-item .label { color: var(--el-text-color-secondary); margin-right: 6px; }
.summary-item .value { font-weight: 600; font-variant-numeric: tabular-nums; }
.warn-alert { margin-bottom: 12px; }
.analysis-table { font-size: var(--wp-font-size, 13px); }
.analysis-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell.abnormal { color: var(--el-color-warning); font-weight: 600; }
.note-card { margin: 16px 0; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
