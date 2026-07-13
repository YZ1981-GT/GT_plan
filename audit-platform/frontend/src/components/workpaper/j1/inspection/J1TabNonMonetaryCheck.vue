<!--
  J1TabNonMonetaryCheck.vue — J1-9 应付职工薪酬-非货币性福利检查表

  对齐致同源模板 J1-9：
    一、审计目标（3认定：存在/完整性+披露/计价分摊+披露）
    二、审计过程（4步）
    1、公司非货币性福利政策及其内容（文本）
    2、计提金额的确定（文本）
    3、抽查本期增减变动的准确性及会计处理的适当性（凭证明细表）
       日期/凭证种类/凭证编号/业务内容/明细科目/对方科目/借方/贷方/附件/非货币性福利形式/实物来源/结论
    三、审计说明
    四、审计结论
  自持久化（selfLoad + 防抖 PUT）。
-->
<template>
  <div class="j1-tab-nonmonetary">
    <!-- 顶部工具栏 -->
    <div class="ie-toolbar">
      <el-dropdown size="small" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate('non_monetary')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData('non_monetary')">导出数据</el-dropdown-item>
            <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的应付职工薪酬（非货币性福利）是存在的，且已记录在恰当的账户中；</li>
        <li><b>完整性：</b>所有应记录的非货币性福利均已记录，所有应披露的相关信息均已包括；</li>
        <li><b>计价分摊与列报：</b>以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- 二、审计过程（琥珀块） -->
    <div class="amber-context">
      <div class="amber-title">二、审计过程</div>
      <p>1. 取得非货币性福利明细表，确定计算的准确性；</p>
      <p>2. 取得非货币性福利核算文件，了解主要政策；</p>
      <p>3. 确定该福利是否满足确认为负债的标准；</p>
      <p>4. 确定负债的计算是否合理。</p>
    </div>

    <!-- 1、非货币性福利政策及其内容 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">1、公司非货币性福利政策及其内容</span></template>
      <el-input v-model="policyText" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="描述以自产产品/外购商品/房屋等提供职工福利的政策、发放对象、计量方式（公允价值/成本）等..." @change="persist" />
    </el-card>

    <!-- 2、计提金额的确定 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">2、计提金额的确定</span></template>
      <el-input v-model="accrualBasisText" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="说明计提基础、公允价值来源、涉及增值税视同销售/个税代扣代缴的税务处理等..." @change="persist" />
    </el-card>

    <!-- 3、抽查本期增减变动 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">3、抽查本期增减变动的准确性及会计处理的适当性</span>
          <div>
            <span class="grp-total">借方合计 {{ fmtAmt(debitTotal) }} ／ 贷方合计 {{ fmtAmt(creditTotal) }}</span>
            <el-button v-if="!isReadonly" size="small" @click="addRow">＋ 新增凭证</el-button>
          </div>
        </div>
      </template>
      <el-table :data="rows" border size="small" :max-height="420" class="voucher-table">
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
        <el-table-column label="业务内容" min-width="130">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.business" size="small" @change="persist" /><span v-else>{{ row.business || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="明细科目" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.subAccount" size="small" @change="persist" /><span v-else>{{ row.subAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方科目" width="110">
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
        <el-table-column label="非货币性福利形式" min-width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.benefitForm" size="small" filterable allow-create placeholder="选择/输入" @change="persist">
              <el-option label="自产产品" value="自产产品" /><el-option label="外购商品" value="外购商品" />
              <el-option label="房屋等资产使用" value="房屋等资产使用" /><el-option label="免费/低价服务" value="免费/低价服务" />
            </el-select>
            <span v-else>{{ row.benefitForm || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实物来源" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.source" size="small" @change="persist" /><span v-else>{{ row.source || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="结论" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" clearable placeholder="—" @change="persist">
              <el-option label="合规" value="合规" /><el-option label="需调整" value="需调整" /><el-option label="待定" value="待定" />
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
        placeholder="描述非货币性福利检查过程、发现的问题及处理意见..." @change="persist" />
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
        <el-option label="B、除上述不合规事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大不合规事项，需进一步调整" value="C" />
      </el-select>
      <el-input v-model="conclusionText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="基于上述检查情况，形成审计结论..." @change="persist" />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（CAS 9 职工薪酬）</summary>
      <div class="guidance-content">
        <p>1. 以自产产品发放的非货币性福利，按产品公允价值计量并计入相关成本费用；</p>
        <p>2. 外购商品、房屋等提供职工使用的，按实际成本或折旧/租金公允价值确认福利费；</p>
        <p>3. 非货币性福利涉及增值税视同销售、个人所得税代扣代缴，须核验税务处理合规性；</p>
        <p>4. 抽查凭证核对：原始凭证齐全、与记账凭证相符、金额计算准确、截止期间正确、会计处理适当；</p>
        <p>5. 结论列标"需调整"的须在审计说明栏说明整改建议。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import { useJ1VoucherOcr } from '@/composables/workpaper/j1/useJ1VoucherOcr'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const isReadonly = computed(() => false)

interface NmRow {
  id: string; date: string; voucherType: string; voucherNo: string; business: string
  subAccount: string; offsetAccount: string; debit: number; credit: number
  attachment: string; benefitForm: string; source: string; conclusion: string
}

const rows = ref<NmRow[]>([])
const policyText = ref('')
const accrualBasisText = ref('')
const auditNote = ref('')
const conclusionText = ref('')
const conclusionOption = ref('')

const debitTotal = computed(() => rows.value.reduce((s, r) => s + (r.debit || 0), 0))
const creditTotal = computed(() => rows.value.reduce((s, r) => s + (r.credit || 0), 0))

const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)
const { ocrLoadingId, uploadAndMerge } = useJ1VoucherOcr(computed(() => props.wpId))

function newRow(): NmRow {
  return {
    id: `nm-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    date: '', voucherType: '记账凭证', voucherNo: '', business: '',
    subAccount: '', offsetAccount: '', debit: 0, credit: 0,
    attachment: '', benefitForm: '', source: '', conclusion: '',
  }
}
function addRow() { rows.value.push(newRow()); persist() }
function removeRow(id: string) { rows.value = rows.value.filter(r => r.id !== id); persist() }

function onOcrUpload(row: NmRow, uploadFile: any) {
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

// ─── selfLoad ────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items: Array<{ item_id: string; remark?: string; conclusion?: string }> = res.data?.data || res.data || []
    for (const it of items) {
      if (it.item_id === 'J1-9-policy') policyText.value = it.remark || ''
      else if (it.item_id === 'J1-9-accrual-basis') accrualBasisText.value = it.remark || ''
      else if (it.item_id === 'J1-9-vouchers') { try { rows.value = JSON.parse(it.remark || '[]') } catch { /* */ } }
      else if (it.item_id === 'J1-9-note') auditNote.value = it.remark || ''
      else if (it.item_id === 'J1-9-conclusion') { conclusionText.value = it.remark || ''; conclusionOption.value = it.conclusion || '' }
    }
  } catch { /* */ }
})

// ─── persist ─────────────────────────────────────────────────────────────
let timer: ReturnType<typeof setTimeout> | null = null
function persist() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
        items: [
          { item_id: 'J1-9-policy', remark: policyText.value, conclusion: null },
          { item_id: 'J1-9-accrual-basis', remark: accrualBasisText.value, conclusion: null },
          { item_id: 'J1-9-vouchers', remark: JSON.stringify(rows.value), conclusion: null },
          { item_id: 'J1-9-note', remark: auditNote.value, conclusion: null },
          { item_id: 'J1-9-conclusion', remark: conclusionText.value, conclusion: conclusionOption.value || null },
        ],
      })
    } catch { /* */ }
  }, 800)
}

function onConclusionSelect(val: string) {
  const map: Record<string, string> = {
    A: '经检查，被审计单位非货币性福利计量方式恰当、金额准确、税务处理合规，未见异常。',
    B: '除上述不合规事项应整改外，其余非货币性福利项目的计量、记录与税务处理未见异常。',
    C: '存在重大不合规事项，非货币性福利计量/税务处理有误，需调整。',
  }
  if (map[val] && !conclusionText.value) conclusionText.value = map[val]
  persist()
}

function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0]; if (!f) return
    const ok = await importData('non_monetary', f)
    if (!ok) return
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items = res.data?.data || res.data || []
    for (const it of items) if (it.item_id === 'J1-9-vouchers') { try { rows.value = JSON.parse(it.remark || '[]') } catch { /* */ } }
  }
  input.click()
}

const aiNoteLoading = ref(false)
const aiConcLoading = ref(false)
async function generateAi(section: 'note' | 'conclusion') {
  if (isReadonly.value) return
  const loading = section === 'note' ? aiNoteLoading : aiConcLoading
  loading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `j1-9-${section}`,
      prompt: section === 'note'
        ? '根据非货币性福利政策、计提金额确定及抽查凭证情况，生成审计说明。'
        : '根据J1-9非货币性福利检查情况和审计说明，生成审计结论。',
      context: { policy: policyText.value, accrualBasis: accrualBasisText.value, 借方合计: debitTotal.value, 贷方合计: creditTotal.value, 凭证数: rows.value.length },
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
.j1-tab-nonmonetary { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
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
.voucher-table { font-size: var(--wp-font-size, 13px); }
.voucher-table :deep(th), .voucher-table :deep(td) { font-size: 13px; }
.amt { font-variant-numeric: tabular-nums; }
.amt-in { width: 100%; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.guidance-details { margin-top: 6px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
