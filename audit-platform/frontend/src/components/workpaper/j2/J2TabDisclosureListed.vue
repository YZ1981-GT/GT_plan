<script setup lang="ts">
/**
 * J2TabDisclosureListed — J2 长期应付职工薪酬/设定受益计划净资产附注披露（上市公司）
 *
 * 对齐源模板「附注披露信息（上市公司）」全 99 行结构：
 *  A 长期应付职工薪酬汇总（设定受益计划净负债/辞退福利/其他长期职工福利净负债/其他长期福利/小计/减一年内/合计）
 *  B (1) 设定受益计划变动：① 义务现值 ② 计划资产 ③ 净负债（各含 CAS9 六要素）+ 到期分析
 *  C (2) 计划资产公允价值构成
 *  D (3) 精算假设
 *  E (4) 敏感性分析
 *  各区块 JSON 持久化到 checklist_responses.remark（item_id J2-listed-*）。
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
  summary: 'J2-listed-summary', dbo: 'J2-listed-dbo', asset: 'J2-listed-planasset',
  net: 'J2-listed-netliab', maturity: 'J2-listed-maturity', assets: 'J2-listed-assets',
  assume: 'J2-listed-assumptions', sens: 'J2-listed-sensitivity',
  noteTerm: 'J2-listed-note-termination', noteDbp: 'J2-listed-note-dbp', noteSens: 'J2-listed-note-sensitivity',
}

function n(v: unknown): number { const x = typeof v === 'number' ? v : parseFloat(String(v ?? '')); return Number.isFinite(x) ? x : 0 }
function fmt(v: number | null | undefined): string { if (v === null || v === undefined || v === 0) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtPct(v: number | null | undefined): string { if (v === null || v === undefined) return '-'; return (v * 100).toFixed(2) + '%' }

// ── A 汇总表 ──────────────────────────────────────────────────────────────────
interface AmtRow { key: string; label: string; end: number; begin: number }
const summaryRows = reactive<AmtRow[]>([
  { key: 'dbp_net', label: '设定受益计划净负债', end: 0, begin: 0 },
  { key: 'termination', label: '辞退福利', end: 0, begin: 0 },
  { key: 'other_lt_net', label: '符合设定受益计划条件的其他长期职工福利的净负债', end: 0, begin: 0 },
  { key: 'other_lt', label: '其他长期福利', end: 0, begin: 0 },
  { key: 'less_within1y', label: '减：一年内到期的长期应付职工薪酬', end: 0, begin: 0 },
])
const summarySubtotal = computed(() => {
  const rows = summaryRows.filter(r => r.key !== 'less_within1y')
  return { end: rows.reduce((s, r) => s + n(r.end), 0), begin: rows.reduce((s, r) => s + n(r.begin), 0) }
})
const summaryTotal = computed(() => {
  const less = summaryRows.find(r => r.key === 'less_within1y')!
  return { end: summarySubtotal.value.end - n(less.end), begin: summarySubtotal.value.begin - n(less.begin) }
})

// ── B 变动表（本期/上期），三张共用结构 ─────────────────────────────────────────
interface MoveRow { key: string; label: string; indent: number; group?: boolean; cur: number; prior: number }
function mv(key: string, label: string, indent = 0, group = false): MoveRow { return { key, label, indent, group, cur: 0, prior: 0 } }
const dboRows = reactive<MoveRow[]>([
  mv('begin', '一、期初余额', 0),
  mv('pl', '二、计入当期损益的设定受益成本', 0, true),
  mv('pl_service', '1．当期服务成本', 1),
  mv('pl_past', '2．过去服务成本', 1),
  mv('pl_settle', '3．结算利得（损失以"-"表示）', 1),
  mv('pl_interest', '4．利息净额', 1),
  mv('oci', '三、计入其他综合收益的设定受益成本', 0, true),
  mv('oci_actuarial', '1．精算利得（损失以"-"表示）', 1),
  mv('oci_return', '2．计划资产的回报（计入利息净额的除外）', 1),
  mv('oci_ceiling', '3．资产上限影响的变动（计入利息净额的除外）', 1),
  mv('other', '四、其他变动', 0, true),
  mv('other_settle', '1．结算时消除的负债', 1),
  mv('other_paid', '2．已支付的福利', 1),
  mv('end', '五、期末余额', 0),
])
const assetRows = reactive<MoveRow[]>([
  mv('begin', '一、期初余额', 0),
  mv('pl', '二、计入当期损益的设定受益成本', 0, true),
  mv('pl_interest', '1．利息净额', 1),
  mv('oci', '三、计入其他综合收益的设定受益成本', 0, true),
  mv('oci_return', '1．计划资产的回报（计入利息净额的除外）', 1),
  mv('oci_ceiling', '2．资产上限影响的变动（计入利息净额的除外）', 1),
  mv('other', '四、其他变动', 0, true),
  mv('end', '五、期末余额', 0),
])
const netRows = reactive<MoveRow[]>([
  mv('begin', '一、期初余额', 0),
  mv('pl', '二、计入当期损益的设定受益成本', 0),
  mv('oci', '三、计入其他综合收益的设定受益成本', 0),
  mv('other', '四、其他变动', 0),
  mv('end', '五、期末余额', 0),
])

// ── 未折现到期分析 ────────────────────────────────────────────────────────────
const maturityRows = reactive([
  { key: 'y1', label: '一年以内', amount: 0 },
  { key: 'y1_2', label: '一到两年', amount: 0 },
  { key: 'y2_5', label: '二到五年', amount: 0 },
  { key: 'y5', label: '五年以上', amount: 0 },
])
const maturityTotal = computed(() => maturityRows.reduce((s, r) => s + n(r.amount), 0))

// ── C 计划资产构成 ────────────────────────────────────────────────────────────
const assetCompRows = reactive<AmtRow[]>([
  { key: 'cash', label: '现金和现金等价物', end: 0, begin: 0 },
  { key: 'equity', label: '权益工具投资', end: 0, begin: 0 },
  { key: 'debt', label: '债务工具投资', end: 0, begin: 0 },
  { key: 'other', label: '其他', end: 0, begin: 0 },
])
const assetCompTotal = computed(() => ({
  end: assetCompRows.reduce((s, r) => s + n(r.end), 0),
  begin: assetCompRows.reduce((s, r) => s + n(r.begin), 0),
}))

// ── D 精算假设 ────────────────────────────────────────────────────────────────
const assumeRows = reactive([
  { key: 'discount', label: '折现率', end: 0, begin: 0 },
  { key: 'mortality', label: '死亡率', end: 0, begin: 0 },
  { key: 'life', label: '预计平均寿命', end: 0, begin: 0 },
  { key: 'turnover', label: '职工的离职率', end: 0, begin: 0 },
  { key: 'salary', label: '薪酬的预期增长率', end: 0, begin: 0 },
])
// ── E 敏感性分析 ──────────────────────────────────────────────────────────────
const sensRows = reactive([
  { key: 'discount', label: '折现率', delta: 0, up: 0, down: 0 },
  { key: 'mortality', label: '死亡率', delta: 0, up: 0, down: 0 },
  { key: 'life', label: '预计平均寿命', delta: 0, up: 0, down: 0 },
  { key: 'turnover', label: '职工的离职率', delta: 0, up: 0, down: 0 },
  { key: 'salary', label: '薪酬的预期增长率', delta: 0, up: 0, down: 0 },
])

// ── 说明文本 ──────────────────────────────────────────────────────────────────
// 源模板固定指引作为 placeholder（灰字提示）：空值时显示、用户输入即隐藏，无需手动删除。
const PH_TERM = '1、辞退福利的性质、内容及计算依据详见附注五、35；\n2、其他长期职工福利的性质及计算依据。'
const PH_DBP = '1、设定受益计划的内容、形成的原因、特征及与之相关的风险；如有对计划的修改或结算的，还应当披露修改或结算计划的有关情况；\n2、设定受益计划对公司未来现金流量的金额、时间和不确定性的影响。披露影响设定受益计划未来缴存金额的有关筹资政策和计划、下一会计年度预期将缴存的金额，设定受益义务有关到期情况的信息（如设定受益义务的加权平均期间、对有关福利支付的到期日分析等）。'
const PH_SENS = '上述敏感性分析是基于一个假设发生变动而其他假设均保持不变，但实际上各种假设通常是相互关联的。上述敏感性分析在计算设定受益义务现值时也同样采用累积福利单位法。进行敏感度分析所采用的重大假设的方法和类型与以前年度比较未发生变动。（如发生变动，应进一步说明发生的具体变动及原因。）'
const noteTerm = ref('')
const noteDbp = ref('')
const noteSens = ref('')
const aiLoading = ref('')

// ── 加载 ──────────────────────────────────────────────────────────────────────
function parseJson<T>(id: string, fb: T): T { const raw = props.allResponses?.get(id)?.remark; if (!raw) return fb; try { const p = JSON.parse(raw); return (p ?? fb) as T } catch { return fb } }
function assignRows<T extends object>(target: T[], saved: unknown) {
  if (!Array.isArray(saved)) return
  for (const s of saved as Record<string, unknown>[]) { const row = target.find(r => (r as Record<string, unknown>).key === s.key); if (row) Object.assign(row, s) }
}
function load() {
  assignRows(summaryRows, parseJson(KEY.summary, null))
  assignRows(dboRows, parseJson(KEY.dbo, null))
  assignRows(assetRows, parseJson(KEY.asset, null))
  assignRows(netRows, parseJson(KEY.net, null))
  assignRows(maturityRows, parseJson(KEY.maturity, null))
  assignRows(assetCompRows, parseJson(KEY.assets, null))
  assignRows(assumeRows, parseJson(KEY.assume, null))
  assignRows(sensRows, parseJson(KEY.sens, null))
  const t = props.allResponses?.get(KEY.noteTerm)?.remark; if (t) noteTerm.value = t
  const d = props.allResponses?.get(KEY.noteDbp)?.remark; if (d) noteDbp.value = d
  const s = props.allResponses?.get(KEY.noteSens)?.remark; if (s) noteSens.value = s
  // 从审定表(J2-1-main)自动 seed 汇总表期末数（仅在汇总表全 0 时）
  const anySum = summaryRows.some(r => n(r.end) !== 0 || n(r.begin) !== 0)
  if (!anySum) {
    const mainRaw = props.allResponses?.get('J2-1-main')?.remark
    if (mainRaw) {
      try {
        const main = JSON.parse(mainRaw) as Array<Record<string, unknown>>
        const audited = (k: string) => { const r = main.find(x => x.key === k); return r ? n(r.endUnadj) + n(r.endAje) : 0 }
        const beginAud = (k: string) => { const r = main.find(x => x.key === k); return r ? n(r.beginUnadj) + n(r.beginAje) : 0 }
        summaryRows.find(r => r.key === 'dbp_net')!.end = audited('dbp')
        summaryRows.find(r => r.key === 'dbp_net')!.begin = beginAud('dbp')
        summaryRows.find(r => r.key === 'termination')!.end = audited('termination')
        summaryRows.find(r => r.key === 'termination')!.begin = beginAud('termination')
        summaryRows.find(r => r.key === 'less_within1y')!.end = audited('less_within1y')
        summaryRows.find(r => r.key === 'less_within1y')!.begin = beginAud('less_within1y')
      } catch { /* ignore */ }
    }
  }
}

// ── 保存（防抖） ──────────────────────────────────────────────────────────────
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  props.saveImmediate([
    { item_id: KEY.summary, conclusion: null, remark: JSON.stringify(summaryRows) },
    { item_id: KEY.dbo, conclusion: null, remark: JSON.stringify(dboRows) },
    { item_id: KEY.asset, conclusion: null, remark: JSON.stringify(assetRows) },
    { item_id: KEY.net, conclusion: null, remark: JSON.stringify(netRows) },
    { item_id: KEY.maturity, conclusion: null, remark: JSON.stringify(maturityRows) },
    { item_id: KEY.assets, conclusion: null, remark: JSON.stringify(assetCompRows) },
    { item_id: KEY.assume, conclusion: null, remark: JSON.stringify(assumeRows) },
    { item_id: KEY.sens, conclusion: null, remark: JSON.stringify(sensRows) },
    { item_id: KEY.noteTerm, conclusion: null, remark: noteTerm.value },
    { item_id: KEY.noteDbp, conclusion: null, remark: noteDbp.value },
    { item_id: KEY.noteSens, conclusion: null, remark: noteSens.value },
  ])
}

// ── AI 辅助说明 ───────────────────────────────────────────────────────────────
async function aiGen(target: 'term' | 'dbp' | 'sens') {
  if (isReadonly.value) return
  aiLoading.value = target
  try {
    const context: Record<string, string> = {
      科目: '2221 长期应付职工薪酬 / 设定受益计划净资产（上市公司附注披露）',
      设定受益计划净负债期末: fmt(summaryRows.find(r => r.key === 'dbp_net')?.end),
      辞退福利期末: fmt(summaryRows.find(r => r.key === 'termination')?.end),
      合计期末: fmt(summaryTotal.value.end),
      折现率: fmtPct(assumeRows.find(r => r.key === 'discount')?.end ?? 0),
      薪酬增长率: fmtPct(assumeRows.find(r => r.key === 'salary')?.end ?? 0),
    }
    const existing = target === 'term' ? noteTerm.value : target === 'dbp' ? noteDbp.value : noteSens.value
    const text = await generateAiText({
      section: `j2-listed-disclosure-${target}`, context, existingContent: existing,
    })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
    } else {
      if (target === 'term') noteTerm.value = text
      else if (target === 'dbp') noteDbp.value = text
      else noteSens.value = text
      scheduleSave()
    }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j2-disclosure-listed">
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证设定受益计划附注披露（上市公司口径）的完整性与准确性——计划性质、精算假设、义务与计划资产调节表、期初期末金额及敏感性分析，满足 CAS 9 与 CAS 30 披露要求。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="doc-title">长期应付职工薪酬/设定受益计划净资产附注披露信息（上市公司）</h3>
      <GtIndexChip value="wp:J2-1" :context-project-id="projectId" />
    </div>

    <!-- A 汇总表 -->
    <el-table :data="summaryRows" border size="small" class="wp-table" style="max-width: 760px">
      <el-table-column label="项目" min-width="320">
        <template #default="{ row }">{{ row.label }}</template>
      </el-table-column>
      <el-table-column label="期末数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.end" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.end) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.begin) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="calc-line">小计：期末 {{ fmt(summarySubtotal.end) }} ｜ 期初 {{ fmt(summarySubtotal.begin) }}　·　合计（减一年内后）：期末 {{ fmt(summaryTotal.end) }} ｜ 期初 {{ fmt(summaryTotal.begin) }}</div>
    <div class="note-wrap">
      <div class="note-hd"><span>说明（辞退福利/其他长期职工福利性质）</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'term'" :disabled="isReadonly" @click="aiGen('term')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="noteTerm" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" :placeholder="PH_TERM" @change="scheduleSave" />
    </div>

    <!-- B (1) 设定受益计划变动情况 -->
    <h4 class="sec-title">（1）设定受益计划变动情况</h4>
    <div class="mv-title">设定受益计划义务现值</div>
    <el-table :data="dboRows" border size="small" class="wp-table" style="max-width: 640px"
      :row-class-name="({ row }) => row.group ? 'group-row' : ''">
      <el-table-column label="项目" min-width="300">
        <template #default="{ row }"><span :style="{ paddingLeft: row.indent * 16 + 'px', fontWeight: row.group ? 600 : 400 }">{{ row.label }}</span></template>
      </el-table-column>
      <el-table-column label="本期金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.group" v-model="row.cur" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.cur) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.group" v-model="row.prior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.prior) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="mv-title">计划资产</div>
    <el-table :data="assetRows" border size="small" class="wp-table" style="max-width: 640px"
      :row-class-name="({ row }) => row.group ? 'group-row' : ''">
      <el-table-column label="项目" min-width="300">
        <template #default="{ row }"><span :style="{ paddingLeft: row.indent * 16 + 'px', fontWeight: row.group ? 600 : 400 }">{{ row.label }}</span></template>
      </el-table-column>
      <el-table-column label="本期金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.group" v-model="row.cur" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.cur) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.group" v-model="row.prior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.prior) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="tip-block">提示：设定受益计划存在资产的，企业应当将设定受益计划义务现值减去设定受益计划资产公允价值所形成的赤字或盈余，确认为一项设定受益计划净负债或净资产。</div>

    <div class="mv-title">设定受益计划净负债（净资产）</div>
    <el-table :data="netRows" border size="small" class="wp-table" style="max-width: 640px">
      <el-table-column label="项目" min-width="300">
        <template #default="{ row }">{{ row.label }}</template>
      </el-table-column>
      <el-table-column label="本期金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.cur" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.cur) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.prior" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.prior) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="note-wrap">
      <div class="note-hd"><span>说明（计划内容/风险/现金流量影响）</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'dbp'" :disabled="isReadonly" @click="aiGen('dbp')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="noteDbp" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" :placeholder="PH_DBP" @change="scheduleSave" />
    </div>

    <div class="mv-title">未折现的离职后福利预计到期分析</div>
    <el-table :data="maturityRows" border size="small" class="wp-table" style="max-width: 460px">
      <el-table-column prop="label" label="项目" min-width="200" />
      <el-table-column label="金额" width="160" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.amount) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="calc-line">合计：{{ fmt(maturityTotal) }}</div>

    <!-- C (2) 计划资产 -->
    <h4 class="sec-title">（2）计划资产（公允价值构成）</h4>
    <el-table :data="assetCompRows" border size="small" class="wp-table" style="max-width: 620px">
      <el-table-column prop="label" label="项目" min-width="240" />
      <el-table-column label="期末数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.end" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.end) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初数" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.begin) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="calc-line">合计：期末 {{ fmt(assetCompTotal.end) }} ｜ 期初 {{ fmt(assetCompTotal.begin) }}</div>
    <div class="tip-block">提示：1、权益工具投资按行业类型或公司规模或地域等分类；2、债务工具投资按债务工具发行人类型或信用评级或地域等分类。</div>

    <!-- D (3) 精算假设 -->
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
    <div class="sec-hint">提示：假设录入小数（如折现率 4% 录入 0.04），系统按百分比展示。</div>

    <!-- E (4) 敏感性分析 -->
    <h4 class="sec-title">（4）敏感性分析</h4>
    <el-table :data="sensRows" border size="small" class="wp-table" style="max-width: 700px">
      <el-table-column prop="label" label="项目" min-width="150" />
      <el-table-column label="假设的变动幅度(%)" width="150" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.delta" :controls="false" :precision="4" :step="0.001" size="small" @change="scheduleSave" />
          <span v-else>{{ fmtPct(row.delta) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对DBO现值影响·计划负债增加" width="180" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.up" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.up) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对DBO现值影响·计划负债减少" width="180" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.down" :controls="false" :precision="2" size="small" @change="scheduleSave" />
          <span v-else>{{ fmt(row.down) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="note-wrap">
      <div class="note-hd"><span>说明（敏感性分析方法）</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'sens'" :disabled="isReadonly" @click="aiGen('sens')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="noteSens" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" :placeholder="PH_SENS" @change="scheduleSave" />
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》及 CAS 30，上市公司须披露设定受益计划性质、风险及关键精算假设。</p>
        <p>2. 义务现值/计划资产/净负债三张调节表须按 CAS9 六要素（服务成本/利息净额/精算利得损失/计划资产回报/结算/已付福利）分解，本期与上期对比列示。</p>
        <p>3. 净负债 = 设定受益义务现值 − 计划资产公允价值；期末余额三表勾稽一致。</p>
        <p>4. 附注金额应与审定表（J2-1）、明细表（J2-2）勾稽一致；汇总表期末数已从审定表自动带入（可覆盖）。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.j2-disclosure-listed { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.doc-title { font-size: 15px; font-weight: 600; margin: 0; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 20px 0 8px; }
.mv-title { font-size: 13px; font-weight: 600; color: #606266; margin: 12px 0 6px; }
.sec-hint, .tip-block { font-size: 12px; color: #909399; margin: 6px 0; }
.tip-block { background: #fdf6ec; border-left: 3px solid #e6a23c; padding: 6px 10px; border-radius: 4px; color: #b88230; }
.calc-line { padding: 4px 12px; font-weight: 600; font-size: 13px; color: #303133; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.wp-table :deep(.el-input-number) { width: 100%; }
.wp-table :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
.wp-table :deep(.group-row) { background: #f5f7fa !important; }
.note-wrap { margin-top: 12px; }
.note-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #303133; }
.note-input { display: none; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
