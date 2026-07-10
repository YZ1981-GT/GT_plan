<script setup lang="ts">
/**
 * D2TabBizModel — 业务模式D2-13
 * QA卡片: 4个Y/N判断 + 业务模式组合表(5列) + 推荐模式高亮
 */
import { inject, ref, toRef, type Ref } from 'vue'
import { useD2BizModel } from '../composables/useD2BizModel'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
function onReview(sectionId: string): void { if (openReviewDialog) openReviewDialog(sectionId) }

const {
  judgments,
  groups,
  allAnswered,
  recommendedModel,
  auditNote,
  auditConclusion,
  updateJudgment,
  updateGroup,
  addGroup,
  removeGroup,
  saveAuditNote,
  saveAuditConclusion,
} = useD2BizModel({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-13',
)

const MEASUREMENT_OPTIONS = ['以摊余成本计量', '以公允价值计量且其变动计入其他综合收益(FVOCI)', '以公允价值计量且其变动计入当期损益(FVTPL)']

const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, generateAndConfirm } = useD2AiGenerate(wpIdRef)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

function buildAiContext(extra = ''): Record<string, unknown> {
  return {
    sheet: 'D2-13',
    allAnswered: allAnswered.value,
    recommendedModel: recommendedModel.value,
    groupCount: groups.value.length,
    judgments: judgments.value.map(j => ({ q: j.question, a: j.answer })),
    guidance: extra,
  }
}

async function generateNoteAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm('bizmodel-note', auditNote.value,
      buildAiContext('结合业务模式判断与 SPPI 测试评价金融资产分类恰当性。'), 'AI · 审计说明')
    if (text) saveAuditNote(text)
  } finally { aiLoadingNote.value = false }
}

async function generateConclusionAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm('bizmodel-note', auditConclusion.value,
      buildAiContext('生成业务模式分析审计结论。'), 'AI · 审计结论')
    if (text) saveAuditConclusion(text)
  } finally { aiLoadingConclusion.value = false }
}

async function handleImport(file: File): Promise<boolean> {
  await onImportFile(file)
  return false
}

const GUIDANCE_TEXTS = [
  '业务模式（CAS 22）：以持有金融资产的管理方式为基础判断——仅收取合同现金流量→摊余成本；兼有收取与出售→FVOCI；以交易/出售为目标→FVTPL。',
  'SPPI 测试：评估合同现金流量是否仅为对本金和以未偿付本金为基础的利息的支付；含杠杆、与业绩挂钩等特征通常不满足 SPPI。',
  '保理与应收账款转让会影响业务模式判断，需结合 D2-12 保理终止确认情况综合评价。',
  '业务模式一经确定不得随意变更，仅在改变管理金融资产方式时才重分类，并按准则要求追溯或未来适用。',
]
</script>

<template>
  <div class="d2-tab-bizmodel">
    <div class="tab-header">
      <h4>应收账款业务模式分析 D2-13</h4>
      <GtReviewTrigger section-id="D2-bizmodel-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>评价应收账款所属金融资产的业务模式与合同现金流量特征（SPPI），判断其分类与计量基础的恰当性（CAS 22）。</p>
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag type="info" size="small">业务模式判定 (CAS 22)</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
    </div>

    <!-- 推荐业务模式 -->
    <el-alert
      v-if="allAnswered && recommendedModel"
      type="success"
      :closable="false"
      class="recommend-alert"
    >
      <template #title>
        <span style="font-weight:600">推荐业务模式: {{ recommendedModel }}</span>
      </template>
    </el-alert>

    <!-- QA判断卡片 -->
    <div class="qa-cards">
      <el-card
        v-for="j in judgments"
        :key="j.questionId"
        shadow="hover"
        class="qa-card"
      >
        <div class="qa-question">
          {{ j.question }}
          <GtReviewTrigger :section-id="`D2-bizmodel-judgment-${j.questionId}`" />
        </div>
        <div class="qa-answer">
          <el-radio-group
            :model-value="j.answer"
            :disabled="isReadonly"
            @change="(v: string) => updateJudgment(j.questionId, 'answer', v)"
          >
            <el-radio-button value="Y">是</el-radio-button>
            <el-radio-button value="N">否</el-radio-button>
          </el-radio-group>
        </div>
        <div class="qa-explanation">
          <el-input
            :model-value="j.explanation"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="判断依据..."
            @change="(v: string) => updateJudgment(j.questionId, 'explanation', v)"
          />
        </div>
      </el-card>
    </div>

    <!-- 业务模式组合表 -->
    <div class="group-section">
      <div class="section-header">
        <span class="section-title">业务模式组合判定</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addGroup">添加组合</el-button>
      </div>
      <el-table :data="groups" border size="small" style="width: 100%">
        <el-table-column label="组合名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.groupName" size="small" @change="(v: string) => updateGroup(row.rowId, 'groupName', v)" />
            <span v-else>{{ row.groupName || '-' }}</span>
            <GtReviewDot row-prefix="D2-bizmodel-group" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="业务模式" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.bizModel" size="small" @change="(v: string) => updateGroup(row.rowId, 'bizModel', v)" />
            <span v-else>{{ row.bizModel || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="SPPI结果" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.sppiResult" size="small" @change="(v: string) => updateGroup(row.rowId, 'sppiResult', v)">
              <el-option label="通过" value="通过" />
              <el-option label="未通过" value="未通过" />
            </el-select>
            <span v-else>{{ row.sppiResult || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计量基础" min-width="240">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.measurementBasis" size="small" clearable placeholder="选择计量基础" style="width:100%" @change="(v: string) => updateGroup(row.rowId, 'measurementBasis', v || '')">
              <el-option v-for="o in MEASUREMENT_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.measurementBasis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(v: string) => updateGroup(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeGroup(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无业务模式组合，点击"添加组合"录入</template>
      </el-table>
    </div>

    <!-- 审计说明 -->
    <div class="section-subtitle">审计说明</div>
    <div class="note-section">
      <el-input type="textarea" autosize :model-value="auditNote" placeholder="请输入审计说明..." :disabled="isReadonly" @change="(v: string) => saveAuditNote(v || '')" />
      <div class="note-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成审计说明' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateNoteAI">🤖 AI</el-button>
        </el-tooltip>
        <el-button v-if="openReviewDialog" size="small" @click="onReview('D2-bizmodel-note')">💬 复核</el-button>
      </div>
    </div>

    <!-- 审计结论 -->
    <div class="section-subtitle">审计结论</div>
    <div class="note-section">
      <el-input type="textarea" autosize :model-value="auditConclusion" placeholder="请输入审计结论..." :disabled="isReadonly" @change="(v: string) => saveAuditConclusion(v || '')" />
      <div class="note-actions">
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成审计结论' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateConclusionAI">🤖 AI</el-button>
        </el-tooltip>
        <el-button v-if="openReviewDialog" size="small" @click="onReview('D2-bizmodel-conclusion')">💬 复核</el-button>
      </div>
    </div>

    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
.d2-tab-bizmodel { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-subtitle { font-size: 14px; font-weight: 600; color: #303133; margin: 16px 0 10px; }
.note-section { margin-bottom: 8px; }
.note-actions { margin-top: 6px; display: flex; gap: 8px; }
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.recommend-alert { margin-bottom: 16px; }
.qa-cards { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.qa-card { }
.qa-question { font-size: 14px; font-weight: 500; margin-bottom: 8px; }
.qa-answer { margin-bottom: 8px; }
.qa-explanation { }
.group-section { }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; }
</style>
