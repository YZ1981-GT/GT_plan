<!--
  WorkpaperSidePanel — 底稿/报表编辑器统一右栏面板 [R7-S3-05 / wp-frontend-ux-polish]

  重构为 4 功能组（一级 el-tabs）+ 组内二级 el-tabs：
  1. 编制辅助：AI / 程序 / 程序要求 / 提示
  2. 质量检查：自检 / 一致性 / 公式 / 复核标记
  3. 追溯关联：附件 / 依赖 / 证据 / PBC / 批注
  4. 历史版本：版本

  badge 汇总到组标签，保留所有现有子面板组件。
-->
<template>
  <div class="gt-wp-side-panel">
    <el-tabs v-model="activeGroup" type="border-card" stretch class="gt-wp-side-group-tabs">
      <!-- ═══ 组 1：编制辅助 ═══ -->
      <el-tab-pane name="assist" lazy>
        <template #label>
          <span class="gt-group-label">
            编制辅助
            <el-badge v-if="assistBadge > 0" :value="assistBadge" :max="99" class="gt-wp-side-badge" />
          </span>
        </template>
        <el-tabs v-model="assistTab" type="card" class="gt-wp-side-inner-tabs">
          <el-tab-pane label="AI" name="ai" lazy>
            <AiAssistantSidebar v-if="wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane label="程序" name="procedures" lazy>
            <ProcedurePanel v-if="wpId" :project-id="projectId" :wp-id="wpId" @completion-change="onProcedureCompletionChange" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane label="程序要求" name="requirements" lazy>
            <ProgramRequirementsSidebar v-if="wpCode && wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">无底稿信息</div>
          </el-tab-pane>
          <el-tab-pane label="提示" name="tips" lazy>
            <QualityScoreBadge v-if="wpId" :score="0" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>

      <!-- ═══ 组 2：质量检查 ═══ -->
      <el-tab-pane name="quality" lazy>
        <template #label>
          <span class="gt-group-label">
            质量检查
            <el-badge v-if="qualityBadge > 0" :value="qualityBadge" :max="99" class="gt-wp-side-badge" />
          </span>
        </template>
        <el-tabs v-model="qualityTab" type="card" class="gt-wp-side-inner-tabs">
          <el-tab-pane name="finecheck" lazy>
            <template #label>
              <span>自检 <el-badge v-if="fineCheckFailCount > 0" :value="fineCheckFailCount" :max="99" class="gt-wp-side-badge" /></span>
            </template>
            <div v-if="!wpId" class="gt-wp-side-placeholder">请先选择底稿</div>
            <div v-else-if="fineCheckLoading" v-loading="true" style="min-height: 120px" />
            <div v-else-if="!fineChecks.length" class="gt-wp-side-placeholder">暂无检查项</div>
            <div v-else class="gt-wp-finecheck-list">
              <div v-for="chk in fineChecks" :key="chk.rule_code" class="gt-wp-finecheck-item" :class="{ 'gt-wp-finecheck-fail': chk.passed === false, 'gt-wp-finecheck-pass': chk.passed === true }">
                <div class="gt-wp-finecheck-header">
                  <span class="gt-wp-finecheck-code">{{ chk.rule_code }}</span>
                  <span v-if="chk.passed === true" class="gt-wp-finecheck-status-ok">✓ 通过</span>
                  <span v-else-if="chk.passed === false" class="gt-wp-finecheck-status-fail">✗ 失败</span>
                  <span v-else class="gt-wp-finecheck-status-pending">待验证</span>
                </div>
                <div class="gt-wp-finecheck-desc">{{ chk.description }}</div>
                <div v-if="chk.passed === false" class="gt-wp-finecheck-msg">
                  {{ chk.message }}
                  <el-button v-if="chk.cell_ref" size="small" text type="primary" @click="onLocateCell(chk)">定位 →</el-button>
                </div>
              </div>
              <div class="gt-wp-finecheck-footer">
                <el-button size="small" text @click="loadFineChecks(true)" :loading="fineCheckLoading">🔄 重新检查</el-button>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane label="一致性" name="consistency" lazy>
            <CrossCheckPanel v-if="wpId" :project-id="projectId" :year="currentYear" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane label="公式" name="formulas" lazy>
            <FormulaStatusPanel v-if="wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane name="review-marks" lazy>
            <template #label>
              <span>复核标记 <el-badge v-if="reviewMarkCount > 0" :value="reviewMarkCount" :max="99" class="gt-wp-side-badge" /></span>
            </template>
            <div v-if="!wpId" class="gt-wp-side-placeholder">请先选择底稿</div>
            <div v-else-if="reviewMarksLoading" v-loading="true" style="min-height: 120px" />
            <div v-else>
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
                <div v-for="mark in filteredReviewMarks" :key="mark.id" class="gt-wp-review-item" @click="onLocateReviewMark(mark)">
                  <div class="gt-wp-review-item-header">
                    <span class="gt-wp-review-cell-ref">{{ mark.sheet_name }}!{{ mark.cell_ref }}</span>
                    <el-tag :type="mark.status === 'reviewed' ? 'success' : mark.status === 'questioned' ? 'warning' : 'info'" size="small" round>
                      {{ mark.status === 'reviewed' ? '已复核' : mark.status === 'questioned' ? '有疑问' : '待确认' }}
                    </el-tag>
                  </div>
                  <div v-if="mark.content" class="gt-wp-review-item-content">{{ mark.content }}</div>
                  <div class="gt-wp-review-item-meta">{{ mark.author_name || '未知' }} · {{ mark.created_at?.slice(0, 16) }}</div>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>

      <!-- ═══ 组 3：追溯关联 ═══ -->
      <el-tab-pane name="trace" lazy>
        <template #label>
          <span class="gt-group-label">
            追溯关联
            <el-badge v-if="traceBadge > 0" :value="traceBadge" :max="99" class="gt-wp-side-badge" />
          </span>
        </template>
        <el-tabs v-model="traceTab" type="card" class="gt-wp-side-inner-tabs">
          <el-tab-pane label="附件" name="attachments" lazy>
            <AttachmentTabPanel v-if="wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane label="依赖" name="dependencies" lazy>
            <DependencyGraph v-if="wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane label="证据" name="evidence" lazy>
            <EvidenceLinkPanel v-if="wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane label="PBC" name="pbc" lazy>
            <PbcCollectionTab v-if="wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
          <el-tab-pane label="批注" name="annotations" lazy>
            <CellAnnotationPanel v-if="wpId" :project-id="projectId" :wp-id="wpId" />
            <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>

      <!-- ═══ 组 4：历史版本 ═══ -->
      <el-tab-pane name="history" lazy>
        <template #label>
          <span class="gt-group-label">历史版本</span>
        </template>
        <SnapshotCompare v-if="wpId" :snapshots="[]" :changes="[]" />
        <div v-else class="gt-wp-side-placeholder">请先选择底稿</div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import AiAssistantSidebar from '@/components/workpaper/AiAssistantSidebar.vue'
import AttachmentTabPanel from '@/components/workpaper/AttachmentTabPanel.vue'
import ProgramRequirementsSidebar from '@/components/workpaper/ProgramRequirementsSidebar.vue'
import ProcedurePanel from '@/components/workpaper/ProcedurePanel.vue'
import DependencyGraph from '@/components/workpaper/DependencyGraph.vue'
import CellAnnotationPanel from '@/components/workpaper/CellAnnotationPanel.vue'
import CrossCheckPanel from '@/components/workpaper/CrossCheckPanel.vue'
import FormulaStatusPanel from '@/components/workpaper/FormulaStatusPanel.vue'
import EvidenceLinkPanel from '@/components/workpaper/EvidenceLinkPanel.vue'
import PbcCollectionTab from '@/components/workpaper/PbcCollectionTab.vue'
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
  projectId: string
  wpId?: string
  wpCode?: string
}>()

const emit = defineEmits<{
  (e: 'finecheck-update', count: number): void
  (e: 'procedure-completion-change', rate: number): void
}>()

// ─── 一级组 Tab ──────────────────────────────
const activeGroup = ref('assist')
// ─── 二级 Tab ──────────────────────────────
const assistTab = ref('ai')
const qualityTab = ref('finecheck')
const traceTab = ref('attachments')

const currentYear = computed(() => new Date().getFullYear())

// ─── Badge 汇总 ──────────────────────────────
const assistBadge = computed(() => 0) // 编制辅助暂无汇总
const qualityBadge = computed(() => fineCheckFailCount.value + reviewMarkCount.value)
const traceBadge = computed(() => 0) // 追溯关联暂无汇总

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
  eventBus.emit('workpaper:locate-cell', {
    wpId: props.wpId || '',
    sheetName: chk.sheet_name || '',
    cellRef: chk.cell_ref,
  })
}

watch(fineCheckFailCount, (n) => emit('finecheck-update', n))

// 组/Tab 切换时按需加载
watch([() => activeGroup.value, () => qualityTab.value], ([group, tab]) => {
  if (group === 'quality' && tab === 'finecheck') loadFineChecks()
  if (group === 'quality' && tab === 'review-marks') loadReviewMarks()
})

watch(() => props.wpId, () => {
  fineChecks.value = []
  reviewMarks.value = []
})

// ─── 复核标记 Tab ──────────────────────────────
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
.gt-wp-side-group-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.gt-wp-side-group-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}
.gt-wp-side-group-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.gt-wp-side-group-tabs :deep(.el-tabs__item) {
  font-size: var(--gt-font-size-xs);
  padding: 0 10px;
}
.gt-wp-side-inner-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}
.gt-wp-side-inner-tabs :deep(.el-tabs__content) {
  padding: var(--gt-space-2);
  overflow-y: auto;
}
.gt-wp-side-inner-tabs :deep(.el-tabs__item) {
  font-size: var(--gt-font-size-xs);
  padding: 0 8px;
}
.gt-group-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.gt-wp-side-placeholder {
  padding: var(--gt-space-8);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}
.gt-wp-side-badge :deep(.el-badge__content) {
  transform: scale(0.8) translate(80%, -30%);
}
.gt-wp-finecheck-list { display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-wp-finecheck-item { padding: var(--gt-space-2) var(--gt-space-3); border-radius: var(--gt-radius-sm); border: 1px solid var(--gt-color-border-light); background: var(--gt-color-bg-elevated); }
.gt-wp-finecheck-fail { background: var(--gt-color-coral-light); border-color: var(--gt-color-coral); }
.gt-wp-finecheck-pass { background: var(--gt-color-success-light); }
.gt-wp-finecheck-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.gt-wp-finecheck-code { font-family: monospace; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); font-weight: 600; }
.gt-wp-finecheck-status-ok { color: var(--gt-color-success); font-size: var(--gt-font-size-xs); font-weight: 600; }
.gt-wp-finecheck-status-fail { color: var(--gt-color-coral); font-size: var(--gt-font-size-xs); font-weight: 600; }
.gt-wp-finecheck-status-pending { color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); }
.gt-wp-finecheck-desc { font-size: var(--gt-font-size-sm); color: var(--gt-color-text); line-height: 1.5; }
.gt-wp-finecheck-msg { margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--gt-color-coral); display: flex; align-items: center; gap: 4px; }
.gt-wp-finecheck-footer { margin-top: var(--gt-space-3); text-align: center; border-top: 1px dashed var(--gt-color-border-light); padding-top: var(--gt-space-2); }
.gt-wp-review-filter { margin-bottom: var(--gt-space-3); }
.gt-wp-review-list { display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-wp-review-item { padding: var(--gt-space-2) var(--gt-space-3); border-radius: var(--gt-radius-sm); border: 1px solid var(--gt-color-border-light); background: var(--gt-color-bg-elevated); cursor: pointer; transition: background 0.15s; }
.gt-wp-review-item:hover { background: var(--gt-color-primary-bg); }
.gt-wp-review-item-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.gt-wp-review-cell-ref { font-family: monospace; font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-primary); }
.gt-wp-review-item-content { font-size: var(--gt-font-size-sm); color: var(--gt-color-text); margin-bottom: 4px; }
.gt-wp-review-item-meta { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
