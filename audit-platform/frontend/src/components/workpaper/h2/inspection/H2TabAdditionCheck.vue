<template>
  <div class="h2-tab-addition-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：针对本期在建工程增加实施细节测试——（1）存在/发生：增加真实且工程存在；（2）准确性与计价：金额与合同/进度/发票相符，资本化范围恰当；（3）截止：记入正确期间；（4）权利与义务：合同权利义务归属于被审计单位。总体与 H2-2 勾稽，关联方→H2-17，调整→H2-3。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-8" :context-project-id="projectId" /></span>
        <GtIndexChip value="wp:H2-3" :context-project-id="projectId" context="调整分录" />
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag v-if="state.summary.value.evidenceGapCount > 0" size="small" type="warning">
          证据缺口 {{ state.summary.value.evidenceGapCount }} 项
        </el-tag>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          :disabled="state.summary.value.evidenceGapCount <= 0"
          @click="handlePushEvidenceGap"
        >
          证据缺口推送至 H2-3
        </el-button>
      </div>
    </div>

    <!-- 区域1: 抽样参数 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>抽样参数</span>
          <div class="section-header-actions">
            <el-button size="small" @click="handleSampling">抽凭引擎</el-button>
          </div>
        </div>
      </template>
      <div class="params-grid">
        <div class="param-item">
          <span class="param-label">总体金额：</span>
          <el-input-number v-model="state.samplingParams.value.populationAmount" :controls="false" size="small"
            :disabled="isReadonly" @change="onParamChange('populationAmount', $event)" />
        </div>
        <div class="param-item">
          <span class="param-label">重要性水平：</span>
          <el-input-number v-model="state.samplingParams.value.materialityLevel" :controls="false" size="small"
            :disabled="isReadonly" @change="onParamChange('materialityLevel', $event)" />
        </div>
        <div class="param-item">
          <span class="param-label">抽样方法：</span>
          <el-select v-model="state.samplingParams.value.samplingMethod" size="small" :disabled="isReadonly"
            @change="onParamChange('samplingMethod', $event)">
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随机抽样" value="随机抽样" />
            <el-option label="判断抽样" value="判断抽样" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">样本量：</span>
          <span class="param-value">{{ state.samplingParams.value.sampleSize ?? '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 区域2: 增加检查明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>本期增加检查明细（H2-8）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-8')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="check-table">
        <el-table-column prop="seq" label="序号" width="50" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="name" label="工程项目" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCellChange(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="date" label="入账日期" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD"
              @change="onCellChange(row.rowId, 'date', $event)" />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="additionMethod" label="增加方式" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.additionMethod" size="small" style="width:100%"
              placeholder="选择"
              @change="onCellChange(row.rowId, 'additionMethod', $event)">
              <el-option label="出包" value="出包" />
              <el-option label="自营" value="自营" />
              <el-option label="设备购置" value="设备购置" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.additionMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="费用类别" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.category" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'category', $event)">
              <el-option label="材料" value="材料" />
              <el-option label="人工" value="人工" />
              <el-option label="机械" value="机械" />
              <el-option label="利息" value="利息" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false"
              size="small" class="amt-input" @change="onCellChange(row.rowId, 'amount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="supplier" label="供应商/施工方" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.supplier" size="small"
              @change="onCellChange(row.rowId, 'supplier', $event)" />
            <span v-else>{{ row.supplier || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 证据列：按增加方式启用/N/A -->
        <el-table-column label="合同(共用)" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.contractNo" size="small"
              :disabled="!evidenceOn(row, 'contractNo')"
              :placeholder="evidencePh(row, 'contractNo')"
              @change="onCellChange(row.rowId, 'contractNo', $event)"
            />
            <span v-else>{{ row.contractNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="监理/进度(出包)" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.progressDoc" size="small"
              :disabled="!evidenceOn(row, 'progressDoc')"
              :placeholder="evidencePh(row, 'progressDoc')"
              @change="onCellChange(row.rowId, 'progressDoc', $event)"
            />
            <span v-else>{{ row.progressDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="领料(自营)" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.materialDoc" size="small"
              :disabled="!evidenceOn(row, 'materialDoc')"
              :placeholder="evidencePh(row, 'materialDoc')"
              @change="onCellChange(row.rowId, 'materialDoc', $event)"
            />
            <span v-else>{{ row.materialDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发票(设备)" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.invoiceNo" size="small"
              :disabled="!evidenceOn(row, 'invoiceNo')"
              :placeholder="evidencePh(row, 'invoiceNo')"
              @change="onCellChange(row.rowId, 'invoiceNo', $event)"
            />
            <span v-else>{{ row.invoiceNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="验收(设备)" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.acceptanceDoc" size="small"
              :disabled="!evidenceOn(row, 'acceptanceDoc')"
              :placeholder="evidencePh(row, 'acceptanceDoc')"
              @change="onCellChange(row.rowId, 'acceptanceDoc', $event)"
            />
            <span v-else>{{ row.acceptanceDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="付款回单" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.paymentRef" size="small"
              :disabled="!evidenceOn(row, 'paymentRef')"
              :placeholder="evidencePh(row, 'paymentRef')"
              @change="onCellChange(row.rowId, 'paymentRef', $event)"
            />
            <span v-else>{{ row.paymentRef || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="capitalizable" label="资本化" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.capitalizable" size="small" style="width:78px"
              @change="onCellChange(row.rowId, 'capitalizable', $event)">
              <el-option label="-" value="" />
              <el-option label="Y" value="Y" />
              <el-option label="N" value="N" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.capitalizable || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 关联方：供 H2-17 带入 -->
        <el-table-column prop="isRelatedParty" label="是否关联方" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRelatedParty" size="small" style="width:88px"
              @change="onCellChange(row.rowId, 'isRelatedParty', $event)">
              <el-option label="-" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isRelatedParty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relatedPartyName" label="关联方名称→H2-17" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isRelatedParty === '是'"
              v-model="row.relatedPartyName" size="small"
              placeholder="必填，供带入"
              @change="onCellChange(row.rowId, 'relatedPartyName', $event)"
            />
            <span v-else>{{ row.isRelatedParty === '是' ? (row.relatedPartyName || '-') : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联关系" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isRelatedParty === '是'"
              v-model="row.relationship" size="small"
              placeholder="可选"
              @change="onCellChange(row.rowId, 'relationship', $event)"
            />
            <span v-else>{{ row.isRelatedParty === '是' ? (row.relationship || '-') : '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="📎" width="50" align="center">
          <template #default="{ row }">
            <el-button size="small" link @click="handleOcr(row.rowId)" :disabled="isReadonly">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="auditConclusion" label="检查结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.auditConclusion" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'auditConclusion', $event)">
              <el-option label="无异常" value="无异常" />
              <el-option label="存疑" value="存疑" />
              <el-option label="需调整" value="需调整" />
            </el-select>
            <el-tag v-else :type="row.auditConclusion === '无异常' ? 'success' : 'warning'" size="small">
              {{ row.auditConclusion || '待检' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-line">
        样本合计: <strong>{{ fmtAmt(state.amountTotal.value) }}</strong>
        <span style="margin-left:16px">已检查: {{ fmtAmt(state.checkedAmount.value) }}</span>
        <span style="margin-left:16px">覆盖率: {{ state.actualCoverageRate.value?.toFixed(1) ?? '-' }}%</span>
        <span style="margin-left:16px;color:var(--el-text-color-secondary)">（样本已检金额 ÷ 总体金额；对照计划比例）</span>
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
      </div>
    </el-card>

    <el-alert
      v-if="state.summary.value.evidenceGapCount > 0"
      type="info"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`有 ${state.summary.value.evidenceGapCount} 项样本适用证据或关键确认项未齐，可「证据缺口推送至 H2-3」生成索引说明行。`"
    />

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="①样本构成（特定样本+抽样）、方法及计划/实际检查比例；比例偏低须扩大样本或说明原因。②异常/存疑/需调整及证据索引（调整→H2-3）。③利息资本化见 H2-10/11；关联方见 H2-17。④核对清单完成情况简述。" :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="基于上述检查，本期抽查的在建工程增加在存在性、准确性/资本化划分及截止方面未见重大异常 / 发现以下需调整事项（详见审计说明及 H2-3）。检查比例 ___%，可为相关认定提供充分、适当的审计证据。" :disabled="isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示 / 执行核对清单</summary>
      <ul>
        <li>先选「增加方式」：出包→监理/进度；自营→领料；设备→发票+验收；不适用证据自动 N/A</li>
        <li>测试总体与 H2-2 本期增加、H2-6 借方发生额勾稽；先抽凭再逐项检查</li>
        <li>特定样本（大额/关联方/异常/年末集中）全测，其余抽样；实际覆盖率对照计划比例</li>
        <li>「是否关联方=是」并填名称后，H2-17 可一键带入</li>
        <li>资本化列：Y=应计入 CIP，N=应费用化；利息详测交叉 H2-10/H2-11</li>
        <li>检查结论「需调整」录入 H2-3；关注虚增造价及第三方配合舞弊</li>
        <li>📎 上传合同/发票后 OCR 可回填关键字段</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1604 在建工程-增加）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="1604"
        phase="final"
        :year="samplingYear"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabAdditionCheck.vue — H2-8 增加检查
 * 双区域(抽样参数+明细) + 固定列+滚动列 + OCR📎 + 抽凭
 * Spec: Task 4.10 + 6.4 + 6.5 | Requirements: 9.1-9.2, 9.5-9.8
 */
import { ref, inject, toRef, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2AdditionCheck, isEvidenceApplicable, type H2AdditionRow, type H2AdditionEvidenceField } from '../../composables/useH2AdditionCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

/** 抽凭引擎所需审计年度：优先父级传入，回退当前年 */
const samplingYear = computed(() => props.year || new Date().getFullYear())

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const showSamplingDialog = ref(false)

const state = useH2AdditionCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isReadonly = computed(() => props.isReadonly)

function onParamChange(field: string, value: any) {
  state.updateSamplingParams({ [field]: value } as any)
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

function evidenceOn(row: H2AdditionRow, field: H2AdditionEvidenceField): boolean {
  return isEvidenceApplicable(row.additionMethod, field)
}

function evidencePh(row: H2AdditionRow, field: H2AdditionEvidenceField): string {
  if (!row.additionMethod) return '先选增加方式'
  return evidenceOn(row, field) ? '填写' : 'N/A'
}

/** 打开抽凭引擎 dialog */
function handleSampling() {
  showSamplingDialog.value = true
}

/** 抽凭引擎完成后回调：将样本行填入检查表 */
function onSampleFilled(payload: any) {
  showSamplingDialog.value = false
  // 引擎 emit('filled', { samples, phase, fillMode, ... })；兼容旧数组形态
  const samples: any[] = Array.isArray(payload) ? payload : (payload?.samples ?? [])
  if (!samples.length) return
  for (const s of samples) {
    state.addRow()
    const lastRow = state.rows.value[state.rows.value.length - 1]
    if (lastRow) {
      // 增加=借方(资产1604)；SampledVoucher 字段 debitAmount/voucherDate/voucherNo/summary
      const amt = s.debitAmount ?? s.amount ?? s.creditAmount
      if (amt != null) lastRow.amount = Number(amt) || 0
      if (s.summary || s.description) lastRow.name = s.summary || s.description
      if (s.voucherNo) lastRow.contractNo = s.voucherNo
      const d = s.voucherDate ?? s.date
      if (d) lastRow.date = d
      lastRow.samplingStatus = '待检查'
    }
  }
  state.fillSamplingResults(
    samples.map((s, i) => ({
      rowId: state.rows.value[state.rows.value.length - samples.length + i]?.rowId ?? '',
      status: '待检查',
    })),
  )
}

/** 行级 OCR：📎上传→POST contract-ocr→ElMessageBox确认→merge字段 */
function handleOcr(rowId: string) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = data?.extracted_fields || {}
      if (!Object.keys(fields).length) {
        ElMessageBox.alert('OCR完成，未识别到可填充字段', '提示')
        return
      }
      const preview = Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(
        `识别结果：\n${preview}\n\n确认填入？`,
        'OCR识别结果',
        { confirmButtonText: '填入', cancelButtonText: '取消' },
      )
      // merge fields into row via composable
      state.mergeOcrResult(rowId, fields)
    } catch { /* user cancelled or request failed */ }
  }
  input.click()
}

function handleAddRow() {
  state.addRow()
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handlePushEvidenceGap() {
  const res = state.pushEvidenceGapsToH23()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-addition-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.param-item { display: flex; align-items: center; gap: 8px; }
.param-label { font-weight: 500; min-width: 90px; }
.param-value { font-weight: 600; color: var(--el-color-primary); }
.check-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.summary-line { padding: 12px 0; font-size: var(--wp-font-size, 13px); border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
