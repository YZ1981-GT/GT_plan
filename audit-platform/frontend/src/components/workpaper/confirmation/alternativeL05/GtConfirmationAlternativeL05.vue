<template>
  <div class="gt-confirmation-alternative-l05">
    <!-- ─── 顶部余额汇总区 ──────────────────────────────────────── -->
    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="card-header">
          <span>余额汇总</span>
        </div>
      </template>
      <el-table :data="[balanceSummary]" border size="small" class="summary-table">
        <el-table-column prop="investmentType" label="函证项目" width="140" />
        <el-table-column prop="openingBalance" label="年初余额" width="120" align="right" />
        <el-table-column prop="debitAmount" label="借方发生额" width="120" align="right" />
        <el-table-column prop="creditAmount" label="贷方发生额" width="120" align="right" />
        <el-table-column prop="closingBalance" label="期末余额" width="120" align="right" />
        <el-table-column prop="currentLoan" label="本期借款金额" width="120" align="right" />
        <el-table-column prop="repaymentCheckRatio" label="期后还款检查比例(%)" width="160" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.repaymentCheckRatio?.toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="mortgageCheckRatio" label="抵质押证据检查比例(%)" width="160" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.mortgageCheckRatio?.toFixed(2) }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ─── 多公司 Master-Detail el-tabs ───────────────────────── -->
    <div class="company-tabs-wrapper">
      <el-tabs
        v-model="selectedCompanyId"
        type="card"
        closable
        @tab-remove="handleRemoveCompany"
      >
        <el-tab-pane
          v-for="company in data.companies.value"
          :key="company._company_id"
          :label="company.entity_name || '未命名'"
          :name="company._company_id"
        />
      </el-tabs>
      <div class="tabs-actions">
        <el-button size="small" type="primary" :icon="Plus" @click="handleAddCompany">新增公司</el-button>
        <el-button size="small" @click="handleImportFromSummary">从L0-1导入未回函</el-button>
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <el-dropdown v-if="!readonly" trigger="click" @command="handleImportExportCmd">
          <el-button size="small">导入导出▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- ─── Detail: 选中公司的内容 ─────────────────────────────── -->
    <template v-if="currentCompany">
      <!-- 抽样参数区 -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="card-header"><span>抽样参数</span></div>
        </template>
        <el-form label-position="top" size="small">
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="测试范围">
                <el-input v-model="currentCompany.sampling!.test_scope" type="textarea" :autosize="{ minRows: 2 }" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="特定样本">
                <el-input v-model="currentCompany.sampling!.specific_samples" type="textarea" :autosize="{ minRows: 2 }" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="抽样总体">
                <el-input v-model="currentCompany.sampling!.sampling_population" type="textarea" :autosize="{ minRows: 2 }" :disabled="readonly" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="确定样本量">
                <el-input v-model="currentCompany.sampling!.sample_size" type="textarea" :autosize="{ minRows: 2 }" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="抽样方法">
                <el-input v-model="currentCompany.sampling!.sampling_method" type="textarea" :autosize="{ minRows: 2 }" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="抽样过程">
                <el-input v-model="currentCompany.sampling!.sampling_process" type="textarea" :autosize="{ minRows: 2 }" :disabled="readonly" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </el-card>

      <!-- 期初余额一致性核对（源模板 L0-5 第3项；confirmation-alternative-structure-alignment 决策 2） -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="card-header">
            <span>期初余额一致性核对（检查期初余额是否与上期期末余额一致）</span>
          </div>
        </template>
        <el-form label-width="140px" size="small" :disabled="readonly">
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="本期期初余额">
                <el-input v-model="openingConsistency.current_opening" placeholder="可手工录入或从平台带入" @change="markDirty">
                  <template #append>
                    <el-button :disabled="readonly" @click="pullOpeningConsistency">带入</el-button>
                  </template>
                </el-input>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="上期期末余额">
                <el-input v-model="openingConsistency.prior_closing" placeholder="可手工录入或从平台带入" @change="markDirty" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="是否一致">
                <el-select v-model="openingConsistency.is_consistent" placeholder="请判定" @change="markDirty" style="width:100%">
                  <el-option label="一致" value="一致" />
                  <el-option label="不一致" value="不一致" />
                  <el-option label="待核对" value="待核对" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-alert
            v-if="openingConsistencyNoteRequired"
            type="error" :closable="false" show-icon
            title="判定不一致时须填写说明" style="margin-bottom:8px"
          />
          <el-form-item label="说明">
            <el-input
              v-model="openingConsistency.note"
              type="textarea" :autosize="{ minRows: 2 }"
              placeholder="不一致时说明原因及处理"
              @change="markDirty"
            />
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 4 区块检查表（block3 拆借方/贷方两表） -->
      <el-card v-for="(block, idx) in BLOCKS_L05" :key="block.direction ? `${block.key}-${block.direction}` : block.key" shadow="never" class="section-card block-card">
        <template #header>
          <div class="card-header">
            <span>{{ block.title }}</span>
            <el-button v-if="!readonly" size="small" type="primary" :icon="Plus" @click="handleAddRow(block.key, block.direction)">新增行</el-button>
          </div>
        </template>
        <!-- 待归位提示：block3 借方表前展示无 direction 的既有行数（只显一次，避免借贷两表各提一次） -->
        <el-alert
          v-if="block.direction === 'debit' && getBlockRows(currentCompany, block.key).some(r => !r.direction)"
          type="warning" :closable="false" show-icon
          style="margin-bottom:8px"
        >
          有 {{ getBlockRows(currentCompany, block.key).filter(r => !r.direction).length }} 行尚未指定借贷方向，请编辑行指定方向后归入对应表
        </el-alert>
        <el-table
          :data="getBlockRowsForDisplay(currentCompany, block.key, block.direction)"
          border
          size="small"
          class="block-table"
          :style="{ fontSize: '13px' }"
        >
          <el-table-column type="index" label="序号" width="50" fixed="left" />
          <!-- 记账凭证5列（左侧固定） -->
          <el-table-column label="日期" prop="voucher_date" width="100">
            <template #default="{ row }">
              <el-input v-model="row.voucher_date" size="small" :disabled="readonly" @change="markDirty" />
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" prop="voucher_no" width="100">
            <template #default="{ row }">
              <el-input v-model="row.voucher_no" size="small" :disabled="readonly" @change="markDirty" />
            </template>
          </el-table-column>
          <el-table-column label="业务内容" prop="business_desc" width="140">
            <template #default="{ row }">
              <el-input v-model="row.business_desc" size="small" :disabled="readonly" @change="markDirty" />
            </template>
          </el-table-column>
          <el-table-column label="对方科目" prop="counter_account" width="100">
            <template #default="{ row }">
              <el-input v-model="row.counter_account" size="small" :disabled="readonly" @change="markDirty" />
            </template>
          </el-table-column>
          <el-table-column label="金额" prop="voucher_amount" width="100" align="right">
            <template #default="{ row }">
              <el-input v-model="row.voucher_amount" size="small" :disabled="readonly" @change="markDirty" />
            </template>
          </el-table-column>
          <!-- 检查证据列（右侧滚动） -->
          <el-table-column
            v-for="col in block.evidenceCols"
            :key="col.key"
            :label="col.label"
            :prop="col.key"
            :width="col.width || 120"
          >
            <template #default="{ row }">
              <template v-if="col.type === 'formula'">
                <span class="formula-cell" :title="col.tooltip">{{ computeFormulaCell(row, col, block.key) }}</span>
              </template>
              <template v-else-if="col.type === 'select'">
                <el-select v-model="row[col.key]" size="small" :disabled="readonly" @change="markDirty">
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
              </template>
              <template v-else>
                <el-input v-model="row[col.key]" size="small" :disabled="readonly" @change="markDirty" />
              </template>
            </template>
          </el-table-column>
          <!-- 📎OCR列 -->
          <el-table-column label="📎" width="50" align="center">
            <template #default="{ row }">
              <el-button size="small" link @click="handleOcr(row, block.key)">📎</el-button>
            </template>
          </el-table-column>
          <!-- 索引号 -->
          <el-table-column label="索引号" prop="ref_index" width="80">
            <template #default="{ row }">
              <el-input v-model="row.ref_index" size="small" :disabled="readonly" @change="markDirty" />
            </template>
          </el-table-column>
          <!-- 是否异常 -->
          <el-table-column label="是否异常" prop="is_abnormal" width="90">
            <template #default="{ row }">
              <el-select v-model="row.is_abnormal" size="small" :disabled="readonly" @change="markDirty">
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </template>
          </el-table-column>
          <!-- 删除 -->
          <el-table-column v-if="!readonly" label="操作" width="60" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="handleDeleteRow(block.key, row._row_id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <!-- 合计行 -->
        <div class="block-total">
          合计：{{ formatBlockTotal(block.key, block.direction) }}
        </div>
      </el-card>

      <!-- ─── 审计说明 + 结论 ───────────────────────────────────── -->
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="card-header">
            <span>审计说明</span>
            <el-button size="small" @click="handleAiGenerate('alternative-audit-note')">AI辅助</el-button>
          </div>
        </template>
        <el-input
          v-model="currentCompany.conclusion!.audit_note"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :disabled="readonly"
          @change="markDirty"
        />
      </el-card>

      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="card-header">
            <span>审计结论</span>
            <el-button size="small" @click="handleAiGenerate('alternative-audit-conclusion')">AI辅助</el-button>
          </div>
        </template>
        <el-input
          v-model="currentCompany.conclusion!.conclusion_text"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :disabled="readonly"
          @change="markDirty"
        />
      </el-card>
    </template>

    <el-empty v-else description="暂无待替代程序公司，请新增或从L0-1导入未回函" />

    <!-- 隐藏的文件上传 -->
    <input ref="fileInputRef" type="file" accept=".xlsx" style="display:none" @change="handleFileSelected" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, watch, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import type { AlternativeCompany, BlockType, CheckRow } from '../alternativeD05/alternativeD05Types'
import { useAlternativeL05Data } from '../l0-confirmation/composables/useAlternativeL05Data'
import { calcReconcileDiff } from '../l0-confirmation/composables/useL0FormulaEngine'
import { useWorkpaperImportExport } from '../../composables/useWorkpaperImportExport'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from '../../composables/useWorkpaperScaffold'
import http from '@/utils/http'

// ─── Props / Emits ──────────────────────────────────────────────────────────

interface Props {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}
const props = withDefaults(defineProps<Props>(), { readonly: false })
const emit = defineEmits<{ (e: 'save', payload: any): void }>()

// ─── Data composable ────────────────────────────────────────────────────────

const data = useAlternativeL05Data({
  wpId: props.wpId,
  projectId: props.projectId,
  htmlData: () => props.htmlData,
  readonly: props.readonly ?? false,
})

const selectedCompanyId = data.selectedCompanyId
const balanceSummary = data.balanceSummary

const currentCompany = computed<AlternativeCompany | undefined>(() => {
  if (!selectedCompanyId.value) return data.companies.value[0]
  return data.companies.value.find((c) => c._company_id === selectedCompanyId.value)
})

// 自动选中第一家
watch(
  () => data.companies.value.length,
  () => {
    if (!selectedCompanyId.value && data.companies.value.length > 0) {
      selectedCompanyId.value = data.companies.value[0]._company_id || null
    }
  },
  { immediate: true },
)

// ─── 期初余额一致性核对（confirmation-alternative-structure-alignment 决策 2） ──
// 挂公司级 company.opening_consistency（每被函证单位一份，随 company 持久化刷新回显）

const openingConsistency = computed(() => {
  const c = currentCompany.value
  if (!c) return {} as Record<string, any>
  if (!(c as any).opening_consistency) {
    ;(c as any).opening_consistency = { is_consistent: '待核对' }
  }
  return (c as any).opening_consistency as {
    current_opening?: any
    prior_closing?: any
    is_consistent?: string
    note?: string
  }
})

/** 判定不一致且未填说明 → 提示必填（Requirement 2.4） */
const openingConsistencyNoteRequired = computed(() => {
  const oc = openingConsistency.value
  return oc.is_consistent === '不一致' && !String(oc.note ?? '').trim()
})

/** 从平台带入期初/上期期末余额；取不到则保持手工录入并明示（Requirement 2.3） */
async function pullOpeningConsistency() {
  const c = currentCompany.value
  if (!c) return
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/l0/opening-balance`, {
      params: { entity_name: c.entity_name, confirm_index: c.confirm_index },
    })
    const d = res.data?.data ?? res.data ?? {}
    const oc = openingConsistency.value
    if (d.current_opening != null) oc.current_opening = d.current_opening
    if (d.prior_closing != null) oc.prior_closing = d.prior_closing
    if (d.current_opening == null && d.prior_closing == null) {
      ElMessage.info('平台未取到期初/上期期末余额，请手工录入')
    } else {
      markDirty()
    }
  } catch {
    ElMessage.info('平台未取到期初/上期期末余额，请手工录入')
  }
}

// ─── Import/Export ──────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const ie = useWorkpaperImportExport({ wpId: wpIdRef, apiPrefix: 'l0' })
const fileInputRef = ref<HTMLInputElement | null>(null)

function handleImportExportCmd(cmd: string) {
  if (cmd === 'export-template') ie.exportTemplate('L0-5')
  else if (cmd === 'export-data') ie.exportData('L0-5')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function handleFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await ie.importData('L0-5', file)
  if (result) {
    // reload after import
    data.loadAll()
  }
  input.value = ''
}

// ─── 4 区块配置 ─────────────────────────────────────────────────────────────

interface EvidenceCol {
  key: string
  label: string
  width?: number
  type?: 'text' | 'formula' | 'select'
  tooltip?: string
}

interface BlockConfig {
  key: BlockType
  title: string
  evidenceCols: EvidenceCol[]
  /** 借贷拆表标记（confirmation-alternative-structure-alignment 决策 1）：block3 本期借款拆借方/贷方两表 */
  direction?: 'debit' | 'credit'
  splitByDirection?: boolean
}

const BLOCKS_L05_BASE: BlockConfig[] = [
  {
    key: 'block1',
    title: '①期后付款/还款检查',
    evidenceCols: [
      { key: 'repay_approval_date_no', label: '还款审批单日期编号', width: 150 },
      { key: 'repay_approved', label: '是否恰当审批', width: 110, type: 'select' },
      { key: 'bank_receipt_date', label: '银行回单日期', width: 110 },
      { key: 'receipt_payee', label: '收款方', width: 100 },
      { key: 'repayment_principal', label: '还款本金', width: 100 },
      { key: 'repayment_interest', label: '还款利息', width: 100 },
    ],
  },
  {
    key: 'block2',
    title: '②期末余额支持性证据(借款合同/银行对账单)',
    evidenceCols: [
      { key: 'contract_no', label: '借款合同编号', width: 130 },
      { key: 'creditor', label: '债权人', width: 100 },
      { key: 'contract_amount', label: '合同金额', width: 100 },
      { key: 'loan_term', label: '借款期限', width: 100 },
      { key: 'statement_date', label: '银行对账单日期', width: 120 },
      { key: 'book_balance', label: '账面余额', width: 100 },
      { key: 'reconcile_diff', label: '对账差异', width: 100, type: 'formula', tooltip: '= 账面余额 - 对账单余额' },
    ],
  },
  {
    key: 'block3',
    title: '③本期借款检查',
    splitByDirection: true, // 源模板 L0-5 第③区块为借方(归还)/贷方(借入)两张表
    evidenceCols: [
      { key: 'loan_approval_date_no', label: '借款审批单日期编号', width: 150 },
      { key: 'loan_approved', label: '是否恰当审批', width: 110, type: 'select' },
      { key: 'arrival_receipt_date', label: '到账银行回单日期', width: 140 },
      { key: 'arrival_amount', label: '到账金额', width: 100 },
      { key: 'loan_rate', label: '借款利率', width: 90 },
    ],
  },
  {
    key: 'block4',
    title: '④抵质押/担保证据',
    evidenceCols: [
      { key: 'mortgage_contract_no', label: '抵质押合同编号', width: 130 },
      { key: 'mortgage_item', label: '抵押物', width: 100 },
      { key: 'mortgage_amount', label: '抵押金额', width: 100 },
      { key: 'guarantee_contract_no', label: '担保合同编号', width: 130 },
      { key: 'guarantor', label: '担保方', width: 100 },
      { key: 'guarantee_amount', label: '担保金额', width: 100 },
      { key: 'title_cert_no', label: '他项权证编号', width: 120 },
    ],
  },
]

/**
 * 渲染用区块列表：block3（splitByDirection）展开为借方表 + 贷方表两个虚拟 block，
 * 各带 direction 过滤（confirmation-alternative-structure-alignment 决策 1，渲染层拆表，数据仍单 block3）。
 */
const BLOCKS_L05 = computed<BlockConfig[]>(() => {
  const out: BlockConfig[] = []
  for (const b of BLOCKS_L05_BASE) {
    if (b.splitByDirection) {
      out.push({ ...b, title: `${b.title}（借方发生额）`, direction: 'debit' })
      out.push({ ...b, title: `${b.title}（贷方发生额）`, direction: 'credit' })
    } else {
      out.push(b)
    }
  }
  return out
})

// ─── Event handlers ─────────────────────────────────────────────────────────

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  return data.getBlockRows(company, blockType)
}

/** 借贷拆表：按 direction 过滤展示行（无 direction 参数=全部；block3 借贷各只显对应方向） */
function getBlockRowsForDisplay(company: AlternativeCompany, blockType: BlockType, direction?: 'debit' | 'credit'): CheckRow[] {
  const rows = data.getBlockRows(company, blockType)
  if (!direction) return rows
  return rows.filter((r) => r.direction === direction)
}

function markDirty() {
  data.isDirty.value = true
  debounceSave()
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', data.buildPayload())
  }, 1500)
}

async function handleAddCompany() {
  const { value } = await ElMessageBox.prompt('请输入被函证单位名称', '新增公司', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputPlaceholder: '被函证单位名称',
  }).catch(() => ({ value: '' }))
  if (!value) return
  const newCompany = data.addCompany({ entity_name: value })
  selectedCompanyId.value = newCompany._company_id || null
  markDirty()
}

function handleRemoveCompany(tabName: string | number) {
  data.deleteCompany(String(tabName))
  markDirty()
}

async function handleImportFromSummary() {
  const count = await data.importFromSummary()
  if (count > 0) {
    ElMessage.success(`已从L0-1导入 ${count} 个未回函被函证单位`)
    markDirty()
  } else {
    ElMessage.info('暂无未回函被函证单位可导入')
  }
}

function handleAddRow(blockType: BlockType, direction?: 'debit' | 'credit') {
  if (!currentCompany.value?._company_id) return
  const row = data.addBlockRow(currentCompany.value._company_id, blockType)
  if (row && direction) {
    data.updateBlockField(currentCompany.value._company_id, blockType, row._row_id!, 'direction', direction)
  }
  markDirty()
}

function handleDeleteRow(blockType: BlockType, rowId: string) {
  if (!currentCompany.value?._company_id) return
  data.deleteBlockRow(currentCompany.value._company_id, blockType, rowId)
  markDirty()
}

function formatBlockTotal(blockType: BlockType, direction?: 'debit' | 'credit'): string {
  if (!currentCompany.value) return '—'
  // 借贷拆表时按方向小计，否则全 block 合计（confirmation-alternative-structure-alignment）
  const totals = direction
    ? data.getBlockTotalByDirection(currentCompany.value, blockType, direction)
    : data.getBlockTotal(currentCompany.value, blockType)
  return Object.entries(totals)
    .map(([k, v]) => `${k}: ${v.toFixed(2)}`)
    .join(' | ')
}

function computeFormulaCell(row: CheckRow, col: EvidenceCol, blockType: BlockType): string {
  if (col.key === 'reconcile_diff') {
    const book = Number(row.book_balance ?? 0)
    const statement = Number(row.voucher_amount ?? 0)
    return calcReconcileDiff(book, statement).toFixed(2)
  }
  return String(row[col.key] ?? '')
}

// ─── OCR ────────────────────────────────────────────────────────────────────

async function handleOcr(row: CheckRow, blockType: BlockType) {
  try {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,.pdf'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post('/api/workpapers/d4/contract-ocr', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const ocrData = res.data?.data ?? res.data
      if (!ocrData || Object.keys(ocrData).length === 0) {
        ElMessage.warning('未识别到有效借款信息')
        return
      }
      await ElMessageBox.confirm(
        `OCR识别结果：${JSON.stringify(ocrData, null, 2).slice(0, 300)}...\n确认填入当前行？`,
        'OCR识别结果',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
      )
      Object.assign(row, ocrData)
      markDirty()
    }
    input.click()
  } catch {
    // 用户取消
  }
}

// ─── AI辅助 ─────────────────────────────────────────────────────────────────

async function handleAiGenerate(section: string) {
  if (!currentCompany.value) return
  try {
    const existingContent = section === 'alternative-audit-note'
      ? currentCompany.value.conclusion?.audit_note || ''
      : currentCompany.value.conclusion?.conclusion_text || ''
    const res = await http.post(`/api/workpapers/${props.wpId}/l0/ai/${section}`, {
      existingContent,
      relatedContext: { entity_name: currentCompany.value.entity_name },
    })
    const content = res.data?.data?.content ?? res.data?.content ?? ''
    if (!content) { ElMessage.warning('AI未生成内容'); return }
    if (section === 'alternative-audit-note') {
      currentCompany.value.conclusion!.audit_note = content
    } else {
      currentCompany.value.conclusion!.conclusion_text = content
    }
    markDirty()
    ElMessage.success('AI内容已生成')
  } catch {
    ElMessage.error('AI生成失败')
  }
}

// ─── selfLoad兜底 ───────────────────────────────────────────────────────────

async function selfLoad() {
  if (props.htmlData) return
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/render-config`)
    const sheets = res.data?.data?.sheets ?? res.data?.sheets ?? []
    for (const s of sheets) {
      if (s.sheet_name === props.sheetName || s.wp_code === 'L0-5') {
        if (s.html_data) data.loadAll()
        break
      }
    }
  } catch { /* ignore */ }
}
selfLoad()

// ─── Version Trail / Review ─────────────────────────────────────────────────

// ─── Runtime Boundary 统一提供版本链 + 复核（GtWpRenderer scaffold），本组件不再本地接线 ───
// 原先本地 provide('openReviewDialog', 占位) 会覆盖 Runtime Boundary 的真实复核入口 → 已删除。
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const openVersionHistory = () => runtime?.version.openVersionHistory()

// autoSnapshot on save
watch(() => data.isDirty.value, (dirty) => {
  if (!dirty) {
    // just saved → auto snapshot
    runtime?.version.scheduleAutoSnapshot()
  }
})
</script>

<style scoped>
.gt-confirmation-alternative-l05 {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}
.summary-card { margin-bottom: 16px; }
.summary-table { font-size: var(--wp-font-size, 13px); }
.company-tabs-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.company-tabs-wrapper .el-tabs { flex: 1; }
.tabs-actions { display: flex; gap: 8px; }
.section-card { margin-bottom: 16px; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.block-card .block-table { font-size: var(--wp-font-size, 13px); }
.block-total {
  padding: 8px 12px;
  background: #f5f7fa;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  border-top: 1px solid #ebeef5;
}
.formula-cell {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
}
</style>
