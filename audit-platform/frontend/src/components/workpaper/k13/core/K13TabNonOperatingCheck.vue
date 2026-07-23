<template>
  <div class="k13-tab-non-operating-check">
    <!-- 审计目标（认定，源模板 K13-4 测试目标） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>所有应当记录的营业外支出均已记录，相关披露均已包括；</li>
        <li><b>准确性：</b>与营业外支出有关的金额及其他数据已恰当记录、计量、描述；</li>
        <li><b>发生与分类：</b>记录的支出确已发生且与本期相关，分类恰当（与日常活动无关），关注捐赠/罚款税前扣除性。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K13-4 营业外支出检查表（凭证级）</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" text :loading="aiLoading" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger section-id="K13-4-check" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 测试原因（源模板 C8） ═══ -->
    <div class="test-reason-bar">
      <span class="test-reason-label">测试原因：</span>
      <el-checkbox-group v-model="testReasons" :disabled="isReadonly" @change="persistCriteria">
        <el-checkbox value="大额" label="大额" />
        <el-checkbox value="关联方" label="关联方" />
        <el-checkbox value="大额交易频繁" label="大额交易频繁" />
        <el-checkbox value="异常" label="异常" />
        <el-checkbox value="其他" label="其他" />
      </el-checkbox-group>
    </div>

    <!-- ═══ 方法论上下文（源模板测试内容说明） ═══ -->
    <div class="methodology-context">
      <p>
        测试内容：1.原始凭证是否齐全；2.记账凭证与原始凭证是否相符；3.账务处理是否正确；
        4.是否记录于恰当的会计期间；5.其他核对事项。支持性文件：付款审批单/支出凭单/银行回单等。
        分类正确性：与日常活动<strong>无关</strong>的损失→6711营业外支出；与日常相关→6602管理费用/6601销售费用。
        税前扣除性：捐赠≤利润12%可扣/罚款滞纳金不可扣/资产损失需备案后扣除，为所得税(L1)提供依据。
        从 K13-2 明细表抽凭核查，异常项红色标记。
      </p>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K13-1" :context-project-id="props.projectId" />
      <GtIndexChip value="K13-2" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
      <GtIndexChip value="L1" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 异常摘要（有异常项时显示） ═══ -->
    <el-alert
      v-if="abnormalCount > 0"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 10px"
    >
      <template #title>⚠️ 发现 {{ abnormalCount }} 项异常</template>
      <template #default>
        <ul class="non-compliance-list">
          <li v-for="item in abnormalItems" :key="item.rowKey">
            {{ item.expenseItem || item.voucherNo || '未命名' }}：{{ item.remark || '标记为异常，未说明原因' }}
          </li>
        </ul>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="danger"
          plain
          style="margin-top:6px"
          @click="pushAbnormalToA13"
        >推送异常至 A13 错报</el-button>
      </template>
    </el-alert>

    <!-- ═══ 凭证检查表（源模板：记账凭证列 + 核对内容1-5 + 索引/异常/备注） ═══ -->
    <el-table
      :data="checkRows"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="480"
      :row-class-name="getRowClassName"
    >
      <el-table-column type="index" label="#" width="42" align="center" fixed />
      <el-table-column prop="expenseItem" label="明细项目" min-width="130" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.expenseItem" size="small" placeholder="明细项目" @change="(v: string) => updateCell(row.rowKey, 'expenseItem', v)" />
          <span v-else>{{ row.expenseItem || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 记账凭证组 -->
      <el-table-column prop="date" label="日期" width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.date" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => updateCell(row.rowKey, 'date', v || '')" />
          <span v-else>{{ row.date || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="voucherNo" label="凭证编号" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateCell(row.rowKey, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="businessContent" label="业务内容" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small" @change="(v: string) => updateCell(row.rowKey, 'businessContent', v)" />
          <span v-else>{{ row.businessContent || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="offsetAccount" label="对方科目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.offsetAccount" size="small" @change="(v: string) => updateCell(row.rowKey, 'offsetAccount', v)" />
          <span v-else>{{ row.offsetAccount || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="offsetSubAccount" label="对方明细科目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.offsetSubAccount" size="small" @change="(v: string) => updateCell(row.rowKey, 'offsetSubAccount', v)" />
          <span v-else>{{ row.offsetSubAccount || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="debitAmount" label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 支持性文件（源模板 H 列） -->
      <el-table-column prop="supportingDoc" label="支持性文件" width="140">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="splitDocs(row.supportingDoc)"
            multiple
            collapse-tags
            size="small"
            placeholder="选择/输入"
            allow-create
            filterable
            default-first-option
            style="width:100%"
            @change="(v: string[]) => updateCell(row.rowKey, 'supportingDoc', joinDocs(v))"
          >
            <el-option v-for="d in SUPPORTING_DOC_OPTIONS" :key="d" :value="d" :label="d" />
          </el-select>
          <span v-else>{{ row.supportingDoc || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 核对内容 1-5（勾选） -->
      <el-table-column
        v-for="(label, i) in CHECK_LABELS"
        :key="i"
        :label="String(i + 1)"
        width="48"
        align="center"
      >
        <template #header>
          <el-tooltip :content="label" placement="top">
            <span style="cursor:help">{{ i + 1 }}</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-checkbox
            :model-value="row.checks[i]"
            :disabled="isReadonly"
            @change="(v: any) => updateCheck(row.rowKey, i, !!v)"
          />
        </template>
      </el-table-column>

      <el-table-column prop="abnormal" label="异常" width="60" align="center">
        <template #default="{ row }">
          <el-checkbox :model-value="row.abnormal" :disabled="isReadonly" @change="(v: any) => updateCell(row.rowKey, 'abnormal', !!v)" />
        </template>
      </el-table-column>
      <!-- 📎 行级OCR列 -->
      <el-table-column label="📎" width="55" align="center">
        <template #default="{ row }">
          <el-button link size="small" :disabled="isReadonly" @click="handleOcrUpload(row.rowKey)">📎</el-button>
          <span v-if="row.ocrAttachment" class="ocr-indicator">✓</span>
        </template>
      </el-table-column>
      <el-table-column prop="indexNo" label="索引号" width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexNo" size="small" @change="(v: string) => updateCell(row.rowKey, 'indexNo', v)" />
          <span v-else>{{ row.indexNo || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注说明" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注/异常说明" @change="(v: string) => updateCell(row.rowKey, 'remark', v)" />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="removeRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增检查项</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭</el-button>
    </div>

    <!-- ═══ 检查比例表（源模板：合计/本期发生额/检查比例） ═══ -->
    <el-card shadow="never" class="ratio-card">
      <template #header>
        <div class="section-header-mini">
          <span>检查比例</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="pullBookOccurrence">从 K13-1/K13-2 带入本期发生额</el-button>
        </div>
      </template>
      <div class="ratio-grid">
        <div class="ratio-item">
          <span class="ratio-label">检查合计（借方金额）</span>
          <span class="ratio-value">{{ fmtAmt(checkedTotal) }}</span>
        </div>
        <div class="ratio-item">
          <span class="ratio-label">本期发生额（账面）</span>
          <el-input-number
            v-if="!isReadonly"
            :model-value="bookOccurrence"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 160px"
            @change="(v: number | undefined) => { bookOccurrence = v ?? 0; persistCriteria() }"
          />
          <span v-else class="ratio-value">{{ fmtAmt(bookOccurrence) }}</span>
        </div>
        <div class="ratio-item">
          <span class="ratio-label">检查比例</span>
          <span :class="['ratio-value', { 'ratio-low': ratioLow }]">{{ formatRatio }}</span>
        </div>
        <el-tag v-if="ratioLow" type="warning" size="small">检查比例偏低（&lt;30%），建议扩大样本或说明</el-tag>
      </div>
    </el-card>

    <!-- ═══ 抽凭引擎 Dialog ═══ -->
    <el-dialog
      v-model="showSamplingDialog"
      title="⚡ 抽凭引擎（科目 6711 营业外支出 — 检查表）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="6711"
        phase="final"
        :year="currentYear"
        @filled="handleVoucherFilled"
      />
    </el-dialog>

    <!-- OCR file input (隐藏) -->
    <input ref="ocrFileInput" type="file" accept="image/*,.pdf" style="display:none" @change="handleOcrFileSelected" />

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span>审计说明</span></template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写营业外支出检查过程说明..."
        @blur="(e: FocusEvent) => saveNote((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span>审计结论</span></template>
      <el-input
        :model-value="checkConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写营业外支出分类正确性及税前扣除性检查结论..."
        @blur="(e: FocusEvent) => saveConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>凭证级逐笔检查：记账凭证（日期/凭证号/业务内容/对方科目/对方明细科目/借方金额）+ 核对内容1-5勾选</li>
        <li>核对内容：①原始凭证齐全 ②账记与原始相符 ③账务处理正确 ④会计期间正确 ⑤其他核对事项</li>
        <li>支持性文件：付款审批单/支出凭单/银行回单等，可多选或自定义</li>
        <li>分类正确性：与日常活动<strong>无关</strong>的损失→6711营业外支出；与日常相关→6602管理费用/6601销售费用</li>
        <li>税前扣除性：捐赠≤利润12%可扣/罚款滞纳金不可扣/资产损失需备案后扣除，检查结论为所得税(L1)提供依据</li>
        <li>使用🎲抽凭从 K13-2 明细中抽取样本；检查比例＝检查合计÷本期发生额（账面可从 K13-1/K13-2 带入）</li>
        <li>📎附件列：上传原始证据→OCR识别→确认后填入备注</li>
        <li>异常项勾"异常"红色高亮，汇总显示在表格上方</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabNonOperatingCheck.vue — K13-4 营业外支出检查表（凭证级）
 *
 * 2026-07-23 重建：原实现为自造「13检查项 × 6维度合规矩阵」，与源模板完全不符。
 * 对齐源模板 K13-4 凭证级结构（镜像已重建的 K12-4，适配借方支出科目 6711）：
 *   记账凭证[日期/凭证编号/业务内容/对方科目/对方明细科目/借方金额]
 *   + 支持性文件（付款审批单/支出凭单/银行回单）
 *   + 核对内容 1-5 勾选 + 索引号/是否异常/备注
 *   + 检查比例表（检查合计 / 本期发生额=明细表K13-2!Q16 / 检查比例）
 *
 * 修复：①抽凭 phase 从非法 substantive → final；②year 用 props.year 非硬编码；
 *   ③AI 经 useK13AiText（context 转 dict[str,str]，修 JSON.stringify → 422）。
 * 自包含持久化（无新后端）：K13-4-check-rows / K13-4-criteria / K13-4-note / K13-4-conclusion。
 */
import { ref, computed, defineAsyncComponent, watch } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { generateK13AiText } from '../../composables/useK13AiText'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))
const GtReviewTrigger = defineAsyncComponent(() => import('../../GtReviewTrigger.vue'))
const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  year?: number
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const isReadonly = computed(() => props.isReadonly)

// ─── 源模板五项核对 ──────────────────────────────────────────────────────────
const CHECK_LABELS = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确',
  '是否记录于恰当的会计期间',
  '其他核对事项',
] as const

// ─── 支持性文件选项（源模板 H12） ────────────────────────────────────────────
const SUPPORTING_DOC_OPTIONS = ['付款审批单', '支出凭单', '银行回单', '法院判决书', '行政处罚决定书', '捐赠票据', '资产报废审批单']

// ─── 凭证检查行 ──────────────────────────────────────────────────────────────
interface VoucherRow {
  rowKey: string
  expenseItem: string
  date: string
  voucherNo: string
  businessContent: string
  offsetAccount: string
  offsetSubAccount: string
  debitAmount: number
  supportingDoc: string
  checks: boolean[]
  abnormal: boolean
  indexNo: string
  remark: string
  ocrAttachment: string
}

const ROWS_KEY = 'K13-4-check-rows'
const CRITERIA_KEY = 'K13-4-criteria'
const NOTE_KEY = 'K13-4-note'
const CONCLUSION_KEY = 'K13-4-conclusion'

const checkRows = ref<VoucherRow[]>([])
const bookOccurrence = ref(0)
const testReasons = ref<string[]>([])
const auditNote = ref('')
const checkConclusion = ref('')

// ─── 从 allResponses 恢复数据 ────────────────────────────────────────────────

function restoreFromResponses(): void {
  const responses = props.allResponses
  if (!responses || responses.size === 0) return

  const stored = responses.get(ROWS_KEY)
  if (stored) {
    try {
      const raw = stored.remark ?? stored.conclusion ?? stored
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) checkRows.value = parsed.map(normalizeRow)
    } catch { /* ignore */ }
  }

  const criteria = responses.get(CRITERIA_KEY)
  if (criteria) {
    try {
      const raw = criteria.remark ?? criteria.conclusion ?? criteria
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (parsed && typeof parsed === 'object') {
        bookOccurrence.value = Number(parsed.bookOccurrence || 0)
        if (Array.isArray(parsed.testReasons)) testReasons.value = parsed.testReasons
      }
    } catch { /* ignore */ }
  }

  const noteData = responses.get(NOTE_KEY)
  if (noteData) auditNote.value = noteData.remark || noteData.conclusion || ''

  const conclusionData = responses.get(CONCLUSION_KEY)
  if (conclusionData) checkConclusion.value = conclusionData.remark || conclusionData.conclusion || ''
}

watch(() => props.allResponses, restoreFromResponses, { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────────────

let rowIdCounter = Date.now()

function createRow(overrides?: Partial<VoucherRow>): VoucherRow {
  return {
    rowKey: `ck-${++rowIdCounter}`,
    expenseItem: '',
    date: '',
    voucherNo: '',
    businessContent: '',
    offsetAccount: '',
    offsetSubAccount: '',
    debitAmount: 0,
    supportingDoc: '',
    checks: [false, false, false, false, false],
    abnormal: false,
    indexNo: '',
    remark: '',
    ocrAttachment: '',
    ...overrides,
  }
}

function normalizeRow(r: any): VoucherRow {
  const base = createRow()
  return {
    ...base,
    ...r,
    checks: Array.isArray(r?.checks) && r.checks.length === 5 ? r.checks.map((x: any) => !!x) : [false, false, false, false, false],
    debitAmount: Number(r?.debitAmount ?? r?.amount ?? 0),
    supportingDoc: r?.supportingDoc ?? '',
  }
}

function updateCell(rowKey: string, field: keyof VoucherRow, value: any): void {
  const row = checkRows.value.find(r => r.rowKey === rowKey)
  if (row) {
    ;(row as any)[field] = value
    persistRows()
  }
}

function updateCheck(rowKey: string, idx: number, value: boolean): void {
  const row = checkRows.value.find(r => r.rowKey === rowKey)
  if (row) {
    row.checks[idx] = value
    persistRows()
  }
}

function removeRow(rowKey: string): void {
  checkRows.value = checkRows.value.filter(r => r.rowKey !== rowKey)
  persistRows()
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入明细项目名称', '新增检查项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：非流动资产处置损失/捐赠支出/罚款滞纳金...',
    })
    if (value?.trim()) {
      checkRows.value.push(createRow({ expenseItem: value.trim() }))
      persistRows()
    }
  } catch { /* cancelled */ }
}

// ─── 支持性文件多选 <-> 顿号字符串 ───────────────────────────────────────────
function splitDocs(v: string): string[] {
  return v ? v.split('、').filter(Boolean) : []
}
function joinDocs(v: string[]): string {
  return (v || []).join('、')
}

function persistRows(): void {
  emit('save', ROWS_KEY, JSON.stringify(checkRows.value))
}

function persistCriteria(): void {
  emit('save', CRITERIA_KEY, JSON.stringify({ bookOccurrence: bookOccurrence.value, testReasons: testReasons.value }))
}

function saveNote(val: string): void {
  auditNote.value = val
  emit('save', NOTE_KEY, val)
}

function saveConclusion(val: string): void {
  checkConclusion.value = val
  emit('save', CONCLUSION_KEY, val)
}

// ─── 从 K13-1/K13-2 带入本期发生额（账面基数，源模板 G23=明细表K13-2!Q16） ──

function pullBookOccurrence(): void {
  let base = 0
  // 优先明细表 K13-2 审定合计（对齐源模板 Q16）
  const detailItem = props.allResponses.get('K13-2-subtotal')
  if (detailItem) {
    base = Number(detailItem.remark ?? detailItem.conclusion ?? 0)
  }
  // 回退审定表 K13-1 审定合计
  if (!base) {
    const totalItem = props.allResponses.get('K13-1-audited-total')
    if (totalItem) base = Number(totalItem.remark ?? totalItem.conclusion ?? 0)
  }
  if (!base) {
    const rowsItem = props.allResponses.get('K13-1-rows')
    if (rowsItem) {
      try {
        const raw = rowsItem.remark ?? rowsItem.conclusion ?? rowsItem
        const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
        if (Array.isArray(rows)) {
          base = rows.reduce((s: number, r: any) => s + Number(
            r.audited ?? (Number(r.unadjusted || 0) + Number(r.aje || 0) + Number(r.rje || 0)),
          ), 0)
        }
      } catch { /* ignore */ }
    }
  }
  if (base) {
    bookOccurrence.value = base
    persistCriteria()
    ElMessage.success(`已带入本期发生额 ${fmtAmt(base)}`)
  } else {
    ElMessage.warning('未找到 K13-2 明细合计 / K13-1 审定发生额，请先编制明细表或审定表')
  }
}

// ─── 检查比例 ────────────────────────────────────────────────────────────────

const checkedTotal = computed(() => checkRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))
const checkRatio = computed(() => (bookOccurrence.value > 0 ? checkedTotal.value / bookOccurrence.value : null))
const ratioLow = computed(() => checkRatio.value != null && checkRatio.value < 0.3)
const formatRatio = computed(() => (checkRatio.value == null ? '—' : (checkRatio.value * 100).toFixed(1) + '%'))

// ─── 异常摘要 ────────────────────────────────────────────────────────────────

const abnormalItems = computed(() =>
  checkRows.value.filter(r => r.abnormal || (hasRowData(r) && !r.checks.every(Boolean))),
)
const abnormalCount = computed(() => abnormalItems.value.length)

function hasRowData(r: VoucherRow): boolean {
  return !!(r.voucherNo || r.debitAmount || r.expenseItem)
}

function getRowClassName({ row }: { row: VoucherRow }): string {
  if (row.abnormal) return 'non-compliance-row'
  return ''
}

// ─── 异常凭证 → A13 错报（K9-8 范式） ────────────────────────────────────────

function pushAbnormalToA13(): void {
  const items = abnormalItems.value
  if (items.length === 0) {
    ElMessage.info('暂无异常项')
    return
  }
  eventBus.emit('a13:push-misstatement', {
    wpCode: 'K13',
    accountCode: '6711',
    source: 'K13-4',
    misstatements: items.map(i => ({
      voucherNo: i.voucherNo,
      amount: i.debitAmount,
      description: `${i.expenseItem || i.businessContent || '营业外支出'}：${i.remark || '凭证核对异常'}`,
    })),
    timestamp: Date.now(),
  })
  ElMessage.success(`已推送 ${items.length} 项异常至 A13 错报汇总`)
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── AI辅助（接真实 /ai/generate-text，context 转 str） ───────────────────────

const aiLoading = ref(false)

async function handleAiAssist(): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const context: Record<string, unknown> = {
      科目: '6711 营业外支出检查表（凭证级）',
      检查笔数: checkRows.value.length,
      检查合计: fmtAmt(checkedTotal.value),
      本期发生额: fmtAmt(bookOccurrence.value),
      检查比例: formatRatio.value,
      异常项数: abnormalCount.value,
      异常明细: abnormalItems.value
        .map(i => `${i.expenseItem || i.voucherNo || '—'}：${i.remark || '异常'}`)
        .join('；'),
    }
    const content = await generateK13AiText(props.wpId, {
      prompt: '你是资深审计师。请基于营业外支出凭证级检查结果（记账凭证核对1-5项、检查比例、异常项），就完整性/准确性/发生认定给出检查结论草稿，重点关注分类正确性（与日常活动无关计入6711、相关计入6602/6601）与税前扣除性（捐赠12%限额/罚款滞纳金不可扣/资产损失需备案），供人工确认。',
      section: 'K13-4-conclusion',
      context,
      existingContent: checkConclusion.value,
    })
    if (!content) return
    saveConclusion(content)
  } finally {
    aiLoading.value = false
  }
}

// ─── 抽凭引擎 ────────────────────────────────────────────────────────────────

const showSamplingDialog = ref(false)
// 优先用项目审计年度（props.year），缺失才回退当前年
const currentYear = computed(() => props.year ?? new Date().getFullYear())

function handleVoucherFilled(payload: any): void {
  const vouchers = payload?.samples ?? []
  const existing = new Set(checkRows.value.map(r => r.voucherNo).filter(Boolean))
  for (const v of vouchers) {
    const voucherNo = v.voucherNo || ''
    if (voucherNo && existing.has(voucherNo)) continue
    checkRows.value.push(createRow({
      expenseItem: v.summary || v.businessContent || '抽凭样本',
      date: v.voucherDate || v.date || '',
      voucherNo,
      businessContent: v.summary || v.businessContent || '',
      offsetAccount: v.counterpartAccount || v.offsetAccount || '',
      offsetSubAccount: v.counterpartSubAccount || v.offsetSubAccount || '',
      debitAmount: Number(v.debitAmount ?? v.amount ?? 0),
      abnormal: !!v.abnormal,
      remark: v.selectionReason || v.remark || '',
    }))
  }
  showSamplingDialog.value = false
  if (vouchers.length) {
    persistRows()
    ElMessage.success(`已填入 ${vouchers.length} 笔凭证样本`)
  }
}

// ─── 行级OCR（📎附件列 → POST /d4/contract-ocr → ElMessageBox确认 → merge） ─

const ocrFileInput = ref<HTMLInputElement | null>(null)
let currentOcrRowKey = ''

function handleOcrUpload(rowKey: string): void {
  currentOcrRowKey = rowKey
  ocrFileInput.value?.click()
}

async function handleOcrFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  try {
    const formData = new FormData()
    formData.append('file', file)

    ElMessage.info('正在OCR识别...')
    const res = await http.post('/api/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrData = res.data?.data || res.data || {}
    const ocrText = ocrData.text || ocrData.content || ''

    if (!ocrText) {
      ElMessage.warning('OCR未识别到文字内容')
      return
    }

    await ElMessageBox.confirm(
      `OCR识别结果：\n\n${ocrText.slice(0, 500)}${ocrText.length > 500 ? '...' : ''}`,
      'OCR识别确认',
      { confirmButtonText: '填入备注', cancelButtonText: '取消', type: 'info' },
    )

    const row = checkRows.value.find(r => r.rowKey === currentOcrRowKey)
    if (row) {
      row.remark = row.remark ? `${row.remark}\n[OCR] ${ocrText}` : `[OCR] ${ocrText}`
      row.ocrAttachment = file.name
      persistRows()
      ElMessage.success('OCR内容已填入备注')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('OCR识别失败：' + (err?.response?.data?.detail || err?.message || '未知错误'))
    }
  }
}
</script>

<style scoped>
.k13-tab-non-operating-check { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.test-reason-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.test-reason-label { color: #606266; font-size: 12px; white-space: nowrap; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.non-compliance-list { margin: 4px 0 0; padding-left: 16px; font-size: 12px; }
.ocr-indicator { color: #67c23a; font-size: 11px; margin-left: 2px; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; }

.ratio-card { margin-top: 16px; }
.ratio-card :deep(.el-card__body) { padding: 10px 16px; }
.section-header-mini { display: flex; justify-content: space-between; align-items: center; }
.ratio-grid { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.ratio-item { display: flex; flex-direction: column; gap: 2px; }
.ratio-label { font-size: 12px; color: #909399; }
.ratio-value { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; }
.ratio-value.ratio-low { color: #e6a23c; }

.conclusion-card { margin-top: 16px; }

:deep(.non-compliance-row) { background-color: #fef2f2 !important; }
:deep(.non-compliance-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
