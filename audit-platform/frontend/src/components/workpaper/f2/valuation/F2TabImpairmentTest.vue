<template>
  <div class="f2-impairment-test">
    <h3 class="title">跌价准备测试 F2-47</h3>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 期末存货按成本与可变现净值孰低计量，可变现净值(NRV)=估计售价 − 估计完工成本 − 估计销售费用 − 相关税费（CAS 1 号存货）。</p>
        <p>2. 灰色底纹列为自动计算列（账面成本、NRV、应计提、应补提、应转回），系统据录入的售价/成本自动测算，不可手工编辑。</p>
        <p>3. "应计提>0 但结论为空"的行自动标橙，须逐项填写测试结论；应补提与应转回据已计提与应计提的差额自动判定。</p>
        <p>4. 关注售价、完工成本、销售费用估计的合理性与证据（近期售价、订单、销售政策），评价跌价准备计提充分性。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：抽取样本存货品种，重新计算可变现净值并与账面成本比较，验证存货跌价准备计提的充分性与准确性，防止存货高估。"
      class="objective-alert"
    />

    <el-input v-model="imp.samplingNote.value" type="textarea" :rows="2" :disabled="isReadonly" placeholder="抽样参数说明..." class="sampling" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="imp.addRow()">+ 新增样本</el-button>
        <el-button size="small" :disabled="isReadonly" @click="imp.publishImpairmentCalculated()">发布跌价测算</el-button>
        <el-segmented v-model="imp.activeSegment.value" :options="segments" size="small" />
        <el-tag v-if="imp.needsConclusionCount.value > 0" type="warning" size="small">
          {{ imp.needsConclusionCount.value }} 笔需填结论
        </el-tag>
      </div>
      <div class="toolbar-right">
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
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ imp.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

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
        <el-table-column label="账面成本" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula" title="数量 × 单位成本">{{ fmt(row.bookCost) }}</span></template>
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
        <el-table-column label="NRV" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula" title="售价 − 完工成本 − 销售费用">{{ fmt(row.nrv) }}</span></template>
        </el-table-column>
        <el-table-column label="应计提" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula" title="账面成本 − NRV（不小于0）">{{ fmt(row.requiredProvision) }}</span></template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="已计提" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.existingProvision" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => imp.updateRow(row.rowId, { existingProvision: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="应补提" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula" title="应计提 − 已计提（大于0时补提）">{{ fmt(row.additionalProvision) }}</span></template>
        </el-table-column>
        <el-table-column label="应转回" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula" title="已计提 − 应计提（大于0时转回，限原计提数内）">{{ fmt(row.reversal) }}</span></template>
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

    <el-card shadow="never" class="opinion-card">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">测试结论</span></div>
      </template>
      <el-input v-model="imp.testConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly"
        placeholder="跌价准备测试结论..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef, type Ref } from 'vue'
import { useF2ImpairmentTest } from '../../composables/useF2ImpairmentTest'
import { useF2ImpairmentOcr } from '../../composables/useF2ImpairmentOcr'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
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
.f2-impairment-test :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-impairment-test :deep(.el-table .cell) { font-size: 13px !important; }
.title { margin: 0 0 8px; }
.sampling { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
.summary { margin: 12px 0; font-size: 12px; }
:deep(.warn-row) { background: #fdf6ec; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; font-size: 13px; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计意见卡片 */
.opinion-card { margin-top: 12px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
