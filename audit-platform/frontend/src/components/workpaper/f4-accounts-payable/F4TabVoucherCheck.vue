<script setup lang="ts">
/**
 * F4TabVoucherCheck — F4-8 应付账款检查表（借方/贷方区块）
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.4
 * 借方区(付款减少) + 贷方区(采购增加) 独立el-table
 * GtVoucherSamplingEngine集成(dialog, 科目2202, 样本按借贷分配)
 * 贷方区特色：三单匹配(采购订单/入库单/发票)
 * 各区独立增删 + 底部小计 + 审计结论textarea(AI)
 * 导入导出 + 虚拟滚动(73行)
 * Requirements: 11.1~11.9, 14.2
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useF4VoucherCheck } from '../composables/useF4VoucherCheck'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  debitRows,
  creditRows,
  debitSubtotal,
  creditSubtotal,
  debitConclusion,
  creditConclusion,
  addDebitRow,
  addCreditRow,
  removeDebitRow,
  removeCreditRow,
  updateDebitCell,
  updateCreditCell,
  distributeSamples,
} = useF4VoucherCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 抽凭引擎 ───────────────────────────────────────────────────────────────
const samplingDialogVisible = ref(false)
const samplingLoading = ref(false)

async function openSamplingDialog() {
  samplingDialogVisible.value = true
}

async function executeSampling() {
  samplingLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/voucher-sampling/execute`, {
      accountCode: '2202',
      sampleSize: 20,
    })
    const samples = data?.data?.samples || data?.samples || []
    if (!samples.length) {
      ElMessage.warning('未获取到抽样结果')
      return
    }
    distributeSamples(samples)
    ElMessage.success(`抽凭完成：共 ${samples.length} 笔，已按借贷分配`)
    samplingDialogVisible.value = false
  } catch {
    ElMessage.error('抽凭引擎执行失败')
  } finally {
    samplingLoading.value = false
  }
}

// ─── AI 生成结论 ─────────────────────────────────────────────────────────────
const debitAiLoading = ref(false)
const creditAiLoading = ref(false)

async function generateDebitConclusion() {
  debitAiLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/ai/voucher-check`)
    debitConclusion.value = data?.data?.debitConclusion || data?.debitConclusion || ''
    ElMessage.success('借方检查AI结论已生成')
  } catch { ElMessage.error('AI生成失败') }
  finally { debitAiLoading.value = false }
}

async function generateCreditConclusion() {
  creditAiLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/ai/voucher-check`)
    creditConclusion.value = data?.data?.creditConclusion || data?.creditConclusion || ''
    ElMessage.success('贷方检查AI结论已生成')
  } catch { ElMessage.error('AI生成失败') }
  finally { creditAiLoading.value = false }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
async function handleExportTemplate() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-template?sheet=F4-8`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-8检查表模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-data?sheet=F4-8`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-8检查表数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      await axios.post(`/api/workpapers/${props.wpId}/f4/import-data?sheet=F4-8`, fd)
      ElMessage.success('导入成功')
      window.location.reload()
    } catch { ElMessage.error('导入失败') }
  }
  input.click()
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="f4-tab-voucher-check">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 检查表分为借方区(付款减少)和贷方区(采购增加)两个独立区块。</p>
        <p>2. 借方检查：核实付款是否有真实采购背景、授权审批是否完整。</p>
        <p>3. 贷方检查：验证采购入账是否有三单匹配（采购订单+入库单+发票）。</p>
        <p>4. 使用抽凭引擎(科目2202)自动抽样，样本按借贷自动分配到对应区域。</p>
        <p>5. 三单匹配不一致需重点关注，记录不一致原因及审计处理。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：对应付账款(2202)借方(付款)与贷方(采购)发生额抽凭检查，验证真实性、准确性与截止，贷方关注采购订单/入库单/发票三单匹配。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button type="primary" size="small" :disabled="isReadonly" @click="openSamplingDialog">
          抽凭引擎
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:F4-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ debitRows.length + creditRows.length }} 行</el-tag>
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="openReviewDialog('f4-8-voucher-check')"
        >复核</el-button>
      </div>
    </div>

    <!-- ─── 借方区（付款减少） ────────────────────────────────────────── -->
    <div class="section-block">
      <div class="block-header">
        <h4 class="block-title">一、借方检查（付款减少）</h4>
        <el-button size="small" :disabled="isReadonly" @click="addDebitRow">+ 新增行</el-button>
      </div>

      <el-table
        :data="debitRows"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        max-height="400"
      >
        <el-table-column prop="seq" label="序号" width="60" />
        <el-table-column label="凭证号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证日期" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small" placeholder="YYYY-MM-DD" @change="(v: string) => updateDebitCell(row.rowId, 'voucherDate', v)" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="供应商" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterparty" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'counterparty', v)" />
            <span v-else>{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="付款金额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDebitCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'summary', v)" />
            <span v-else>{{ row.summary }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计程序" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditProcedure" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'auditProcedure', v)" />
            <span v-else>{{ row.auditProcedure }}</span>
          </template>
        </el-table-column>
        <el-table-column label="检查结果" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.checkResult" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'checkResult', v)" />
            <span v-else>{{ row.checkResult }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeDebitRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">借方合计：{{ fmtAmount(debitSubtotal) }}</div>

      <el-card class="opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">借方检查审计结论</span>
            <div class="opinion-actions">
              <el-button size="small" type="primary" plain :loading="debitAiLoading" :disabled="isReadonly" @click="generateDebitConclusion">🤖 AI辅助</el-button>
              <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-8-debit-conclusion')">💬</el-button>
            </div>
          </div>
        </template>
        <el-input
          v-model="debitConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="借方检查（付款减少）审计结论..."
        />
      </el-card>
    </div>

    <!-- ─── 贷方区（采购增加） ────────────────────────────────────────── -->
    <div class="section-block">
      <div class="block-header">
        <h4 class="block-title">二、贷方检查（采购增加）— 三单匹配</h4>
        <el-button size="small" :disabled="isReadonly" @click="addCreditRow">+ 新增行</el-button>
      </div>

      <el-table
        :data="creditRows"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        max-height="400"
      >
        <el-table-column prop="seq" label="序号" width="60" />
        <el-table-column label="凭证号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证日期" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small" placeholder="YYYY-MM-DD" @change="(v: string) => updateCreditCell(row.rowId, 'voucherDate', v)" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="供应商" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterparty" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'counterparty', v)" />
            <span v-else>{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="采购金额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCreditCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'summary', v)" />
            <span v-else>{{ row.summary }}</span>
          </template>
        </el-table-column>
        <el-table-column label="采购订单号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.purchaseOrderNo" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'purchaseOrderNo', v)" />
            <span v-else>{{ row.purchaseOrderNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="入库单号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.receiptNo" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'receiptNo', v)" />
            <span v-else>{{ row.receiptNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发票号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.invoiceNo" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'invoiceNo', v)" />
            <span v-else>{{ row.invoiceNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="三单匹配" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.threeWayMatch" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'threeWayMatch', v)">
              <el-option label="" value="" />
              <el-option label="一致" value="一致" />
              <el-option label="不一致" value="不一致" />
            </el-select>
            <span v-else :class="{ 'match-fail': row.threeWayMatch === '不一致' }">{{ row.threeWayMatch }}</span>
          </template>
        </el-table-column>
        <el-table-column label="检查结果" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.checkResult" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'checkResult', v)" />
            <span v-else>{{ row.checkResult }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeCreditRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">贷方合计：{{ fmtAmount(creditSubtotal) }}</div>

      <el-card class="opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">贷方检查审计结论</span>
            <div class="opinion-actions">
              <el-button size="small" type="primary" plain :loading="creditAiLoading" :disabled="isReadonly" @click="generateCreditConclusion">🤖 AI辅助</el-button>
              <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-8-credit-conclusion')">💬</el-button>
            </div>
          </div>
        </template>
        <el-input
          v-model="creditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="贷方检查（采购增加 + 三单匹配）审计结论..."
        />
      </el-card>
    </div>

    <!-- ─── 抽凭引擎对话框 ───────────────────────────────────────────── -->
    <el-dialog
      v-model="samplingDialogVisible"
      title="抽凭引擎 — 科目2202应付账款"
      width="500px"
    >
      <p style="margin-bottom:12px">将对科目2202(应付账款)执行抽凭采样，样本按借方/贷方自动分配到对应检查区域。</p>
      <template #footer>
        <el-button @click="samplingDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="samplingLoading" @click="executeSampling">执行抽凭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.f4-tab-voucher-check {
  font-size: 13px;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
  font-size: 13px;
}
.guidance-details .guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-details .guidance-content p {
  margin: 2px 0;
}
.audit-objective {
  margin-bottom: 12px;
}
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}
.section-block {
  margin-bottom: 24px;
}
.block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.block-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}
.block-subtotal {
  margin-top: 6px;
  padding: 6px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}
.opinion-card {
  margin-top: 10px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
.match-fail {
  color: #f56c6c;
  font-weight: 600;
}
</style>
