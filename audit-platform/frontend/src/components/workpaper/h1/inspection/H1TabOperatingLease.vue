<template>
  <div class="h1-tab-operating-lease">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：（1）已记录的经营租出固定资产真实存在；（2）租金收入与折旧费用计入恰当会计期间；（3）折旧与租金计价分摊正确；（4）财务报表列报披露恰当。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-19" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ operatingRows.length }} 项</el-tag>
      <el-tag v-if="operatingSummary.abnormalDepCount > 0" size="small" type="danger">
        折旧差异 {{ operatingSummary.abnormalDepCount }} 项
      </el-tag>
      <el-tag v-if="operatingSummary.abnormalIncomeCount > 0" size="small" type="danger">
        租金差异 {{ operatingSummary.abnormalIncomeCount }} 项
      </el-tag>
    </div>

    <div class="methodology-context">
      <p>
        编制思路：获取租出明细与租赁合同 → 核对条款/分类 →
        <b>重算本期应计折旧</b>（月折旧×本年月份，与其他业务支出核对）→
        <b>重算本期应计租金</b>（月租金×本年月份，与其他业务收入核对）→
        评价收益率及市场租金偏离 → 差异入审计说明并索引合同底稿。
      </p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>二、审计过程 — 经营租出固定资产检查表</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly || !operatingRows.length" @click="handleFillMonths">推算本年月份</el-button>
            <el-button size="small" :disabled="isReadonly || !operatingRows.length" @click="handleDraftNote">生成差异说明</el-button>
            <el-button size="small" :disabled="isReadonly || !operatingRows.length" @click="handleSyncDisclosure">同步至附注</el-button>
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-19')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="operatingRows" border stripe size="small" max-height="520" class="lease-table">
        <el-table-column type="index" label="序号" width="48" fixed />
        <el-table-column prop="assetName" label="固定资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="onCell(row, 'assetName')" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetCategory" label="资产类别" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small" @change="onCell(row, 'assetCategory')" />
            <span v-else>{{ row.assetCategory }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="specModel" label="规格型号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.specModel" size="small" @change="onCell(row, 'specModel')" />
            <span v-else>{{ row.specModel }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessee" label="承租单位" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessee" size="small" @change="onCell(row, 'lessee')" />
            <span v-else>{{ row.lessee }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseStart" label="租赁开始日" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.leaseStart" type="date" value-format="YYYY-MM-DD" size="small" style="width:110px" @change="onCell(row, 'leaseStart')" />
            <span v-else>{{ row.leaseStart }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseEnd" label="租赁到期日" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.leaseEnd" type="date" value-format="YYYY-MM-DD" size="small" style="width:110px" @change="onCell(row, 'leaseEnd')" />
            <span v-else>{{ row.leaseEnd }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contractAmount" label="合同总金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.contractAmount" :controls="false" size="small" @change="onCell(row, 'contractAmount')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.contractAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="monthsThisYear" label="本年月份" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.monthsThisYear" :controls="false" :min="0" :max="12" size="small" @change="onCell(row, 'monthsThisYear')" />
            <span v-else>{{ row.monthsThisYear }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCost" label="固定资产原值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" @change="onCell(row, 'originalCost')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accumDep" label="累计折旧" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accumDep" :controls="false" size="small" @change="onCell(row, 'accumDep')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accumDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="depYears" label="折旧年限" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.depYears" :controls="false" :min="0" size="small" @change="onCell(row, 'depYears')" />
            <span v-else>{{ row.depYears || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="residualRate" label="残值率%" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.residualRate" :controls="false" :min="0" :max="100" size="small" @change="onCell(row, 'residualRate')" />
            <span v-else>{{ row.residualRate }}%</span>
          </template>
        </el-table-column>

        <!-- 折旧费用核对 -->
        <el-table-column label="经营租出固定资产应计提的折旧费用核对" align="center">
          <el-table-column label="月折旧额" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="月折旧=原值×(1−残值率)/折旧年限/12">{{ fmtAmt(row.monthlyDep) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期应计折旧" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="应计折旧=本年月份×月折旧额">{{ fmtAmt(row.expectedDep) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bookedDep" label="账面折旧" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.bookedDep" :controls="false" size="small" @change="onCell(row, 'bookedDep')" />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookedDep) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="90" align="right">
            <template #default="{ row }">
              <span :class="['formula-cell', { 'error-amount': Math.abs(row.depDiff) > 0.01 }]" title="差异=应计折旧−账面折旧">
                {{ fmtAmt(row.depDiff) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 租金收入核对 -->
        <el-table-column label="经营租出固定资产应计提的租金收入核对" align="center">
          <el-table-column label="月租金" width="100" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly && !(row.contractAmount > 0 && row.leaseTerm > 0)">
                <el-input-number v-model="row.monthlyRent" :controls="false" size="small" @change="onCell(row, 'monthlyRent')" />
              </template>
              <span v-else class="formula-cell" :title="rentTitle(row)">{{ fmtAmt(row.monthlyRent) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期应计租金" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="应计租金=本年月份×月租金">{{ fmtAmt(row.expectedRent) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bookedRent" label="账面租金" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.bookedRent" :controls="false" size="small" @change="onCell(row, 'bookedRent')" />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookedRent) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="90" align="right">
            <template #default="{ row }">
              <span :class="['formula-cell', { 'error-amount': Math.abs(row.incomeDiff) > 0.01 }]" title="差异=应计租金−账面租金">
                {{ fmtAmt(row.incomeDiff) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 收益率分析（数字底稿增强） -->
        <el-table-column label="收益率分析" align="center">
          <el-table-column label="年租金" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="年租金=月租金×12">{{ fmtAmt(row.annualRent) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="maintenanceCost" label="维护费" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.maintenanceCost" :controls="false" size="small" @change="onCell(row, 'maintenanceCost')" />
              <span v-else class="amount-cell">{{ fmtAmt(row.maintenanceCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净收益" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="净收益=年租金−年折旧−维护费">{{ fmtAmt(row.netIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="收益率%" width="80" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="收益率=净收益÷原值×100%">{{ row.originalCost > 0 ? row.returnRate.toFixed(1) + '%' : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="marketRent" label="市场年租" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.marketRent" :controls="false" size="small" @change="onCell(row, 'marketRent')" />
              <span v-else class="amount-cell">{{ fmtAmt(row.marketRent) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="偏离%" width="70" align="right">
            <template #default="{ row }">
              <span :class="['formula-cell', { 'error-amount': Math.abs(deviation(row) ?? 0) > 20 }]" title="偏离=(年租金−市场年租)÷市场年租×100%">
                {{ deviation(row) != null ? deviation(row)!.toFixed(1) + '%' : '-' }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="contractIndex" label="合同索引号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractIndex" size="small" placeholder="如 H1-19-1" @change="onCell(row, 'contractIndex')" />
            <span v-else>{{ row.contractIndex }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isRelatedParty" label="关联" width="70" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRelatedParty" size="small" style="width:56px" @change="onCell(row, 'isRelatedParty')">
              <el-option label="否" value="N" />
              <el-option label="是" value="Y" />
            </el-select>
            <span v-else>{{ row.isRelatedParty === 'Y' ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" :loading="ocrLoadingId === row.rowId" title="上传租赁合同 OCR 预填" @click="handleOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" fixed="right" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('19', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>合同金额合计: <b class="amount-cell">{{ fmtAmt(operatingSummary.totalContractAmount) }}</b></span>
        <span>应计折旧: <b class="amount-cell">{{ fmtAmt(operatingSummary.totalExpectedDep) }}</b>
          / 账面 <b class="amount-cell">{{ fmtAmt(operatingSummary.totalBookedDep) }}</b>
          / 差异 <b :class="{ 'error-amount': Math.abs(operatingSummary.totalDepDiff) > 0.01 }">{{ fmtAmt(operatingSummary.totalDepDiff) }}</b>
        </span>
        <span>应计租金: <b class="amount-cell">{{ fmtAmt(operatingSummary.totalExpectedRent) }}</b>
          / 账面 <b class="amount-cell">{{ fmtAmt(operatingSummary.totalBookedRent) }}</b>
          / 差异 <b :class="{ 'error-amount': Math.abs(operatingSummary.totalIncomeDiff) > 0.01 }">{{ fmtAmt(operatingSummary.totalIncomeDiff) }}</b>
        </span>
        <span>平均收益率: <b>{{ operatingSummary.avgReturnRate.toFixed(1) }}%</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input v-model="auditNoteText" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="说明：租赁分类结论、折旧/租金差异原因、关联方租赁公允性、市场偏离解释、合同抽查范围等。"
        @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="结论示例：经检查，经营租出固定资产真实存在，本期折旧与租金收入重算差异未超过可接受水平 / 已提出调整建议……"
        @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>月折旧 = 原值×(1−残值率)/折旧年限/12；折旧年限未填时月折旧为 0（避免 #DIV/0!）</li>
        <li>本期应计折旧/租金 = 本年月份 × 月折旧/月租金；与账面「其他业务支出/收入」核对，差异≠0 标红</li>
        <li>「推算本年月份」按租期与本会计年度重叠月数填写（也可改起止日后自动重算）</li>
        <li>「生成差异说明」按异常行起草审计说明；「同步至附注」写入上市/国企附注经营租出子节</li>
        <li>有合同总额与租期时，月租金 = 合同总额÷租赁月数；否则可手填月租金</li>
        <li>净收益 = 年租金 − 年折旧 − 维护费；收益率 = 净收益÷原值；市场偏离&gt;20% 标红</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH1LeaseCheck,
  buildOperatingLeaseNoteDraft,
  type OperatingLeaseRow,
} from '../../composables/useH1LeaseCheck'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const auditNoteText = ref('')
const ocrLoadingId = ref('')
const NOTE_KEY = 'H1-19-audit-note'
const CONCLUSION_KEY = 'H1-19-audit-conclusion'
function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) conclusion.value = c.remark
})

const {
  operatingRows,
  operatingSummary,
  addOperatingRow,
  removeRow,
  updateOperatingCell,
  applyOperatingLeaseOcr,
  fillMonthsThisYear,
  syncOperatingToDisclosure,
} = useH1LeaseCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

function deviation(row: OperatingLeaseRow): number | null {
  return row.marketRent > 0 ? ((row.annualRent - row.marketRent) / row.marketRent * 100) : null
}

function rentTitle(row: OperatingLeaseRow): string {
  if (row.contractAmount > 0 && row.leaseTerm > 0) return `月租金=合同总额÷租期(${row.leaseTerm}月)`
  return '月租金（手填）'
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('资产名称', '新增经营租出', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (name != null) {
      addOperatingRow()
      const last = operatingRows.value[operatingRows.value.length - 1]
      if (last) updateOperatingCell(last.rowId, 'assetName', name)
    }
  } catch { /* cancel */ }
}

function handleFillMonths() {
  const n = fillMonthsThisYear()
  ElMessage.success(n > 0 ? `已按本年租期重叠推算 ${n} 项「本年月份」` : '请先填写租赁起止日')
}

async function handleDraftNote() {
  const draft = buildOperatingLeaseNoteDraft(operatingRows.value)
  if (auditNoteText.value.trim()) {
    try {
      await ElMessageBox.confirm('将覆盖当前审计说明，是否继续？', '生成差异说明', {
        confirmButtonText: '覆盖',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch { return }
  }
  auditNoteText.value = draft
  saveAuditNote()
  ElMessage.success('已生成审计说明草稿，请复核后定稿')
}

function handleSyncDisclosure() {
  const n = syncOperatingToDisclosure()
  ElMessage.success(n > 0
    ? `已同步 ${n} 项至附注「经营租出」子节（上市/国企）`
    : '暂无经营租出数据可同步')
}

function onCell(row: OperatingLeaseRow, field: keyof OperatingLeaseRow) {
  updateOperatingCell(row.rowId, field, (row as any)[field])
}

/** 行级租赁合同 OCR：📎 → contract-ocr → 确认 → 仅填空预填 */
async function handleOcr(row: OperatingLeaseRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    ocrLoadingId.value = row.rowId
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = { ...(data?.extracted_fields || {}) }
      if (data?.attachment_id) fields.attachment_id = data.attachment_id
      const preview = Object.entries(fields)
        .filter(([k, v]) => k !== 'attachment_id' && v !== '' && v != null && v !== 0)
        .map(([k, v]) => `${k}: ${v}`)
      if (!preview.length) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段', '提示')
        return
      }
      await ElMessageBox.confirm(`识别结果：\n${preview.join('\n')}\n\n确认填入空白字段？`, '租赁合同 OCR 识别结果', {
        confirmButtonText: '填入', cancelButtonText: '取消',
      })
      const filled = applyOperatingLeaseOcr(row.rowId, fields)
      ElMessage.success(filled.length ? `已预填 ${filled.length} 个字段` : '无可填空字段（已有值未覆盖）')
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('合同 OCR 失败，请稍后重试或手工录入')
    } finally {
      ocrLoadingId.value = ''
    }
  }
  input.click()
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-operating-lease { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; line-height: 1.6; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.lease-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.summary-bar { display: flex; flex-wrap: wrap; gap: 16px 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; font-size: 12px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
