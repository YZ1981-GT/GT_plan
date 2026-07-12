<template>
  <div class="f2-contract-check">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 合同履约成本按 CAS14 号确认，须同时满足：与合同（或预期取得的合同）直接相关、增加未来用于履约的资源、预期能够收回。</p>
        <p>2. 按重要性与可容忍错报确定样本量，抽取凭证检查其真实性、计量准确性与期间归属。</p>
        <p>3. 关注是否将不符合资本化条件的支出（如管理费用、非正常消耗）错误计入合同履约成本。</p>
        <p>4. 覆盖率偏低（低于阈值标红）时应扩大样本量或补充分析性程序，并在审计说明中记录。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：检查合同履约成本的真实性、完整性与计量准确性，确认其符合资本化条件且期间归属正确。</template>
    </el-alert>

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

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="chk.addRow()">+ 新增样本</el-button>
        <span class="stat-text">检查合计: {{ chk.checkedTotal.value.toLocaleString() }}</span>
        <span class="stat-text" :class="{ warn: chk.isCoverageLow.value }">覆盖率 {{ chk.coverageRatio.value.toFixed(1) }}%</span>
        <el-tag v-if="chk.issueCount.value > 0" type="danger" size="small">{{ chk.issueCount.value }} 笔异常</el-tag>
      </div>
      <div class="toolbar-right">
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
        <GtIndexChip value="wp:F2-56" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ chk.enrichedRows.value.length }} 行</el-tag>
      </div>
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

    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
        </div>
      </template>
      <el-input v-model="chk.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请说明合同履约成本抽样检查结果、异常笔数及处理情况……" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, type Ref } from 'vue'
import { useF2ContractCostCheck } from '../../composables/useF2ContractCostCheck'
import { useF2SpecialContractOcr } from '../../composables/useF2SpecialContractOcr'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import type { SampledVoucher, FillMode } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

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
.f2-contract-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-contract-check :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-contract-check :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.params-card { margin-bottom: 12px; }
.params-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.params-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.stat-text { font-size: 12px; color: #606266; }
.sampling-collapse { margin-bottom: 10px; }
.warn { color: #e6a23c; font-weight: 600; }
:deep(.error-row) { background: #fef0f0; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
