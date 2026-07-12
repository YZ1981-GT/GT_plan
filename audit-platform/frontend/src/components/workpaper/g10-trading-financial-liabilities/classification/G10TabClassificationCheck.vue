<template>
  <div class="g10-classification" data-testid="g10-classification-check">
    <div class="methodology">
      交易性金融负债分类条件(CAS22/37)：①近期出售或回购目的 ②集中管理可辨认金融工具组合(短期获利) ③衍生金融负债(不符合套期会计)
    </div>
    <div class="toolbar">
      <h3>G10-4 分类适当性检查（{{ cc.rows.value.length }} 行 · 4 区段）</h3>
      <el-tag v-if="cc.missingCompliance.value.length" type="danger" size="small">
        待填合规 {{ cc.missingCompliance.value.length }} 行
      </el-tag>
      <GtReviewTrigger section-id="G10-4-classification" />
    </div>

    <el-collapse v-model="expandedSections" class="sections">
      <el-collapse-item v-for="sec in cc.sections.value" :key="sec.title" :name="sec.title">
        <template #title>
          <span class="sec-title">{{ sec.title }}</span>
          <el-tag size="small" type="info" style="margin-left:8px">{{ sec.rows.length }} 项</el-tag>
          <el-button size="small" link :loading="cc.aiLoading.value" :disabled="isReadonly"
            @click.stop="cc.generateAiConclusion()">🤖 AI</el-button>
        </template>
        <el-table :data="sec.rows" border size="small" style="font-size:13px">
          <el-table-column label="#" prop="seq" width="44" />
          <el-table-column label="检查项目" prop="checkItem" min-width="140" show-overflow-tooltip />
          <el-table-column label="审计要求" prop="auditRequirement" min-width="120" show-overflow-tooltip />
          <el-table-column label="管理层回复" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.managementReply" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" :disabled="isReadonly"
                @change="() => cc.updateCell(row.rowId, 'managementReply', row.managementReply)" />
            </template>
          </el-table-column>
          <el-table-column label="是否合规" width="110">
            <template #default="{ row }">
              <el-select v-model="row.compliance" size="small" :disabled="isReadonly"
                :class="{ missing: !row.compliance }"
                @change="(v: string) => cc.updateCell(row.rowId, 'compliance', v)">
                <el-option v-for="o in G10_COMPLIANCE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="结论" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.conclusion" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
                @change="() => cc.updateCell(row.rowId, 'conclusion', row.conclusion)" />
            </template>
          </el-table-column>
          <el-table-column label="索引" width="80">
            <template #default="{ row }">
              <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
                @change="() => cc.updateCell(row.rowId, 'indexRef', row.indexRef)" />
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-head">
          <span>综合审计结论</span>
          <el-button size="small" :loading="cc.aiLoading.value" :disabled="isReadonly" @click="cc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="cc.overallConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="cc.updateOverallConclusion" />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <p>逐项填写管理层回复与合规判断；不合规项须在结论中说明审计应对。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useG10ClassificationCheck } from '../../composables/useG10ClassificationCheck'
import { G10_COMPLIANCE_OPTIONS } from '../../composables/g10Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const cc = useG10ClassificationCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId: toRef(props, 'wpId'),
})

const expandedSections = ref<string[]>([])
</script>

<style scoped>
.g10-classification { font-size: var(--wp-font-size, 13px); padding: 4px; }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.sec-title { font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
:deep(.missing .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
</style>
