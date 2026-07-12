<template>
  <div class="i1-tab-disposal-check">
    <!-- 方法论上下文（琥珀色左边线） -->
    <div class="methodology-context">
      <p>对本期减少无形资产进行逐项检查：验证处置方式及审批流程、复核处置损益计算（处置损益 = 处置收入 - 净值）、确认减少合计与审定表"本期减少"勾稽一致。</p>
    </div>

    <!-- 主检查表 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I1-6 减少明细表（{{ rows.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" @click="showSamplingDialog = true" :disabled="isReadonly">🎲 抽凭</el-button>
            <el-button size="small" type="default" link @click="handleReview('I1-6')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border stripe size="small" max-height="500" class="check-table">
        <!-- 1. 序号 -->
        <el-table-column type="index" label="序号" width="50" align="center" fixed />
        <!-- 2. 名称 -->
        <el-table-column prop="name" label="名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" placeholder="无形资产名称" @change="handleChange" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <!-- 3. 原值 -->
        <el-table-column prop="originalCost" label="原值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" :precision="2" @change="handleChange" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <!-- 4. 累计摊销 -->
        <el-table-column prop="accAmort" label="累计摊销" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accAmort" :controls="false" size="small" :precision="2" @change="handleChange" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accAmort) }}</span>
          </template>
        </el-table-column>
        <!-- 5. 减值 -->
        <el-table-column prop="impairment" label="减值" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false" size="small" :precision="2" @change="handleChange" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <!-- 6. 净值（公式） -->
        <el-table-column label="净值" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="净值 = 原值 - 累计摊销 - 减值" placement="top">
              <span class="formula-cell">{{ fmtAmt(calcNetValue(row.originalCost, row.accAmort, row.impairment)) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <!-- 7. 处置方式 -->
        <el-table-column prop="disposalType" label="处置方式" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.disposalType" size="small" placeholder="选择" @change="handleChange">
              <el-option label="出售" value="出售" />
              <el-option label="报废" value="报废" />
              <el-option label="转让" value="转让" />
              <el-option label="到期注销" value="到期注销" />
            </el-select>
            <span v-else>{{ row.disposalType || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 8. 处置收入 -->
        <el-table-column prop="disposalIncome" label="处置收入" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.disposalIncome" :controls="false" size="small" :precision="2" @change="handleChange" />
            <span v-else class="amount-cell">{{ fmtAmt(row.disposalIncome) }}</span>
          </template>
        </el-table-column>
        <!-- 9. 处置损益（公式） -->
        <el-table-column label="处置损益" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="处置损益 = 处置收入 - 净值" placement="top">
              <span :class="['formula-cell', { 'error-amount': getGainLoss(row) < 0 }]">
                {{ fmtAmt(getGainLoss(row)) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <!-- 10. 审批文件 -->
        <el-table-column prop="approvalDoc" label="审批文件" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.approvalDoc" size="small" placeholder="文号" @change="handleChange" />
            <span v-else>{{ row.approvalDoc || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 11. 日期 -->
        <el-table-column prop="disposalDate" label="日期" width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.disposalDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="handleChange" />
            <span v-else>{{ row.disposalDate || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 12. 结论 -->
        <el-table-column prop="conclusion" label="结论" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" placeholder="-" @change="handleChange">
              <el-option label="无异常" value="无异常" />
              <el-option label="有异常" value="有异常" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <el-tag v-else :type="row.conclusion === '无异常' ? 'success' : row.conclusion === '有异常' ? 'danger' : 'warning'" size="small">
              {{ row.conclusion || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <!-- 操作列 -->
        <el-table-column label="操作" width="50" v-if="!isReadonly" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="handleRemoveRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="summary-bar">
        <span>原值合计: <b class="amount-cell">{{ fmtAmt(totalOriginalCost) }}</b></span>
        <span>净值合计: <b class="amount-cell">{{ fmtAmt(totalNetValue) }}</b></span>
        <span>处置收入合计: <b class="amount-cell">{{ fmtAmt(totalDisposalIncome) }}</b></span>
        <span>处置损益合计: <b :class="['amount-cell', { 'error-amount': totalGainLoss < 0 }]">{{ fmtAmt(totalGainLoss) }}</b></span>
        <GtIndexChip value="审定表I1" @click="emit('navigate-sheet', '审定表I1')" />
      </div>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('disposal-conclusion')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="对本期无形资产减少事项的审计结论..."
        @change="saveConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>处置损益 = 处置收入 - 净值（净值 = 原值 - 累计摊销 - 减值）</li>
        <li>处置方式选项：出售 / 报废 / 转让 / 到期注销</li>
        <li>合计行联动审定表I1"本期减少"列</li>
        <li>关注到期注销的无形资产是否有残值回收或转让收入</li>
        <li>报废/注销需审批文件，出售/转让需合同/协议</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1701 无形资产-减少）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :account-codes="['1701']"
        dialog-mode
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, watch, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { calcNetValue, calcDisposalGainLoss } from '../../composables/useI1FormulaEngine'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props & Emits ────────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject ───────────────────────────────────────────────────────────────────
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── State ────────────────────────────────────────────────────────────────────
interface DisposalRow {
  rowId: string
  name: string
  originalCost: number
  accAmort: number
  impairment: number
  disposalType: string
  disposalIncome: number
  approvalDoc: string
  disposalDate: string
  conclusion: string
}

const rows = ref<DisposalRow[]>([])
const auditConclusion = ref('')
const showSamplingDialog = ref(false)

const STORAGE_KEY = 'I1-6-rows'
const CONCLUSION_KEY = 'I1-6-conclusion'

// ─── Computed Totals ──────────────────────────────────────────────────────────
const totalOriginalCost = computed(() => rows.value.reduce((s, r) => s + (r.originalCost || 0), 0))
const totalNetValue = computed(() => rows.value.reduce((s, r) => s + calcNetValue(r.originalCost || 0, r.accAmort || 0, r.impairment || 0), 0))
const totalDisposalIncome = computed(() => rows.value.reduce((s, r) => s + (r.disposalIncome || 0), 0))
const totalGainLoss = computed(() => rows.value.reduce((s, r) => s + getGainLoss(r), 0))

// ─── Formula Helpers ──────────────────────────────────────────────────────────
function getGainLoss(row: DisposalRow): number {
  const netVal = calcNetValue(row.originalCost || 0, row.accAmort || 0, row.impairment || 0)
  return calcDisposalGainLoss(row.disposalIncome || 0, netVal)
}

// ─── Row Operations ───────────────────────────────────────────────────────────
function createRow(name: string): DisposalRow {
  return {
    rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    originalCost: 0,
    accAmort: 0,
    impairment: 0,
    disposalType: '',
    disposalIncome: 0,
    approvalDoc: '',
    disposalDate: '',
    conclusion: '',
  }
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入无形资产名称', '新增减少项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX专利/商标/软件',
    })
    if (name?.trim()) {
      rows.value.push(createRow(name.trim()))
      handleChange()
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(index: number) {
  rows.value.splice(index, 1)
  handleChange()
}

// ─── Persistence ──────────────────────────────────────────────────────────────
function handleChange() {
  emit('save', STORAGE_KEY, JSON.stringify(rows.value))
}

function saveConclusion() {
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

function loadFromResponses() {
  if (!props.allResponses) return
  const raw = props.allResponses.get(STORAGE_KEY)
  if (raw) {
    try {
      rows.value = JSON.parse(typeof raw === 'string' ? raw : raw.value || '[]')
    } catch { rows.value = [] }
  }
  const concRaw = props.allResponses.get(CONCLUSION_KEY)
  if (concRaw) {
    auditConclusion.value = typeof concRaw === 'string' ? concRaw : concRaw.value || ''
  }
}

// ─── Sampling Callback ────────────────────────────────────────────────────────
function onSampleFilled(samples: any[]) {
  showSamplingDialog.value = false
  if (!samples?.length) return
  for (const s of samples) {
    const row = createRow(s.summary || s.description || '处置项')
    row.originalCost = s.amount ?? 0
    row.disposalIncome = s.disposalIncome ?? 0
    rows.value.push(row)
  }
  handleChange()
}

// ─── AI Generate ──────────────────────────────────────────────────────────────
async function handleAiGenerate(section: string) {
  try {
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: '请根据减少明细检查结果生成审计结论',
      context: `本期减少${rows.value.length}项无形资产，原值合计${totalOriginalCost.value}，处置损益合计${totalGainLoss.value}`,
      existingContent: auditConclusion.value,
    })
    if (resp.data?.data?.content) {
      auditConclusion.value = resp.data.data.content
      saveConclusion()
    }
  } catch { /* silent */ }
}

// ─── Review ───────────────────────────────────────────────────────────────────
function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── Format ───────────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  loadFromResponses()
})

watch(() => props.allResponses, () => {
  loadFromResponses()
}, { deep: true })
</script>

<style scoped>
.i1-tab-disposal-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #6b5900;
}
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; align-items: center; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.error-amount { color: var(--el-color-danger); }
.summary-bar {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: center;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
}
.note-card { margin-top: 12px; }
.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
