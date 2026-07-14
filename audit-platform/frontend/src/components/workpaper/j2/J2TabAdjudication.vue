<script setup lang="ts">
/**
 * J2TabAdjudication — J2-1 长期应付职工薪酬/设定受益计划净资产审定表（专项组件）
 *
 * 对齐源模板「审定表J2-1」全结构：
 *  ① 主审定表（设定受益计划/其中离职后福利·其他长期/辞退福利/减一年内/合计）
 *  ② 未终止设定受益福利期后支付账龄分析
 *  ③ (1) 设定受益计划情况（DBO 现值六要素分解 + 计划资产公允价值 + 净负债）
 *  ④ (2) 计划资产公允价值构成
 *  ⑤ (3) 精算假设（折现率/死亡率/工资增长率/离职率）
 *  ⑥ (4) 敏感性分析
 *  ⑦ 试算平衡表勾稽 + 审计说明 + 审计结论
 *
 * 未审数默认从 TB(2221) seed；各区块 JSON 持久化到 checklist_responses.remark。
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 */
import { ref, reactive, computed, inject, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { GenerateWorkpaperAiText } from '../composables/useWorkpaperScaffold'
import GtIndexChip from '../GtIndexChip.vue'

interface RespItem { item_id: string; conclusion: string | null; remark: string | null }

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, RespItem>
  isReadonly?: boolean
  saveImmediate?: (items: RespItem[]) => Promise<void> | void
}>()

const isReadonly = computed(() => props.isReadonly ?? false)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const mode = ref<'html' | 'oo'>('html')

// ─── 持久化 item_id ────────────────────────────────────────────────────────
const KEY = {
  main: 'J2-1-main',
  post: 'J2-1-postperiod',
  dbo: 'J2-1-dbo',
  assets: 'J2-1-plan-assets',
  assume: 'J2-1-assumptions',
  sens: 'J2-1-sensitivity',
  note: 'J2-1-note',
  concl: 'J2-1-conclusion',
}

// ─── 数值工具 ────────────────────────────────────────────────────────────────
function n(v: unknown): number {
  const x = typeof v === 'number' ? v : parseFloat(String(v ?? ''))
  return Number.isFinite(x) ? x : 0
}
function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return (v * 100).toFixed(2) + '%'
}

// ─── ① 主审定表 ──────────────────────────────────────────────────────────────
interface MainRow {
  key: string; label: string; indent: number
  beginUnadj: number; beginAje: number
  endUnadj: number; endAje: number
  reason: string
}
function emptyMain(key: string, label: string, indent = 0): MainRow {
  return { key, label, indent, beginUnadj: 0, beginAje: 0, endUnadj: 0, endAje: 0, reason: '' }
}
const mainRows = reactive<MainRow[]>([
  emptyMain('dbp', '设定受益计划', 0),
  emptyMain('post_emp', '其中：离职后福利', 1),
  emptyMain('other_lt', '其中：其他长期职工福利', 1),
  emptyMain('termination', '辞退福利', 0),
  emptyMain('less_within1y', '减：一年内支付的长期应付职工薪酬', 0),
])
function auditedOf(r: MainRow, period: 'begin' | 'end'): number {
  return period === 'begin' ? n(r.beginUnadj) + n(r.beginAje) : n(r.endUnadj) + n(r.endAje)
}
/** 合计 = 设定受益计划 + 辞退福利 − 一年内（顶层项，不含"其中"子项） */
const mainTotal = computed(() => {
  const dbp = mainRows.find(r => r.key === 'dbp')!
  const term = mainRows.find(r => r.key === 'termination')!
  const less = mainRows.find(r => r.key === 'less_within1y')!
  const beginUnadj = n(dbp.beginUnadj) + n(term.beginUnadj) - n(less.beginUnadj)
  const beginAudited = auditedOf(dbp, 'begin') + auditedOf(term, 'begin') - auditedOf(less, 'begin')
  const endUnadj = n(dbp.endUnadj) + n(term.endUnadj) - n(less.endUnadj)
  const endAudited = auditedOf(dbp, 'end') + auditedOf(term, 'end') - auditedOf(less, 'end')
  return { beginUnadj, beginAudited, endUnadj, endAudited }
})
function changeAmt(r: MainRow): number { return auditedOf(r, 'end') - auditedOf(r, 'begin') }
function changeRate(r: MainRow): number {
  const b = auditedOf(r, 'begin'); return b === 0 ? 0 : (auditedOf(r, 'end') - b) / b
}

// ─── ② 期后账龄分析 ──────────────────────────────────────────────────────────
const postRows = reactive([
  { key: 'y1', label: '一年以内（含一年）', amount: 0 },
  { key: 'y1_2', label: '一至二年', amount: 0 },
  { key: 'y2_5', label: '二至五年', amount: 0 },
  { key: 'y5', label: '五年以上', amount: 0 },
])
const postTotal = computed(() => postRows.reduce((s, r) => s + n(r.amount), 0))

// ─── ③ (1) 设定受益计划情况（DBO 六要素） ────────────────────────────────────
interface DboRow { key: string; label: string; indent: number; group?: boolean; dboUnadj: number; dboAje: number; planAsset: number }
function emptyDbo(key: string, label: string, indent = 0, group = false): DboRow {
  return { key, label, indent, group, dboUnadj: 0, dboAje: 0, planAsset: 0 }
}
const dboRows = reactive<DboRow[]>([
  emptyDbo('begin', '一、期初余额', 0),
  emptyDbo('pl_group', '二、计入当期损益的设定受益成本', 0, true),
  emptyDbo('pl_service', '1. 当期服务成本', 1),
  emptyDbo('pl_past', '2. 过去服务成本', 1),
  emptyDbo('pl_settle', '3. 结算利得和损失（损失以"-"号填列）', 1),
  emptyDbo('pl_interest', '4. 利息费用/利息收入', 1),
  emptyDbo('oci_group', '三、计入其他综合收益的设定受益成本', 0, true),
  emptyDbo('oci_actuarial', '1. 精算利得（损失以"-"号填列）', 1),
  emptyDbo('oci_return', '2. 计划资产的回报（计入利息费用净额的除外）', 1),
  emptyDbo('oci_ceiling', '3. 资产上限影响的变动（计入利息费用净额的除外）', 1),
  emptyDbo('other_group', '四、其他变动', 0, true),
  emptyDbo('other_settle', '结算对应付款的负债', 1),
  emptyDbo('other_paid', '已支付的福利', 1),
  emptyDbo('end', '五、期末余额', 0),
])
function dboAudited(r: DboRow): number { return n(r.dboUnadj) + n(r.dboAje) }
function dboNet(r: DboRow): number { return dboAudited(r) - n(r.planAsset) }

// ─── ④ (2) 计划资产公允价值 ───────────────────────────────────────────────────
interface AssetRow { key: string; label: string; indent: number; unadj: number; aje: number; begin: number }
function emptyAsset(key: string, label: string, indent = 0): AssetRow {
  return { key, label, indent, unadj: 0, aje: 0, begin: 0 }
}
const assetRows = reactive<AssetRow[]>([
  emptyAsset('cash', '现金和现金等价物', 0),
  emptyAsset('equity', '权益工具投资', 0),
  emptyAsset('debt', '债务工具投资', 0),
  emptyAsset('other', '其他', 0),
])
function assetEnd(r: AssetRow): number { return n(r.unadj) + n(r.aje) }
const assetTotal = computed(() => ({
  unadj: assetRows.reduce((s, r) => s + n(r.unadj), 0),
  aje: assetRows.reduce((s, r) => s + n(r.aje), 0),
  end: assetRows.reduce((s, r) => s + assetEnd(r), 0),
  begin: assetRows.reduce((s, r) => s + n(r.begin), 0),
}))

// ─── ⑤ (3) 精算假设 ──────────────────────────────────────────────────────────
const assumeRows = reactive([
  { key: 'discount', label: '折现率', end: 0, begin: 0 },
  { key: 'mortality', label: '死亡率', end: 0, begin: 0 },
  { key: 'salary', label: '预计工资增长率', end: 0, begin: 0 },
  { key: 'turnover', label: '职工的离职率', end: 0, begin: 0 },
  { key: 'medical', label: '医疗费用增长率', end: 0, begin: 0 },
])

// ─── ⑥ (4) 敏感性分析 ────────────────────────────────────────────────────────
const sensRows = reactive([
  { key: 'discount', label: '折现率', delta: 0, up: 0, down: 0 },
  { key: 'mortality', label: '死亡率', delta: 0, up: 0, down: 0 },
  { key: 'salary', label: '工资增长率', delta: 0, up: 0, down: 0 },
  { key: 'turnover', label: '离职率', delta: 0, up: 0, down: 0 },
])

// ─── 审计说明/结论 ────────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

/** AI 辅助生成审计说明/结论（统一 Runtime AI provider，附审定表关键数据上下文） */
async function aiGenerate(kind: 'note' | 'conclusion') {
  if (isReadonly.value) return
  const loadingRef = kind === 'note' ? aiLoadingNote : aiLoadingConclusion
  loadingRef.value = true
  try {
    // 端点要求 context 为 dict[str,str]，所有值转字符串
    const context: Record<string, string> = {
      科目: '2221 长期应付职工薪酬 / 设定受益计划净资产',
      期初审定合计: fmt(mainTotal.value.beginAudited),
      期末审定合计: fmt(mainTotal.value.endAudited),
      试算平衡表数: fmt(tbAmount.value),
      勾稽差异: fmt(tbDiff.value),
      设定受益计划期末未审: fmt(n(mainRows.find(r => r.key === 'dbp')?.endUnadj)),
      辞退福利期末未审: fmt(n(mainRows.find(r => r.key === 'termination')?.endUnadj)),
      折现率: fmtPct(assumeRows.find(r => r.key === 'discount')?.end ?? 0),
      工资增长率: fmtPct(assumeRows.find(r => r.key === 'salary')?.end ?? 0),
    }
    const existing = kind === 'note' ? auditNote.value : auditConclusion.value
    const text = await generateAiText({
      section: `j2-adjudication-${kind}`,
      context,
      existingContent: existing,
    })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
    } else {
      if (kind === 'note') auditNote.value = text
      else auditConclusion.value = text
      scheduleSave()
    }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally {
    loadingRef.value = false
  }
}

// ─── 试算平衡表勾稽 ───────────────────────────────────────────────────────────
const tbAmount = ref(0)
const tbDiff = computed(() => mainTotal.value.endAudited - tbAmount.value)

// ─── 加载 ─────────────────────────────────────────────────────────────────────
function parseJson<T>(itemId: string, fallback: T): T {
  const raw = props.allResponses?.get(itemId)?.remark
  if (!raw) return fallback
  try { const p = JSON.parse(raw); return (p ?? fallback) as T } catch { return fallback }
}
// 固定展示字段（label/indent/group/seq 等）以组件权威默认值为准，禁止被持久化值覆盖，
// 避免历史 remark 中的编码损坏或结构漂移随保存链持续放大。
const PRESENTATION_FIELDS = new Set(['label', 'indent', 'group', 'seq'])
function assignRows<T extends object>(target: T[], saved: unknown) {
  if (!Array.isArray(saved)) return
  for (const s of saved as Record<string, unknown>[]) {
    const row = target.find(r => (r as Record<string, unknown>).key === s.key)
    if (!row) continue
    for (const [field, value] of Object.entries(s)) {
      if (PRESENTATION_FIELDS.has(field)) continue
      ;(row as Record<string, unknown>)[field] = value
    }
  }
}
function load() {
  assignRows(mainRows, parseJson(KEY.main, null))
  assignRows(postRows, parseJson(KEY.post, null))
  assignRows(dboRows, parseJson(KEY.dbo, null))
  assignRows(assetRows, parseJson(KEY.assets, null))
  assignRows(assumeRows, parseJson(KEY.assume, null))
  assignRows(sensRows, parseJson(KEY.sens, null))
  auditNote.value = props.allResponses?.get(KEY.note)?.remark || ''
  auditConclusion.value = props.allResponses?.get(KEY.concl)?.remark || ''
  // TB seed（未审数默认取 2221 审定/未审额，仅在主表未审全为 0 时 seed 到设定受益计划行）
  const tb = (props.htmlData?.tb_data || {}) as Record<string, number>
  tbAmount.value = n(tb.audited_amount)
  const anyMain = mainRows.some(r => n(r.endUnadj) !== 0 || n(r.beginUnadj) !== 0)
  if (!anyMain && n(tb.audited_amount) !== 0) {
    const dbp = mainRows.find(r => r.key === 'dbp')!
    dbp.endUnadj = n(tb.unadjusted_amount) || n(tb.audited_amount)
  }
}

// ─── 保存（防抖） ─────────────────────────────────────────────────────────────
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  const items: RespItem[] = [
    { item_id: KEY.main, conclusion: null, remark: JSON.stringify(mainRows) },
    { item_id: KEY.post, conclusion: null, remark: JSON.stringify(postRows) },
    { item_id: KEY.dbo, conclusion: null, remark: JSON.stringify(dboRows) },
    { item_id: KEY.assets, conclusion: null, remark: JSON.stringify(assetRows) },
    { item_id: KEY.assume, conclusion: null, remark: JSON.stringify(assumeRows) },
    { item_id: KEY.sens, conclusion: null, remark: JSON.stringify(sensRows) },
    { item_id: KEY.note, conclusion: null, remark: auditNote.value },
    { item_id: KEY.concl, conclusion: null, remark: auditConclusion.value },
  ]
  props.saveImmediate(items)
}

onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j2-tab-adjudication">
    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="mode" :options="[{ label: 'HTML', value: 'html' }, { label: 'OnlyOffice', value: 'oo' }]" size="small" />
      <span class="chip-wrap"><GtIndexChip value="wp:J2-2" :context-project-id="projectId" /></span>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：确认设定受益计划净负债/净资产、其他长期职工福利及辞退福利的期初、期末审定数的准确性，分析变动合理性，形成审定结论并回写试算平衡表（科目 2221）。
      </template>
    </el-alert>

    <template v-if="mode === 'html'">
      <h3 class="doc-title">长期应付职工薪酬/设定受益计划净资产审定表</h3>

      <!-- ① 主审定表 -->
      <el-table :data="mainRows" border size="small" class="wp-table">
        <el-table-column label="项目名称" min-width="200" fixed>
          <template #default="{ row }">
            <span :style="{ paddingLeft: row.indent * 16 + 'px' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.beginUnadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(row.beginUnadj) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.beginAje" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(row.beginAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="未审+调整">{{ fmt(auditedOf(row, 'begin')) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.endUnadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(row.endUnadj) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.endAje" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(row.endAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="未审+调整">{{ fmt(auditedOf(row, 'end')) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期审定与上期审定比较" align="center">
          <el-table-column label="变动额" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(changeAmt(row)) }}</template>
          </el-table-column>
          <el-table-column label="变动率" width="80" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span :class="{ 'text-danger': Math.abs(changeRate(row)) > 0.3 }">{{ fmtPct(changeRate(row)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="scheduleSave" />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="total-row">
        <span>合计（设定受益计划 + 辞退福利 − 一年内）</span>
        <span>期初审定：{{ fmt(mainTotal.beginAudited) }}</span>
        <span>期末审定：{{ fmt(mainTotal.endAudited) }}</span>
      </div>

      <!-- 试算平衡表勾稽 -->
      <div class="tb-reconcile">
        <span class="tb-label">试算平衡表数（2221）</span><span class="tb-val">{{ fmt(tbAmount) }}</span>
        <span class="tb-label">期末审定合计</span><span class="tb-val">{{ fmt(mainTotal.endAudited) }}</span>
        <span class="tb-label">差异</span>
        <span class="tb-val" :class="{ 'text-danger': Math.abs(tbDiff) > 0.01 }">{{ fmt(tbDiff) }}</span>
        <el-tag :type="Math.abs(tbDiff) < 0.01 ? 'success' : 'danger'" size="small">
          {{ Math.abs(tbDiff) < 0.01 ? '✓ 勾稽一致' : '✕ 存在差异' }}
        </el-tag>
      </div>

      <!-- ② 期后账龄 -->
      <h4 class="sec-title">未终止设定受益福利和辞退福利的期后支付分析</h4>
      <el-table :data="postRows" border size="small" class="wp-table" style="max-width: 460px">
        <el-table-column prop="label" label="项目" min-width="200" />
        <el-table-column label="金额" width="160" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="mini-total">合计：{{ fmt(postTotal) }}</div>

      <!-- ③ (1) 设定受益计划情况 -->
      <h4 class="sec-title">（1）设定受益计划情况（DBO 现值分解与净负债计量）</h4>
      <el-table :data="dboRows" border size="small" class="wp-table"
        :row-class-name="({ row }) => row.group ? 'group-row' : ''">
        <el-table-column label="项目" min-width="260" fixed>
          <template #default="{ row }"><span :style="{ paddingLeft: row.indent * 16 + 'px', fontWeight: row.group ? 600 : 400 }">{{ row.label }}</span></template>
        </el-table-column>
        <el-table-column label="设定受益计划义务现值" align="center">
          <el-table-column label="未审数" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && !row.group" v-model="row.dboUnadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(row.dboUnadj) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && !row.group" v-model="row.dboAje" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(row.dboAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmt(dboAudited(row)) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="计划资产公允价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.group" v-model="row.planAsset" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.planAsset) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="设定受益计划净负债" width="130" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="DBO审定 − 计划资产">{{ fmt(dboNet(row)) }}</span></template>
        </el-table-column>
      </el-table>

      <!-- ④ (2) 计划资产 -->
      <h4 class="sec-title">（2）计划资产公允价值构成</h4>
      <el-table :data="assetRows" border size="small" class="wp-table" style="max-width: 760px">
        <el-table-column prop="label" label="项目" min-width="200" />
        <el-table-column label="期末未审数" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.unadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.unadj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定数" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">{{ fmt(assetEnd(row)) }}</template>
        </el-table-column>
        <el-table-column label="期初数" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.begin) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="mini-total">合计（期末审定）：{{ fmt(assetTotal.end) }} ｜ 期初：{{ fmt(assetTotal.begin) }}</div>

      <!-- ⑤ (3) 精算假设 -->
      <h4 class="sec-title">（3）精算假设</h4>
      <el-table :data="assumeRows" border size="small" class="wp-table" style="max-width: 460px">
        <el-table-column prop="label" label="假设项目" min-width="180" />
        <el-table-column label="期末数(%)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.end" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
            <span v-else>{{ fmtPct(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数(%)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
            <span v-else>{{ fmtPct(row.begin) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="sec-hint">提示：折现率、死亡率等假设录入小数（如折现率 4% 录入 0.04）；系统按百分比展示。</div>

      <!-- ⑥ (4) 敏感性分析 -->
      <h4 class="sec-title">（4）敏感性分析</h4>
      <el-table :data="sensRows" border size="small" class="wp-table" style="max-width: 640px">
        <el-table-column prop="label" label="假设项目" min-width="160" />
        <el-table-column label="假设变动幅度(%)" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.delta" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
            <span v-else>{{ fmtPct(row.delta) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对DBO影响·负债增加" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.up" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.up) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对DBO影响·负债减少" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.down" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.down) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- ⑦ 审计说明/结论 -->
      <el-card shadow="never" class="note-card">
        <template #header>
          <div class="card-hd">
            <span>1、审计说明</span>
            <el-button size="small" type="primary" plain :loading="aiLoadingNote" :disabled="isReadonly" @click="aiGenerate('note')">🤖 AI辅助</el-button>
          </div>
        </template>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly" placeholder="填写审计说明..." @change="scheduleSave" />
      </el-card>
      <el-card shadow="never" class="note-card">
        <template #header>
          <div class="card-hd">
            <span>2、审计结论</span>
            <el-button size="small" type="primary" plain :loading="aiLoadingConclusion" :disabled="isReadonly" @click="aiGenerate('conclusion')">🤖 AI辅助</el-button>
          </div>
        </template>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="填写审计结论..." @change="scheduleSave" />
      </el-card>
    </template>

    <div v-else class="oo-placeholder">
      <el-empty description="OnlyOffice 模式（审定表J2-1）" />
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，设定受益计划净负债 = 设定受益义务现值(DBO) − 计划资产公允价值。</p>
        <p>2. DBO 期末余额 = 期初 + 当期服务成本 + 利息费用 ± 精算利得损失 − 已支付福利（分解见"(1)设定受益计划情况"）。</p>
        <p>3. 灰底"审定数/净负债"列为自动计算列，不可手动编辑。</p>
        <p>4. 精算假设与敏感性分析须利用管理层的精算专家工作（ISA 620），关注折现率、死亡率、工资增长率的合理性。</p>
        <p>5. 审定期末合计回写试算平衡表科目 2221，并与明细表(J2-2)、计提检查表(J2-4)勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.j2-tab-adjudication { padding: 16px; }
.mode-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-objective { margin-bottom: 12px; }
.doc-title { font-size: 15px; font-weight: 600; text-align: center; margin: 8px 0 12px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 20px 0 8px; }
.sec-hint { font-size: 12px; color: #909399; margin: 6px 0; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.wp-table :deep(.el-input-number) { width: 100%; }
.wp-table :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
.wp-table :deep(.group-row) { background: #f5f7fa !important; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.total-row { display: flex; gap: 24px; padding: 8px 12px; margin-top: 4px; background: #ecf5ff; font-weight: 600; font-size: 13px; border-radius: 4px; }
.mini-total { padding: 4px 12px; font-weight: 600; font-size: 13px; color: #303133; }
.tb-reconcile { display: flex; align-items: center; gap: 10px; margin: 10px 0; padding: 8px 12px; background: #f8f9fa; border: 1px solid #e8e8e8; border-radius: 6px; font-size: 13px; }
.tb-label { color: #606266; }
.tb-val { font-family: 'Courier New', monospace; font-weight: 600; color: #303133; margin-right: 8px; }
.text-danger { color: #f56c6c; }
.note-card { margin-top: 14px; }
.note-card :deep(.el-card__header) { padding: 8px 16px; font-weight: 600; font-size: 13px; }
.card-hd { display: flex; justify-content: space-between; align-items: center; }
.note-card :deep(.el-textarea__inner) { font-size: 13px; }
.oo-placeholder { min-height: 300px; display: flex; align-items: center; justify-content: center; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
