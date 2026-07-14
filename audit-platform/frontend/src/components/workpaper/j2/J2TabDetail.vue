<script setup lang="ts">
/**
 * J2TabDetail — J2-2 长期应付职工薪酬/设定受益计划净资产明细表
 *
 * 对齐源模板「明细表J2-2」全 90 行结构（6 区块 + 审计说明/结论）：
 *  A 主表：设定受益计划（离职后福利/其他长期职工福利）/辞退福利/减一年内/合计
 *          —— 未审数(期初/增/减/期末) + 期初调整 + 账项调整(增/减) + 审定数(期初/增/减/期末)
 *  B 1、未折现的离职后福利预计到期分析（同上增减四栏结构）
 *  C 2、设定受益计划情况（义务现值 未审/调整/审定/上期 · 计划资产 本期/上期 · 净负债 本期/上期，CAS9 六要素）
 *  D 3、计划资产（现金/权益工具投资/债务工具投资/其他，增减四栏结构）
 *  E 4、精算假设（期末数/期初数）
 *  F 5、敏感性分析（变动幅度/负债增加/负债减小）
 *  + 审计说明 + 审计结论（AI 辅助）
 *
 *  各区块 JSON 持久化到 checklist_responses.remark（item_id J2-2-*），复用父 GtJ2 的 saveImmediate + allResponses。
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

const KEY = {
  main: 'J2-2-main', maturity: 'J2-2-maturity', status: 'J2-2-dbp-status',
  planAssets: 'J2-2-plan-assets', assume: 'J2-2-assumptions', sens: 'J2-2-sensitivity',
  note: 'J2-2-note', conclusion: 'J2-2-conclusion',
}

function n(v: unknown): number { const x = typeof v === 'number' ? v : parseFloat(String(v ?? '')); return Number.isFinite(x) ? x : 0 }
function fmt(v: number | null | undefined): string { if (v === null || v === undefined || v === 0) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

// ══════════════════════════════════════════════════════════════════════════════
// 增减四栏表（主表 / 到期分析 / 计划资产 共用结构）
//   未审：beginUnadj(C) incUnadj(D) decUnadj(E) → endUnadj(F=C+D-E, auto)
//   期初调整：openAdjust(G)
//   账项调整：incAdjust(H) decAdjust(I)
//   审定：beginAud(J=C+G) incAud(K=D+H) decAud(L=E+I) endAud(M=J+K-L)  全 auto
// ══════════════════════════════════════════════════════════════════════════════
interface AdjRow {
  key: string; seq: string; label: string; indent: number
  kind: 'leaf' | 'agg'; add?: string[]; sub?: string[]
  beginUnadj: number; incUnadj: number; decUnadj: number
  openAdjust: number; incAdjust: number; decAdjust: number
  remark: string
}
function leaf(key: string, seq: string, label: string, indent = 0): AdjRow {
  return { key, seq, label, indent, kind: 'leaf', beginUnadj: 0, incUnadj: 0, decUnadj: 0, openAdjust: 0, incAdjust: 0, decAdjust: 0, remark: '' }
}
function agg(key: string, seq: string, label: string, indent: number, add: string[], sub: string[] = []): AdjRow {
  return { key, seq, label, indent, kind: 'agg', add, sub, beginUnadj: 0, incUnadj: 0, decUnadj: 0, openAdjust: 0, incAdjust: 0, decAdjust: 0, remark: '' }
}
type AdjBase = 'beginUnadj' | 'incUnadj' | 'decUnadj' | 'openAdjust' | 'incAdjust' | 'decAdjust'
function findRow(rows: AdjRow[], key: string): AdjRow | undefined { return rows.find(r => r.key === key) }
function baseOf(rows: AdjRow[], row: AdjRow, field: AdjBase): number {
  if (row.kind === 'leaf') return n(row[field])
  let s = 0
  for (const k of row.add || []) { const r = findRow(rows, k); if (r) s += baseOf(rows, r, field) }
  for (const k of row.sub || []) { const r = findRow(rows, k); if (r) s -= baseOf(rows, r, field) }
  return s
}
function endUnadj(rows: AdjRow[], row: AdjRow) { return baseOf(rows, row, 'beginUnadj') + baseOf(rows, row, 'incUnadj') - baseOf(rows, row, 'decUnadj') }
function beginAud(rows: AdjRow[], row: AdjRow) { return baseOf(rows, row, 'beginUnadj') + baseOf(rows, row, 'openAdjust') }
function incAud(rows: AdjRow[], row: AdjRow) { return baseOf(rows, row, 'incUnadj') + baseOf(rows, row, 'incAdjust') }
function decAud(rows: AdjRow[], row: AdjRow) { return baseOf(rows, row, 'decUnadj') + baseOf(rows, row, 'decAdjust') }
function endAud(rows: AdjRow[], row: AdjRow) { return beginAud(rows, row) + incAud(rows, row) - decAud(rows, row) }

// ── A 主表 ─────────────────────────────────────────────────────────────────────
const mainRows = reactive<AdjRow[]>([
  agg('dbp', '一', '设定受益计划', 0, ['post_emp', 'other_lt']),
  leaf('post_emp', '', '其中：1、离职后福利', 1),
  leaf('other_lt', '', '　　　2、其他长期职工福利', 1),
  leaf('termination', '二', '辞退福利', 0),
  leaf('less_within1y', '', '减：一年内支付的辞退福利', 1),
  agg('total', '合计', '合计', 0, ['dbp', 'termination'], ['less_within1y']),
])
// ── B 到期分析 ─────────────────────────────────────────────────────────────────
const maturityRows = reactive<AdjRow[]>([
  leaf('y1', '1', '一年以内', 0),
  leaf('y1_2', '2', '一到两年', 0),
  leaf('y2_5', '3', '二到五年', 0),
  leaf('y5', '4', '五年以上', 0),
  agg('total', '合计', '合计', 0, ['y1', 'y1_2', 'y2_5', 'y5']),
])
// ── D 计划资产 ─────────────────────────────────────────────────────────────────
const planAssetRows = reactive<AdjRow[]>([
  leaf('cash', '一', '现金和现金等价物', 0),
  agg('equity', '二', '权益工具投资', 0, ['equity_1', 'equity_2']),
  leaf('equity_1', '1', '……', 1),
  leaf('equity_2', '2', '……', 1),
  agg('debt', '三', '债务工具投资', 0, ['debt_1', 'debt_2']),
  leaf('debt_1', '1', '……', 1),
  leaf('debt_2', '2', '……', 1),
  leaf('other', '四', '其他', 0),
  agg('total', '五', '合计', 0, ['cash', 'equity', 'debt', 'other']),
])
const adjTables = [
  { key: 'main', title: '（主表）长期应付职工薪酬', rows: mainRows },
  { key: 'maturity', title: '1、未折现的离职后福利预计到期分析', rows: maturityRows },
  { key: 'planAssets', title: '3、计划资产', rows: planAssetRows },
]

// ══════════════════════════════════════════════════════════════════════════════
// C 设定受益计划情况（8 数值列）
//   义务现值：dboUnadj(C 本期未审) dboAdjust(D 账项调整) → dboAud(E=C+D auto) dboPrior(F 上期)
//   计划资产：assetCur(G 本期) assetPrior(H 上期)          （N/A 行显示 —）
//   净负债：  netCur(I=C−G auto) netPrior(J=F−H auto)
// ══════════════════════════════════════════════════════════════════════════════
interface StatusRow {
  key: string; seq: string; label: string; indent: number
  kind: 'leaf' | 'agg'; add?: string[]; sub?: string[]; assetNa?: boolean
  dboUnadj: number; dboAdjust: number; dboPrior: number; assetCur: number; assetPrior: number
}
function sLeaf(key: string, seq: string, label: string, indent: number, assetNa = false): StatusRow {
  return { key, seq, label, indent, kind: 'leaf', assetNa, dboUnadj: 0, dboAdjust: 0, dboPrior: 0, assetCur: 0, assetPrior: 0 }
}
function sAgg(key: string, seq: string, label: string, indent: number, add: string[], sub: string[] = []): StatusRow {
  return { key, seq, label, indent, kind: 'agg', add, sub, dboUnadj: 0, dboAdjust: 0, dboPrior: 0, assetCur: 0, assetPrior: 0 }
}
type SBase = 'dboUnadj' | 'dboAdjust' | 'dboPrior' | 'assetCur' | 'assetPrior'
const statusRows = reactive<StatusRow[]>([
  sLeaf('begin', '一、', '期初余额', 0),
  sAgg('pl', '二、', '计入当期损益的设定受益成本', 0, ['pl_service', 'pl_past', 'pl_settle', 'pl_interest']),
  sLeaf('pl_service', '1', '当期服务成本', 1, true),
  sLeaf('pl_past', '2', '过去服务成本', 1, true),
  sLeaf('pl_settle', '3', '结算利得（损失以"-"表示）', 1, true),
  sLeaf('pl_interest', '4', '利息净额', 1),
  sAgg('oci', '三、', '计入其他综合收益的设定受益成本', 0, ['oci_remeasure']),
  sAgg('oci_remeasure', '', '设定受益计划净负债（净资产）的重新计量', 1, ['oci_actuarial', 'oci_return', 'oci_ceiling']),
  sLeaf('oci_actuarial', '1', '精算利得（损失以"-"表示）', 2, true),
  sLeaf('oci_return', '2', '计划资产的回报（计入利息净额的除外）', 2),
  sLeaf('oci_ceiling', '3', '资产上限影响的变动（计入利息净额的除外）', 2),
  sAgg('other', '四、', '其他变动', 0, ['other_settle', 'other_paid', 'other_etc']),
  sLeaf('other_settle', '1', '结算时消除的负债', 1),
  sLeaf('other_paid', '2', '已支付的福利', 1),
  sLeaf('other_etc', '', '……', 1),
  sAgg('end', '五、', '期末余额', 0, ['begin', 'pl', 'oci'], ['other']),
])
function sFind(key: string): StatusRow | undefined { return statusRows.find(r => r.key === key) }
function sBaseOf(row: StatusRow, field: SBase): number {
  if (row.kind === 'leaf') { if (row.assetNa && (field === 'assetCur' || field === 'assetPrior')) return 0; return n(row[field]) }
  let s = 0
  for (const k of row.add || []) { const r = sFind(k); if (r) s += sBaseOf(r, field) }
  for (const k of row.sub || []) { const r = sFind(k); if (r) s -= sBaseOf(r, field) }
  return s
}
function dboAud(row: StatusRow) { return sBaseOf(row, 'dboUnadj') + sBaseOf(row, 'dboAdjust') }
function netCur(row: StatusRow) { return sBaseOf(row, 'dboUnadj') - sBaseOf(row, 'assetCur') }
function netPrior(row: StatusRow) { return sBaseOf(row, 'dboPrior') - sBaseOf(row, 'assetPrior') }
function sEditable(row: StatusRow, field: SBase): boolean {
  if (isReadonly.value || row.kind !== 'leaf') return false
  if (row.assetNa && (field === 'assetCur' || field === 'assetPrior')) return false
  return true
}

// ── E 精算假设 ────────────────────────────────────────────────────────────────
const assumeRows = reactive([
  { key: 'discount', seq: '一、', label: '折现率', end: 0, begin: 0 },
  { key: 'mortality', seq: '二、', label: '死亡率', end: 0, begin: 0 },
  { key: 'life', seq: '三、', label: '预计平均寿命', end: 0, begin: 0 },
  { key: 'turnover', seq: '四、', label: '职工的离职率', end: 0, begin: 0 },
  { key: 'salary', seq: '五、', label: '薪酬的预期增长率', end: 0, begin: 0 },
])
// ── F 敏感性分析 ──────────────────────────────────────────────────────────────
const sensRows = reactive([
  { key: 'discount', seq: '一、', label: '折现率', delta: 0, up: 0, down: 0 },
  { key: 'mortality', seq: '二、', label: '死亡率', delta: 0, up: 0, down: 0 },
  { key: 'life', seq: '三、', label: '预计平均寿命', delta: 0, up: 0, down: 0 },
  { key: 'turnover', seq: '四、', label: '职工的离职率', delta: 0, up: 0, down: 0 },
  { key: 'salary', seq: '五、', label: '薪酬的预期增长率', delta: 0, up: 0, down: 0 },
])

// ── 审计说明 / 结论 ───────────────────────────────────────────────────────────
const PH_NOTE = '审计说明可以概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。'
const auditNote = ref('')
const auditConclusion = ref('')
const aiLoading = ref('')

// ── 加载 ──────────────────────────────────────────────────────────────────────
function parseJson<T>(id: string, fb: T): T { const raw = props.allResponses?.get(id)?.remark; if (!raw) return fb; try { const p = JSON.parse(raw); return (p ?? fb) as T } catch { return fb } }
function assignRows<T extends object>(target: T[], saved: unknown) {
  if (!Array.isArray(saved)) return
  for (const s of saved as Record<string, unknown>[]) { const row = target.find(r => (r as Record<string, unknown>).key === s.key); if (row) Object.assign(row, s) }
}
function load() {
  assignRows(mainRows, parseJson(KEY.main, null))
  assignRows(maturityRows, parseJson(KEY.maturity, null))
  assignRows(statusRows, parseJson(KEY.status, null))
  assignRows(planAssetRows, parseJson(KEY.planAssets, null))
  assignRows(assumeRows, parseJson(KEY.assume, null))
  assignRows(sensRows, parseJson(KEY.sens, null))
  const nt = props.allResponses?.get(KEY.note)?.remark; if (nt) auditNote.value = nt
  const cc = props.allResponses?.get(KEY.conclusion)?.remark; if (cc) auditConclusion.value = cc
}

// ── 保存（防抖） ──────────────────────────────────────────────────────────────
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  props.saveImmediate([
    { item_id: KEY.main, conclusion: null, remark: JSON.stringify(mainRows) },
    { item_id: KEY.maturity, conclusion: null, remark: JSON.stringify(maturityRows) },
    { item_id: KEY.status, conclusion: null, remark: JSON.stringify(statusRows) },
    { item_id: KEY.planAssets, conclusion: null, remark: JSON.stringify(planAssetRows) },
    { item_id: KEY.assume, conclusion: null, remark: JSON.stringify(assumeRows) },
    { item_id: KEY.sens, conclusion: null, remark: JSON.stringify(sensRows) },
    { item_id: KEY.note, conclusion: null, remark: auditNote.value },
    { item_id: KEY.conclusion, conclusion: null, remark: auditConclusion.value },
  ])
}

// ── AI 辅助 ───────────────────────────────────────────────────────────────────
async function aiGen(target: 'note' | 'conclusion') {
  if (isReadonly.value) return
  aiLoading.value = target
  try {
    const dbpEnd = endAud(mainRows, findRow(mainRows, 'dbp')!)
    const termEnd = endAud(mainRows, findRow(mainRows, 'termination')!)
    const totalEnd = endAud(mainRows, findRow(mainRows, 'total')!)
    const context: Record<string, string> = {
      科目: '2221 长期应付职工薪酬 / 设定受益计划净资产明细表（J2-2）',
      设定受益计划审定期末: fmt(dbpEnd),
      辞退福利审定期末: fmt(termEnd),
      合计审定期末: fmt(totalEnd),
      设定受益义务现值期末: fmt(dboAud(sFind('end')!)),
      计划资产公允价值期末: fmt(endAud(planAssetRows, findRow(planAssetRows, 'total')!)),
    }
    const existing = target === 'note' ? auditNote.value : auditConclusion.value
    const text = await generateAiText({ section: `j2-2-${target}`, context, existingContent: existing })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
    } else {
      if (target === 'note') auditNote.value = text; else auditConclusion.value = text
      scheduleSave()
    }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j2-tab-detail">
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：①资产负债表中记录的长期应付职工薪酬是存在的且已记录在恰当账户；②所有应记录的长期应付职工薪酬及相关披露均已记录/包括（完整性）；③由被审计单位拥有或控制；④以恰当金额列示，计价/分摊调整已恰当记录，相关披露已恰当计量和描述。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="doc-title">长期应付职工薪酬/设定受益计划净资产明细表</h3>
      <GtIndexChip value="wp:J2-2" :context-project-id="projectId" />
    </div>

    <div class="guide-area">
      <div class="guide-step"><span class="step-num">①</span> 录入各项目未审数（期初/增加/减少）与账项调整</div>
      <div class="guide-step"><span class="step-num">②</span> 系统自动计算期末数、审定数与净负债，并按 CAS9 六要素勾稽</div>
    </div>

    <!-- A/B/D 增减四栏表（主表 / 到期分析 / 计划资产） -->
    <template v-for="t in adjTables" :key="t.key">
      <h4 class="sec-title">{{ t.title }}</h4>
      <el-table :data="t.rows" border size="small" class="wp-table"
        :row-class-name="({ row }) => row.kind === 'agg' ? 'group-row' : ''">
        <el-table-column label="序号" width="56" align="center"><template #default="{ row }">{{ row.seq }}</template></el-table-column>
        <el-table-column label="项目名称" min-width="220" fixed>
          <template #default="{ row }"><span :style="{ paddingLeft: row.indent * 14 + 'px', fontWeight: row.kind === 'agg' ? 600 : 400 }">{{ row.label }}</span></template>
        </el-table-column>
        <el-table-column label="未审数" align="center">
          <el-table-column label="期初数" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && row.kind === 'leaf'" v-model="row.beginUnadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(baseOf(t.rows, row, 'beginUnadj')) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && row.kind === 'leaf'" v-model="row.incUnadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(baseOf(t.rows, row, 'incUnadj')) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期减少" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && row.kind === 'leaf'" v-model="row.decUnadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(baseOf(t.rows, row, 'decUnadj')) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" min-width="105" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="= 期初 + 增加 − 减少">{{ fmt(endUnadj(t.rows, row)) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初调整" align="center">
          <el-table-column label="账项调整" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && row.kind === 'leaf'" v-model="row.openAdjust" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(baseOf(t.rows, row, 'openAdjust')) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="账项调整" align="center">
          <el-table-column label="本期增加" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && row.kind === 'leaf'" v-model="row.incAdjust" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(baseOf(t.rows, row, 'incAdjust')) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期减少" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && row.kind === 'leaf'" v-model="row.decAdjust" :controls="false" :precision="2" size="small" @change="scheduleSave" />
              <span v-else>{{ fmt(baseOf(t.rows, row, 'decAdjust')) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="审定数" align="center">
          <el-table-column label="期初数" min-width="105" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="= 未审期初 + 期初调整">{{ fmt(beginAud(t.rows, row)) }}</span></template>
          </el-table-column>
          <el-table-column label="本期增加" min-width="105" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="= 未审增加 + 账项调整增加">{{ fmt(incAud(t.rows, row)) }}</span></template>
          </el-table-column>
          <el-table-column label="本期减少" min-width="105" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="= 未审减少 + 账项调整减少">{{ fmt(decAud(t.rows, row)) }}</span></template>
          </el-table-column>
          <el-table-column label="期末数" min-width="105" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="= 审定期初 + 审定增加 − 审定减少">{{ fmt(endAud(t.rows, row)) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && row.kind === 'leaf'" v-model="row.remark" size="small" @change="scheduleSave" />
            <span v-else>{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- C 设定受益计划情况 -->
    <h4 class="sec-title">2、设定受益计划情况</h4>
    <el-table :data="statusRows" border size="small" class="wp-table"
      :row-class-name="({ row }) => row.kind === 'agg' ? 'group-row' : ''">
      <el-table-column label="序号" width="56" align="center"><template #default="{ row }">{{ row.seq }}</template></el-table-column>
      <el-table-column label="项目名称" min-width="280" fixed>
        <template #default="{ row }"><span :style="{ paddingLeft: row.indent * 14 + 'px', fontWeight: row.kind === 'agg' ? 600 : 400 }">{{ row.label }}</span></template>
      </el-table-column>
      <el-table-column label="设定受益计划义务现值" align="center">
        <el-table-column label="本期未审金额" min-width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-if="sEditable(row, 'dboUnadj')" v-model="row.dboUnadj" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(sBaseOf(row, 'dboUnadj')) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="sEditable(row, 'dboAdjust')" v-model="row.dboAdjust" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(sBaseOf(row, 'dboAdjust')) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定金额" min-width="115" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="= 本期未审 + 账项调整">{{ fmt(dboAud(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="上期金额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="sEditable(row, 'dboPrior')" v-model="row.dboPrior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(sBaseOf(row, 'dboPrior')) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="计划资产的公允价值" align="center">
        <el-table-column label="本期金额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="sEditable(row, 'assetCur')" v-model="row.assetCur" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else class="na-cell">{{ row.assetNa ? '—' : fmt(sBaseOf(row, 'assetCur')) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期金额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="sEditable(row, 'assetPrior')" v-model="row.assetPrior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else class="na-cell">{{ row.assetNa ? '—' : fmt(sBaseOf(row, 'assetPrior')) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="设定受益计划净负债（净资产）" align="center">
        <el-table-column label="本期金额" min-width="105" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="= 义务现值本期未审 − 计划资产本期">{{ fmt(netCur(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="上期金额" min-width="105" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="= 义务现值上期 − 计划资产上期">{{ fmt(netPrior(row)) }}</span></template>
        </el-table-column>
      </el-table-column>
    </el-table>
    <div class="tip-block">提示：期末余额 = 期初余额 + 计入当期损益 + 计入其他综合收益 − 其他变动；净负债 = 设定受益义务现值 − 计划资产公允价值；标"—"的计划资产单元格为不适用项目。</div>

    <!-- E 精算假设 -->
    <h4 class="sec-title">4、精算假设</h4>
    <el-table :data="assumeRows" border size="small" class="wp-table" style="max-width: 520px">
      <el-table-column label="序号" width="56" align="center"><template #default="{ row }">{{ row.seq }}</template></el-table-column>
      <el-table-column prop="label" label="项 目" min-width="180" />
      <el-table-column label="期末数" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.end" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.end) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初数" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.begin) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="sec-hint">提示：折现率/死亡率/离职率/薪酬增长率按比率录入（如 4.00 表示 4%），预计平均寿命按年数录入。</div>

    <!-- F 敏感性分析 -->
    <h4 class="sec-title">5、敏感性分析</h4>
    <el-table :data="sensRows" border size="small" class="wp-table" style="max-width: 760px">
      <el-table-column label="序号" width="56" align="center"><template #default="{ row }">{{ row.seq }}</template></el-table-column>
      <el-table-column prop="label" label="项目" min-width="150" />
      <el-table-column label="假设的变动幅度" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.delta" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.delta) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对设定受益义务现值的影响" align="center">
        <el-table-column label="计划负债增加" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.up" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.up) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划负债减小" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.down" :controls="false" :precision="2" size="small" @change="scheduleSave" />
            <span v-else>{{ fmt(row.down) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <div class="note-wrap">
      <div class="note-hd"><span>三、审计说明</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'note'" :disabled="isReadonly" @click="aiGen('note')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly" :placeholder="PH_NOTE" @change="scheduleSave" />
    </div>

    <!-- 审计结论 -->
    <div class="note-wrap">
      <div class="note-hd"><span>四、审计结论</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="aiGen('conclusion')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="请输入审计结论，或点击 AI 辅助生成（如：未见异常；或除上述调整事项外其余未见异常等）。" @change="scheduleSave" />
    </div>

    <details class="guidance-details">
      <summary>📋 编制说明</summary>
      <div class="guidance-content">
        <p>1. 本科目列示辞退福利中将于资产负债表日起十二个月之后支付的部分、离职后福利中设定受益计划净负债、其他长期职工福利中符合设定受益计划条件的净负债。</p>
        <p>2. 设定受益计划还应关注：（1）计划形成的原因、特征及相关风险；（2）如有计划修改或结算的有关情况；（3）影响未来缴存金额的筹资政策/计划、下一会计年度预期缴存金额、义务到期情况（加权平均期间、到期日分析等）。</p>
        <p>3. 灰色底纹列为自动计算：期末数=期初+增加−减少；审定数=未审数+账项调整；净负债=义务现值−计划资产公允价值。</p>
        <p>4. 明细表审定期末数应与审定表（J2-1）、附注披露信息勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.j2-tab-detail { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.doc-title { font-size: 15px; font-weight: 600; margin: 0; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 20px 0 8px; }
.sec-hint, .tip-block { font-size: 12px; color: #909399; margin: 6px 0; }
.tip-block { background: #fdf6ec; border-left: 3px solid #e6a23c; padding: 6px 10px; border-radius: 4px; color: #b88230; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.wp-table :deep(.el-input-number) { width: 100%; }
.wp-table :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
.wp-table :deep(.group-row) { background: #f5f7fa !important; }
.na-cell { color: #c0c4cc; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.formula-cell { border-bottom: 1px dashed #409eff; cursor: help; }
.guide-area { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; padding: 12px; background: linear-gradient(135deg, #ecf5ff 0%, #f0f9ff 100%); border-radius: 8px; }
.guide-step { font-size: 13px; color: #303133; }
.step-num { display: inline-block; width: 20px; height: 20px; line-height: 20px; text-align: center; background: #409eff; color: #fff; border-radius: 50%; font-size: 11px; margin-right: 6px; }
.note-wrap { margin-top: 14px; }
.note-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #303133; }
.conclusion-actions { display: flex; gap: 6px; align-items: center; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
