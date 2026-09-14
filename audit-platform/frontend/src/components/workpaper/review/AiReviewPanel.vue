<script setup lang="ts">
/**
 * ReviewPanel — 复核结果展示面板
 *
 * Feature: review-prompt-sheet-level-split
 * Requirements: 6.1, 6.2, 6.3, 6.4
 *
 * 展示每张底稿的复核发现：通过/未通过徽章、发现项数、风险等级分布。
 * 支持批量复核、单底稿展开、Excel 导出。
 */
import { computed, ref } from 'vue'
import { useReviewPanel } from './useReviewPanel'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'

interface ReviewPanelProps {
  projectId: string
  wpCodePrefix: string
  year: number
}

const props = defineProps<ReviewPanelProps>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const {
  sheets,
  isReviewing,
  progress,
  expandedSheet,
  startBatchReview,
  reviewCurrentSheet,
  exportReviewExcel,
  toggleSheet,
  updateFindingStatus,
} = useReviewPanel(props.projectId, props.wpCodePrefix, props.year)

defineExpose({
  reviewCurrentSheet,
  startBatchReview,
})

const { currentRole } = usePermissionMatrix()

/** 筛选：全部 / 仅底稿级 / 仅降级（科目级+通用） */
const sourceFilter = ref<'all' | 'sheet' | 'fallback'>('all')

const filteredSheets = computed(() => {
  if (sourceFilter.value === 'all') return sheets.value
  if (sourceFilter.value === 'sheet') {
    return sheets.value.filter((s) => s.promptSource === 'sheet')
  }
  return sheets.value.filter((s) => s.promptSource === 'subject' || s.promptSource === 'base')
})

const fallbackCount = computed(() =>
  sheets.value.filter((s) => s.promptSource === 'subject' || s.promptSource === 'base').length,
)

/** 批量复核按钮可见性：现场经理/业务合伙人/QC合伙人 */
const canStartReview = computed(() => {
  const allowedRoles = ['manager', 'partner', 'qc', 'admin']
  return allowedRoles.includes(currentRole.value)
})

/** 复核进度百分比 */
const progressPercent = computed(() => {
  if (progress.total === 0) return 0
  return Math.round((progress.current / progress.total) * 100)
})

/** 通过/未通过 badge 类型 */
function getPassBadgeType(status: string): string {
  switch (status) {
    case 'pass': return 'success'
    case 'fail': return 'danger'
    case 'review_error': return 'warning'
    default: return 'info'
  }
}

/** 通过/未通过 badge 文案 */
function getPassBadgeText(status: string): string {
  switch (status) {
    case 'pass': return '通过'
    case 'fail': return '未通过'
    case 'review_error': return '复核异常'
    default: return '待复核'
  }
}

/** 风险等级 tag 类型 */
function getRiskTagType(level: string): string {
  switch (level) {
    case 'high': return 'danger'
    case 'medium': return 'warning'
    case 'low': return 'info'
    default: return 'info'
  }
}

/** 风险等级标签文字 */
function getRiskLabel(level: string): string {
  switch (level) {
    case 'high': return '高风险'
    case 'medium': return '中风险'
    case 'low': return '低风险'
    default: return '未知'
  }
}

/** 提示词来源标签 */
function getPromptSourceLabel(source?: string): string {
  switch (source) {
    case 'sheet': return '底稿级'
    case 'subject': return '科目级'
    case 'base': return '通用'
    default: return ''
  }
}

function getPromptSourceTagType(source?: string): string {
  switch (source) {
    case 'sheet': return 'success'
    case 'subject': return 'warning'
    case 'base': return 'info'
    default: return 'info'
  }
}
</script>

<template>
  <div class="review-panel">
    <!-- 工具栏 -->
    <div class="review-panel__toolbar">
      <el-button
        v-if="canStartReview"
        type="primary"
        :loading="isReviewing"
        @click="startBatchReview"
      >
        {{ isReviewing ? '复核中...' : '开始批量复核' }}
      </el-button>
      <el-button
        :disabled="sheets.length === 0"
        @click="exportReviewExcel"
      >
        导出Excel
      </el-button>
      <el-radio-group
        v-if="sheets.length > 0"
        v-model="sourceFilter"
        size="small"
        class="review-panel__filter"
      >
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="sheet">底稿级</el-radio-button>
        <el-radio-button value="fallback">
          降级{{ fallbackCount > 0 ? `(${fallbackCount})` : '' }}
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- 复核汇总统计 -->
    <div v-if="sheets.length > 0" class="review-panel__summary">
      <el-statistic title="底稿总数" :value="sheets.length" />
      <el-statistic title="通过" :value="sheets.filter(s => s.passStatus === 'pass').length" />
      <el-statistic title="未通过" :value="sheets.filter(s => s.passStatus === 'fail').length" />
      <el-statistic title="总发现项" :value="sheets.reduce((sum, s) => sum + s.findingCount, 0)" />
      <el-statistic title="降级提示词" :value="fallbackCount" />
    </div>

    <!-- 复核进度 -->
    <div v-if="isReviewing" class="review-panel__progress">
      <el-progress
        :percentage="progressPercent"
        :stroke-width="16"
        striped
        striped-flow
      />
      <span class="review-panel__progress-text">
        正在复核：{{ progress.currentSheet }}（{{ progress.current }}/{{ progress.total }}）
      </span>
    </div>

    <!-- 底稿卡片列表 -->
    <div v-if="filteredSheets.length > 0" class="review-panel__sheets">
      <el-collapse v-model="expandedSheet" accordion>
        <el-collapse-item
          v-for="sheet in filteredSheets"
          :key="sheet.sheetName"
          :name="sheet.sheetName"
        >
          <template #title>
            <div class="review-card__header">
              <span class="review-card__name">{{ sheet.sheetName }}</span>
              <el-tag
                v-if="sheet.promptSource"
                :type="getPromptSourceTagType(sheet.promptSource)"
                size="small"
                effect="plain"
              >
                {{ getPromptSourceLabel(sheet.promptSource) }}
              </el-tag>
              <el-tag
                :type="getPassBadgeType(sheet.passStatus)"
                size="small"
                effect="dark"
              >
                {{ getPassBadgeText(sheet.passStatus) }}
              </el-tag>
              <el-badge :value="sheet.findingCount" :max="99" class="review-card__badge">
                <span class="review-card__badge-label">发现项</span>
              </el-badge>
              <span class="review-card__risk-dist">
                <el-tag
                  v-if="sheet.riskDistribution.high > 0"
                  type="danger"
                  size="small"
                >
                  高{{ sheet.riskDistribution.high }}
                </el-tag>
                <el-tag
                  v-if="sheet.riskDistribution.medium > 0"
                  type="warning"
                  size="small"
                >
                  中{{ sheet.riskDistribution.medium }}
                </el-tag>
                <el-tag
                  v-if="sheet.riskDistribution.low > 0"
                  type="info"
                  size="small"
                >
                  低{{ sheet.riskDistribution.low }}
                </el-tag>
              </span>
            </div>
          </template>

          <!-- 展开后的 Finding 列表 -->
          <div class="review-card__findings">
            <div
              v-for="finding in sheet.findings"
              :key="finding.id"
              class="finding-item"
            >
              <div class="finding-item__header">
                <el-tag
                  :type="getRiskTagType(finding.risk_level)"
                  size="small"
                >
                  {{ getRiskLabel(finding.risk_level) }}
                </el-tag>
                <span class="finding-item__category">{{ finding.category }}</span>
              </div>
              <div class="finding-item__desc">{{ finding.description }}</div>
              <div v-if="finding.sheet_location" class="finding-item__location" @click="emit('navigate-sheet', finding.sheet_location)" style="cursor: pointer; color: var(--el-color-primary);">
                📍 {{ finding.sheet_location }}
              </div>
              <div v-if="finding.suggestion" class="finding-item__suggestion">
                建议：{{ finding.suggestion }}
              </div>
              <div class="finding-item__actions">
                <el-select
                  :model-value="(finding as any).status || 'pending'"
                  size="small"
                  style="width: 100px"
                  @change="(val: string) => updateFindingStatus(finding.id, val as any)"
                >
                  <el-option value="pending" label="待处理" />
                  <el-option value="resolved" label="已整改" />
                  <el-option value="ignored" label="已忽略" />
                  <el-option value="not_applicable" label="不适用" />
                </el-select>
              </div>
            </div>
            <el-empty
              v-if="sheet.findings.length === 0"
              description="暂无发现项"
              :image-size="60"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 无数据 -->
    <el-empty
      v-else-if="!isReviewing && sheets.length === 0"
      description='暂无复核结果，点击"开始批量复核"启动'
      :image-size="100"
    />
    <el-empty
      v-else-if="!isReviewing && filteredSheets.length === 0"
      description="当前筛选条件下无底稿"
      :image-size="80"
    />
  </div>
</template>

<style scoped>
.review-panel {
  padding: 16px;
}

.review-panel__toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.review-panel__filter {
  margin-left: auto;
}

.review-panel__summary {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.review-panel__progress {
  margin-bottom: 16px;
}

.review-panel__progress-text {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.review-panel__sheets {
  margin-top: 8px;
}

.review-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.review-card__name {
  font-weight: 500;
  font-size: 14px;
}

.review-card__badge {
  margin-left: 4px;
}

.review-card__badge-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.review-card__risk-dist {
  display: flex;
  gap: 4px;
  margin-left: auto;
}

.review-card__findings {
  padding: 8px 0;
}

.finding-item {
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.finding-item:last-child {
  border-bottom: none;
}

.finding-item__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.finding-item__category {
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.finding-item__desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
}

.finding-item__location {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.finding-item__suggestion {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-success);
}

.finding-item__actions {
  margin-top: 6px;
  display: flex;
  align-items: center;
}
</style>
