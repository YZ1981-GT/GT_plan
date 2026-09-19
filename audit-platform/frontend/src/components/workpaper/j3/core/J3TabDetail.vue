<script setup lang="ts">
/**
 * J3TabDetail — J3-1 应付职工薪酬/股份支付情况表
 *
 * 对齐源模板「股份支付情况表J3-1」全 43 行结构：
 *  审计目标(5) + 二、审计过程[1.股份支付决议内容 · 2.公允价值确定及假设 · 3.专家资质与利用(S12/S12A)]
 *  + 股份支付明细表(源模板14列动态行) + 三、审计说明 + 四、审计结论
 *  + 提示1「股份支付主要审计过程和关注要点」8 要点方法论参考(琥珀内嵌，帮助用户理解与应用)
 *
 * 导入导出参照 D4-2 范式：el-dropdown「导入导出▾」(导出模板/导出数据/导入数据) + 后端三端点，导入后重载。
 * 持久化到 checklist_responses.remark（item_id J3-1-*），复用父 GtJ3 的 saveImmediate + allResponses。
 */
import { ref, reactive, computed, onMounted, watch } from 'vue'
import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useJ3ImportExport } from '@/composables/workpaper/j3/useJ3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import GtThTip from '../../GtThTip.vue'
import J3PlanDialog from './J3PlanDialog.vue'

interface RespItem { item_id: string; conclusion: string | null; remark: string | null }
const props = defineProps<{
  wpId: string
  projectId: string
  year?: string | number
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, RespItem>
  isReadonly?: boolean
  saveImmediate?: (items: RespItem[]) => Promise<void> | void
}>()
const isReadonly = computed(() => props.isReadonly ?? false)

const KEY = {
  plans: 'J3-1-plans', resolution: 'J3-1-resolution', fairValue: 'J3-1-fairvalue',
  expert: 'J3-1-expert', note: 'J3-1-note', conclusion: 'J3-1-conclusion',
}

// ── 股份支付明细表（源模板 14 列，动态行） ────────────────────────────────────
interface SbpRow {
  id: number
  name: string; type: string; grantDate: string; approvalDept: string; exerciseDate: string
  instrumentQty: number; vestingPeriod: string; fvMethod: string; agreementChange: string
  bsUpdate: string; remainingPeriod: string; agreementIndex: string; calcTableIndex: string; conclusion: string
}
let seq = 1
const plans = reactive<SbpRow[]>([])
const TYPE_OPTIONS = ['以权益工具结算', '以现金结算', '以权益与现金结合结算']

function emptyPlan(name: string): SbpRow {
  return {
    id: seq++, name, type: '以权益工具结算', grantDate: '', approvalDept: '', exerciseDate: '',
    instrumentQty: 0, vestingPeriod: '', fvMethod: '', agreementChange: '', bsUpdate: '',
    remainingPeriod: '', agreementIndex: '', calcTableIndex: '', conclusion: '',
  }
}
function removePlan(id: number) {
  if (isReadonly.value) return
  const i = plans.findIndex(p => p.id === id)
  if (i >= 0) { plans.splice(i, 1); scheduleSave() }
}

// ── 引导式弹窗（新增/编辑方案） ───────────────────────────────────────────────
const dialogVisible = ref(false)
const editingPlan = ref<SbpRow | null>(null)
function openAddDialog() { if (isReadonly.value) return; editingPlan.value = null; dialogVisible.value = true }
function openEditDialog(row: SbpRow) { if (isReadonly.value) return; editingPlan.value = { ...row }; dialogVisible.value = true }
function onDialogSave(plan: SbpRow) {
  const idx = plans.findIndex(p => p.id === plan.id)
  if (idx >= 0) plans.splice(idx, 1, { ...plan })
  else plans.push({ ...plan, id: seq++ })
  scheduleSave()
}

// ── 专家资质与利用（S12/S12A） ────────────────────────────────────────────────
interface ExpertRow { key: string; item: string; indexCode: string; remark: string }
const expertRows = reactive<ExpertRow[]>([
  { key: 'e1', item: '利用专家的工作', indexCode: 'S12', remark: '' },
  { key: 'e2', item: '评估专家工作', indexCode: 'S12A', remark: '' },
])

// ── 审计过程文本 / 审计说明 / 结论 ────────────────────────────────────────────
const PH_NOTE = '被审计单位确认以现金/权益结算的股份支付 XX 元，计入应付职工薪酬/资本公积，同时分配计入管理费用 XX 元、销售费用 XX 元、……'
const resolutionText = ref('')
const fairValueText = ref('')
const auditNote = ref('')
const auditConclusion = ref('')
const aiLoading = ref('')

// ── 提示1：股份支付主要审计过程和关注要点（8 要点） ──────────────────────────
const GUIDE_POINTS = [
  '取得股份支付薪酬奖励与董事会会议纪录或其他支持性文件，了解主要条款及条件（授予日期、期权价格、股数、行使日期等），确定企业是否有政策限制该奖励的发行日期；关注是否授权日与行权日之间存在重大时间间隔；取得股份支付的所有个人均为雇员或提供类似服务的人员，并复核条件。',
  '根据股份支付奖励的条款和条件，确定其分类（权益结算/现金结算/二者结合）是否适当，并判断所采用的会计处理是否能恰当反映该分类。',
  '检查授予后立即可行权的以现金结算的股份支付，是否在授权日以承担负债的公允价值计入相关成本或费用。',
  '对新的或修改的股份支付进行分析：①确定所有个人均为雇员或提供类似服务的人员；②将新奖励与董事会会议纪录/授权文件比较，确认是否有遗漏，如有则取得支持性文件并判断遗漏是否适当；③是否已适当确认对现有奖励的修改（如有）。',
  '选取样本（如需要）：①取得合同及其他支持性文件；②确认主要条款及条件与股份支付工具是否一致（授予日期、期权价格、股数、行使日期等）；③确定授权日与行权日之间是否存在重大时间间隔，如有则向适当人员询问原因。',
  '了解股份支付公允价值计算相关假设，确定假设的合理性。',
  '确定是否需要聘请估值专家协助评价企业专家（第三方或内部员工）对该工具估值的工作；完成"专家资质"和"专家工作"的审计程序，评估估值专家的资质及其工作。',
  '考虑公司是否存在缺乏现金用于奖励员工、过去股价波动很大、授予日刻意选在特定日期、期权授予与预定日期不一致而无规则出现等情况，以识别利用股票期权日期倒签等获取不正当利益的股份期权。',
]

// ── 导入导出（D4-2 范式） ─────────────────────────────────────────────────────
const importExport = useJ3ImportExport(props.wpId)
async function handleImportExport(command: string) {
  if (command === 'template') importExport.exportTemplate()
  else if (command === 'export') importExport.exportData()
  else if (command === 'import') {
    const input = document.createElement('input')
    input.type = 'file'; input.accept = '.xlsx,.xls'
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      const ok = await importExport.importData(file)
      if (ok) await reloadPlans()
    }
    input.click()
  }
}

// ── 加载 / 保存 ───────────────────────────────────────────────────────────────
function n(v: unknown): number { const x = typeof v === 'number' ? v : parseFloat(String(v ?? '')); return Number.isFinite(x) ? x : 0 }
function parsePlans(raw: string | null | undefined): SbpRow[] | null {
  if (!raw) return null
  try { const p = JSON.parse(raw); return Array.isArray(p) ? p : null } catch { return null }
}
function applyPlans(loaded: SbpRow[]) {
  plans.splice(0, plans.length, ...loaded.map((p, i) => ({ ...emptyPlan(''), ...p, id: p.id ?? i + 1 })))
  seq = Math.max(0, ...plans.map(p => p.id)) + 1
}
function load() {
  const saved = parsePlans(props.allResponses?.get(KEY.plans)?.remark)
  if (saved) applyPlans(saved)
  const savedExpert = props.allResponses?.get(KEY.expert)?.remark
  if (savedExpert) { try { const a = JSON.parse(savedExpert); if (Array.isArray(a)) for (const s of a) { const r = expertRows.find(x => x.key === s.key); if (r) Object.assign(r, s) } } catch { /* ignore */ } }
  const r = props.allResponses?.get(KEY.resolution)?.remark; if (r) resolutionText.value = r
  const f = props.allResponses?.get(KEY.fairValue)?.remark; if (f) fairValueText.value = f
  const nt = props.allResponses?.get(KEY.note)?.remark; if (nt) auditNote.value = nt
  const cc = props.allResponses?.get(KEY.conclusion)?.remark; if (cc) auditConclusion.value = cc
}
/** 导入后从服务器重载 J3-1-plans */
async function reloadPlans() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items = res.data?.data || res.data || []
    if (Array.isArray(items)) {
      const rec = items.find((it: any) => it.item_id === KEY.plans)
      const loaded = parsePlans(rec?.remark)
      if (loaded) { applyPlans(loaded); ElMessage.success('已从导入数据刷新明细表') }
    }
  } catch { /* silent */ }
}

let timer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    props.saveImmediate?.([
      { item_id: KEY.plans, conclusion: null, remark: JSON.stringify(plans) },
      { item_id: KEY.expert, conclusion: null, remark: JSON.stringify(expertRows) },
      { item_id: KEY.resolution, conclusion: null, remark: resolutionText.value },
      { item_id: KEY.fairValue, conclusion: null, remark: fairValueText.value },
      { item_id: KEY.note, conclusion: null, remark: auditNote.value },
      { item_id: KEY.conclusion, conclusion: null, remark: auditConclusion.value },
    ])
  }, 800)
}

// ── AI 辅助 ───────────────────────────────────────────────────────────────────
async function aiGen(target: 'resolution' | 'fairValue' | 'note' | 'conclusion') {
  if (isReadonly.value) return
  aiLoading.value = target
  try {
    const context: Record<string, string> = {
      科目: '应付职工薪酬-股份支付情况表（J3-1，CAS 11 股份支付）',
      方案数: String(plans.length),
      方案概览: plans.map(p => `${p.name}(${p.type})`).join('；') || '（暂无方案）',
    }
    const map = { resolution: resolutionText, fairValue: fairValueText, note: auditNote, conclusion: auditConclusion }
    const existing = map[target].value
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, { section: `j3-1-${target}`, context, existingContent: existing })
    const d = (res as { data?: Record<string, any> })?.data
    const text = d?.data?.content || d?.content || d?.data?.text || d?.text || ''
    if (text) { map[target].value = text; scheduleSave() }
  } catch { /* 静默 */ } finally { aiLoading.value = '' }
}
onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j3-tab-detail">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：①应付职工薪酬（股份支付）存在且记录于恰当账户；②所有应记录的股份支付及相关披露均已记录/包括（完整性）；③由被审计单位拥有或控制；④以恰当金额列示，计价/分摊调整已恰当记录，相关披露已恰当计量与描述；⑤已恰当汇总/分解且表述清楚，披露在企业会计准则编制基础下相关、可理解。
      </template>
    </el-alert>

    <!-- 提示1：方法论参考（内嵌，帮助理解与应用） -->
    <details class="methodology-block" open>
      <summary>📖 股份支付主要审计过程和关注要点（方法论参考 · CAS 11）</summary>
      <ol class="guide-list">
        <li v-for="(p, i) in GUIDE_POINTS" :key="i">{{ p }}</li>
      </ol>
      <div class="methodology-cta">
        <span>💡 下方"审计过程"与"股份支付明细表"逐项落实以上要点；建议用</span>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="openAddDialog">引导式录入向导</el-button>
        <span>边填边分析，逐步完成底稿。</span>
      </div>
    </details>

    <div class="proc-title">二、审计过程</div>

    <!-- 1. 股份支付决议及其内容 -->
    <div class="note-wrap">
      <div class="note-hd"><span>1. 公司股份支付决议及其内容</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'resolution'" :disabled="isReadonly" @click="aiGen('resolution')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="resolutionText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="描述董事会/股东会决议内容：授予对象、授予日期、权益工具数量、行权价格、行权条件、等待期等主要条款。" @change="scheduleSave" />
    </div>

    <!-- 2. 公允价值的确定及相关假设 -->
    <div class="note-wrap">
      <div class="note-hd"><span>2. 公允价值的确定及相关假设</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'fairValue'" :disabled="isReadonly" @click="aiGen('fairValue')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="fairValueText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="描述授予日权益工具公允价值的确定方法（如 Black-Scholes 期权定价模型）及关键假设：股价、行权价、预期波动率、无风险利率、预期股利率、期权期限等，并评价假设的合理性。" @change="scheduleSave" />
    </div>

    <!-- 3. 了解专家资质及利用精算师的工作 -->
    <h4 class="sec-title">3. 了解专家资质及利用精算师的工作</h4>
    <el-table :data="expertRows" border size="small" class="wp-table" style="max-width: 760px">
      <el-table-column label="序号" width="56" align="center"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
      <el-table-column label="项目" min-width="200"><template #default="{ row }">{{ row.item }}</template></el-table-column>
      <el-table-column label="索引号" width="120" align="center">
        <template #default="{ row }"><GtIndexChip :value="`wp:${row.indexCode}`" :context-project-id="projectId" /></template>
      </el-table-column>
      <el-table-column label="评价说明" min-width="260">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 股份支付明细表 -->
    <div class="sec-head">
      <h4 class="sec-title">股份支付明细表</h4>
      <div class="toolbar-right">
        <el-tag size="small" type="info">共 {{ plans.length }} 个方案</el-tag>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="openAddDialog">+ 引导式新增方案</el-button>
        <el-dropdown trigger="click" :disabled="isReadonly" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <el-table :data="plans" border size="small" class="wp-table" style="width: 100%">
      <el-table-column label="序号" type="index" width="50" align="center" fixed />
      <el-table-column label="股份支付项目名称" min-width="160" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="150">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.type" size="small" @change="scheduleSave">
            <el-option v-for="o in TYPE_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.type }}</span>
        </template>
      </el-table-column>
      <el-table-column label="授予日" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.grantDate" size="small" placeholder="YYYY-MM-DD" @change="scheduleSave" />
          <span v-else>{{ row.grantDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="批准部门" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.approvalDept" size="small" @change="scheduleSave" />
          <span v-else>{{ row.approvalDept }}</span>
        </template>
      </el-table-column>
      <el-table-column label="行权日" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.exerciseDate" size="small" placeholder="YYYY-MM-DD" @change="scheduleSave" />
          <span v-else>{{ row.exerciseDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="权益工具数量" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.instrumentQty" :controls="false" size="small" @change="scheduleSave" />
          <span v-else>{{ row.instrumentQty }}</span>
        </template>
      </el-table-column>
      <el-table-column label="等待期" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.vestingPeriod" size="small" placeholder="如 3 年" @change="scheduleSave" />
          <span v-else>{{ row.vestingPeriod }}</span>
        </template>
      </el-table-column>
      <el-table-column min-width="200">
        <template #header><GtThTip text="公允价值确定方法和数据来源" /></template>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.fvMethod" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.fvMethod }}</span>
        </template>
      </el-table-column>
      <el-table-column min-width="160">
        <template #header><GtThTip text="协议变更/取消情况" /></template>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.agreementChange" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.agreementChange }}</span>
        </template>
      </el-table-column>
      <el-table-column min-width="180">
        <template #header><GtThTip text="资产负债表日估计更新情况" /></template>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.bsUpdate" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.bsUpdate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="剩余等待期限" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remainingPeriod" size="small" @change="scheduleSave" />
          <span v-else>{{ row.remainingPeriod }}</span>
        </template>
      </el-table-column>
      <el-table-column label="协议索引号" width="110" align="center">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.agreementIndex" size="small" @change="scheduleSave" />
          <span v-else>{{ row.agreementIndex }}</span>
        </template>
      </el-table-column>
      <el-table-column width="140" align="center">
        <template #header><GtThTip text="股份支付计算表索引号" /></template>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.calcTableIndex" size="small" @change="scheduleSave" />
          <span v-else>{{ row.calcTableIndex }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.conclusion" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.conclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="90" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-button type="danger" link size="small" @click="removePlan(row.id)">删</el-button>
        </template>
      </el-table-column>
      <template #empty><span class="empty-hint">暂无方案。点击"+ 引导式新增方案"打开录入向导，或"导入数据"批量添加。</span></template>
    </el-table>

    <!-- 引导式新增/编辑方案弹窗 -->
    <J3PlanDialog v-model="dialogVisible" :plan="editingPlan" :is-readonly="isReadonly" @save="onDialogSave" />

    <!-- 三、审计说明 -->
    <div class="note-wrap">
      <div class="note-hd"><span>三、审计说明</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'note'" :disabled="isReadonly" @click="aiGen('note')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" :placeholder="PH_NOTE" @change="scheduleSave" />
    </div>

    <!-- 四、审计结论 -->
    <div class="note-wrap">
      <div class="note-hd"><span>四、审计结论</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="aiGen('conclusion')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="请输入审计结论，或点击 AI 辅助生成（如：未见异常；或除上述调整事项外其余未见异常等）。" @change="scheduleSave" />
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 11《股份支付》：权益结算按授予日权益工具公允价值计量（贷记资本公积 M4），后续不重新计量；现金结算按每个资产负债表日重新计量公允价值（贷记应付职工薪酬 J1）。</p>
        <p>2. 费用在等待期内按最佳估计的可行权数量分期确认，计入管理费用/销售费用等（K8/K9）；取消/失效时按 CAS 11 加速或转回处理。</p>
        <p>3. 明细表逐方案列示条款要素、公允价值方法、协议变更及索引；金额分配详见"股份支付计算表"（填索引号）。</p>
        <p>4. 导入导出：可下载模板批量录入方案后导入；导入将覆盖明细表并从服务器刷新。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.j3-tab-detail { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.methodology-block { margin-bottom: 14px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 4px; padding: 8px 12px; }
.methodology-block summary { cursor: pointer; font-weight: 600; color: #b88230; }
.guide-list { margin: 10px 0 2px; padding-left: 20px; font-size: 12px; color: #8c6d1f; line-height: 1.7; }
.guide-list li { margin-bottom: 6px; }
.methodology-cta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 10px; padding-top: 8px; border-top: 1px dashed #f0c78a; font-size: 12px; color: #8c6d1f; }
.proc-title { font-size: 14px; font-weight: 600; color: #303133; margin: 8px 0; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 18px 0 8px; }
.sec-head { display: flex; align-items: center; justify-content: space-between; margin: 18px 0 8px; }
.sec-head .sec-title { margin: 0; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.wp-table :deep(.el-input-number) { width: 100%; }
.empty-hint { font-size: 12px; color: #909399; }
.note-wrap { margin-top: 14px; }
.note-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #303133; }
.conclusion-actions { display: flex; gap: 6px; align-items: center; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
