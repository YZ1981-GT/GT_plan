<template>
  <div class="h1-tab-policy-check">
    <!-- 引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> CAS4六段落逐项评价(确认/分类/折旧/后续/减值/处置)</div>
        <div class="guide-step"><span class="step-num">②</span> 折旧参数表：各分类×方法×年限×残值率合理性</div>
        <div class="guide-step"><span class="step-num">③</span> 各段落结论Y/N/NA + N时强制填写原因</div>
        <div class="guide-step"><span class="step-num">④</span> 完成度达100%方可关闭此检查项</div>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-section">
      <el-progress :percentage="completionPct" :stroke-width="10" :format="() => `${completedCount}/${totalCount}`" />
    </div>

    <!-- CAS4六段落卡片 -->
    <template v-for="(section, idx) in state.sections.value" :key="section.key">
      <el-card shadow="never" class="policy-card" :class="{ 'policy-card-done': section.conclusion === 'Y' || section.conclusion === 'NA' }">
        <template #header>
          <div class="section-title">
            <span>{{ section.title }}</span>
            <div class="title-actions">
              <el-tag v-if="section.conclusion" :type="getConclusionType(section.conclusion)" size="small">
                {{ section.conclusion }}
              </el-tag>
              <el-button size="small" type="primary" link @click="handleAiGenerate(section.key)">
                <el-icon><MagicStick /></el-icon> AI
              </el-button>
              <el-button size="small" type="default" link @click="handleReview(`H1-5-${section.key}`)">💬</el-button>
            </div>
          </div>
        </template>

        <!-- 准则条款引用 -->
        <div class="cas-reference">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ section.description }}</span>
        </div>

        <!-- 被审计单位实际政策 -->
        <div class="field-group">
          <label>被审计单位实际政策：</label>
          <el-input v-model="section.actualPolicy" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly"
            placeholder="描述被审计单位就此方面的实际会计政策..." @blur="onSectionUpdate(idx)" />
        </div>

        <!-- 审计师评价 -->
        <div class="field-group">
          <label>审计师评价：</label>
          <el-input v-model="section.evaluation" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly"
            placeholder="评价该政策是否符合CAS4要求..." @blur="onSectionUpdate(idx)" />
        </div>

        <!-- 结论 -->
        <div class="field-group conclusion-group">
          <label>结论：</label>
          <el-radio-group v-model="section.conclusion" :disabled="isReadonly" @change="onSectionUpdate(idx)">
            <el-radio value="Y">Y 符合</el-radio>
            <el-radio value="N">N 不符合</el-radio>
            <el-radio value="NA">NA 不适用</el-radio>
          </el-radio-group>
        </div>

        <!-- N时强制说明 -->
        <div v-if="section.conclusion === 'N'" class="field-group n-explanation">
          <label>不符合原因及影响：</label>
          <el-input v-model="section.explanationIfN" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly"
            placeholder="必须说明不符合的具体原因和对审计的影响..." @blur="onSectionUpdate(idx)" />
          <el-alert v-if="!section.explanationIfN" type="error" :closable="false" show-icon>
            结论为N时必须填写原因说明
          </el-alert>
        </div>
      </el-card>
    </template>

    <!-- 折旧参数表 -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>折旧参数合理性评价</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddParam" :disabled="isReadonly">+ 新增分类</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.depParams.value" border stripe size="small">
        <el-table-column prop="category" label="资产分类" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.category" size="small" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="depMethod" label="折旧方法" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.depMethod" size="small">
              <el-option label="直线法" value="直线法" />
              <el-option label="双倍余额" value="双倍余额递减法" />
              <el-option label="年数总和" value="年数总和法" />
              <el-option label="工作量法" value="工作量法" />
            </el-select>
            <span v-else>{{ row.depMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLifeMin" label="年限下限" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLifeMin" :controls="false" size="small" :min="1" />
            <span v-else>{{ row.usefulLifeMin }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLifeMax" label="年限上限" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLifeMax" :controls="false" size="small" :min="1" />
            <span v-else>{{ row.usefulLifeMax }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="salvageRate" label="残值率%" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.salvageRate" :controls="false" size="small" :min="0" :max="99" />
            <span v-else>{{ row.salvageRate }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="isReasonable" label="合理" width="70" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" style="width:50px">
              <el-option label="Y" value="Y" />
              <el-option label="N" value="N" />
            </el-select>
            <el-tag v-else :type="row.isReasonable === 'Y' ? 'success' : 'danger'" size="small">{{ row.isReasonable }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明/结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('policy-evaluation')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="policyConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="会计政策检查总体结论..." />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>CAS4六段落必须逐项评价，不可空白</li>
        <li>折旧参数表可参考同行业上市公司披露</li>
        <li>结论为N时必须填写具体原因并评估影响</li>
        <li>关注前后期一致性，政策变更需特殊处理</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick, InfoFilled } from '@element-plus/icons-vue'
import { useH1PolicyCheck } from '../../composables/useH1PolicyCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const policyConclusion = ref('')

const state = useH1PolicyCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

const totalCount = computed(() => state.sections.value.length)
const completedCount = computed(() => state.sections.value.filter((s: any) => s.conclusion).length)
const completionPct = computed(() => Math.round((completedCount.value / totalCount.value) * 100))

function getConclusionType(conclusion: string): 'success' | 'danger' | 'info' {
  if (conclusion === 'Y') return 'success'
  if (conclusion === 'N') return 'danger'
  return 'info'
}

function onSectionUpdate(_idx: number) { /* debounce save */ }
function handleAddParam() { state.addDepParam?.() }
function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.h1-tab-policy-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.progress-section { margin-bottom: 16px; }
.policy-card { margin-bottom: 12px; }
.policy-card-done { border-left: 3px solid var(--el-color-success); }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; align-items: center; gap: 8px; }
.cas-reference { display: flex; align-items: flex-start; gap: 6px; padding: 8px 12px; background: var(--el-fill-color-light); border-radius: 4px; margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.field-group { margin-bottom: 12px; }
.field-group label { display: block; font-weight: 500; margin-bottom: 4px; }
.conclusion-group { display: flex; align-items: center; gap: 12px; }
.n-explanation { border-left: 3px solid var(--el-color-danger); padding-left: 12px; }
.params-card { margin-bottom: 12px; }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
