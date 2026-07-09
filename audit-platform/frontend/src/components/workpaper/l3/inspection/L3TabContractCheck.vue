<template>
  <div class="l3-tab-contract-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="l3-contract-header">
      <div class="l3-contract-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="l3-contract-title">L3-6 贷款合同检查</h3>
      </div>
      <div class="l3-contract-header-right">
        <!-- 导入导出 -->
        <el-dropdown trigger="click" :disabled="isReadonly" @command="handleImportExport">
          <el-button size="small" :disabled="isReadonly">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <!-- AI辅助 -->
        <el-button size="small" @click="$emit('ai-assist', 'L3-6')">AI</el-button>
        <!-- 复核 -->
        <el-button size="small" @click="$emit('open-review', 'L3-6')">复核</el-button>
        <!-- 新增合同行 -->
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
    <div class="l3-methodology-context">
      <div class="l3-methodology-text">
        <strong>合同检查目标：</strong>
        逐笔核对长期借款合同要素，确保合同号/金额/利率/期限/担保与账面一致。
        32列按4区段Tab切换（基础要素/利率条款/担保条款/违约条款），行同步。
        可上传合同扫描件OCR自动识别填充。关注长期借款特有的还款计划和提前还款条件。
      </div>
    </div>

    <!-- ═══ 区段Tab切换 ═══ -->
    <div class="l3-segment-bar">
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
        <el-table-column prop="borrower" label="借款单位" min-width="130">
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

      <!-- ═══ 区段2：利率条款（5列） ═══ -->
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
        <el-table-column prop="repaymentPlan" label="还款方式" min-width="120">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.repaymentPlan"
              size="small"
              placeholder="选择"
              @change="(val: string) => updateField($index, 'repaymentPlan', val)"
            >
              <el-option label="到期一次还本" value="到期一次还本" />
              <el-option label="等额本息" value="等额本息" />
              <el-option label="等额本金" value="等额本金" />
              <el-option label="分期还本" value="分期还本" />
            </el-select>
            <span v-else>{{ row.repaymentPlan || '-' }}</span>
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

      <!-- ═══ 区段4：违约条款（4列） ═══ -->
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
        <el-table-column prop="financialCovenant" label="财务约束条款" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.financialCovenant"
              size="small"
              @change="(val: string) => updateField($index, 'financialCovenant', val)"
            />
            <span v-else>{{ row.financialCovenant || '-' }}</span>
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

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>区段切换</strong>：32列按4区段切换（基础要素/利率条款/担保条款/违约条款），行同步</li>
        <li><strong>OCR识别</strong>：点击📎上传合同扫描件(PDF/图片)，OCR自动识别合同要素并弹窗确认后填入</li>
        <li><strong>动态行</strong>：点击"新增合同"输入合同号后创建新行</li>
        <li><strong>长期借款特有</strong>：关注还款方式/财务约束条款/提前还款条件</li>
        <li><strong>检查要点</strong>：核对合同金额/利率/期限与账面一致；确认担保有效；关注违约条款</li>
      </ul>
    </details>

    <!-- 隐藏文件选择（导入用） -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabContractCheck — L3-6 贷款合同检查（区段Tab + OCR）
 *
 * 32列宽表按4区段Tab切换（基础要素/利率条款/担保条款/违约条款），行同步。
 * - 区段1「基础要素」8列：合同号/借款单位/贷款银行/金额/起始日/到期日/期限/币种
 * - 区段2「利率条款」5列：利率类型/年利率/调整方式/计息基准/还款方式
 * - 区段3「担保条款」4列：担保方式/担保人/抵质押物/担保金额
 * - 区段4「违约条款」4列：提前还款条件/逾期罚则/交叉违约/财务约束条款
 * - 行级OCR：📎列上传合同→POST contract-ocr→ElMessageBox确认→merge
 * - 动态行：ElMessageBox.prompt 输入合同号后新增
 * - 导入导出三级 sheet='L3-6'
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.6
 * Requirements: 8.1-8.2
 */
import { inject, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useL3ImportExport } from '@/components/workpaper/composables/useL3ImportExport'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'ai-assist', section: string): void
  (e: 'open-review', section: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── Import/Export ───────────────────────────────────────────────────────────

const wpIdRef = ref(props.wpId)
const projectIdRef = ref(props.projectId)
const { exportTemplate, exportData, importData } = useL3ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

const fileInputRef = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate': exportTemplate('L3-6'); break
    case 'exportData': exportData('L3-6'); break
    case 'importData': fileInputRef.value?.click(); break
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await importData(file, 'L3-6')
  if (result?.success) {
    await formData.loadData()
    loadFromFormData()
  }
  input.value = ''
}

// ─── Segment definitions ─────────────────────────────────────────────────────

interface SegmentDef {
  key: string
  label: string
  fields: string[]
}

const CONTRACT_SEGMENTS: SegmentDef[] = [
  { key: 'basic', label: '基础要素', fields: ['contractNo', 'borrower', 'lender', 'loanAmount', 'startDate', 'endDate', 'term', 'currency'] },
  { key: 'rate', label: '利率条款', fields: ['rateType', 'annualRate', 'adjustMethod', 'interestBasis', 'repaymentPlan'] },
  { key: 'guarantee', label: '担保条款', fields: ['guaranteeType', 'guarantor', 'pledgeAsset', 'guaranteeAmount'] },
  { key: 'default', label: '违约条款', fields: ['prepaymentCondition', 'overduePenalty', 'crossDefault', 'financialCovenant'] },
]

const activeSegment = ref('basic')

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
  repaymentPlan: string
  guaranteeType: string
  guarantor: string
  pledgeAsset: string
  guaranteeAmount: number
  prepaymentCondition: string
  overduePenalty: string
  crossDefault: string
  financialCovenant: string
}

const ALL_FIELDS: (keyof ContractRow)[] = [
  'contractNo', 'borrower', 'lender', 'loanAmount', 'startDate', 'endDate', 'term', 'currency',
  'rateType', 'annualRate', 'adjustMethod', 'interestBasis', 'repaymentPlan',
  'guaranteeType', 'guarantor', 'pledgeAsset', 'guaranteeAmount',
  'prepaymentCondition', 'overduePenalty', 'crossDefault', 'financialCovenant',
]

function createEmptyRow(contractNo = ''): ContractRow {
  return {
    contractNo, borrower: '', lender: '', loanAmount: 0,
    startDate: '', endDate: '', term: 0, currency: 'CNY',
    rateType: '', annualRate: 0, adjustMethod: '', interestBasis: '365天', repaymentPlan: '',
    guaranteeType: '', guarantor: '', pledgeAsset: '', guaranteeAmount: 0,
    prepaymentCondition: '', overduePenalty: '', crossDefault: '', financialCovenant: '',
  }
}

// ─── State ───────────────────────────────────────────────────────────────────

const contractRows = ref<ContractRow[]>([])

// ─── Load from checklist_responses ───────────────────────────────────────────

function loadFromFormData(): void {
  const pattern = /^L3-con-(\d+)-(\w+)$/
  const rows: ContractRow[] = []

  const map = formData.allResponses.value
  for (const [itemId, resp] of map.entries()) {
    const match = itemId.match(pattern)
    if (!match) continue
    const idx = parseInt(match[1], 10)
    const field = match[2] as keyof ContractRow

    while (rows.length < idx) rows.push(createEmptyRow())
    if (ALL_FIELDS.includes(field)) {
      const val = resp.remark || resp.conclusion || ''
      const numVal = parseFloat(val)
      ;(rows[idx - 1] as any)[field] = isNaN(numVal) ? val : numVal
    }
  }

  contractRows.value = rows.length > 0 ? rows : []
}

onMounted(() => {
  loadFromFormData()
})

// ─── Persistence ─────────────────────────────────────────────────────────────

function saveRow(index: number): void {
  const row = contractRows.value[index]
  if (!row) return
  const n = index + 1
  const items: Array<{ itemId: string; data: { remark: string | null } }> = []
  for (const field of ALL_FIELDS) {
    const val = row[field]
    const strVal = val != null && val !== '' && val !== 0 ? String(val) : null
    items.push({ itemId: `L3-con-${n}-${field}`, data: { remark: strVal } })
  }
  formData.saveBatch(items)
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
        inputPlaceholder: '如：2024年长借字第001号',
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
  const items: Array<{ itemId: string; data: { remark: string | null } }> = []
  for (let i = 0; i < contractRows.value.length; i++) {
    const row = contractRows.value[i]
    const n = i + 1
    for (const field of ALL_FIELDS) {
      const val = row[field]
      const strVal = val != null && val !== '' && val !== 0 ? String(val) : null
      items.push({ itemId: `L3-con-${n}-${field}`, data: { remark: strVal } })
    }
  }
  formData.saveBatch(items)
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
      contract_no: '合同号', borrower: '借款单位', lender: '贷款银行',
      amount: '贷款金额', start_date: '起始日', end_date: '到期日',
      rate: '年利率', guarantee_type: '担保方式', guarantor: '担保人',
      pledge_asset: '抵质押物', term: '期限', repayment_plan: '还款方式',
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
    if (fields.term) row.term = parseInt(fields.term, 10) || row.term
    if (fields.repayment_plan) row.repaymentPlan = fields.repayment_plan
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
.l3-tab-contract-check {
  padding: 12px;
  font-size: 13px;
}

/* ─── 头部 ─── */
.l3-contract-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.l3-contract-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.l3-contract-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.l3-contract-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色） ─── */
.l3-methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.l3-methodology-text strong {
  color: #b88230;
}

/* ─── 区段切换栏 ─── */
.l3-segment-bar {
  margin-bottom: 12px;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
