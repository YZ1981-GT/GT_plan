<template>
  <div class="g10-fv" data-testid="g10-fv-test">
    <div class="methodology">
      公允价值三层次：Level1—活跃市场相同负债报价；Level2—可观察输入值；Level3—不可观察输入值(估值技术)。
      Level3 时估值技术与不可观察输入值描述必填。
    </div>
    <div class="toolbar">
      <h3>G10-5 公允价值测试</h3>
      <G10ImportExportDropdown :wp-id="wpId" sheet="G10-5" @imported="emit('imported')" />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="fv.addRow()">+ 新增</el-button>
      <el-button size="small" :disabled="isReadonly" @click="fv.validateLevel3()">Level3校验</el-button>
      <GtReviewTrigger section-id="G10-5-fv-test" />
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实交易性金融负债期末公允价值计量的准确性，验证公允价值层次划分与估值技术的恰当性，Level3 不可观察输入值的充分披露。" />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G10-5" /></span>
        <el-tag size="small" type="info">共 {{ fv.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-alert v-if="fv.level3Violations.value.length" type="warning" :closable="false" class="l3-alert">
      Level3 必填缺失：{{ fv.level3Violations.value.map(v => v.liabilityName).join('、') }}
    </el-alert>

    <el-segmented v-model="fv.activeTab.value" :options="tabOptions" size="small" />

    <el-table :data="fv.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="440"
      highlight-current-row @current-change="(r: any) => r && (fv.selectedRowId.value = r.rowId)">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="负债名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input v-model="row.liabilityName" size="small" :disabled="isReadonly"
            @change="(v: string) => fv.updateCell(row.rowId, 'liabilityName', v)" />
        </template>
      </el-table-column>

      <template v-if="fv.activeTab.value === 'basic'">
        <el-table-column label="初始日期" width="108">
          <template #default="{ row }">
            <el-input v-model="row.initialDate" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'initialDate', v)" />
          </template>
        </el-table-column>
        <el-table-column label="未审数量" width="92" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.closingUnadjustedQty" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingUnadjustedQty', v)" />
          </template>
        </el-table-column>
        <el-table-column label="未审单价" width="92" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.closingUnadjustedPrice" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingUnadjustedPrice', v)" />
          </template>
        </el-table-column>
        <el-table-column label="未审FV" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ fmt(row.closingUnadjustedFV) }}</span></template>
        </el-table-column>
        <el-table-column label="审定数量" width="92" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.closingAuditedQty" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingAuditedQty', v)" />
          </template>
        </el-table-column>
        <el-table-column label="审定单价" width="92" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.closingAuditedPrice" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingAuditedPrice', v)" />
          </template>
        </el-table-column>
        <el-table-column label="审定FV" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ fmt(row.closingAuditedFV) }}</span></template>
        </el-table-column>
        <el-table-column label="层次" width="100">
          <template #default="{ row }">
            <el-select v-model="row.fairValueLevel" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'fairValueLevel', v)">
              <el-option v-for="l in fv.G10_FV_LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
            </el-select>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="估值方法" width="110">
          <template #default="{ row }">
            <el-select v-model="row.valuationMethod" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationMethod', v)">
              <el-option v-for="m in fv.G10_VALUATION_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致" width="96">
          <template #default="{ row }">
            <el-select v-model="row.methodConsistentWithPrior" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'methodConsistentWithPrior', v)">
              <el-option label="是" value="yes" /><el-option label="否" value="no" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="来源机构" width="100">
          <template #default="{ row }">
            <el-input v-model="row.valuationSource" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationSource', v)" />
          </template>
        </el-table-column>
        <el-table-column label="输入值来源" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.inputSourceAndAdjustment" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
              @change="() => fv.updateCell(row.rowId, 'inputSourceAndAdjustment', row.inputSourceAndAdjustment)" />
          </template>
        </el-table-column>
        <el-table-column label="估值技术" width="100">
          <template #default="{ row }">
            <el-input v-model="row.valuationTechnique" size="small" :disabled="isReadonly"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.valuationTechnique }"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationTechnique', v)" />
          </template>
        </el-table-column>
        <el-table-column label="不可观察输入值" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.unobservableInputDesc" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.unobservableInputDesc }"
              @change="() => fv.updateCell(row.rowId, 'unobservableInputDesc', row.unobservableInputDesc)" />
          </template>
        </el-table-column>
        <el-table-column label="数值" width="88">
          <template #default="{ row }">
            <el-input v-model="row.unobservableInputValue" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'unobservableInputValue', v)" />
          </template>
        </el-table-column>
        <el-table-column label="敏感性分析" min-width="100">
          <template #default="{ row }">
            <el-input v-model="row.sensitivityAnalysis" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
              @change="() => fv.updateCell(row.rowId, 'sensitivityAnalysis', row.sensitivityAnalysis)" />
          </template>
        </el-table-column>
        <el-table-column label="索引" width="72">
          <template #default="{ row }">
            <el-input v-model="row.valuationDocIndex" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationDocIndex', v)" />
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="fv.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusionProxy"
      note-ai-section="fair-value-note"
      conclusion-ai-section="fair-value-conclusion"
      note-placeholder="填写审计说明：可概述公允价值测试的程序执行情况、估值方法与来源核实、Level3 输入值合理性及与 G10-6 调节表勾稽结果。"
      note-hint="覆盖公允层级划分与估值来源可靠性。"
      conclusion-placeholder="填写审计结论：公允价值计量是否准确、层次划分是否恰当。"
      :related-context="{ 行数: fv.rows.value.length, Level3缺失: fv.level3Violations.value.length }"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>依据 CAS 39《公允价值计量》，按输入值可观察程度划分三层次；Level3 使用不可观察输入值时须记录估值技术、关键参数及敏感性分析。</p>
        <p>审定FV = 审定数量 × 审定单价；关注估值方法与上期是否一致，不一致须说明变更理由及影响。</p>
        <p>Level3 负债的期末公允价值变动应与 G10-6 第三层次调节表勾稽。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, watch } from 'vue'
import { useG10FairValueTest } from '../../composables/useG10FairValueTest'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const fv = useG10FairValueTest({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId: toRef(props, 'wpId'),
})

const NOTE_KEY = 'G10-5-fv-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})

const conclusionProxy = computed({
  get: () => fv.conclusion.value,
  set: (v: string) => fv.updateConclusion(v),
})

const tabOptions = [
  { label: '基础+审定', value: 'basic' },
  { label: '估值详情', value: 'valuation' },
]

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g10-fv { font-size: var(--wp-font-size, 13px); }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.formula { border-bottom: 1px dashed #909399; }
.l3-alert { margin-bottom: 8px; }
:deep(.l3-required .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
</style>
