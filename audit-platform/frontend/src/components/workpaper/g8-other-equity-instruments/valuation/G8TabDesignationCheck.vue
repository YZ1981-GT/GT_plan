<template>
  <div class="g8-designation" data-testid="g8-designation-check">
    <div class="methodology">
      CAS22 指定条件：① 非为交易目的而持有 ② 初始确认时不可撤销指定 ③ 公允价值变动计入其他综合收益 ④ 处置时累计 OCI 可转入留存收益（不经损益）
    </div>
    <div class="toolbar">
      <h3>G8-5 指定适当性检查（{{ dc.rows.value.length }} 行 · 4 区段）</h3>
      <el-tag v-if="dc.missingCompliance.value.length" type="danger" size="small">
        待填合规 {{ dc.missingCompliance.value.length }} 行
      </el-tag>
      <GtReviewTrigger section-id="G8-5-designation" />
    </div>

    <el-collapse v-model="expandedSections" class="sections">
      <el-collapse-item v-for="sec in dc.sections.value" :key="sec.title" :name="sec.title">
        <template #title>
          <span class="sec-title">{{ sec.title }}</span>
          <el-tag size="small" type="info" style="margin-left:8px">{{ sec.rows.length }} 项</el-tag>
          <el-button size="small" link :loading="dc.aiLoading.value" :disabled="isReadonly"
            data-testid="g8-designation-ai-btn" @click.stop="dc.generateAiConclusion()">🤖 AI</el-button>
        </template>
        <el-table :data="sec.rows" border size="small" style="font-size:13px">
          <el-table-column label="#" prop="seq" width="44" />
          <el-table-column label="检查项目" prop="checkItem" min-width="140" show-overflow-tooltip />
          <el-table-column label="审计要求" prop="auditRequirement" min-width="120" show-overflow-tooltip />
          <el-table-column label="证据/回复" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.evidenceOrReply" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'evidenceOrReply', row.evidenceOrReply)" />
            </template>
          </el-table-column>
          <el-table-column label="是否合规" width="110">
            <template #default="{ row }">
              <el-select v-model="row.compliance" size="small" :disabled="isReadonly"
                :class="{ missing: !row.compliance }"
                @change="(v: string) => dc.updateCell(row.rowId, 'compliance', v)">
                <el-option v-for="o in G8_COMPLIANCE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="审计结论" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.auditConclusion" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'auditConclusion', row.auditConclusion)" />
            </template>
          </el-table-column>
          <el-table-column label="索引" width="80">
            <template #default="{ row }">
              <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'indexRef', row.indexRef)" />
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-head">
          <span>综合审计结论</span>
          <el-button size="small" :loading="dc.aiLoading.value" :disabled="isReadonly" @click="dc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="dc.overallConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="dc.updateOverallConclusion" />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <p>逐项填写证据/回复与合规判断；不合规项须在审计结论中说明应对措施。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useG8DesignationCheck } from '../../composables/useG8DesignationCheck'
import { G8_COMPLIANCE_OPTIONS } from '../../composables/g8Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const dc = useG8DesignationCheck({
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const expandedSections = ref<string[]>([])
</script>

<style scoped>
.g8-designation { font-size: 13px; padding: 4px; }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.sec-title { font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
:deep(.missing .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
</style>
