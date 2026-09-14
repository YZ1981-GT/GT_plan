<template>
  <div class="g12-ne" data-testid="g12-net-exposure-check">
    <div class="toolbar">
      <h3>G12-5 风险净敞口检查表</h3>
      <CycleImportExportDropdown :wp-id="wpId" api-prefix="g12" sheet="G12-5" :disabled="isReadonly" @imported="emit('imported')" />
      <el-tag v-if="ne.incompleteRows.value.length" type="warning" size="small">
        待完善 {{ ne.incompleteRows.value.length }} 行
      </el-tag>
      <el-tag v-if="crossIssues.length" type="danger" size="small" data-testid="g12-ne-cross-count">
        交叉差异 {{ crossIssues.length }}
      </el-tag>
      <el-button size="small" :disabled="isReadonly" @click="saveCheck">保存校验</el-button>
      <GtReviewTrigger section-id="G12-5-net-exposure" />
    </div>

    <el-alert
      v-if="crossIssues.length"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g12-ne-cross-bar"
    >
      <template #title>交叉验证（{{ crossIssues.length }} 处）</template>
      <div v-for="(iss, i) in crossIssues.slice(0, 4)" :key="`${iss.rowId}-${iss.kind}-${i}`" class="cross-line">
        #{{ iss.seq }} {{ iss.detail }}
      </div>
      <span v-if="crossIssues.length > 4">…另有 {{ crossIssues.length - 4 }} 处</span>
      <div class="cross-chips">
        <GtIndexChip v-if="jumpToSection" label="G12-2" :prevent-navigate="true" :validate="false"
          @click="jumpToSection(resolveG12SheetLabel('G12-2'))" />
        <GtIndexChip v-if="jumpToSection" label="G12-4" :prevent-navigate="true" :validate="false"
          @click="jumpToSection(resolveG12SheetLabel('G12-4'))" />
      </div>
    </el-alert>
    <el-alert
      v-else-if="hasPeerData"
      type="success"
      :closable="false"
      class="cross-alert cross-ok"
      data-testid="g12-ne-cross-ok"
    >
      G12-5 净头寸计算与 G12-2/G12-4 套期工具勾稽一致
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ne.addRow()">+ 测试项目</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromG12_2">从 G12-2 带入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="syncNetPositionToG12_2">从 G12-2 同步净头寸</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G12-5" /></span>
        <GtIndexChip v-if="jumpToSection" label="G12-2" :prevent-navigate="true" :validate="false"
          @click="jumpToSection(resolveG12SheetLabel('G12-2'))" />
        <GtIndexChip v-if="jumpToSection" label="G12-4" :prevent-navigate="true" :validate="false"
          @click="jumpToSection(resolveG12SheetLabel('G12-4'))" />
        <el-tag size="small" type="info">{{ ne.rows.value.length }} 行 · {{ ne.distinctCurrencyCount.value }} 币种</el-tag>
      </div>
    </div>

    <div class="section-label">一、测试目标</div>
    <el-input
      :model-value="ne.testObjective.value"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isReadonly"
      class="section-text"
      placeholder="检查风险净敞口的支持性证据"
      @update:model-value="ne.updateTestObjective"
    />

    <div class="section-label">二、样本选取标准与规模</div>
    <el-input
      :model-value="ne.sampleCriteria.value"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isReadonly"
      class="section-text"
      placeholder="运用风险净敞口套期的风险净敞口"
      @update:model-value="ne.updateSampleCriteria"
    />

    <div class="section-label">三、测试</div>
    <div class="view-toggle">
      <el-switch v-model="groupByItem" active-text="按项目分组" inactive-text="平铺列表" size="small" />
    </div>

    <template v-if="groupByItem && ne.itemGroups.value.length > 1">
      <el-collapse v-model="expandedGroups" class="item-groups">
        <el-collapse-item v-for="g in ne.itemGroups.value" :key="g.key" :name="g.key">
          <template #title>
            <span class="group-title">{{ g.item.trim() || '(未命名项目)' }}</span>
            <el-tag v-if="g.hedgeRelationId" size="small" type="info" class="group-tag">{{ g.hedgeRelationId }}</el-tag>
            <el-tag size="small" class="group-tag">{{ g.rows.length }} 行 · {{ g.currencies.join(' / ') || '—' }}</el-tag>
          </template>
          <G12NetExposurePositionTable
            :rows="g.rows"
            :total-rows="ne.rows.value.length"
            :is-readonly="isReadonly"
            :ne="ne"
            :cross-issues="crossIssues"
            :all-responses="allResponses"
          />
        </el-collapse-item>
      </el-collapse>
    </template>
    <G12NetExposurePositionTable
      v-else
      :rows="ne.rows.value"
      :total-rows="ne.rows.value.length"
      :is-readonly="isReadonly"
      :ne="ne"
      :cross-issues="crossIssues"
      :all-responses="allResponses"
    />

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>四、审计说明</span></div></template>
      <el-input :model-value="ne.auditNote.value" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明净敞口计算依据、支持性证据获取情况、与 G12-2/G12-4 的勾稽及异常处理。"
        @update:model-value="ne.updateAuditNote" />
    </el-card>

    <el-card shadow="never" class="overall">
      <template #header>
        <div class="overall-head">
          <span>五、审计结论</span>
          <el-button
            size="small"
            link
            :disabled="isReadonly || ne.aiLoading.value"
            :loading="ne.aiLoading.value"
            @click="generateAi"
          >🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="ne.overallConclusion.value" type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="基于各测试项目的净头寸与支持性证据，评价风险净敞口套期的合规性与充分性。"
        @update:model-value="ne.updateOverallConclusion" />
    </el-card>

    <details class="methodology-hint">
      <summary>📋 编制提示（CAS24 净敞口套期）</summary>
      <p>
        本表对齐源模板「风险净敞口检查表 G12-5」：按项目列示相对头寸（如预期销售 vs 预期采购），
        同一项目可按币种分行（USD/EUR 等），分别计算净头寸并获取支持性证据（类型 + 索引）、对应套期工具。
        净头寸可由系统从头寸金额自动建议（头寸1 − 头寸2），亦可手工覆盖。
        AI 结论会注入与 G12-2/G12-4 的交叉验证结果。
        套期关系指定与有效性测试见 G12-2/G12-4，会计处理见 G12-3/G12-6。
      </p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useG12NetExposure } from '../../composables/useG12NetExposure'
import { useG12HedgeDetail } from '../../composables/useG12HedgeDetail'
import {
  findG12NetExposureCrossIssues,
  hasG12NetExposureData,
} from '../../composables/g12NetExposureCross'
import { hasG12HedgeDetailData, hasG12FvTestData } from '../../composables/useG12CrossValidate'
import { resolveG12SheetLabel } from '../../composables/g12SheetLabels'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import G12NetExposurePositionTable from './G12NetExposurePositionTable.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<(label: string) => void>('jumpToSection', undefined)

const ne = useG12NetExposure({
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

const groupByItem = ref(true)
const expandedGroups = ref<string[]>([])

watch(
  () => ne.itemGroups.value.map((g) => g.key),
  (keys) => { expandedGroups.value = keys },
  { immediate: true },
)

const crossIssues = computed(() =>
  findG12NetExposureCrossIssues(ne.rows.value, props.allResponses),
)

const hasPeerData = computed(() =>
  hasG12NetExposureData(props.allResponses)
  && (hasG12HedgeDetailData(props.allResponses) || hasG12FvTestData(props.allResponses)),
)

function saveCheck() { ne.saveValidated() }

function generateAi() { void ne.generateAiConclusion(crossIssues.value) }

function importFromG12_2() {
  ne.importFromHedgeDetail(
    hd.rows.value
      .filter((r) => r.rowKind === 'fv_allocation')
      .map((r) => ({
        item: r.item,
        netPosition: r.netPosition,
        hedgingInstrument: r.hedgingInstrument,
        indexRef: r.indexRef,
        hedgeRelationId: r.indexRef || r.item,
      })),
  )
}

function syncNetPositionToG12_2() {
  const n = ne.syncNetPositionFromG12_2(hd.rows.value)
  if (n) ElMessage.success(`已从 G12-2 同步 ${n} 行净头寸`)
  else ElMessage.info('无可同步的净头寸（请先匹配项目/套期工具）')
}
</script>

<style scoped>
.g12-ne { padding: 12px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-label { font-weight: 600; margin: 12px 0 6px; color: #303133; }
.view-toggle { margin-bottom: 8px; }
.item-groups { margin-bottom: 12px; }
.group-title { margin-right: 8px; font-weight: 500; }
.group-tag { margin-right: 6px; }
.section-text { margin-bottom: 4px; }
.audit-note-card, .overall { margin-top: 8px; }
.card-header, .overall-head { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.cross-alert { margin-bottom: 8px; }
.cross-ok { --el-alert-bg-color: #f0f9eb; }
.cross-line { font-size: 12px; line-height: 1.5; }
.cross-chips { display: flex; gap: 6px; margin-top: 6px; }
.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
</style>
