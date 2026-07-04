<template>
  <div class="f2-impairment-test">
    <h3 class="title">跌价准备测试 F2-47</h3>
    <el-input v-model="imp.samplingNote.value" type="textarea" :rows="2" :disabled="isReadonly" placeholder="抽样参数说明..." class="sampling" />

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="imp.addRow()">+ 新增样本</el-button>
      <el-button size="small" :disabled="isReadonly" @click="imp.publishImpairmentCalculated()">发布跌价测算</el-button>
      <el-tag v-if="imp.needsConclusionCount.value > 0" type="warning" size="small">
        {{ imp.needsConclusionCount.value }} 笔需填结论
      </el-tag>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-47"
        :disabled="isReadonly"
        ai-section="impairment-evaluation"
        :existing-content="imp.testConclusion.value"
        :related-context="{ needsConclusion: imp.needsConclusionCount.value }"
        ai-title="AI 生成 · 跌价测试评价"
        review-section="F2-47-conclusion"
        @ai-filled="(t: string) => { imp.testConclusion.value = t }"
      />
    </div>

    <el-segmented v-model="imp.activeSegment.value" :options="segments" size="small" class="segment-bar" />

    <el-table :data="imp.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.requiredProvision > 0 && !row.conclusion ? 'warn-row' : ''">
      <el-table-column prop="seq" label="序号" width="55" fixed />
      <el-table-column label="品名" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(v: string) => imp.updateRow(row.rowId, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>

      <template v-if="imp.activeSegment.value === 'basic'">
        <el-table-column label="数量" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.qty" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => imp.updateRow(row.rowId, { qty: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="单位成本" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.unitCost" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => imp.updateRow(row.rowId, { unitCost: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="账面成本" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ fmt(row.bookCost) }}</span></template>
        </el-table-column>
      </template>

      <template v-else-if="imp.activeSegment.value === 'nrv'">
        <el-table-column label="售价" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.sellingPrice" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => imp.updateRow(row.rowId, { sellingPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="完工成本" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.completionCost" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => imp.updateRow(row.rowId, { completionCost: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="销售费用" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.sellingExpense" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => imp.updateRow(row.rowId, { sellingExpense: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="NRV" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ fmt(row.nrv) }}</span></template>
        </el-table-column>
        <el-table-column label="应计提" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ fmt(row.requiredProvision) }}</span></template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="已计提" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.existingProvision" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => imp.updateRow(row.rowId, { existingProvision: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="应补提" width="90" align="right">
          <template #default="{ row }">{{ fmt(row.additionalProvision) }}</template>
        </el-table-column>
        <el-table-column label="应转回" width="90" align="right">
          <template #default="{ row }">{{ fmt(row.reversal) }}</template>
        </el-table-column>
        <el-table-column label="结论" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small"
              @change="(v: string) => imp.updateRow(row.rowId, { conclusion: v })" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="imp.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
      <el-table-column v-if="wpId && !isReadonly" label="📎" width="45" align="center" fixed="right">
        <template #default="{ row }">
          <el-upload
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.png,.jpg,.jpeg"
            :disabled="ocrLoadingId === row.rowId"
            @change="(uploadFile: any) => handleOcrUpload(row.rowId, uploadFile?.raw)"
          >
            <el-button link size="small" :loading="ocrLoadingId === row.rowId">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary">
      合计账面 {{ fmt(imp.totalSummary.value.bookCost) }} |
      合计NRV {{ fmt(imp.totalSummary.value.nrv) }} |
      应计提 {{ fmt(imp.totalSummary.value.requiredProvision) }} |
      已计提 {{ fmt(imp.totalSummary.value.existingProvision) }}
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="conclusion-title">测试结论</span></template>
      <el-input v-model="imp.testConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <p>选取样本存货品种，核算可变现净值(NRV=估计售价-估计完工成本-估计销售费用-税金)并与账面比较，验证跌价准备计提的充分性。关注应计提>0但结论为空的项目。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, type Ref } from 'vue'
import { useF2ImpairmentTest } from '../../composables/useF2ImpairmentTest'
import { useF2ImpairmentOcr } from '../../composables/useF2ImpairmentOcr'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const imp = useF2ImpairmentTest({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2ImpairmentOcr(wpIdRef)

function handleOcrUpload(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge(rowId, file, (id, patch) => imp.updateRow(id, patch))
}

const segments = [
  { label: '基础信息', value: 'basic' },
  { label: 'NRV测算', value: 'nrv' },
  { label: '跌价结论', value: 'conclusion' },
]

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.f2-impairment-test { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.sampling { margin-bottom: 8px; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.segment-bar { margin-bottom: 12px; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
.summary { margin: 12px 0; font-size: 12px; }
.conclusion-card { margin-top: 12px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 12px; font-size: 13px; }
.conclusion-title { font-weight: 600; color: #606266; }
.guidance-details { margin-top: 12px; font-size: 12px; color: #909399; }
.guidance-details summary { cursor: pointer; font-weight: 500; }
.guidance-details p { margin: 6px 0 0 12px; line-height: 1.6; }
:deep(.warn-row) { background: #fdf6ec; }
</style>
