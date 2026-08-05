<template>
  <div class="g1-voucher-check" data-testid="g1-voucher-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-13 交易性金融资产检查表</h3>
        <p class="sheet-sub">抽样计划 → 本期/期后凭证核对（六项）→ 检查比例 → 说明与结论</p>
      </div>
      <div class="head-actions">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-13"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="vc.addRow()">新增检查行</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-3" /></span>
        <el-button size="small" @click="openReviewDialog('G1-13-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="一、审计目标：①核实交易性金融资产存在且由被审计单位持有；②核实权属清晰、无未披露限制/质押；③核实公允价值计量与列报披露符合准则。"
    />

    <!-- 二、样本选取 -->
    <section class="plan-card">
      <header class="plan-head">
        <div>
          <h4>二、样本选取标准与根据</h4>
          <p>测试总体、金额门槛、关联方、抽样方法（可与抽凭引擎配合）</p>
        </div>
      </header>
      <div class="plan-grid">
        <label>
          <span>总体借方发生额</span>
          <el-input-number
            :model-value="vc.samplingPlan.value.populationDebit"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: number | undefined) => vc.updateSamplingPlan({ populationDebit: v ?? 0 })"
          />
        </label>
        <label>
          <span>总体贷方发生额</span>
          <el-input-number
            :model-value="vc.samplingPlan.value.populationCredit"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: number | undefined) => vc.updateSamplingPlan({ populationCredit: v ?? 0 })"
          />
        </label>
        <label>
          <span>总体笔数</span>
          <el-input-number
            :model-value="vc.samplingPlan.value.populationCount"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: number | undefined) => vc.updateSamplingPlan({ populationCount: v ?? 0 })"
          />
        </label>
        <label>
          <span>金额门槛</span>
          <el-input
            :model-value="vc.samplingPlan.value.amountThreshold"
            size="small"
            :disabled="isReadonly"
            placeholder="如：单笔≥50万元"
            @update:model-value="(v: string) => vc.updateSamplingPlan({ amountThreshold: v })"
          />
        </label>
        <label>
          <span>抽样方法</span>
          <el-select
            :model-value="vc.samplingPlan.value.method"
            size="small"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string) => vc.updateSamplingPlan({ method: v as any })"
          >
            <el-option v-for="o in G1_SAMPLING_METHOD_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </label>
        <label class="check-label">
          <el-checkbox
            :model-value="vc.samplingPlan.value.includeRelatedParty"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => vc.updateSamplingPlan({ includeRelatedParty: !!v })"
          />
          <span>全部关联方交易纳入样本</span>
        </label>
      </div>
      <el-input
        :model-value="vc.samplingPlan.value.criteriaNote"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 3 }"
        size="small"
        :disabled="isReadonly"
        placeholder="其他选取标准说明（如 IDEA 导出条件、分层抽样等）"
        class="plan-note"
        @update:model-value="(v: string) => vc.updateSamplingPlan({ criteriaNote: v })"
      />
    </section>

    <!-- 抽凭引擎 -->
    <el-collapse v-if="wpId && projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1501）— 填入当前区段" name="sampling">
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

    <!-- 状态栏 -->
    <div class="status-bar">
      <span>
        当前区段样本 <b>{{ vc.periodRows.value.length }}</b> 笔 ·
        借方 {{ fmt(vc.sampleDebit.value) }} · 贷方 {{ fmt(vc.sampleCredit.value) }}
      </span>
      <span>
        检查比例
        <b :class="{ warn: ratioPct != null && ratioPct < 0.05 }">
          {{ ratioPct == null ? '—' : `${(ratioPct * 100).toFixed(2)}%` }}
        </b>
        <small v-if="ratioPct == null">（请先填写测试总体）</small>
      </span>
      <span>
        异常 <b :class="{ warn: vc.abnormalCount.value > 0 }">{{ vc.abnormalCount.value }}</b> ·
        待核 <b>{{ vc.pendingCheckCount.value }}</b> ·
        抽凭来源 {{ vc.sampledCount.value }}
      </span>
    </div>

    <!-- 三、测试：本期 / 期后 -->
    <div class="seg-row">
      <el-segmented v-model="vc.activePeriod.value" :options="periodOptions" size="small" />
      <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
    </div>

    <p class="check-legend">
      <strong>核对内容：</strong>
      <span v-for="item in vc.CHECK_ITEMS" :key="item.key" class="legend-item" :title="item.hint">
        {{ item.label }}
      </span>
    </p>

    <el-table
      :data="vc.periodRows.value"
      border
      size="small"
      max-height="460"
      :row-class-name="({ row }) => row.isAbnormal ? 'abnormal-row' : ''"
    >
      <el-table-column label="#" width="52" fixed>
        <template #default="{ row, $index }">
          <span>{{ $index + 1 }}</span>
          <el-tooltip v-if="row.sampleSource" :content="`样本来源：${row.sampleSource}`" placement="top">
            <span class="sample-flag">📌</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="日期" width="118">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.voucherDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              @update:model-value="(v: string) => vc.updateRow(row.id, { voucherDate: v || '' })"
            />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="100">
          <template #default="{ row }">
            <el-input :model-value="row.voucherNo" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => vc.updateRow(row.id, { voucherNo: v })" />
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="130">
          <template #default="{ row }">
            <el-input :model-value="row.businessContent" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => vc.updateRow(row.id, { businessContent: v })" />
          </template>
        </el-table-column>
        <el-table-column label="借方科目" width="110">
          <template #default="{ row }">
            <el-input :model-value="row.debitAccount" size="small" :disabled="isReadonly" placeholder="1501…"
              @update:model-value="(v: string) => vc.updateRow(row.id, { debitAccount: v })" />
          </template>
        </el-table-column>
        <el-table-column label="贷方科目" width="110">
          <template #default="{ row }">
            <el-input :model-value="row.creditAccount || row.counterAccount" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => vc.updateRow(row.id, { creditAccount: v, counterAccount: v })" />
          </template>
        </el-table-column>
        <el-table-column label="借方金额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.debitAmount" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => vc.updateRow(row.id, { debitAmount: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
              :disabled="isReadonly"
              @update:model-value="(v: number | undefined) => vc.updateRow(row.id, { creditAmount: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>

      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="📎" width="56" align="center">
          <template #default="{ row }">
            <el-upload
              :show-file-list="false"
              accept="image/*,.pdf"
              :disabled="isReadonly"
              :before-upload="(file: File) => handleRowOcr(row.id, file)"
            >
              <el-button size="small" link :loading="ocrLoadingRowId === row.id" :disabled="isReadonly">📎</el-button>
            </el-upload>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="140">
          <template #default="{ row }">
            <el-input
              :model-value="row.supportingDocs"
              size="small"
              :disabled="isReadonly"
              placeholder="合同/交割单/银行回单…"
              @update:model-value="(v: string) => vc.updateRow(row.id, { supportingDocs: v })"
            />
          </template>
        </el-table-column>
        <el-table-column
          v-for="item in vc.CHECK_ITEMS"
          :key="item.key"
          :label="item.label.replace(/^[①-⑥]/, '')"
          width="72"
          align="center"
        >
          <template #header>
            <el-tooltip :content="item.hint" placement="top">
              <span>{{ item.label.replace(/^[①-⑥]/, '') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox
              v-if="!isReadonly"
              :model-value="row[item.key] === true"
              :indeterminate="row[item.key] === null"
              @change="(v: boolean | string | number) => vc.setCheck(row.id, item.key, !!v)"
            />
            <span v-else>{{ row[item.key] === true ? '✓' : row[item.key] === false ? '✗' : '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="索引" width="88">
          <template #default="{ row }">
            <el-input :model-value="row.indexRef" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => vc.updateRow(row.id, { indexRef: v })" />
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="88" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
              {{ row.isAbnormal ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.abnormalDesc" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => vc.updateRow(row.id, { abnormalDesc: v, isAbnormal: !!v || row.isAbnormal })" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
              @update:model-value="(v: string) => vc.updateRow(row.id, { remark: v })" />
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="vc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-bar">
      <span>本区段合计：借方 {{ fmt(vc.sampleDebit.value) }} · 贷方 {{ fmt(vc.sampleCredit.value) }}</span>
      <span>
        本期发生额（总体）{{ fmt(vc.populationAmount.value) }} ·
        检查比例 {{ ratioPct == null ? '—' : `${(ratioPct * 100).toFixed(2)}%` }}
      </span>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusionProxy"
      note-ai-section="voucher-note"
      conclusion-ai-section="voucher-check-conclusion"
      note-placeholder="四、审计说明：抽样范围与方法、本期/期后检查覆盖、六项核对异常及处理（可交叉索引 G1-3）。"
      note-hint="覆盖总体、样本、核对程序与异常事项。"
      conclusion-placeholder="五、审计结论：A 未见异常；B 除重大调整外未见异常；C 因未调整或范围受限无法确认。"
      :related-context="{
        样本笔数: vc.periodRows.value.length,
        检查比例: ratioPct == null ? '未填总体' : `${(ratioPct * 100).toFixed(1)}%`,
        异常: vc.abnormalCount.value,
        待核: vc.pendingCheckCount.value,
      }"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>先填写「测试总体」再看检查比例；总体为 0 时比例显示「—」，避免 Excel 的 #DIV/0!。</li>
        <li>「本期发生额」与「期后处置/新售」分表编制；抽凭默认写入当前区段。</li>
        <li>六项核对：单据齐全、凭证相符、账务正确、期间正确、公允价值正确、授权恰当；任一项「否」自动标异常。</li>
        <li>支持性文件可注明：付款审批、银行回单、投资协议、交易交割单等；📎 可 OCR 填入。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, computed, ref, inject, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useG1VoucherCheck,
  G1_SAMPLING_METHOD_OPTIONS,
} from '../../composables/useG1VoucherCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'
import type { SampledVoucher, FillMode, Phase } from '../../composables/useSamplingAlgorithms'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
  bsDate?: string
}>()

const wpId = computed(() => props.wpId ?? '')
const emit = defineEmits<{ imported: [] }>()
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const vc = useG1VoucherCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const periodOptions = [
  { label: '三、本期发生额检查', value: 'current' },
  { label: '三、期后处置/新售', value: 'subsequent' },
]
const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '异常/索引', value: 'result' },
]

const AUDIT_NOTE_KEY = 'G1-13-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const conclusionProxy = computed({
  get: () => vc.auditConclusion.value,
  set: (v: string) => { vc.auditConclusion.value = v },
})

const ratioPct = computed(() => vc.inspectionRatio.value)

const year = computed(() => {
  if (props.bsDate && props.bsDate.length >= 4) return parseInt(props.bsDate.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

function fmt(n: number): string {
  return (n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'G1',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => props.debouncedSave(itemId, { remark, conclusion: null }),
  isReadonly: computed(() => props.isReadonly === true),
})

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  vc.applySamplingResults(payload.samples, payload.fillMode)
  ElMessage.success(`已填入 ${payload.samples.length} 笔至「${vc.activePeriod.value === 'current' ? '本期' : '期后'}」`)
}

function onImported() {
  emit('imported')
  vc.loadAll()
}

const ocrLoadingRowId = ref<string | null>(null)
const OCR_FIELD_MAP: Record<string, string> = {
  date: 'voucherDate', 凭证日期: 'voucherDate', voucher_date: 'voucherDate',
  voucher_no: 'voucherNo', 凭证号: 'voucherNo',
  summary: 'businessContent', 摘要: 'businessContent',
  amount: 'debitAmount', 金额: 'debitAmount',
  counter_account: 'creditAccount', 对方科目: 'creditAccount',
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
    if (!Object.keys(patch).length) {
      ElMessage.info('OCR完成，识别字段无法匹配')
      return false
    }
    const preview = Object.entries(patch).map(([k, v]) => `${k}: ${v}`).join('，')
    await ElMessageBox.confirm(`识别到凭证信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
    })
    vc.updateRow(rowId, { ...patch, attachment: file.name, supportingDocs: file.name })
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
.g1-voucher-check { padding: 4px 4px 20px; font-size: var(--wp-font-size, 13px); color: #303133; }
.section-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.title-block { min-width: 220px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #86909c; }
.head-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 10px; }

.plan-card {
  margin-bottom: 12px; border: 1px solid #e8ecf2; border-left: 3px solid #3d6b8e;
  background: #f7fafc; border-radius: 6px; padding: 12px 14px;
}
.plan-head h4 { margin: 0; font-size: 13px; font-weight: 600; color: #1f2a37; }
.plan-head p { margin: 2px 0 10px; font-size: 12px; color: #86909c; }
.plan-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px 14px; margin-bottom: 8px;
}
.plan-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #606266; }
.plan-grid .check-label { flex-direction: row; align-items: center; gap: 8px; padding-top: 18px; }
.plan-note { width: 100%; }

.sampling-collapse { margin-bottom: 10px; }
.status-bar {
  display: flex; flex-wrap: wrap; gap: 12px 20px; margin-bottom: 10px;
  padding: 8px 12px; background: #f8f9fb; border: 1px solid #ebeef5; border-radius: 6px;
  font-size: 12px; color: #606266;
}
.status-bar .warn { color: #f56c6c; }
.seg-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 8px; }
.check-legend {
  margin: 0 0 8px; font-size: 12px; color: #86909c; line-height: 1.6;
  display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center;
}
.legend-item { cursor: help; border-bottom: 1px dashed #c0c4cc; }
.sample-flag { margin-left: 2px; cursor: help; }
.totals-bar {
  display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px;
  margin: 8px 0 12px; padding: 8px 10px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 4px; font-size: 12px; color: #606266;
}
:deep(.abnormal-row) { --el-table-tr-bg-color: #fff5f5; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.6; }
</style>
