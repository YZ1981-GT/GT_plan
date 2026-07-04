<template>
  <div class="f2-contract-check">
    <h3 class="title">合同履约成本检查 F2-56</h3>

    <el-card shadow="never" class="params-card">
      <template #header>抽样参数</template>
      <div class="params-grid">
        <label>总体金额
          <el-input-number :model-value="chk.params.value.populationAmount" size="small" :controls="false"
            :disabled="isReadonly" @change="(v: number) => chk.updateParams({ populationAmount: v ?? 0 })" />
        </label>
        <label>重要性
          <el-input-number :model-value="chk.params.value.materiality" size="small" :controls="false"
            :disabled="isReadonly" @change="(v: number) => chk.updateParams({ materiality: v ?? 0 })" />
        </label>
        <label>可容忍错报
          <el-input-number :model-value="chk.params.value.tolerableMisstatement" size="small" :controls="false"
            :disabled="isReadonly" @change="(v: number) => chk.updateParams({ tolerableMisstatement: v ?? 0 })" />
        </label>
        <label>样本量
          <el-input-number :model-value="chk.params.value.sampleSize" size="small" :controls="false"
            :disabled="isReadonly" @change="(v: number) => chk.updateParams({ sampleSize: v ?? 0 })" />
        </label>
        <label>抽样方法
          <el-input v-if="!isReadonly" :model-value="chk.params.value.method" size="small"
            @change="(v: string) => chk.updateParams({ method: v })" />
          <span v-else>{{ chk.params.value.method }}</span>
        </label>
      </div>
    </el-card>

    <el-collapse v-if="wpId && projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1410 合同履约成本）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1410"
          phase="final"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="chk.addRow()">+ 新增样本</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-56"
        :disabled="isReadonly"
        ai-section="contract-cost-note"
        :existing-content="chk.auditNote.value"
        review-section="F2-56-note"
        @ai-filled="(t: string) => { chk.auditNote.value = t }"
      />
      <span>检查合计: {{ chk.checkedTotal.value.toLocaleString() }}</span>
      <span :class="{ warn: chk.isCoverageLow.value }">覆盖率 {{ chk.coverageRatio.value.toFixed(1) }}%</span>
      <el-tag v-if="chk.issueCount.value > 0" type="danger" size="small">{{ chk.issueCount.value }} 笔异常</el-tag>
    </div>

    <el-table :data="chk.enrichedRows.value" border size="small" max-height="440"
      :row-class-name="({ row }) => row.hasIssue ? 'error-row' : ''">
      <el-table-column label="项目" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
            @change="(v: string) => chk.updateRow(row.id, { projectName: v })" />
          <span v-else>{{ row.projectName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证日期" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small"
            @change="(v: string) => chk.updateRow(row.id, { voucherDate: v })" />
          <span v-else>{{ row.voucherDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
            @change="(v: string) => chk.updateRow(row.id, { voucherNo: v })" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => chk.updateRow(row.id, { amount: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="是否正确" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isCorrect" size="small"
            @change="(v: '是'|'否') => chk.updateRow(row.id, { isCorrect: v })">
            <el-option label="是" value="是" /><el-option label="否" value="否" />
          </el-select>
          <span v-else>{{ row.isCorrect }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="wpId && !isReadonly" label="📎" width="45" align="center">
        <template #default="{ row }">
          <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg"
            :disabled="ocrLoadingId === row.id"
            @change="(f: any) => handleOcr(row.id, f?.raw)">
            <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="chk.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <h4>审计说明</h4>
    <el-input v-model="chk.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, type Ref } from 'vue'
import { useF2ContractCostCheck } from '../../composables/useF2ContractCostCheck'
import { useF2SpecialContractOcr } from '../../composables/useF2SpecialContractOcr'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import type { SampledVoucher, FillMode } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import F2SheetToolbar from '../../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const chk = useF2ContractCostCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const { ocrLoadingId, uploadAndMerge } = useF2SpecialContractOcr(
  toRef(() => props.wpId || '') as Ref<string>,
)

const auditYear = computed(() => props.auditYear ?? new Date().getFullYear() - 1)

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode }) {
  chk.fillFromSampling(payload.samples, payload.fillMode)
}

function handleOcr(rowId: string, file?: File) {
  if (!file || !props.wpId) return
  void uploadAndMerge(rowId, file, (id, patch) => chk.updateRow(id, patch))
}
</script>

<style scoped>
.f2-contract-check { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.params-card { margin-bottom: 12px; }
.params-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.params-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.sampling-collapse { margin-bottom: 10px; }
.warn { color: #e6a23c; font-weight: 600; }
:deep(.error-row) { background: #fef0f0; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
