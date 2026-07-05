<template>
  <div class="g12-vc">
    <div class="toolbar">
      <h3>G12-6 凭证检查</h3>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="vc.addRow()">+ 新增</el-button>
      <GtVoucherSamplingEngine v-if="wpId && projectId" :project-id="projectId" :account-codes="['6103']" dialog-mode />
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-6" :disabled="isReadonly" @imported="emit('imported')" />
      <GtReviewTrigger section-id="G12-6-voucher" />
    </div>

    <div class="stats">
      借贷：{{ vc.debitTotal.value.toFixed(2) }} / {{ vc.creditTotal.value.toFixed(2) }} ·
      <span :class="vc.isBalanced.value ? 'ok' : 'bad'">{{ vc.isBalanced.value ? '平衡' : '不平衡' }}</span> ·
      异常 {{ vc.abnormalCount.value }}
    </div>

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ vc.rows.value.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '分区编辑' }} · 双击行切换编辑
      </el-alert>
      <el-button size="small" @click="toggleBrowseMode">
        {{ browseMode ? '切换分区编辑' : '切换虚拟速览' }}
      </el-button>
    </div>

    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="vc.rows.value"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="36"
      :header-height="40"
      :row-event-handlers="rowEventHandlers"
      fixed
      class="virtual-table"
      data-testid="g12-vc-virtual-table"
    />

    <template v-else>
    <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />

    <el-table :data="vc.rows.value" border size="small" style="font-size:13px;margin-top:8px"
      max-height="480" :row-class-name="rowClassName">
      <el-table-column label="#" prop="seq" width="44" fixed />

      <!-- Tab1: 凭证基础 7列 -->
      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="日期" width="110">
          <template #default="{ row }">
            <el-input v-model="row.voucherDate" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'voucherDate', v)" />
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'voucherNo', v)" />
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.businessContent" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'businessContent', v)" />
          </template>
        </el-table-column>
        <el-table-column label="套期关系编号" width="110">
          <template #default="{ row }">
            <el-input v-model="row.hedgeRelationId" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'hedgeRelationId', v)" />
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="110">
          <template #default="{ row }">
            <el-input v-model="row.counterAccount" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'counterAccount', v)" />
          </template>
        </el-table-column>
        <el-table-column label="借方" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.debitAmount" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => vc.updateCell(row.rowId, 'debitAmount', v)" />
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.creditAmount" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => vc.updateCell(row.rowId, 'creditAmount', v)" />
          </template>
        </el-table-column>
      </template>

      <!-- Tab2: 核对内容 7列 -->
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="📎" width="70" align="center">
          <template #default="{ row }">
            <el-upload :show-file-list="false" accept="image/*,.pdf"
              :before-upload="(f: File) => handleOcr(row.rowId, f)">
              <el-button link size="small" :loading="ocrLoading === row.rowId" :disabled="isReadonly">📎</el-button>
            </el-upload>
            <span v-if="row.attachment" class="attach-name">{{ row.attachment }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.supportingDocDesc" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'supportingDocDesc', v)" />
          </template>
        </el-table-column>
        <el-table-column label="原始凭证" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.check1OriginalComplete" :disabled="isReadonly"
              @change="(v: boolean) => vc.updateCell(row.rowId, 'check1OriginalComplete', v)" />
          </template>
        </el-table-column>
        <el-table-column label="授权批准" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.check2Authorization" :disabled="isReadonly"
              @change="(v: boolean) => vc.updateCell(row.rowId, 'check2Authorization', v)" />
          </template>
        </el-table-column>
        <el-table-column label="账务处理" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.check3Accounting" :disabled="isReadonly"
              @change="(v: boolean) => vc.updateCell(row.rowId, 'check3Accounting', v)" />
          </template>
        </el-table-column>
        <el-table-column label="套期文档" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.check4HedgeDesignation" :disabled="isReadonly"
              @change="(v: boolean) => vc.updateCell(row.rowId, 'check4HedgeDesignation', v)" />
          </template>
        </el-table-column>
        <el-table-column label="FV依据" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.check5FVValuation" :disabled="isReadonly"
              @change="(v: boolean) => vc.updateCell(row.rowId, 'check5FVValuation', v)" />
          </template>
        </el-table-column>
      </template>

      <!-- Tab3: 结论 5列 -->
      <template v-else>
        <el-table-column label="索引" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small"
              @change="(v: string) => vc.updateCell(row.rowId, 'indexNo', v)" />
            <GtIndexChip v-else-if="row.indexNo" :value="row.indexNo" />
          </template>
        </el-table-column>
        <el-table-column label="异常" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">{{ row.isAbnormal ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.abnormalDesc" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'abnormalDesc', v)" />
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90">
          <template #default="{ row }">
            <el-select v-model="row.riskLevel" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'riskLevel', v)">
              <el-option v-for="l in G12_RISK_LEVELS" :key="l.value" :label="l.label" :value="l.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly"
              @change="(v: string) => vc.updateCell(row.rowId, 'remark', v)" />
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="vc.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useG12VoucherCheck } from '../../composables/useG12VoucherCheck'
import type { GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../../composables/gCycleCutoffFill'
import { useWorkpaperBrowseMode } from '../../composables/useWorkpaperBrowseMode'
import { virtualTextCol } from '../../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import { G12_RISK_LEVELS } from '../../composables/g12Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()

const vc = useG12VoucherCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('seq', '#', 44),
  virtualTextCol('voucherDate', '日期', 100),
  virtualTextCol('voucherNo', '凭证号', 100),
  virtualTextCol('businessContent', '业务内容', 180),
  virtualTextCol('debitAmount', '借方', 100),
  virtualTextCol('creditAmount', '贷方', 100),
  virtualTextCol('isAbnormal', '异常', 72),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: computed(() => vc.rows.value),
  virtualColumns,
  threshold: 50,
  tableWidth: 900,
  tableHeight: 480,
})

const ocrLoading = ref<string | null>(null)

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  vc.applyCutoffResults(detail.samples, detail.fillMode)
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g12, onCutoffFilled as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g12, onCutoffFilled as EventListener)
})

async function handleOcr(rowId: string, file: File) {
  if (props.isReadonly || !props.wpId) return false
  ocrLoading.value = rowId
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) { ElMessage.info('OCR未识别到字段'); return false }
    await ElMessageBox.confirm(`识别到 ${Object.keys(fields).length} 个字段，填入当前行？`, 'OCR')
    vc.updateCell(rowId, 'attachment', file.name)
    if (fields.voucher_no) vc.updateCell(rowId, 'voucherNo', fields.voucher_no)
    if (fields.date) vc.updateCell(rowId, 'voucherDate', fields.date)
    ElMessage.success('OCR已填入')
  } catch (e) {
    if (e !== 'cancel') ElMessage.warning('OCR失败，请手动填写')
  } finally {
    ocrLoading.value = null
  }
  return false
}

function rowClassName({ row }: { row: { isAbnormal: boolean } }): string {
  return row.isAbnormal ? 'g12-vc-abnormal' : ''
}
</script>

<style scoped>
.g12-vc { padding: 12px; font-size: 13px; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.stats { font-size: 12px; margin-bottom: 8px; color: #606266; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.virtual-hint { flex: 1; margin: 0; }
.ok { color: #67c23a; }
.bad { color: #f56c6c; font-weight: 600; }
.attach-name { font-size: 11px; color: #909399; display: block; max-width: 60px; overflow: hidden; text-overflow: ellipsis; }
:deep(.g12-vc-abnormal) { background: #fef0f0 !important; }
</style>
