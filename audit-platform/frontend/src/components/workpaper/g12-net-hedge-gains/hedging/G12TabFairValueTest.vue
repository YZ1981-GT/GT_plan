<template>
  <div class="g12-fv">
    <div class="methodology">CAS24套期有效性：经济关系 + 套期比率 + 有效性测试（前瞻性/回顾性）</div>
    <div class="toolbar">
      <h3>G12-4 公允价值测试</h3>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="fv.addRow()">+ 新增</el-button>
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-4" :disabled="isReadonly" @imported="emit('imported')" />
      <GtReviewTrigger section-id="G12-4-fv-test" />
    </div>

    <el-alert
      v-if="fvCrossMessage"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g12-fv-cross-bar"
    >
      {{ fvCrossMessage }}
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-2"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-2'))"
      />
    </el-alert>
    <el-alert
      v-else-if="hasHedgeData"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g12-fv-cross-ok"
    >
      G12-2 与 G12-4 公允价值测试一致
      <GtIndexChip
        v-if="jumpToSection"
        label="G12-2"
        :prevent-navigate="true"
        :validate="false"
        class="ok-chip"
        @click="jumpToSection(resolveG12SheetLabel('G12-2'))"
      />
    </el-alert>

    <el-segmented v-model="fv.activeTab.value" :options="tabOptions" size="small" />

    <el-table :data="fv.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="440"
      highlight-current-row @current-change="(r: any) => r && (fv.selectedRowId.value = r.rowId)">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="套期关系编号" prop="hedgeRelationId" width="110" fixed />

      <template v-if="fv.activeTab.value === 'instrument'">
        <el-table-column label="工具名称" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.instrumentName" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'instrumentName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="工具类型" width="110">
          <template #default="{ row }">
            <el-select v-model="row.instrumentType" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'instrumentType', v)">
              <el-option v-for="t in G12_INSTRUMENT_TYPES" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="期初FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.instrumentOpeningFV" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'instrumentOpeningFV', v)" />
          </template>
        </el-table-column>
        <el-table-column label="期末FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.instrumentClosingFV" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'instrumentClosingFV', v)" />
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.instrumentFVChange.toFixed(2) }}</span></template>
        </el-table-column>
        <el-table-column label="估值方法" width="100">
          <template #default="{ row }">
            <el-input v-model="row.instrumentValuationMethod" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'instrumentValuationMethod', v)" />
          </template>
        </el-table-column>
        <el-table-column label="FV层次" width="100">
          <template #default="{ row }">
            <el-select v-model="row.instrumentFVLevel" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'instrumentFVLevel', v)">
              <el-option v-for="l in G12_FV_LEVELS" :key="l.value" :label="l.label" :value="l.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="估值来源" min-width="100">
          <template #default="{ row }">
            <el-input v-model="row.instrumentValuationSource" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'instrumentValuationSource', v)" />
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="项目名称" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.itemName" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'itemName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="项目类型" width="120">
          <template #default="{ row }">
            <el-select v-model="row.itemType" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'itemType', v)">
              <el-option v-for="t in G12_ITEM_TYPES" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="期初FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.itemOpeningFV" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'itemOpeningFV', v)" />
          </template>
        </el-table-column>
        <el-table-column label="期末FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.itemClosingFV" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'itemClosingFV', v)" />
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.itemFVChange.toFixed(2) }}</span></template>
        </el-table-column>
        <el-table-column label="风险因素" width="100">
          <template #default="{ row }">
            <el-input v-model="row.itemRiskFactor" size="small" placeholder="利率/汇率…" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'itemRiskFactor', v)" />
          </template>
        </el-table-column>
        <el-table-column label="测试方法" width="120">
          <template #default="{ row }">
            <el-select v-model="row.itemTestMethod" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'itemTestMethod', v)">
              <el-option v-for="m in G12_TEST_METHODS" :key="m.value" :label="m.label" :value="m.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="有效性结论" width="110">
          <template #default="{ row }">
            <el-select v-model="row.itemEffectivenessConclusion" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'itemEffectivenessConclusion', v)">
              <el-option v-for="o in fv.G12_EFFECTIVENESS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="fv.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="conclusion">
      <template #header>
        <div class="conclusion-head">
          <span>审计结论</span>
          <el-button size="small" :loading="fv.aiLoading.value" :disabled="isReadonly"
            @click="fv.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="fv.conclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" @update:model-value="fv.updateConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { useG12FairValueTest } from '../../composables/useG12FairValueTest'
import { useG12HedgeDetail } from '../../composables/useG12HedgeDetail'
import {
  findG12FvCrossMismatches,
  formatG12FvCrossSummaryMessage,
  hasG12HedgeDetailData,
} from '../../composables/useG12CrossValidate'
import { resolveG12SheetLabel } from '../../composables/g12SheetLabels'
import { G12_INSTRUMENT_TYPES, G12_ITEM_TYPES, G12_FV_LEVELS, G12_TEST_METHODS } from '../../composables/g12Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()
const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const fv = useG12FairValueTest({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
  wpId: toRef(props, 'wpId'),
})

const hd = useG12HedgeDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  debouncedSave: props.debouncedSave,
})

const hasHedgeData = computed(() => hasG12HedgeDetailData(props.allResponses))

const fvCrossMessage = computed(() => {
  const mismatches = findG12FvCrossMismatches(hd.rows.value, props.allResponses)
  return formatG12FvCrossSummaryMessage(mismatches)
})

const tabOptions = [
  { label: '套期工具侧（9列）', value: 'instrument' },
  { label: '被套期项目侧（9列）', value: 'item' },
]
</script>

<style scoped>
.g12-fv { padding: 12px; font-size: 13px; }
.methodology { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 12px; font-size: 12px; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.cross-alert { margin-bottom: 8px; }
.cross-ok :deep(.el-alert__content) { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.warn-chip, .ok-chip { margin-left: 8px; }
.formula { border-bottom: 1px dashed #909399; }
.conclusion { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
</style>
