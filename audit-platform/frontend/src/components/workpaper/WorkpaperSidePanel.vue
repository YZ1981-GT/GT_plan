<!--
  WorkpaperSidePanel — 底稿/报表编辑器统一右栏面板 [R7-S3-05 Task 24 / R8-S2-01]

  @docs ../../../docs/WORKPAPER_SIDE_PANEL_GUIDE.md

  10 Tab 容器：AI / 附件 / 版本 / 批注 / 程序 / 程序要求 / 依赖 / 一致性 / 自检 / 提示
  所有编辑器（WorkpaperEditor/WorkpaperWorkbench/DisclosureEditor/AuditReportEditor/ReportConfigEditor）
  统一使用此组件作为右栏，禁止各自自建独立面板。

  用法：
    <WorkpaperSidePanel :project-id="projectId" :wp-id="wpId" :wp-code="wpCode" />
-->
<template>
  <div class="gt-wp-side-panel">
    <el-tabs v-model="activeTab" type="border-card" stretch class="gt-wp-side-tabs">
      <el-tab-pane label="AI" name="ai" lazy>
        <slot name="ai">
          <AiAssistantSidebar v-if="wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="附件" name="attachments" lazy>
        <slot name="attachments">
          <AttachmentDropZone v-if="wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="版本" name="versions" lazy>
        <slot name="versions">
          <SnapshotCompare
            v-if="wpId"
            :snapshots="[]"
            :changes="[]"
          />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="批注" name="annotations" lazy>
        <slot name="annotations">
          <CellAnnotationPanel
            v-if="wpId"
            :project-id="projectId"
            :wp-id="wpId"
          />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="程序" name="procedures" lazy>
        <slot name="procedures">
          <ProcedurePanel
            v-if="wpId"
            :project-id="projectId"
            :wp-id="wpId"
            @completion-change="onProcedureCompletionChange"
          />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="程序要求" name="requirements" lazy>
        <slot name="requirements">
          <ProgramRequirementsSidebar v-if="wpCode && wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">无底稿信息</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="依赖" name="dependencies" lazy>
        <slot name="dependencies">
          <DependencyGraph v-if="wpId" :project-id="projectId" :wp-id="wpId" />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="一致性" name="consistency" lazy>
        <slot name="consistency">
          <CrossCheckPanel
            v-if="wpId"
            :project-id="projectId"
            :year="currentYear"
          />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
      <!-- 公式状态 Tab -->
      <el-tab-pane label="公式" name="formulas" lazy>
        <FormulaStatusPanel
          v-if="wpId"
          :project-id="projectId"
          :wp-id="wpId"
        />
        <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
      </el-tab-pane>
      <!-- 证据链 Tab -->
      <el-tab-pane label="证据" name="evidence" lazy>
        <EvidenceLinkPanel
          v-if="wpId"
          :project-id="projectId"
          :wp-id="wpId"
        />
        <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
      </el-tab-pane>
      <!-- Task 2.5: 复核标记 Tab -->
      <el-tab-pane name="review-marks" lazy>
        <template #label>
          <span>
            复核标记
            <el-badge
              v-if="reviewMarkCount > 0"
              :value="reviewMarkCount"
              :max="99"
              class="gt-wp-side-badge"
            />
          </span>
        </template>
        <div v-if="!wpId" class="gt-wp-side-placeholder">请先选择底稿</div>
        <div v-else-if="reviewMarksLoading" v-loading="true" style="min-height: 120px" />
        <div v-else>
          <!-- 状态筛选 -->
          <div class="gt-wp-review-filter">
            <el-radio-group v-model="reviewFilterStatus" size="small">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="reviewed">已复核</el-radio-button>
              <el-radio-button value="pending">待确认</el-radio-button>
              <el-radio-button value="questioned">有疑问</el-radio-button>
            </el-radio-group>
          </div>
          <div v-if="filteredReviewMarks.length === 0" class="gt-wp-side-placeholder">暂无复核标记</div>
          <div v-else class="gt-wp-review-list">
            <div
              v-for="mark in filteredReviewMarks"
              :key="mark.id"
              class="gt-wp-review-item"
              @click="onLocateReviewMark(mark)"
            >
              <div class="gt-wp-review-item-header">
                <span class="gt-wp-review-cell-ref">{{ mark.sheet_name }}!{{ mark.cell_ref }}</span>
                <el-tag
                  :type="mark.status === 'reviewed' ? 'success' : mark.status === 'questioned' ? 'warning' : 'info'"
                  size="small"
                  round
                >
                  {{ mark.status === 'reviewed' ? '已复核' : mark.status === 'questioned' ? '有疑问' : '待确认' }}
                </el-tag>
              </div>
              <div v-if="mark.content" class="gt-wp-review-item-content">{{ mark.content }}</div>
              <div class="gt-wp-review-item-meta">
                {{ mark.author_name || '未知' }} · {{ mark.created_at?.slice(0, 16) }}
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>
      <!-- R8-S2-02：自检 Tab（失败项可定位到 Univer 单元格） -->
      <el-tab-pane name="finecheck" lazy>
        <template #label>
          <span>
            自检
            <el-badge
              v-if="fineCheckFailCount > 0"
              :value="fineCheckFailCount"
              :max="99"
              class="gt-wp-side-badge"
            />
          </span>
        </template>
        <slot name="finecheck">
          <div v-if="!wpId" class="gt-wp-side-placeholder">请先选择底稿</div>
          <div v-else-if="fineCheckLoading" v-loading="true" style="min-height: 120px" />
          <div v-else-if="!fineChecks.length" class="gt-wp-side-placeholder">暂无检查项</div>
          <div v-else class="gt-wp-finecheck-list">
            <div
              v-for="chk in fineChecks"
              :key="chk.rule_code"
              class="gt-wp-finecheck-item"
              :class="{ 'gt-wp-finecheck-fail': chk.passed === false, 'gt-wp-finecheck-pass': chk.passed === true }"
            >
              <div class="gt-wp-finecheck-header">
                <span class="gt-wp-finecheck-code">{{ chk.rule_code }}</span>
                <span v-if="chk.passed === true" class="gt-wp-finecheck-status-ok">✓ 通过</span>
                <span v-else-if="chk.passed === false" class="gt-wp-finecheck-status-fail">✗ 失败</span>
                <span v-else class="gt-wp-finecheck-status-pending">待验证</span>
              </div>
              <div class="gt-wp-finecheck-desc">{{ chk.description }}</div>
              <div v-if="chk.passed === false" class="gt-wp-finecheck-msg">
                {{ chk.message }}
                <el-button
                  v-if="chk.cell_ref"
                  size="small"
                  text
                  type="primary"
                  @click="onLocateCell(chk)"
                >
                  定位 →
                </el-button>
              </div>
            </div>
          </div>
          <div v-if="fineChecks.length" class="gt-wp-finecheck-footer">
            <el-button size="small" text @click="loadFineChecks(true)" :loading="fineCheckLoading">
              🔄 重新检查
            </el-button>
          </div>
        </slot>
      </el-tab-pane>
      <el-tab-pane label="提示" name="tips" lazy>
        <slot name="tips">
          <QualityScoreBadge
            v-if="wpId"
            :score="0"
          />
          <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
        </slot>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import AiAssistantSidebar from '@/components/workpaper/AiAssistantSidebar.vue'
import AttachmentDropZone from '@/components/workpaper/AttachmentDropZone.vue'
import ProgramRequirementsSidebar from '@/components/workpaper/ProgramRequirementsSidebar.vue'
import ProcedurePanel from '@/components/workpaper/ProcedurePanel.vue'
import DependencyGraph from '@/components/workpaper/DependencyGraph.vue'
import CellAnnotationPanel from '@/components/workpaper/CellAnnotationPanel.vue'
import CrossCheckPanel from '@/components/workpaper/CrossCheckPanel.vue'
import FormulaStatusPanel from '@/components/workpaper/FormulaStatusPanel.vue'
import EvidenceLinkPanel from '@/components/workpaper/EvidenceLinkPanel.vue'
import SnapshotCompare from '@/components/workpaper/SnapshotCompare.vue'
import QualityScoreBadge from '@/components/workpaper/QualityScoreBadge.vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

interface FineCheckResult {
  rule_code: string
  description: string
  passed: boolean | null
  message?: string
  cell_ref?: string
  sheet_name?: string
}

interface ReviewMarkItem {
  id: string
  sheet_name: string
  cell_ref: string
  status: string
  content: string
  author_name?: string
  created_at: string
}

const props = defineProps<{
  /** 项目 ID */
  projectId: string
  /** 底稿 ID（可选，非底稿编辑器可不传） */
  wpId?: string
  /** 底稿编码（可选，用于程序要求 Tab） */
  wpCode?: string
}>()

const emit = defineEmits<{
  (e: 'finecheck-update', count: number): void
  (e: 'procedure-completion-change', rate: number): void
}>()

const activeTab = ref('ai')
const currentYear = computed(() => new Date().getFullYear())

// ─── 程序完成率联动 ──────────────────────────────
function onProcedureCompletionChange(rate: number) {
  emit('procedure-completion-change', rate)
}

// ─── 自检 Tab ──────────────────────────────
const fineChecks = ref<FineCheckResult[]>([])
const fineCheckLoading = ref(false)

const fineCheckFailCount = computed(
  () => fineChecks.value.filter((c) => c.passed === false).length,
)

async function loadFineChecks(force = false) {
  if (!props.wpId || !props.projectId) return
  if (!force && fineChecks.value.length > 0) return
  fineCheckLoading.value = true
  try {
    // 复用已有的 fine-checks/summary 端点，按 wp_id 过滤
    const data: any = await api.get(
      `/api/projects/${props.projectId}/fine-checks/summary`,
      { validateStatus: (s: number) => s < 600 },
    )
    const wpResult = data?.[props.wpId] || data?.results?.[props.wpId]
    fineChecks.value = wpResult?.checks || []
  } catch {
    fineChecks.value = []
  } finally {
    fineCheckLoading.value = false
  }
}

function onLocateCell(chk: FineCheckResult) {
  if (!chk.cell_ref) return
  // R8-S2-02：发 eventBus 事件，由 WorkpaperEditor 接收后调 Univer API 定位
  eventBus.emit('workpaper:locate-cell', {
    wpId: props.wpId || '',
    sheetName: chk.sheet_name || '',
    cellRef: chk.cell_ref,
  })
}

// badge 数量变化时通知父组件
watch(fineCheckFailCount, (n) => emit('finecheck-update', n))

// Tab 切到自检时按需加载
watch(activeTab, (tab) => {
  if (tab === 'finecheck') loadFineChecks()
  if (tab === 'review-marks') loadReviewMarks()
})

// wpId 变化时清空缓存
watch(
  () => props.wpId,
  () => {
    fineChecks.value = []
    reviewMarks.value = []
  },
)

// ─── Task 2.5: Review Marks Tab ──────────────────────────────
const reviewMarks = ref<ReviewMarkItem[]>([])
const reviewMarksLoading = ref(false)
const reviewFilterStatus = ref('')

const reviewMarkCount = computed(() => reviewMarks.value.length)

const filteredReviewMarks = computed(() => {
  if (!reviewFilterStatus.value) return reviewMarks.value
  return reviewMarks.value.filter(m => m.status === reviewFilterStatus.value)
})

async function loadReviewMarks() {
  if (!props.wpId || !props.projectId) return
  reviewMarksLoading.value = true
  try {
    const data: any = await api.get(
      `/api/projects/${props.projectId}/cell-annotations`,
      { params: { object_id: props.wpId, annotation_type: 'review_mark' } },
    )
    const items = data?.items || data || []
    reviewMarks.value = items.map((item: any) => ({
      id: item.id,
      sheet_name: item.sheet_name || '',
      cell_ref: item.cell_ref || '',
      status: item.status || 'pending',
      content: item.content || '',
      author_name: item.author_name,
      created_at: item.created_at || '',
    }))
  } catch {
    reviewMarks.value = []
  } finally {
    reviewMarksLoading.value = false
  }
}

function onLocateReviewMark(mark: ReviewMarkItem) {
  if (!mark.cell_ref) return
  eventBus.emit('workpaper:locate-cell', {
    wpId: props.wpId || '',
    sheetName: mark.sheet_name || '',
    cellRef: mark.cell_ref,
  })
}

// Subscribe to review-mark:changed event for refresh
eventBus.on('review-mark:changed', (payload: any) => {
  if (payload?.wpId === props.wpId) {
    loadReviewMarks()
  }
})
</script>

<style scoped>
.gt-wp-side-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-white);
}
.gt-wp-side-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.gt-wp-side-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
  padding: var(--gt-space-2);
}
.gt-wp-side-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.gt-wp-side-tabs :deep(.el-tabs__item) {
  font-size: var(--gt-font-size-xs);
  padding: 0 8px;
}
.gt-wp-side-placeholder {
  padding: var(--gt-space-8);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}

/* 自检 Tab 样式 */
.gt-wp-side-badge :deep(.el-badge__content) {
  transform: scale(0.8) translate(80%, -30%);
}
.gt-wp-finecheck-list {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-2);
}
.gt-wp-finecheck-item {
  padding: var(--gt-space-2) var(--gt-space-3);
  border-radius: var(--gt-radius-sm);
  border: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-elevated);
}
.gt-wp-finecheck-fail {
  background: var(--gt-color-coral-light);
  border-color: var(--gt-color-coral);
}
.gt-wp-finecheck-pass {
  background: var(--gt-color-success-light);
}
.gt-wp-finecheck-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.gt-wp-finecheck-code {
  font-family: monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  font-weight: 600;
}
.gt-wp-finecheck-status-ok {
  color: var(--gt-color-success);
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
}
.gt-wp-finecheck-status-fail {
  color: var(--gt-color-coral);
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
}
.gt-wp-finecheck-status-pending {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
}
.gt-wp-finecheck-desc {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  line-height: 1.5;
}
.gt-wp-finecheck-msg {
  margin-top: 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-coral);
  display: flex;
  align-items: center;
  gap: 4px;
}
.gt-wp-finecheck-footer {
  margin-top: var(--gt-space-3);
  text-align: center;
  border-top: 1px dashed var(--gt-color-border-light);
  padding-top: var(--gt-space-2);
}

/* ─── Task 2.5: Review Marks Tab ─── */
.gt-wp-review-filter {
  margin-bottom: var(--gt-space-3);
}
.gt-wp-review-list {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-2);
}
.gt-wp-review-item {
  padding: var(--gt-space-2) var(--gt-space-3);
  border-radius: var(--gt-radius-sm);
  border: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-elevated);
  cursor: pointer;
  transition: background 0.15s;
}
.gt-wp-review-item:hover {
  background: var(--gt-color-primary-bg);
}
.gt-wp-review-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.gt-wp-review-cell-ref {
  font-family: monospace;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-wp-review-item-content {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  margin-bottom: 4px;
}
.gt-wp-review-item-meta {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
</style>
