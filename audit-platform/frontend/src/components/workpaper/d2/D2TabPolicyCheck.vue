<script setup lang="ts">
/**
 * D2TabPolicyCheck — 政策检查D2-8
 * 段落卡片式布局(非table), 6个政策段落, Y/N/NA radio, 结论=N红色边框
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2PolicyCheck, type PolicyParagraph } from '../composables/useD2PolicyCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function openReviewForParagraph(paragraphIdx: number): void {
  if (!openReviewDialog) return
  openReviewDialog(`D2-policy-paragraph-${paragraphIdx}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  paragraphs,
  completedCount,
  totalCount,
  hasNonCompliant,
  updateParagraph,
} = useD2PolicyCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function getConclusionClass(p: PolicyParagraph): string {
  if (p.conclusion === 'N') return 'non-compliant'
  return ''
}
</script>

<template>
  <div class="d2-tab-policy">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="progress-text">已完成: {{ completedCount }} / {{ totalCount }}</span>
        <el-tag v-if="hasNonCompliant" type="danger" size="small">存在不合规项</el-tag>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-block">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        逐段检查被审计单位应收账款相关会计政策的执行情况，对照企业会计准则要求评价政策适用性和一致性。
        每段结论：Y=符合、N=不符合（需关注）、NA=不适用。
      </div>
    </details>

    <!-- 政策段落卡片 -->
    <div class="paragraphs-list">
      <el-card
        v-for="p in paragraphs"
        :key="p.paragraphId"
        :class="['paragraph-card', getConclusionClass(p)]"
        shadow="hover"
      >
        <template #header>
          <div class="para-header">
            <span class="para-title">{{ p.title }}</span>
            <el-tag v-if="p.conclusion === 'N'" type="danger" size="small">需关注</el-tag>
            <el-tag v-else-if="p.conclusion === 'Y'" type="success" size="small">符合</el-tag>
            <el-tag v-else-if="p.conclusion === 'NA'" type="info" size="small">不适用</el-tag>
          </div>
        </template>

        <div class="para-body">
          <!-- 左栏：政策条款 -->
          <div class="policy-text">
            <div class="field-label">政策条款</div>
            <div class="policy-desc">{{ p.policyDescription }}</div>
          </div>

          <!-- 右栏：实际情况 -->
          <div class="actual-area">
            <div class="field-label">实际情况</div>
            <el-input
              :model-value="p.actualSituation"
              type="textarea"
              :rows="3"
              :disabled="isReadonly"
              placeholder="请描述被审计单位实际情况..."
              @change="(v: string) => updateParagraph(p.paragraphId, 'actualSituation', v)"
            />
          </div>
        </div>

        <!-- 下方：评价 + 结论 -->
        <div class="eval-area">
          <div class="eval-text">
            <div class="field-label">审计师评价</div>
            <el-input
              :model-value="p.auditorEvaluation"
              type="textarea"
              :rows="2"
              :disabled="isReadonly"
              placeholder="请输入评价意见..."
              @change="(v: string) => updateParagraph(p.paragraphId, 'auditorEvaluation', v)"
            />
          </div>
          <div class="conclusion-area">
            <div class="field-label">结论</div>
            <el-radio-group
              :model-value="p.conclusion"
              :disabled="isReadonly"
              @change="(v: string) => updateParagraph(p.paragraphId, 'conclusion', v)"
            >
              <el-radio-button value="Y">Y</el-radio-button>
              <el-radio-button value="N">N</el-radio-button>
              <el-radio-button value="NA">NA</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-policy { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 12px; align-items: center; }
.progress-text { font-size: 13px; font-weight: 600; }

.guidance-block {
  margin-bottom: 12px; padding: 8px 12px;
  border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px;
}
.guidance-block summary { cursor: pointer; font-weight: 600; font-size: 13px; color: #409eff; }
.guidance-content { margin-top: 6px; font-size: 12px; color: #606266; white-space: pre-wrap; }

.paragraphs-list { display: flex; flex-direction: column; gap: 12px; }
.paragraph-card.non-compliant { border: 2px solid #f56c6c; }
.para-header { display: flex; justify-content: space-between; align-items: center; }
.para-title { font-weight: 600; font-size: 14px; }

.para-body { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px; }
.field-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.policy-desc { font-size: 13px; color: #303133; padding: 8px; background: #f5f7fa; border-radius: 4px; }

.eval-area { display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: start; }
.conclusion-area { padding-top: 18px; }
</style>
