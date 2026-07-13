<!--
  J1TabSeveranceCheck.vue — J1-10 应付职工薪酬-辞退福利检查表

  对齐致同源模板 J1-10：
    一、审计目标（3认定）
    二、审计过程（6步）
    1、公司是否制定辞退福利相关制度及内容（文本）
    2、近期是否正在实施辞退或裁减计划及所处阶段（文本）
    3、解除劳动关系计划/自愿裁减建议是否符合准则确认条件（文本）
    4、了解专家资质及利用精算师的工作（表：序号/项目/索引号，S12/S12A）
    5、抽查本期增减变动的真实性（凭证明细表）
    三、审计说明  四、审计结论
    提示：辞退福利计算关键假设与参数（增长率/死亡率/折现率）+ 折现率确定方法
  自持久化（selfLoad + 防抖 PUT）。
-->
<template>
  <div class="j1-tab-severance">
    <!-- 顶部工具栏 -->
    <div class="ie-toolbar">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('severance')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('severance')">导出数据</el-dropdown-item>
            <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的应付职工薪酬（辞退福利）是存在的，且已记录在恰当的账户中；</li>
        <li><b>完整性：</b>所有应记录的辞退福利均已记录，所有应披露的相关信息均已包括；</li>
        <li><b>计价分摊与列报：</b>以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- 二、审计过程（琥珀块） -->
    <div class="amber-context">
      <div class="amber-title">二、审计过程</div>
      <p>1. 取得辞退福利相关制度、决议、计划、协议，确定该福利是否满足确认为负债的标准，确定负债的计算是否合理；</p>
      <p>2. 对于职工没有选择权的辞退计划，检查按辞退职工数量、辞退补偿标准计提辞退福利负债金额是否正确；</p>
      <p>3. 对于自愿接受裁减的建议，检查按接受裁减建议的预计职工数量、辞退补偿标准等计提辞退福利负债金额是否正确；</p>
      <p>4. 检查实质性辞退工作在一年内完成、但付款时间超过一年的辞退福利，是否按折现后的金额计量，折现率的选择是否合理；</p>
      <p>5. 识别辞退福利中是否包含未予辞退的员工，检查其工资薪酬是否已恰当计入相关费用；</p>
      <p>6. 检查辞退福利会计处理是否正确。</p>
    </div>

    <!-- 1/2/3 文本政策区 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">1、公司是否制定了关于辞退福利的相关制度，及其内容</span>
          <el-button size="small" type="primary" plain :loading="aiField === 'policy'" :disabled="isReadonly" @click="generateField('policy')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="policyText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="描述辞退福利相关制度、决议、计划、协议及主要内容..." @change="persist" />
    </el-card>
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">2、公司近期是否正在实施辞退或裁减计划，具体内容及所处阶段</span>
          <el-button size="small" type="primary" plain :loading="aiField === 'plan'" :disabled="isReadonly" @click="generateField('plan')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="planText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="描述近期辞退/裁减计划的具体内容、涉及范围及所处阶段（拟定/公告/执行/完成）..." @change="persist" />
    </el-card>
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">3、解除劳动关系计划/自愿裁减建议是否符合准则规定的确认辞退福利的条件</span>
          <el-button size="small" type="primary" plain :loading="aiField === 'condition'" :disabled="isReadonly" @click="generateField('condition')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="conditionText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="判断是否满足CAS9确认条件：①企业已制定正式的解除劳动关系计划或提出自愿裁减建议且即将实施；②企业不能单方面撤回..." @change="persist" />
    </el-card>

    <!-- 4、专家利用 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">4、了解专家资质及利用精算师的工作</span></template>
      <el-table :data="expertRows" border size="small" class="expert-table">
        <el-table-column label="序号" type="index" width="56" align="center" />
        <el-table-column label="项目" min-width="200"><template #default="{ row }">{{ row.label }}</template></el-table-column>
        <el-table-column label="索引号" width="200">
          <template #default="{ row }">
            <div class="idx-cell">
              <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" style="width:100px" @change="persist" />
              <span v-else>{{ row.indexNo || '-' }}</span>
              <GtIndexChip v-if="row.indexNo" :value="`wp:${row.indexNo}`" :context-project-id="projectId" />
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 5、抽查本期增减变动 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">5、抽查本期增减变动的真实性</span>
          <div>
            <span class="grp-total">借方合计 {{ fmtAmt(debitTotal) }} ／ 贷方合计 {{ fmtAmt(creditTotal) }}</span>
            <el-button v-if="!isReadonly" size="small" @click="addRow">＋ 新增凭证</el-button>
          </div>
        </div>
      </template>
      <el-table :data="rows" border size="small" :max-height="400" class="voucher-table">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="日期" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证种类" width="90">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherType" size="small" @change="persist" /><span v-else>{{ row.voucherType || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.business" size="small" @change="persist" /><span v-else>{{ row.business || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="明细科目" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.subAccount" size="small" @change="persist" /><span v-else>{{ row.subAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方明细科目" width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="借方" width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" size="small" class="amt-in" @change="persist" /><span v-else class="amt">{{ fmtAmt(row.debit) }}</span></template>
        </el-table-column>
        <el-table-column label="贷方" width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" size="small" class="amt-in" @change="persist" /><span v-else class="amt">{{ fmtAmt(row.credit) }}</span></template>
        </el-table-column>
        <el-table-column label="附件" width="80" align="center">
          <template #default="{ row }">
            <el-upload v-if="!isReadonly" :show-file-list="false" :auto-upload="false" :on-change="(f: any) => onOcrUpload(row, f)" accept=".pdf,.png,.jpg,.jpeg">
              <el-button size="small" :loading="ocrLoadingId === row.id" text bg>📎{{ row.attachment ? '✓' : '' }}</el-button>
            </el-upload>
            <span v-else>{{ row.attachment ? '有' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" clearable placeholder="—" @change="persist">
              <el-option label="真实" value="真实" /><el-option label="需调整" value="需调整" /><el-option label="待定" value="待定" />
            </el-select>
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeRow(row.id)">删除</el-button></template>
        </el-table-column>
        <template #empty><el-empty description="暂无凭证，点击「＋新增凭证」" :image-size="60" /></template>
      </el-table>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、审计说明</span>
          <el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly" @click="generateAi('note')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="描述辞退福利确认条件判断、金额计量、折现处理及检查发现..." @change="persist" />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">四、审计结论</span>
          <el-button size="small" type="primary" plain :loading="aiConcLoading" :disabled="isReadonly" @click="generateAi('conclusion')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionSelect">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大未调整事项，需进一步处理" value="C" />
      </el-select>
      <el-input v-model="conclusionText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="基于上述检查情况，形成审计结论..." @change="persist" />
    </el-card>

    <!-- 关键假设与参数 -->
    <el-card shadow="never" class="section-card assumptions-card">
      <template #header><span class="card-title">提示：辞退福利计算中使用的关键假设和主要参数</span></template>
      <el-table :data="assumptionRows" border size="small" class="assumption-table">
        <el-table-column label="序号" type="index" width="56" align="center" />
        <el-table-column label="关键假设/参数" min-width="180"><template #default="{ row }">{{ row.label }}</template></el-table-column>
        <el-table-column label="取值" width="140">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.value" size="small" placeholder="如 3% / 见依据" @change="persist" /><span v-else>{{ row.value || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="确定依据" min-width="220">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.basis" size="small" @change="persist" /><span v-else>{{ row.basis || '-' }}</span></template>
        </el-table-column>
      </el-table>
      <div class="amber-context discount-note">
        <div class="amber-title">折现率确定方法</div>
        <p>折现率为同期限同币种国债利率或高质量公司债券的市场收益率。不存在与辞退福利支付期限相匹配国债利率的，应当以短于辞退福利支付期限的国债利率为基础，并根据国债收益率曲线采用外推法估计超出期限部分的利率，合理确定折现率。</p>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（CAS 9 职工薪酬 · 辞退福利）</summary>
      <div class="guidance-content">
        <p>1. 辞退福利在"企业不能单方面撤回解除劳动关系计划或裁减建议"与"确认重组相关成本或费用"两者孰早日确认为负债并计入当期损益；</p>
        <p>2. 实质性辞退工作在一年内完成、但付款超过一年的，按折现后金额计量（属其他长期职工福利）；</p>
        <p>3. 涉及重大精算估计的（如提前退休计划），评估是否利用精算师工作并复核其资质（第4区专家利用表）；</p>
        <p>4. 关键假设（工资/生活费增长率、社保公积金增长率、死亡率、折现率）须有合理依据，折现率按上方方法确定；</p>
        <p>5. 识别辞退福利中是否混入未予辞退员工的工资薪酬，若有须重分类计入相关费用。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import GtIndexChip from '../../GtIndexChip.vue'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import { useJ1VoucherOcr } from '@/composables/workpaper/j1/useJ1VoucherOcr'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const isReadonly = computed(() => false)

interface SevRow {
  id: string; date: string; voucherType: string; voucherNo: string; business: string
  subAccount: string; offsetAccount: string; debit: number; credit: number
  attachment: string; conclusion: string
}

const rows = ref<SevRow[]>([])
const policyText = ref('')
const planText = ref('')
const conditionText = ref('')
const auditNote = ref('')
const conclusionText = ref('')
const conclusionOption = ref('')

const expertRows = ref([
  { label: '利用专家的工作', indexNo: 'S12' },
  { label: '评估专家工作', indexNo: 'S12A' },
])
const assumptionRows = ref([
  { label: '基本工资/生活费增长率', value: '', basis: '' },
  { label: '社保、公积金增长率', value: '', basis: '' },
  { label: '死亡率', value: '', basis: '' },
  { label: '折现率', value: '', basis: '' },
])

const debitTotal = computed(() => rows.value.reduce((s, r) => s + (r.debit || 0), 0))
const creditTotal = computed(() => rows.value.reduce((s, r) => s + (r.credit || 0), 0))

const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)
const { ocrLoadingId, uploadAndMerge } = useJ1VoucherOcr(computed(() => props.wpId))

function newRow(): SevRow {
  return {
    id: `sev-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    date: '', voucherType: '记账凭证', voucherNo: '', business: '',
    subAccount: '', offsetAccount: '', debit: 0, credit: 0,
    attachment: '', conclusion: '',
  }
}
function addRow() { rows.value.push(newRow()); persist() }
function removeRow(id: string) { rows.value = rows.value.filter(r => r.id !== id); persist() }

function onOcrUpload(row: SevRow, uploadFile: any) {
  const file: File | undefined = uploadFile?.raw
  if (!file) return
  row.attachment = file.name
  uploadAndMerge(row.id, file, 'debit', (_id, patch) => {
    if (patch.date) row.date = patch.date
    if (patch.voucherNo) row.voucherNo = patch.voucherNo
    if (patch.debitAmount) row.debit = patch.debitAmount
    if (patch.businessContent) row.business = patch.businessContent
    persist()
  })
}

onMounted(async () => {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items: Array<{ item_id: string; remark?: string; conclusion?: string }> = res.data?.data || res.data || []
    for (const it of items) {
      if (it.item_id === 'J1-10-policy') policyText.value = it.remark || ''
      else if (it.item_id === 'J1-10-plan') planText.value = it.remark || ''
      else if (it.item_id === 'J1-10-condition') conditionText.value = it.remark || ''
      else if (it.item_id === 'J1-10-experts') { try { const a = JSON.parse(it.remark || '[]'); if (Array.isArray(a) && a.length) expertRows.value = a } catch { /* */ } }
      else if (it.item_id === 'J1-10-assumptions') { try { const a = JSON.parse(it.remark || '[]'); if (Array.isArray(a) && a.length) assumptionRows.value = a } catch { /* */ } }
      else if (it.item_id === 'J1-10-vouchers') { try { rows.value = JSON.parse(it.remark || '[]') } catch { /* */ } }
      else if (it.item_id === 'J1-10-note') auditNote.value = it.remark || ''
      else if (it.item_id === 'J1-10-conclusion') { conclusionText.value = it.remark || ''; conclusionOption.value = it.conclusion || '' }
    }
  } catch { /* */ }
})

let timer: ReturnType<typeof setTimeout> | null = null
function persist() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
        items: [
          { item_id: 'J1-10-policy', remark: policyText.value, conclusion: null },
          { item_id: 'J1-10-plan', remark: planText.value, conclusion: null },
          { item_id: 'J1-10-condition', remark: conditionText.value, conclusion: null },
          { item_id: 'J1-10-experts', remark: JSON.stringify(expertRows.value), conclusion: null },
          { item_id: 'J1-10-assumptions', remark: JSON.stringify(assumptionRows.value), conclusion: null },
          { item_id: 'J1-10-vouchers', remark: JSON.stringify(rows.value), conclusion: null },
          { item_id: 'J1-10-note', remark: auditNote.value, conclusion: null },
          { item_id: 'J1-10-conclusion', remark: conclusionText.value, conclusion: conclusionOption.value || null },
        ],
      })
    } catch { /* */ }
  }, 800)
}

function onConclusionSelect(val: string) {
  const map: Record<string, string> = {
    A: '经检查，被审计单位辞退福利确认条件满足、金额计量合理、折现处理恰当，未见异常。',
    B: '除上述事项应予调整外，其余辞退福利的确认、计量与列报未见异常。',
    C: '存在重大未调整事项（辞退福利确认条件/计量/折现有误），需进一步处理。',
  }
  if (map[val] && !conclusionText.value) conclusionText.value = map[val]
  persist()
}

function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0]; if (!f) return
    const ok = await importData('severance', f)
    if (!ok) return
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items = res.data?.data || res.data || []
    for (const it of items) if (it.item_id === 'J1-10-vouchers') { try { rows.value = JSON.parse(it.remark || '[]') } catch { /* */ } }
  }
  input.click()
}

// 三个文本政策区 AI 辅助
const aiField = ref<'policy' | 'plan' | 'condition' | null>(null)
const FIELD_META: Record<'policy' | 'plan' | 'condition', { ref: () => string; set: (v: string) => void; prompt: string }> = {
  policy: {
    ref: () => policyText.value, set: (v) => { policyText.value = v },
    prompt: '根据被审计单位辞退福利相关制度、决议、计划、协议，生成"公司辞退福利制度及其内容"说明段落，客观描述制度依据与主要内容。',
  },
  plan: {
    ref: () => planText.value, set: (v) => { planText.value = v },
    prompt: '根据被审计单位近期辞退或裁减计划情况，生成"近期辞退/裁减计划及所处阶段"说明段落，涵盖计划内容、涉及范围与所处阶段（拟定/公告/执行/完成）。',
  },
  condition: {
    ref: () => conditionText.value, set: (v) => { conditionText.value = v },
    prompt: '依据CAS9辞退福利确认条件，生成"解除劳动关系计划/自愿裁减建议是否符合确认条件"的判断段落：①是否已制定正式方案且即将实施；②企业是否不能单方面撤回；③预计经济利益流出可能性是否超过50%。',
  },
}
async function generateField(field: 'policy' | 'plan' | 'condition') {
  if (isReadonly.value) return
  aiField.value = field
  const meta = FIELD_META[field]
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `j1-10-${field}`,
      prompt: meta.prompt,
      context: { policy: policyText.value, plan: planText.value, condition: conditionText.value },
      existingContent: meta.ref(),
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) { meta.set(text); persist() }
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiField.value = null }
}

const aiNoteLoading = ref(false)
const aiConcLoading = ref(false)
async function generateAi(section: 'note' | 'conclusion') {
  if (isReadonly.value) return
  const loading = section === 'note' ? aiNoteLoading : aiConcLoading
  loading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `j1-10-${section}`,
      prompt: section === 'note'
        ? '根据辞退福利制度、裁减计划、确认条件判断、关键假设及抽查凭证情况，生成审计说明。'
        : '根据J1-10辞退福利检查情况和审计说明，生成审计结论。',
      context: { policy: policyText.value, plan: planText.value, condition: conditionText.value, 借方合计: debitTotal.value, 贷方合计: creditTotal.value, 凭证数: rows.value.length },
      existingContent: section === 'note' ? auditNote.value : conclusionText.value,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) { if (section === 'note') auditNote.value = text; else conclusionText.value = text; persist() }
  } catch { ElMessage.warning('AI 生成失败') }
  finally { loading.value = false }
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.j1-tab-severance { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.ie-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.amber-context { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.7; }
.amber-context .amber-title { font-weight: 600; color: #92400e; margin-bottom: 4px; }
.amber-context p { margin: 2px 0; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.grp-total { font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; margin-right: 10px; }
.expert-table, .assumption-table { font-size: var(--wp-font-size, 13px); max-width: 720px; }
.idx-cell { display: flex; align-items: center; gap: 8px; }
.voucher-table { font-size: var(--wp-font-size, 13px); }
.voucher-table :deep(th), .voucher-table :deep(td) { font-size: 13px; }
.amt { font-variant-numeric: tabular-nums; }
.amt-in { width: 100%; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.assumptions-card :deep(.el-card__header) { background: #fdf6ec; }
.discount-note { margin: 12px 0 0; }
.guidance-details { margin-top: 6px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
