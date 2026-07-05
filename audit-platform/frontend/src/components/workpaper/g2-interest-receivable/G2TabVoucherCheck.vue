<template>
  <div class="g2-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G2-8 凭证检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="success" @click="openSamplingEngine">使用抽凭引擎</el-button>
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G2-8-voucher-check')">💬复核</el-button>
      </div>
    </div>

    <!-- ═══ 借方检查区（增加/利息确认）═══ -->
    <div class="block-section">
      <div class="block-head">
        <h4 class="block-title">借方检查区（增加/利息确认）</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="vc.addDebitRow()">新增借方行</el-button>
      </div>

      <el-table :data="vc.debitRows.value" border size="small" max-height="400">
        <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
        <el-table-column label="摘要" width="130">
          <template #default="{ row }">
            <el-input :model-value="row.summary" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateDebitCell(row.id, 'summary', v)" />
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="110">
          <template #default="{ row }">
            <el-input :model-value="row.counterAccount" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateDebitCell(row.id, 'counterAccount', v)" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'amount', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="凭证日期" width="120">
          <template #default="{ row }">
            <el-date-picker :model-value="row.voucherDate" type="date" size="small" value-format="YYYY-MM-DD"
              :disabled="isReadonly" style="width:100%"
              @update:model-value="(v: string) => vc.updateDebitCell(row.id, 'voucherDate', v ?? '')" />
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.voucherNo" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateDebitCell(row.id, 'voucherNo', v)" />
          </template>
        </el-table-column>
        <el-table-column label="投资标的" width="120">
          <template #default="{ row }">
            <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateDebitCell(row.id, 'investTarget', v)" />
          </template>
        </el-table-column>
        <el-table-column label="面值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.faceValue" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'faceValue', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="利率(%)" width="90" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.rate" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" :precision="4"
              @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'rate', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="计息天数" width="90" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.accruedDays" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => vc.updateDebitCell(row.id, 'accruedDays', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="测算利息" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="测算利息 = 面值 × 利率/100 × 计息天数/365">
              {{ fmtNum(row.calculatedInterest) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="差异 = 测算利息 - 金额">{{ fmtNum(row.variance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" width="120">
          <template #default="{ row }">
            <el-input :model-value="row.auditConclusion" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateDebitCell(row.id, 'auditConclusion', v)" />
          </template>
        </el-table-column>
        <el-table-column label="来源" width="70">
          <template #default="{ row }">
            <el-tooltip v-if="row.source" :content="row.source" placement="top">
              <el-tag size="small" type="info">{{ row.source === '抽凭' ? '抽凭' : 'OCR' }}</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" size="small" type="danger" link @click="vc.removeDebitRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <span class="subtotal-label">借方小计：</span>
        金额 {{ fmtNum(vc.debitTotals.value.amount) }} ·
        测算利息 {{ fmtNum(vc.debitTotals.value.calculatedInterest) }} ·
        差异 {{ fmtNum(vc.debitTotals.value.variance) }}
      </div>
    </div>

    <!-- ═══ 贷方检查区（减少/利息收回）═══ -->
    <div class="block-section">
      <div class="block-head">
        <h4 class="block-title">贷方检查区（减少/利息收回）</h4>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="vc.addCreditRow()">新增贷方行</el-button>
      </div>

      <el-table :data="vc.creditRows.value" border size="small" max-height="400">
        <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
        <el-table-column label="摘要" width="130">
          <template #default="{ row }">
            <el-input :model-value="row.summary" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCreditCell(row.id, 'summary', v)" />
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="110">
          <template #default="{ row }">
            <el-input :model-value="row.counterAccount" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCreditCell(row.id, 'counterAccount', v)" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => vc.updateCreditCell(row.id, 'amount', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="凭证日期" width="120">
          <template #default="{ row }">
            <el-date-picker :model-value="row.voucherDate" type="date" size="small" value-format="YYYY-MM-DD"
              :disabled="isReadonly" style="width:100%"
              @update:model-value="(v: string) => vc.updateCreditCell(row.id, 'voucherDate', v ?? '')" />
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.voucherNo" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCreditCell(row.id, 'voucherNo', v)" />
          </template>
        </el-table-column>
        <el-table-column label="收款银行" width="120">
          <template #default="{ row }">
            <el-input :model-value="row.receivingBank" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCreditCell(row.id, 'receivingBank', v)" />
          </template>
        </el-table-column>
        <el-table-column label="收款日期" width="120">
          <template #default="{ row }">
            <el-date-picker :model-value="row.receiptDate" type="date" size="small" value-format="YYYY-MM-DD"
              :disabled="isReadonly" style="width:100%"
              @update:model-value="(v: string) => vc.updateCreditCell(row.id, 'receiptDate', v ?? '')" />
          </template>
        </el-table-column>
        <el-table-column label="到期收回" width="100">
          <template #default="{ row }">
            <el-select :model-value="row.isOnTimeRecovery" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCreditCell(row.id, 'isOnTimeRecovery', v)">
              <el-option value="是" label="是" />
              <el-option value="否" label="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="逾期天数" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'overdue-warn': row.overdueDays > 0 }">{{ row.overdueDays }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" width="120">
          <template #default="{ row }">
            <el-input :model-value="row.auditConclusion" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCreditCell(row.id, 'auditConclusion', v)" />
          </template>
        </el-table-column>
        <el-table-column label="来源" width="70">
          <template #default="{ row }">
            <el-tooltip v-if="row.source" :content="row.source" placement="top">
              <el-tag size="small" type="info">{{ row.source === '抽凭' ? '抽凭' : 'OCR' }}</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" size="small" type="danger" link @click="vc.removeCreditRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-subtotal">
        <span class="subtotal-label">贷方小计：</span>
        金额 {{ fmtNum(vc.creditTotals.value.amount) }} ·
        逾期笔数 {{ vc.creditTotals.value.overdueCount }}
      </div>
    </div>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对凭证检查的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>借方区：测算利息 = 面值 × 利率/100 × 计息天数/365（365天基准）</li>
        <li>借方差异 = 测算利息 - 凭证金额</li>
        <li>贷方区：关注是否到期收回，逾期天数判断利息回收风险</li>
        <li>抽凭引擎按科目1132抽取样本，自动按借贷方向分配至对应区块</li>
        <li>📎OCR：上传凭证扫描件→自动识别填入对应字段</li>
      </ul>
    </details>

    <!-- 抽凭引擎对话框（占位：集成时由GtVoucherSamplingEngine提供） -->
    <el-dialog v-model="showSamplingDialog" title="抽凭引擎 - 科目1132应收利息" width="800px" destroy-on-close>
      <p class="sampling-placeholder">抽凭引擎将在集成阶段接入（科目1132，样本按借贷方向分配）</p>
      <template #footer>
        <el-button @click="showSamplingDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { useG2VoucherCheck } from '../../composables/useG2VoucherCheck'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const vc = useG2VoucherCheck({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const auditConclusion = ref('')
const showSamplingDialog = ref(false)

function openSamplingEngine() {
  showSamplingDialog.value = true
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}

function fillAiDraft() {
  if (props.isReadonly) return
  const dt = vc.debitTotals.value
  const ct = vc.creditTotals.value
  const draft =
    `经抽凭检查，借方（利息确认）共 ${vc.debitRows.value.length} 笔，` +
    `金额合计 ${dt.amount.toLocaleString()} 元，测算利息合计 ${dt.calculatedInterest.toLocaleString()} 元，` +
    `差异合计 ${dt.variance.toLocaleString()} 元；` +
    `贷方（利息收回）共 ${vc.creditRows.value.length} 笔，` +
    `金额合计 ${ct.amount.toLocaleString()} 元，逾期 ${ct.overdueCount} 笔。` +
    (Math.abs(dt.variance) < 100 && ct.overdueCount === 0
      ? '凭证检查未发现异常，利息确认与收回核算恰当。'
      : '存在差异或逾期收回情况，需进一步关注。')
  auditConclusion.value = auditConclusion.value ? `${auditConclusion.value}\n${draft}` : draft
}
</script>

<style scoped>
.g2-voucher-check { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }

.block-section { margin-bottom: 20px; }
.block-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }
.block-title { margin: 0; font-size: 14px; color: #303133; }
.block-subtotal { margin-top: 8px; font-size: 12px; font-weight: 600; color: #303133; padding: 6px 0; border-top: 1px solid #ebeef5; }
.subtotal-label { color: #606266; }

.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.overdue-warn { color: #e6a23c; font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.sampling-placeholder { color: #909399; text-align: center; padding: 20px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
