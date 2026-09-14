<template>
  <div class="l1-tab-contract-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="contract-header">
      <div class="contract-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="contract-title">L1-6 贷款合同检查</h3>
      </div>
      <div class="contract-header-right">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增合同
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>合同检查目标：</strong>
        逐笔核对短期借款合同要素，确保合同号/金额/利率/期限/担保与账面一致。
        32列按4区段Tab切换（基础要素/利率条款/担保条款/违约条款），行同步。
        可上传合同扫描件OCR自动识别填充。
      </div>
    </div>

    <!-- ═══ 区段Tab切换 + 列设置 ═══ -->
    <div class="segment-bar">
      <el-radio-group
        :model-value="activeSegment"
        size="small"
        @change="(val: string) => activeSegment = val"
      >
        <el-radio-button
          v-for="seg in CONTRACT_SEGMENTS"
          :key="seg.key"
          :value="seg.key"
        >
          {{ seg.label }}（{{ seg.fields.length }}列）
        </el-radio-button>
      </el-radio-group>
      <el-popover placement="bottom-end" :width="220" trigger="click">
        <template #reference>
          <el-button size="small" style="margin-left:8px">⚙ 列设置</el-button>
        </template>
        <div class="col-prefs">
          <div class="col-prefs-title">当前区段列显隐</div>
          <template v-for="col in currentSegCols" :key="col.key">
            <el-checkbox v-model="col.visible" size="small" @change="persistContractColPrefs">{{ col.label }}</el-checkbox>
          </template>
          <el-divider style="margin:6px 0" />
          <el-button size="small" link @click="resetContractColPrefs">重置默认</el-button>
        </div>
      </el-popover>
    </div>

    <!-- ═══ 合同检查表主体 ═══ -->
    <el-table
      :data="contractRows"
      border
      size="small"
      style="width: 100%"
      max-height="520"
    >
      <!-- 序号固定列 -->
      <el-table-column type="index" label="#" width="42" fixed />

      <!-- 📎 OCR列 -->
      <el-table-column label="📎" width="50" fixed align="center">
        <template #default="{ $index }">
          <el-upload
            v-if="!isReadonly"
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.jpg,.jpeg,.png"
            @change="(uploadFile: any) => handleOcrUpload(uploadFile, $index)"
          >
            <el-button text size="small" title="上传合同OCR识别">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>

      <!-- ═══ 区段1：基础要素（8列） ═══ -->
      <template v-if="activeSegment === 'basic'">
        <el-table-column prop="contractNo" label="合同号" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.contractNo"
              size="small"
              @change="(val: string) => updateField($index, 'contractNo', val)"
            />
            <span v-else>{{ row.contractNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="borrower" label="贷款单位" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.borrower"
              size="small"
              @change="(val: string) => updateField($index, 'borrower', val)"
            />
            <span v-else>{{ row.borrower || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lender" label="贷款银行" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.lender"
              size="small"
              @change="(val: string) => updateField($index, 'lender', val)"
            />
            <span v-else>{{ row.lender || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="loanAmount" label="贷款金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.loanAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateField($index, 'loanAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.loanAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="startDate" label="起始日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.startDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="(val: string) => updateField($index, 'startDate', val || '')"
            />
            <span v-else>{{ row.startDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="endDate" label="到期日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.endDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="(val: string) => updateField($index, 'endDate', val || '')"
            />
            <span v-else>{{ row.endDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="term" label="期限(月)" min-width="80" align="center">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.term"
              :controls="false"
              :min="0"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateField($index, 'term', val ?? 0)"
            />
            <span v-else>{{ row.term || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currency" label="币种" min-width="80">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.currency"
              size="small"
              @change="(val: string) => updateField($index, 'currency', val)"
            >
              <el-option label="CNY" value="CNY" />
              <el-option label="USD" value="USD" />
              <el-option label="EUR" value="EUR" />
              <el-option label="HKD" value="HKD" />
            </el-select>
            <span v-else>{{ row.currency || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2：利率条款（4列） ═══ -->
      <template v-if="activeSegment === 'rate'">
        <el-table-column prop="rateType" label="利率类型" min-width="110">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.rateType"
              size="small"
              placeholder="选择"
              @change="(val: string) => updateField($index, 'rateType', val)"
            >
              <el-option label="固定" value="固定" />
              <el-option label="浮动" value="浮动" />
              <el-option label="LPR加点" value="LPR加点" />
            </el-select>
            <span v-else>{{ row.rateType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualRate" label="年利率(%)" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.annualRate"
              :controls="false"
              :precision="4"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateField($index, 'annualRate', val ?? 0)"
            />
            <span v-else>{{ row.annualRate ? (row.annualRate * 100).toFixed(2) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="adjustMethod" label="调整方式" min-width="120">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.adjustMethod"
              size="small"
              placeholder="选择"
              @change="(val: string) => updateField($index, 'adjustMethod', val)"
            >
              <el-option label="一年一调" value="一年一调" />
              <el-option label="按季调整" value="按季调整" />
              <el-option label="不调整" value="不调整" />
              <el-option label="LPR同步" value="LPR同步" />
            </el-select>
            <span v-else>{{ row.adjustMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="interestBasis" label="计息基准" min-width="100">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.interestBasis"
              size="small"
              placeholder="选择"
              @change="(val: string) => updateField($index, 'interestBasis', val)"
            >
              <el-option label="365天" value="365天" />
              <el-option label="360天" value="360天" />
              <el-option label="实际天数" value="实际天数" />
            </el-select>
            <span v-else>{{ row.interestBasis || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段3：担保条款（4列） ═══ -->
      <template v-if="activeSegment === 'guarantee'">
        <el-table-column prop="guaranteeType" label="担保方式" min-width="100">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.guaranteeType"
              size="small"
              placeholder="选择"
              @change="(val: string) => updateField($index, 'guaranteeType', val)"
            >
              <el-option label="信用" value="信用" />
              <el-option label="保证" value="保证" />
              <el-option label="抵押" value="抵押" />
              <el-option label="质押" value="质押" />
              <el-option label="组合" value="组合" />
            </el-select>
            <span v-else>{{ row.guaranteeType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="guarantor" label="担保人/物" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.guarantor"
              size="small"
              @change="(val: string) => updateField($index, 'guarantor', val)"
            />
            <span v-else>{{ row.guarantor || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pledgeAsset" label="抵质押物" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.pledgeAsset"
              size="small"
              @change="(val: string) => updateField($index, 'pledgeAsset', val)"
            />
            <span v-else>{{ row.pledgeAsset || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="guaranteeAmount" label="担保金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.guaranteeAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateField($index, 'guaranteeAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.guaranteeAmount) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段4：违约条款（3列） ═══ -->
      <template v-if="activeSegment === 'default'">
        <el-table-column prop="prepaymentCondition" label="提前还款条件" min-width="180">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.prepaymentCondition"
              size="small"
              @change="(val: string) => updateField($index, 'prepaymentCondition', val)"
            />
            <span v-else>{{ row.prepaymentCondition || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="overduePenalty" label="逾期罚则" min-width="180">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.overduePenalty"
              size="small"
              @change="(val: string) => updateField($index, 'overduePenalty', val)"
            />
            <span v-else>{{ row.overduePenalty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="crossDefault" label="交叉违约" min-width="180">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.crossDefault"
              size="small"
              @change="(val: string) => updateField($index, 'crossDefault', val)"
            />
            <span v-else>{{ row.crossDefault || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right" align="center">
        <template #default="{ $index }">
          <el-button text type="danger" size="small" @click="handleRemoveRow($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 审计说明 ═══ -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计说明</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :loading="aiNoteLoading"
            @click="handleAiNote"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="note"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="核对合同金额/利率/期限与账面是否一致；确认担保有效性；如存在违反债务协议约定或条款情况，确定其影响及额外执行的程序（书面豁免/补签合同等），并评估对持续经营的影响。"
        @input="onNoteInput"
      />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :loading="aiConclusionLoading"
            @click="handleAiConclusion"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="参考：A.合同要素与账面相符，未见异常。 B.存在需关注事项（如违约/条款不一致）。 C.无法获取充分证据，不可确认。"
        @input="onConclusionInput"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>区段切换</strong>：32列按4区段切换（基础要素/利率条款/担保条款/违约条款），行同步</li>
        <li><strong>OCR识别</strong>：点击📎上传合同扫描件(PDF/图片)，OCR自动识别合同要素并弹窗确认后填入</li>
        <li><strong>动态行</strong>：点击"新增合同"输入合同号后创建新行</li>
        <li><strong>检查要点</strong>：核对合同金额/利率/期限与账面一致；确认担保有效；关注违约条款</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabContractCheck — L1-6 贷款合同检查（32列区段Tab + OCR）
 *
 * 32列宽表按4区段Tab切换（基础要素/利率条款/担保条款/违约条款），行同步。
 * - 区段1「基础要素」8列：合同号/贷款单位/贷款银行/金额/起始日/到期日/期限/币种
 * - 区段2「利率条款」4列：利率类型/年利率/调整方式/计息基准
 * - 区段3「担保条款」4列：担保方式/担保人/抵质押物/担保金额
 * - 区段4「违约条款」3列：提前还款条件/逾期罚则/交叉违约
 * - 行级OCR：📎列上传合同→POST contract-ocr→ElMessageBox确认→merge
 * - 动态行：ElMessageBox.prompt 输入合同号后新增
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.6
 * Requirements: 7.1-7.2
 */
import { inject, ref, reactive, computed, onMounted, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { useL1FormData, ChecklistItem } from '@/composables/useL1FormData'
import { useL1AiNote } from '@/composables/useL1AiNote'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── Segment definitions ─────────────────────────────────────────────────────

interface SegmentDef {
  key: string
  label: string
  fields: string[]
}

const CONTRACT_SEGMENTS: SegmentDef[] = [
  { key: 'basic', label: '基础要素', fields: ['contractNo', 'borrower', 'lender', 'loanAmount', 'startDate', 'endDate', 'term', 'currency'] },
  { key: 'rate', label: '利率条款', fields: ['rateType', 'annualRate', 'adjustMethod', 'interestBasis'] },
  { key: 'guarantee', label: '担保条款', fields: ['guaranteeType', 'guarantor', 'pledgeAsset', 'guaranteeAmount'] },
  { key: 'default', label: '违约条款', fields: ['prepaymentCondition', 'overduePenalty', 'crossDefault'] },
]

const activeSegment = ref('basic')

// ─── 列设置（⚙ popover）────────────────────────────────────────────────────
const CONTRACT_COL_PREFS_KEY = 'l1-6-column-prefs'
interface ColPref { key: string; label: string; visible: boolean }
/** 字段中文标签（避免 popover 显示英文字段名） */
const FIELD_LABELS: Record<string, string> = {
  contractNo: '合同号', borrower: '贷款单位', lender: '贷款银行', loanAmount: '贷款金额',
  startDate: '起始日', endDate: '到期日', term: '期限(月)', currency: '币种',
  rateType: '利率类型', annualRate: '年利率', adjustMethod: '调整方式', interestBasis: '计息基准',
  guaranteeType: '担保方式', guarantor: '担保人/物', pledgeAsset: '抵质押物', guaranteeAmount: '担保金额',
  prepaymentCondition: '提前还款条件', overduePenalty: '逾期罚则', crossDefault: '交叉违约',
}
const contractColDefs: Record<string, ColPref[]> = reactive({
  basic: CONTRACT_SEGMENTS[0].fields.map(f => ({ key: f, label: FIELD_LABELS[f] || f, visible: true })),
  rate: CONTRACT_SEGMENTS[1].fields.map(f => ({ key: f, label: FIELD_LABELS[f] || f, visible: true })),
  guarantee: CONTRACT_SEGMENTS[2].fields.map(f => ({ key: f, label: FIELD_LABELS[f] || f, visible: true })),
  default: CONTRACT_SEGMENTS[3].fields.map(f => ({ key: f, label: FIELD_LABELS[f] || f, visible: true })),
})
const currentSegCols = computed(() => contractColDefs[activeSegment.value] || [])
function persistContractColPrefs(): void {
  try { localStorage.setItem(CONTRACT_COL_PREFS_KEY, JSON.stringify(Object.fromEntries(Object.entries(contractColDefs).map(([k, v]) => [k, v.map(c => ({ key: c.key, visible: c.visible }))])))) } catch { /* */ }
}
function resetContractColPrefs(): void {
  for (const cols of Object.values(contractColDefs)) cols.forEach(c => { c.visible = true })
  persistContractColPrefs()
}
;(function loadContractColPrefs() {
  try {
    const saved = localStorage.getItem(CONTRACT_COL_PREFS_KEY)
    if (!saved) return
    const data = JSON.parse(saved)
    for (const [seg, prefs] of Object.entries(data as Record<string, Array<{ key: string; visible: boolean }>>)) {
      const target = contractColDefs[seg]
      if (!target) continue
      for (const p of prefs) { const col = target.find(c => c.key === p.key); if (col) col.visible = p.visible }
    }
  } catch { /* */ }
})()

// ─── Contract row type ───────────────────────────────────────────────────────

interface ContractRow {
  contractNo: string
  borrower: string
  lender: string
  loanAmount: number
  startDate: string
  endDate: string
  term: number
  currency: string
  rateType: string
  annualRate: number
  adjustMethod: string
  interestBasis: string
  guaranteeType: string
  guarantor: string
  pledgeAsset: string
  guaranteeAmount: number
  prepaymentCondition: string
  overduePenalty: string
  crossDefault: string
}

const ALL_FIELDS: (keyof ContractRow)[] = [
  'contractNo', 'borrower', 'lender', 'loanAmount', 'startDate', 'endDate', 'term', 'currency',
  'rateType', 'annualRate', 'adjustMethod', 'interestBasis',
  'guaranteeType', 'guarantor', 'pledgeAsset', 'guaranteeAmount',
  'prepaymentCondition', 'overduePenalty', 'crossDefault',
]

function createEmptyRow(contractNo = ''): ContractRow {
  return {
    contractNo, borrower: '', lender: '', loanAmount: 0,
    startDate: '', endDate: '', term: 0, currency: 'CNY',
    rateType: '', annualRate: 0, adjustMethod: '', interestBasis: '365天',
    guaranteeType: '', guarantor: '', pledgeAsset: '', guaranteeAmount: 0,
    prepaymentCondition: '', overduePenalty: '', crossDefault: '',
  }
}

// ─── State ───────────────────────────────────────────────────────────────────

const contractRows = ref<ContractRow[]>([])

// ─── Load from checklist_responses ───────────────────────────────────────────

function loadFromFormData(): void {
  // Parse L1-con-{n}-{field} items
  // 🔴 必须用 getItemsByPrefix 从已加载的原始 responses 恢复，
  //    不能用 serializeAll()（仅含结构化 sheet 字段，不含 L1-con-* → 刷新后合同数据丢失）。
  const pattern = /^L1-con-(\d+)-(\w+)$/
  const rows: ContractRow[] = []

  try {
    const allItems = formData.getItemsByPrefix('L1-con-')
    for (const item of allItems) {
      const match = item.item_id.match(pattern)
      if (!match) continue
      const idx = parseInt(match[1], 10)
      const field = match[2] as keyof ContractRow

      while (rows.length < idx) rows.push(createEmptyRow())
      if (ALL_FIELDS.includes(field)) {
        const val = item.remark || item.conclusion || ''
        const numVal = parseFloat(val)
        ;(rows[idx - 1] as any)[field] = isNaN(numVal) ? val : numVal
      }
    }
  } catch {
    // Empty state on first load
  }

  contractRows.value = rows.length > 0 ? rows : []
}

// ─── 审计说明 + 审计结论（AI 辅助） ─────────────────────────────────────────

const {
  note, conclusion, aiNoteLoading, aiConclusionLoading,
  load: loadNote, onNoteInput, onConclusionInput, generateNote, generateConclusion,
} = useL1AiNote(formData, toRef(props, 'wpId'), 'con', toRef(props, 'isReadonly'))

function _aiContext() {
  return {
    合同笔数: contractRows.value.length,
    合同金额合计: contractRows.value.reduce((s, r) => s + (r.loanAmount || 0), 0),
  }
}
function handleAiNote() {
  generateNote('请基于贷款合同检查情况撰写审计说明，覆盖合同要素核对、担保有效性、违约条款影响。', _aiContext())
}
function handleAiConclusion() {
  generateConclusion('请基于贷款合同检查情况生成审计结论。', _aiContext())
}

onMounted(() => {
  loadFromFormData()
  loadNote()
})

// ─── Persistence ─────────────────────────────────────────────────────────────

function saveRow(index: number): void {
  const row = contractRows.value[index]
  if (!row) return
  const n = index + 1
  const items: ChecklistItem[] = ALL_FIELDS.map(field => {
    const val = row[field]
    const strVal = val != null && val !== '' && val !== 0 ? String(val) : null
    return { item_id: `L1-con-${n}-${field}`, conclusion: null, remark: strVal }
  })
  formData.debounceSave(items)
}

// ─── Field update ────────────────────────────────────────────────────────────

function updateField(index: number, field: keyof ContractRow, value: string | number): void {
  const row = contractRows.value[index]
  if (!row) return
  ;(row as any)[field] = value
  saveRow(index)
}

// ─── Dynamic row add/remove ──────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入合同号',
      '新增贷款合同',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：2024年信字第001号',
        inputValidator: (val: string) => {
          if (!val?.trim()) return '合同号不能为空'
          return true
        },
      },
    )
    if (value?.trim()) {
      contractRows.value.push(createEmptyRow(value.trim()))
      saveRow(contractRows.value.length - 1)
    }
  } catch {
    // User cancelled
  }
}

function handleRemoveRow(index: number): void {
  contractRows.value.splice(index, 1)
  // Re-save all rows to update indices
  const items: ChecklistItem[] = []
  for (let i = 0; i < contractRows.value.length; i++) {
    const row = contractRows.value[i]
    const n = i + 1
    for (const field of ALL_FIELDS) {
      const val = row[field]
      const strVal = val != null && val !== '' && val !== 0 ? String(val) : null
      items.push({ item_id: `L1-con-${n}-${field}`, conclusion: null, remark: strVal })
    }
  }
  formData.saveImmediate(items)
}

// ─── OCR Upload ──────────────────────────────────────────────────────────────

async function handleOcrUpload(uploadFile: any, index: number): Promise<void> {
  const file = uploadFile?.raw || uploadFile
  if (!file) return

  const fd = new FormData()
  fd.append('file', file)

  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return
    }

    // Build confirmation message
    const lines: string[] = []
    const fieldLabels: Record<string, string> = {
      contract_no: '合同号', borrower: '贷款单位', lender: '贷款银行',
      amount: '贷款金额', start_date: '起始日', end_date: '到期日',
      rate: '年利率', guarantee_type: '担保方式', guarantor: '担保人',
      pledge_asset: '抵质押物',
    }
    for (const [key, val] of Object.entries(fields)) {
      const label = fieldLabels[key] || key
      lines.push(`${label}：${val}`)
    }

    await ElMessageBox.confirm(
      `OCR识别结果：\n\n${lines.join('\n')}\n\n确认填入当前行？`,
      'OCR识别确认',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )

    // Merge OCR results to row
    const row = contractRows.value[index]
    if (!row) return
    if (fields.contract_no) row.contractNo = fields.contract_no
    if (fields.borrower) row.borrower = fields.borrower
    if (fields.lender) row.lender = fields.lender
    if (fields.amount) row.loanAmount = parseFloat(fields.amount) || row.loanAmount
    if (fields.start_date) row.startDate = fields.start_date
    if (fields.end_date) row.endDate = fields.end_date
    if (fields.rate) row.annualRate = parseFloat(fields.rate) || row.annualRate
    if (fields.guarantee_type) row.guaranteeType = fields.guarantee_type
    if (fields.guarantor) row.guarantor = fields.guarantor
    if (fields.pledge_asset) row.pledgeAsset = fields.pledge_asset
    saveRow(index)
    ElMessage.success('OCR识别结果已填入')
  } catch (err: any) {
    if (err !== 'cancel' && err?.toString() !== 'cancel') {
      ElMessage.error('OCR识别失败，请重试')
    }
  }
}

// ─── Utils ───────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l1-tab-contract-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.contract-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.contract-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.contract-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.contract-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 区段切换栏 ─── */
.segment-bar {
  margin-bottom: 12px;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
.opinion-card { margin-top: 16px; }
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}
.opinion-card :deep(.el-textarea__inner) { font-size: var(--wp-font-size, 13px); }
.col-prefs { max-height: 280px; overflow-y: auto; }
.col-prefs-title { font-weight: 600; margin-bottom: 6px; font-size: 13px; }
.col-prefs :deep(.el-checkbox) { display: block; margin-bottom: 3px; }
</style>
