<template>
  <div class="l7-tab-other-check">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>核查其他非流动负债各项目的性质、确认依据、计量准确性与列报披露的完整性，形成分项审计结论。
      </template>
    </el-alert>

    <!-- ═══ 完成度统计进度条 ═══ -->
    <div class="completion-bar">
      <span class="completion-label">检查完成度</span>
      <el-progress
        :percentage="completionStats.rate"
        :stroke-width="14"
        :format="() => `${completionStats.completed}/${completionStats.total}`"
        style="flex: 1"
      />
    </div>

    <!-- ═══ Section Cards ═══ -->
    <template v-for="sectionKey in sectionKeys" :key="sectionKey">
      <el-card shadow="never" class="check-section-card">
        <template #header>
          <div class="card-header">
            <span class="card-title">{{ sectionLabels[sectionKey] }}</span>
            <div class="card-header-right">
              <el-button
                v-if="sectionHasAi(sectionKey)"
                size="small"
                @click="handleAI(sectionKey)"
              >
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
              <el-button size="small" @click="handleReview(sectionKey)">
                <el-icon><Check /></el-icon> 复核
              </el-button>
            </div>
          </div>
        </template>

        <!-- 检查项列表 -->
        <div
          v-for="item in sections[sectionKey]"
          :key="item.key"
          class="check-item"
        >
          <div class="check-item-title">{{ item.title }}</div>
          <div class="check-item-fields">
            <div class="field-group">
              <label class="field-label">结论</label>
              <el-select
                :model-value="item.conclusion"
                size="small"
                placeholder="请选择"
                clearable
                :disabled="isReadonly"
                style="width: 120px"
                @change="(val: string) => updateCheckItem(item.key, 'conclusion', val || '')"
              >
                <el-option
                  v-for="opt in L7_CONCLUSION_OPTIONS.filter(o => o !== '')"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
            </div>
            <div class="field-group field-remark">
              <label class="field-label">备注</label>
              <el-input
                :model-value="item.auditRemark"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 4 }"
                size="small"
                placeholder="审计说明/备注..."
                :readonly="isReadonly"
                @input="(val: string) => updateCheckItem(item.key, 'auditRemark', val)"
              />
            </div>
          </div>
        </div>
      </el-card>
    </template>

    <!-- ═══ 总体审计结论区 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">五、总体审计结论</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="handleReview('conclusion')">
              <el-icon><Check /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>

      <div class="conclusion-fields">
        <div class="field-group">
          <label class="field-label">审计结论</label>
          <el-select
            :model-value="auditConclusion"
            size="small"
            placeholder="请选择总体结论"
            clearable
            :disabled="isReadonly"
            style="width: 160px"
            @change="(val: string) => saveAuditConclusion(val || '')"
          >
            <el-option label="通过" value="通过" />
            <el-option label="不通过" value="不通过" />
            <el-option label="有保留" value="有保留" />
          </el-select>
        </div>
        <div class="field-group field-remark">
          <label class="field-label">结论说明</label>
          <el-input
            :model-value="conclusionRemark"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            placeholder="综合判断其他非流动负债是否真实、完整、分类恰当、计量准确..."
            :readonly="isReadonly"
            @input="(val: string) => updateConclusionRemark(val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>检查项结论选项：通过/不通过/不适用</li>
        <li>需逐项确认存在性、完整性、分类、准确性</li>
        <li>完整性重点关注一年内到期部分是否重分类</li>
        <li>准确性核对明细表L7-2合计与审定表L7-1一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabOtherCheck.vue — L7-4 其他非流动负债检查表
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 4.4
 * Requirements: 4.1-4.2
 *
 * 功能：
 * - 4 sections (存在性/完整性/分类/准确性) each in el-card
 * - Section header: title on left, AI button + review button on right
 * - Each check item: title + conclusion (el-select) + remark (el-input textarea autosize)
 * - Overall audit conclusion section (el-card包裹)
 * - Completion stats progress bar
 * - Font 13px, inject openReviewDialog
 */
import { computed, inject, onMounted } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL7FormData } from '../../composables/useL7FormData'
import {
  useL7OtherCheck,
  L7_CONCLUSION_OPTIONS,
  type L7CheckSection,
} from '../../composables/useL7OtherCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useL7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── useL7OtherCheck ────────────────────────────────────────────────────────

const {
  sections,
  sectionLabels,
  auditConclusion,
  conclusionRemark,
  completionStats,
  updateCheckItem,
  saveAuditConclusion,
  updateConclusionRemark,
} = useL7OtherCheck({
  allResponses: formData.allResponses,
  saveField: formData.saveField,
  debouncedSave: formData.debouncedSave,
})

// ─── Section keys (排除conclusion，独立处理) ────────────────────────────────

const sectionKeys: L7CheckSection[] = ['existence', 'completeness', 'classification', 'accuracy']

/** 判断section是否有AI辅助项 */
function sectionHasAi(section: L7CheckSection): boolean {
  return (sections.value[section] || []).some(item => item.hasAiAssist)
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l7-other-check-${section}`,
      prompt: `请基于其他非流动负债底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview(sectionId?: string) {
  openReviewDialog?.(sectionId || 'L7-4-check')
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l7-tab-other-check { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* 完成度进度条 */
.completion-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding: 10px 16px; background: linear-gradient(135deg, #f8f9fe, #f0f4ff); border-radius: 6px; border: 1px solid #e4e7ed; }
.completion-label { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #303133; white-space: nowrap; }

/* Section Cards */
.check-section-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.card-header-right { display: flex; align-items: center; gap: 8px; }

/* 检查项 */
.check-item { padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
.check-item:last-child { border-bottom: none; }
.check-item-title { font-size: var(--wp-font-size, 13px); color: #303133; margin-bottom: 8px; line-height: 1.5; }
.check-item-fields { display: flex; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.field-group { display: flex; flex-direction: column; gap: 4px; }
.field-label { font-size: 12px; color: #909399; }
.field-remark { flex: 1; min-width: 200px; }

/* 结论区 */
.conclusion-card { margin-bottom: 16px; border: 1px solid #d9ecff; }
.conclusion-fields { display: flex; flex-direction: column; gap: 12px; }

/* 编制提示 */
.l7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
</style>
