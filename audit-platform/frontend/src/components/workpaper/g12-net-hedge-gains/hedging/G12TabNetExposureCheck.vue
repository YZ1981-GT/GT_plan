<template>

  <div class="g12-ne">

    <div class="methodology">CAS24套期会计三要素 + 有效性条件 + 净敞口定义</div>

    <div class="toolbar">

      <h3>G12-5 风险净敞口检查（{{ ne.rows.value.length }} 行 · 5 区段）</h3>

      <el-tag v-if="ne.missingCompliance.value.length" type="danger" size="small">

        待填合规 {{ ne.missingCompliance.value.length }} 行

      </el-tag>

      <el-button size="small" :disabled="isReadonly" @click="saveCheck">保存校验</el-button>

      <GtReviewTrigger section-id="G12-5-net-exposure" />

    </div>



    <div v-if="ne.useVirtualScroll.value" class="virtual-toolbar">

      <el-alert type="info" :closable="false" class="virtual-hint">

        行数较多（{{ ne.rows.value.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '分区编辑' }} · 双击行切换编辑

      </el-alert>

      <el-button size="small" @click="toggleBrowseMode">

        {{ browseMode ? '切换分区编辑' : '切换虚拟速览' }}

      </el-button>

    </div>



    <el-table-v2

      v-if="ne.useVirtualScroll.value && browseMode"

      :columns="virtualColumns"

      :data="ne.rows.value"

      :width="tableWidth"

      :height="tableHeight"

      :row-height="36"

      :header-height="40"

      :row-event-handlers="rowEventHandlers"

      fixed

      class="virtual-table"

      data-testid="g12-ne-virtual-table"

    />



    <el-collapse v-else v-model="expandedSections" class="sections">

      <el-collapse-item v-for="sec in ne.sections.value" :key="sec.title" :name="sec.title">

        <template #title>

          <span class="sec-title">{{ sec.title }}</span>

          <el-tag size="small" type="info" style="margin-left:8px">{{ sec.rows.length }} 项</el-tag>

        </template>

        <el-table :data="sec.rows" border size="small" style="font-size:13px" :row-class-name="rowClassName">

          <el-table-column label="#" prop="seq" width="44" />

          <el-table-column label="检查区域" prop="checkArea" width="100" show-overflow-tooltip />

          <el-table-column label="检查项目" prop="checkItem" min-width="140" show-overflow-tooltip />

          <el-table-column label="审计要求" prop="auditRequirement" min-width="120" show-overflow-tooltip />

          <el-table-column label="检查结果" min-width="120">

            <template #default="{ row }">

              <el-input v-model="row.checkResult" size="small" type="textarea"

                :autosize="{ minRows: 1, maxRows: 3 }" :disabled="isReadonly"

                @change="() => ne.updateCell(row.rowId, 'checkResult', row.checkResult)" />

            </template>

          </el-table-column>

          <el-table-column label="是否合规" width="110">

            <template #default="{ row }">

              <el-select v-model="row.compliance" size="small" :disabled="isReadonly"

                :class="{ missing: !row.compliance }"

                @change="(v: string) => ne.updateCell(row.rowId, 'compliance', v)">

                <el-option v-for="o in G12_COMPLIANCE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />

              </el-select>

            </template>

          </el-table-column>

          <el-table-column label="风险等级" width="90">

            <template #default="{ row }">

              <el-select v-model="row.riskLevel" size="small" :disabled="isReadonly"

                @change="(v: string) => ne.updateCell(row.rowId, 'riskLevel', v)">

                <el-option v-for="l in G12_RISK_LEVELS" :key="l.value" :label="l.label" :value="l.value" />

              </el-select>

            </template>

          </el-table-column>

          <el-table-column label="结论" min-width="100">

            <template #default="{ row }">

              <el-input v-model="row.conclusion" size="small" type="textarea"

                :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"

                @change="(v: string) => ne.updateCell(row.rowId, 'conclusion', v)" />

            </template>

          </el-table-column>

          <el-table-column label="索引" width="90">

            <template #default="{ row }">

              <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"

                @change="(v: string) => ne.updateCell(row.rowId, 'indexRef', v)" />

              <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />

            </template>

          </el-table-column>

          <el-table-column label="备注" min-width="80">

            <template #default="{ row }">

              <el-input v-model="row.remark" size="small" :disabled="isReadonly"

                @change="(v: string) => ne.updateCell(row.rowId, 'remark', v)" />

            </template>

          </el-table-column>

        </el-table>

      </el-collapse-item>

    </el-collapse>



    <el-card shadow="never" class="overall">

      <template #header>

        <div class="overall-head">

          <span>综合审计结论</span>

          <el-button size="small" link :disabled="isReadonly" @click="generateAi">🤖 AI</el-button>

        </div>

      </template>

      <el-input :model-value="ne.overallConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"

        :disabled="isReadonly" @update:model-value="ne.updateOverallConclusion" />

    </el-card>

    <details class="methodology-hint">

      <summary>📋 编制提示（CAS24 套期会计）</summary>

      <p>按 5 区段逐项检查净敞口套期的合规性：净敞口定义、套期会计三要素、有效性条件、公允价值与文档、损益列报。每项须选择「是否合规」并评估风险等级；存在未合规项时须在结论中说明处理措施。全部行完成合规判断后方可「保存校验」。</p>

    </details>

  </div>

</template>



<script setup lang="ts">

import { ref, toRef, watch, computed } from 'vue'

import { useG12NetExposure } from '../../composables/useG12NetExposure'

import { useG12Disclosure } from '../../composables/useG12Disclosure'

import { useWorkpaperBrowseMode } from '../../composables/useWorkpaperBrowseMode'

import { virtualTextCol, virtualSelectCol } from '../../composables/virtualColumnHelpers'

import type { VirtualColumn } from '@/composables/useVirtualTable'

import { G12_COMPLIANCE_OPTIONS, G12_RISK_LEVELS } from '../../composables/g12Constants'

import type { ChecklistResponse } from '../../composables/useF1FormData'

import GtReviewTrigger from '../../GtReviewTrigger.vue'

import GtIndexChip from '../../GtIndexChip.vue'



const props = defineProps<{

  allResponses: Map<string, ChecklistResponse>

  wpId: string

  isReadonly: boolean

  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void

}>()



const ne = useG12NetExposure({

  allResponses: toRef(props, 'allResponses'),

  isReadonly: toRef(props, 'isReadonly'),

  debouncedSave: props.debouncedSave,

})



const ai = useG12Disclosure({

  variant: 'listed',

  allResponses: toRef(props, 'allResponses'),

  wpId: toRef(props, 'wpId'),

  isReadonly: toRef(props, 'isReadonly'),

  debouncedSave: props.debouncedSave,

})



const expandedSections = ref<string[]>([])



watch(() => ne.sections.value, (secs) => {

  if (secs.length && !expandedSections.value.length) {

    expandedSections.value = [secs[0].title]

  }

}, { immediate: true })



const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('seq', '#', 44),
  virtualTextCol('sectionTitle', '区段', 120),
  virtualTextCol('checkItem', '检查项目', 220),
  virtualSelectCol('compliance', '合规', 100),
  virtualSelectCol('riskLevel', '风险', 80),
])

const {
  browseMode,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({

  rows: ne.rows,

  virtualColumns,

  threshold: 50,

  tableWidth: 1100,

  tableHeight: 480,

})



function saveCheck() { ne.saveValidated() }

function generateAi() { void ai.generateAi('net-position-conclusion') }



function rowClassName({ row }: { row: { compliance: string } }): string {

  if (!row.compliance) return 'g12-ne-missing'

  if (row.compliance === 'non_compliant') return 'g12-ne-bad'

  return ''

}

</script>



<style scoped>

.g12-ne { padding: 12px; font-size: var(--wp-font-size, 13px); }

.methodology { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 12px; font-size: 12px; }

.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }

.virtual-hint { flex: 1; margin: 0; }

.sections { margin-bottom: 12px; }

.sec-title { font-weight: 600; }

.overall { margin-top: 8px; }

.overall-head { display: flex; justify-content: space-between; align-items: center; }

.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }

.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }

.missing :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }

:deep(.g12-ne-missing) { background: #fef0f0 !important; }

:deep(.g12-ne-bad) { background: #fdf6ec !important; }

</style>


