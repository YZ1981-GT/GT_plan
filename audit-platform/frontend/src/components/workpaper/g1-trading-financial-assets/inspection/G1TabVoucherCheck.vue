<template>
  <div class="g1-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G1-13 交易性金融资产检查表（凭证核对）</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="vc.addRow()">新增检查行</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info">共 {{ vc.rows.value.length }} 笔</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-13-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：抽取交易性金融资产（科目1501）凭证逐笔核对合同、结算单、报价/估值、授权审批与账务处理，确认交易真实、计量准确、记录完整。"
      class="objective-alert"
    />

    <div class="stats-bar">
      检查凭证：<b>{{ vc.rows.value.length }}</b> 笔 ·
      已抽凭：<b>{{ vc.sampledCount.value }}</b> 笔 ·
      金额合计：{{ vc.total.value.toLocaleString() }} ·
      异常：<b :class="{ warn: vc.abnormalCount.value > 0 }">{{ vc.abnormalCount.value }}</b>
    </div>

    <!-- 抽凭引擎（科目1501） -->
    <el-collapse v-if="wpId && projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1501 交易性金融资产）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1501"
          phase="final"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="year"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <el-table :data="vc.rows.value" border size="small" max-height="480">
      <el-table-column label="序号" width="60" fixed="left">
        <template #default="{ row, $index }">
          <span>{{ $index + 1 }}</span>
          <el-tooltip v-if="row.sampleSource" :content="`样本来源：${row.sampleSource}`" placement="top">
            <span class="sample-flag">📌</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column
        v-for="col in vc.columns.filter((c) => c.prop !== 'seq')"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
      >
        <template #default="{ row }">
          <el-input-number
            v-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="vc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="vc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <!-- 📎 OCR 附件列 -->
      <el-table-column label="📎" width="70" align="center">
        <template #default="{ row }">
          <el-upload
            :show-file-list="false"
            accept="image/*,.pdf"
            :before-upload="(file: File) => handleRowOcr(row.id, file)"
          >
            <el-button size="small" link :loading="ocrLoadingRowId === row.id" :disabled="isReadonly">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="vc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：（1）抽凭范围、方法及逐笔核对结果；（2）合同/结算单/报价/授权/账务处理核对的异常事项。" />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="vc.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对凭证核对检查的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>可使用自动抽凭引擎按科目 1501 抽取样本，样本自动填入检查表并标记来源。</li>
        <li>点击 📎 上传凭证扫描件，OCR 自动识别凭证信息后确认填入当前行。</li>
        <li>逐笔核对合同、结算单、报价/估值、授权审批、账务处理。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, computed, ref, inject, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useG1VoucherCheck } from '../../composables/useG1VoucherCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import type { SampledVoucher, FillMode, Phase } from '../../composables/useSamplingAlgorithms'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
  bsDate?: string
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const vc = useG1VoucherCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-13-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const year = computed(() => {
  if (props.bsDate && props.bsDate.length >= 4) return parseInt(props.bsDate.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

// --- 抽凭引擎样本填入 ---
function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  vc.applySamplingResults(payload.samples, payload.fillMode)
}

// --- 行级 OCR：上传凭证扫描件 → contract-ocr 识别 → 确认 → merge 填入当前行 ---
const ocrLoadingRowId = ref<string | null>(null)

const OCR_FIELD_MAP: Record<string, string> = {
  date: 'voucherDate', 凭证日期: 'voucherDate', voucher_date: 'voucherDate',
  voucher_no: 'voucherNo', 凭证号: 'voucherNo',
  summary: 'summary', 摘要: 'summary',
  security_name: 'securityName', 证券名称: 'securityName',
  amount: 'amount', 金额: 'amount',
  counter_account: 'counterAccount', 对方科目: 'counterAccount',
}

async function handleRowOcr(rowId: string, file: File): Promise<boolean> {
  if (props.isReadonly || !props.wpId) return false
  ocrLoadingRowId.value = rowId
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return false
    }
    const patch: Record<string, any> = {}
    for (const [ocrKey, val] of Object.entries(fields)) {
      const target = OCR_FIELD_MAP[ocrKey]
      if (target && val != null && String(val).trim() !== '') patch[target] = val
    }
    if (Object.keys(patch).length === 0) {
      ElMessage.info('OCR完成，识别字段无法匹配')
      return false
    }
    const preview = Object.entries(patch).map(([k, v]) => `${k}: ${v}`).join('，')
    await ElMessageBox.confirm(`识别到凭证信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
    })
    vc.updateRow(rowId, { ...patch, attachment: file.name })
    ElMessage.success('已填入识别结果')
  } catch (e) {
    if (e !== 'cancel') ElMessage.warning('OCR识别失败')
  } finally {
    ocrLoadingRowId.value = null
  }
  return false
}
</script>

<style scoped>
.g1-voucher-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-voucher-check :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-voucher-check :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.stats-bar { margin-bottom: 10px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #f56c6c; }
.sampling-collapse { margin-bottom: 12px; }
.sample-flag { margin-left: 2px; cursor: help; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
