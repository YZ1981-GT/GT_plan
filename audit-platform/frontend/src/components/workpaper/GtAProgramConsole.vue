<!--
  GtAProgramConsole.vue — A 类程序表中控台组件

  按 design §3.3 实现：
  - 程序行展开显示完整描述 + 历史决策
  - 状态切换（执行/裁剪/已完成）+ 必填理由
  - 关联底稿索引号渲染为 GtIndexChip 可点击
  - 类别筛选（常规★/IPO 加项/备选程序/舞弊应对）
  - 批量裁剪（多选 + 填理由 → 写回 ProcedureInstance.status='not_applicable'）
  - 进度条（17/20 完成 / 2 已裁 / 1 进行中）
  - 5 项认定 checkmark 展示（存在/完整性/权利义务/准确性/列报）

  锚定 spec workpaper-html-renderer Task 3.9
  Validates: Requirements 1.1（D2A 痛点 7 项）+ 3.2（A 程序表详细需求）

  ─── cross-ref:updated 订阅契约（Task 13.2）──────────────────────────────────
  本组件**不直接订阅** eventBus 'cross-ref:updated' 事件。跨底稿引用变化由
  `useWpRenderer.ts`（GtWpRenderer 父组件持有）统一监听 + 重拉 renderConfig，
  本组件通过 props 接收最新 htmlData 自动更新（单一订阅入口避免内存泄漏）。
  Layer 4 联动复用 `useStaleImpact` composable（WorkpaperEditor 已接入）。
-->

<template>
  <div class="gt-a-program-console">
    <!-- B30 等仅限合并审计：standalone 项目不适用覆盖层 -->
    <div v-if="isNotApplicable" class="gt-a-program-console__not-applicable">
      <el-result icon="info" title="不适用">
        <template #sub-title>
          <span>本底稿仅适用于合并审计项目（当前项目为单体审计）</span>
        </template>
      </el-result>
    </div>

    <template v-else>
    <!-- 程序行为空但有网格兜底数据 → 显示只读模板原样（替代程序检查表等非程序行结构） -->
    <div v-if="gridFallback" class="gt-a-program-console__grid-fallback">
      <GtGridSheet
        :wp-id="wpId"
        :sheet-name="sheetName"
        :html-data="gridFallback"
        :readonly="true"
      />
    </div>
    <template v-else>
    <!-- ─── 顶部：进度条 + 工具栏 ─── -->
    <div class="gt-a-program-console__header">
      <!-- 进度条 -->
      <div class="gt-a-program-console__progress">
        <el-progress
          :percentage="progressPercentage"
          :stroke-width="18"
          :text-inside="true"
          :format="progressFormat"
        />
        <div class="gt-a-program-console__progress-detail">
          <el-tag type="success" size="small" effect="plain">
            {{ completedCount }} 已完成
          </el-tag>
          <el-tag type="info" size="small" effect="plain">
            {{ trimmedCount }} 已裁剪
          </el-tag>
          <el-tag type="warning" size="small" effect="plain">
            {{ inProgressCount }} 进行中
          </el-tag>
          <el-tag size="small" effect="plain">
            {{ pendingCount }} 待执行
          </el-tag>
        </div>
        <!-- 阶段分组进度条 -->
        <div v-if="hasPhaseGroups" class="gt-a-program-console__phase-progress">
          <div v-for="group in phaseGroups" :key="group.phase" class="phase-chip">
            <span class="phase-label">{{ group.label }}</span>
            <el-progress
              :percentage="group.progress"
              :stroke-width="8"
              :show-text="false"
              :color="group.progress === 100 ? '#67C23A' : '#4b2d77'"
              style="width: 60px; display: inline-flex; margin-left: 6px"
            />
            <span class="phase-pct">{{ group.progress }}%</span>
          </div>
        </div>
      </div>

      <!-- 工具栏：类别筛选 + 批量操作 -->
      <div class="gt-a-program-console__toolbar">
        <div v-if="!hideCategories" class="gt-a-program-console__filters">
          <el-radio-group v-model="activeCategory" size="small">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button
              v-for="cat in availableCategories"
              :key="cat"
              :label="cat"
            >
              {{ cat }}
            </el-radio-button>
          </el-radio-group>
        </div>

        <div class="gt-a-program-console__actions">
          <!-- Sprint 4 Task 17.7: 审计逻辑图折叠按钮 -->
          <el-button text size="small" @click="flowGraphExpanded = !flowGraphExpanded" title="审计逻辑图">
            🗺️ {{ flowGraphExpanded ? '收起' : '审计逻辑图' }}
          </el-button>
          <!-- Sprint 4 Task 14.3: 重新触发引导按钮 -->
          <el-button text size="small" @click="triggerGuide" title="使用引导">?</el-button>
          <el-button
            v-if="!readonly"
            type="primary"
            size="small"
            @click="openAddDialog"
          >
            + 新增程序
          </el-button>
          <el-button
            v-if="!readonly && selectedIds.length > 0"
            type="warning"
            size="small"
            @click="openBatchTrimDialog"
          >
            批量裁剪 ({{ selectedIds.length }})
          </el-button>
          <el-button size="small" @click="exportProgramTable">📥 导出 Excel</el-button>
        </div>
      </div>
    </div>

    <!-- Sprint 4 Task 17.7: 审计逻辑流程图 -->
    <GtAuditFlowGraph
      v-if="wpId && projectId"
      :wp-id="wpId"
      :project-id="projectId"
      :expanded="flowGraphExpanded"
      :programs="programs"
      @scroll-to-program="scrollToProgramRow"
    />

    <!-- ─── 程序清单表格 ─── -->
    <el-table
      ref="tableRef"
      :data="filteredPrograms"
      border
      row-key="id"
      empty-text="暂无审计程序，请点击上方「+ 新增程序」添加"
      :expand-row-keys="expandedRowKeys"
      @expand-change="handleExpandChange"
      @selection-change="handleSelectionChange"
      class="gt-a-program-console__table gt-tb-font-md"
    >
      <!-- 多选列 -->
      <el-table-column
        v-if="!readonly"
        type="selection"
        width="40"
        :selectable="isRowSelectable"
      />

      <!-- 展开列：子步骤明细 + 历史决策（默认折叠，点击展开） -->
      <el-table-column v-if="hasExpandContent" type="expand">
        <template #default="{ row }">
          <div class="gt-a-program-console__expand-content">
            <!-- 子步骤（二级明细）：从 content 解析的 （N）... 编号子程序 -->
            <div v-if="row.sub_steps && row.sub_steps.length > 0" class="gt-a-program-console__sub-steps">
              <h4>子程序步骤（{{ row.sub_steps.length }}项）</h4>
              <ol class="gt-a-program-console__sub-list">
                <li v-for="step in row.sub_steps" :key="step.no" class="gt-a-program-console__sub-item">
                  {{ step.text }}
                </li>
              </ol>
            </div>
            <!-- 原始完整描述（无子步骤时显示，或作为补充） -->
            <div v-if="!row.sub_steps || row.sub_steps.length === 0" class="gt-a-program-console__expand-desc">
              <h4>程序描述</h4>
              <p>{{ row.program_desc }}</p>
            </div>
            <div
              v-if="row.history && row.history.length > 0"
              class="gt-a-program-console__expand-history"
            >
              <h4>历史决策</h4>
              <el-timeline>
                <el-timeline-item
                  v-for="(item, idx) in row.history"
                  :key="idx"
                  :timestamp="item.timestamp"
                  :type="historyItemType(item.action)"
                  placement="top"
                >
                  <span>{{ item.user }} — {{ item.action }}</span>
                  <span v-if="item.reason" class="gt-a-program-console__history-reason">
                    （{{ item.reason }}）
                  </span>
                </el-timeline-item>
              </el-timeline>
            </div>
          </div>
        </template>
      </el-table-column>

      <!-- 序号 -->
      <el-table-column
        label="序号"
        prop="program_no"
        width="60"
        align="center"
      />

      <!-- 程序描述（截断显示） -->
      <el-table-column
        label="程序描述"
        prop="program_desc"
        min-width="300"
        show-overflow-tooltip
      />

      <!-- 类别（仅当有非空分类数据时显示；A1 等总括程序表此列全空则隐藏） -->
      <el-table-column
        v-if="hasCategory"
        label="类别"
        prop="program_category"
        width="110"
        align="center"
      >
        <template #header>
          <el-tooltip content="程序分类：常规★/IPO加项/备选程序/舞弊应对" placement="top">
            <span>类别</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tag
            :type="categoryTagType(row.program_category)"
            size="small"
            effect="plain"
          >
            {{ row.program_category }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 5 项认定列（仅当程序行含 assertions 数据时显示；A1 等总括程序表无此列） -->
      <el-table-column v-if="hasAssertions" label="存在" width="50" align="center" :resizable="false">
        <template #header>
          <el-tooltip content="存在或发生" placement="top"><span>存在</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.assertions?.existence" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column v-if="hasAssertions" label="完整" width="50" align="center" :resizable="false">
        <template #header>
          <el-tooltip content="完整性" placement="top"><span>完整</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.assertions?.completeness" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column v-if="hasAssertions" label="权利" width="50" align="center" :resizable="false">
        <template #header>
          <el-tooltip content="权利和义务" placement="top"><span>权利</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.assertions?.rights" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column v-if="hasAssertions" label="准确" width="50" align="center" :resizable="false">
        <template #header>
          <el-tooltip content="准确性、计价和分摊" placement="top"><span>准确</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.assertions?.accuracy" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>
      <el-table-column v-if="hasAssertions" label="列报" width="50" align="center" :resizable="false">
        <template #header>
          <el-tooltip content="列报和披露" placement="top"><span>列报</span></el-tooltip>
        </template>
        <template #default="{ row }">
          <span v-if="row.assertions?.presentation" class="gt-a-program-console__check">√</span>
        </template>
      </el-table-column>

      <!-- 关联底稿（I 列 GtIndexChip）— 展示型子组件 GtAProgramLinkedChips -->
      <el-table-column label="关联底稿" min-width="140">
        <template #default="{ row }">
          <GtAProgramLinkedChips
            :row="row"
            :inline-popup-wp-codes="INLINE_POPUP_WP_CODES"
            :popup-completion-status="popupCompletionStatus"
            :a16-recommended-code="a16RecommendedCode"
            :a16-other-versions="a16OtherVersions"
            v-model:a16-expanded="a16OtherExpanded"
            v-model:a17-expanded="a17OtherExpanded"
            :is-a16-seq2-row="isA16Seq2Row"
            :is-row-chip-disabled="isRowChipDisabled"
            :is-a17-seq5-row="isA17Seq5Row"
            :a17-applicable-refs="a17ApplicableRefs"
            :a17-inapplicable-refs="a17InapplicableRefs"
            :parse-linked-workpapers="parseLinkedWorkpapers"
            :review-chip-display-value="reviewChipDisplayValue"
            :is-a17_5-chip-disabled="isA17_5ChipDisabled"
            :is-review-chip-disabled="isReviewChipDisabled"
            :a17_5-badge="a17_5Badge"
            :review-chip-badge="reviewChipBadge"
            :chip-completion-key="chipCompletionKey"
            @chip-click="handleIndexChipClick"
          />
        </template>
      </el-table-column>

      <!-- 执行说明（可编辑，失焦保存到 FieldOverrideService） -->
      <el-table-column label="执行说明" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            v-model="row.execution_summary"
            size="small"
            placeholder="填写执行情况"
            @blur="saveExecutionSummary(row)"
          />
          <span v-else>{{ row.execution_summary || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 状态 -->
      <el-table-column label="状态" width="120" align="center">
        <template #default="{ row }">
          <el-dropdown
            v-if="!readonly"
            trigger="click"
            @command="(cmd: string) => handleStatusChange(row, cmd)"
          >
            <el-tag
              :type="statusTagType(row.status)"
              size="small"
              class="gt-a-program-console__status-tag"
            >
              {{ statusLabel(row.status) }}
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-tag>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="in_progress">执行中</el-dropdown-item>
                <el-dropdown-item command="completed">已完成</el-dropdown-item>
                <el-dropdown-item command="not_applicable" divided>裁剪</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tag v-else :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 证据附件 -->
      <el-table-column label="证据" width="70" align="center">
        <template #default="{ row }">
          <el-badge :value="row.attachment_count" :hidden="!row.attachment_count" :max="9">
            <el-button text size="small" @click="openAttachment(row)">📎</el-button>
          </el-badge>
        </template>
      </el-table-column>

      <!-- 裁剪理由（仅裁剪状态显示） -->
      <el-table-column label="裁剪理由" min-width="120">
        <template #default="{ row }">
          <span v-if="row.status === 'not_applicable'" class="gt-a-program-console__trim-reason">
            {{ row.trim_reason || '—' }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 裁剪理由弹窗（单条） ─── -->
    <el-dialog
      v-model="trimDialogVisible"
      title="裁剪理由"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form ref="trimFormRef" :model="trimForm" :rules="trimRules" label-width="80px">
        <el-form-item label="程序">
          <span>{{ trimForm.programDesc }}</span>
        </el-form-item>
        <el-form-item label="理由" prop="reason" required>
          <el-input
            v-model="trimForm.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入裁剪理由（必填）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="trimDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!trimForm.reason.trim()"
          @click="confirmTrim"
        >
          确认裁剪
        </el-button>
      </template>
    </el-dialog>

    <!-- ─── 批量裁剪弹窗 ─── -->
    <el-dialog
      v-model="batchTrimDialogVisible"
      title="批量裁剪"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form ref="batchTrimFormRef" :model="batchTrimForm" :rules="batchTrimRules" label-width="80px">
        <el-form-item label="选中程序">
          <span>共 {{ selectedIds.length }} 条程序</span>
        </el-form-item>
        <el-form-item label="理由" prop="reason" required>
          <el-input
            v-model="batchTrimForm.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入批量裁剪理由（必填，将应用到所有选中程序）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchTrimDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!batchTrimForm.reason.trim()"
          @click="confirmBatchTrim"
        >
          确认批量裁剪 ({{ selectedIds.length }})
        </el-button>
      </template>
    </el-dialog>

    <!-- ─── 新增程序弹窗 ─── -->
    <el-dialog
      v-model="addDialogVisible"
      title="新增审计程序"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form ref="addFormRef" :model="addForm" :rules="addRules" label-width="90px">
        <el-form-item label="程序描述" prop="desc" required>
          <el-input
            v-model="addForm.desc"
            type="textarea"
            :rows="4"
            placeholder="请输入审计程序描述（必填）"
            maxlength="1000"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="addForm.category" placeholder="选择类别" style="width: 100%">
            <el-option label="常规★" value="常规★" />
            <el-option label="备选" value="备选" />
            <el-option label="IPO/上市公司/新三板/舞弊应对" value="IPO/上市公司/新三板/舞弊应对" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联底稿">
          <el-input
            v-model="addForm.linkedWorkpapers"
            placeholder="可选，多个底稿索引用 / 分隔，如 D1-1/D1-2"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!addForm.desc.trim()"
          @click="confirmAdd"
        >
          确认新增
        </el-button>
      </template>
    </el-dialog>

    <!-- Sprint 4 Task 14.1: 首次使用引导 el-tour -->
    <el-tour v-model="showGuide">
      <el-tour-step
        v-for="(step, idx) in guideSteps"
        :key="idx"
        :target="step.target"
        :title="step.title"
        :description="step.description"
      />
    </el-tour>

    <!-- 子底稿弹窗（A1-11/A1-12/A1-17/A1-18） -->
    <WpInlinePopup
      v-model:visible="showPopup"
      :wp-code="popupWpCode"
      :wp-id="wpId"
      :project-id="projectId"
      :project-info="projectInfo"
      @save="onPopupSave"
    />
    </template><!-- end: inner v-else (program table) -->
    </template><!-- end: outer v-else (not isNotApplicable) -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import GtAProgramLinkedChips from '@/components/workpaper/GtAProgramLinkedChips.vue'
import GtAuditFlowGraph from '@/components/workpaper/GtAuditFlowGraph.vue'
import GtGridSheet from '@/components/workpaper/GtGridSheet.vue'
import WpInlinePopup from '@/components/workpaper/WpInlinePopup.vue'
import { api } from '@/services/apiProxy'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'
import { useWpOnboardingGuide } from '@/composables/useWpOnboardingGuide'
import { useAProgramReview } from '@/composables/useAProgramReview'
import { useAProgramData } from '@/composables/useAProgramData'
import { useAProgramPopups } from '@/composables/useAProgramPopups'
import { INLINE_POPUP_WP_CODES } from '@/components/workpaper/wpPopupDocxConfigs'
import { isReviewRoleRef } from '@/components/workpaper/reviewWpResolve'

// ─── Types ───
interface ProgramAssertions {
  existence?: boolean
  completeness?: boolean
  rights?: boolean
  accuracy?: boolean
  presentation?: boolean
}

interface ProgramHistoryItem {
  timestamp: string
  user: string
  action: string
  reason?: string
}

interface ProgramRow {
  id: string
  program_no: number
  program_desc: string
  program_category: string
  assertions?: ProgramAssertions
  linked_workpapers?: string
  execution_summary?: string
  status: string
  trim_reason?: string
  history?: ProgramHistoryItem[]
  attachment_count?: number
  phase?: string
  sub_steps?: { no: number; text: string }[]
}

interface TrimDecision {
  programId: string
  reason: string
  timestamp?: string
  user?: string
}

interface AProgramSchema {
  fixed_cells?: Record<string, string>
  programs?: Array<Record<string, any>>
  assertions?: string[]
  [key: string]: any
}

interface AProgramHtmlData {
  programs: ProgramRow[]
  trim_decisions: TrimDecision[]
  signatures?: Array<{ role: string; name: string; date: string }>
}

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: AProgramSchema
  htmlData: AProgramHtmlData
  readonly?: boolean
  hideCategories?: boolean
}>(), {
  readonly: false,
  hideCategories: false,
})

const emit = defineEmits<{
  'program-trim': [payload: { programId: string; reason: string }]
  'program-status-change': [payload: { programId: string; status: string }]
  'jump-to-workpaper': [wpCode: string]
  'save': [data: AProgramHtmlData]
  'open-attachment': [payload: { wpId: string; sheetName: string; rowRef: string }]
  'program-add': [payload: { programId: string; description: string }]
}>()

// ─── State ───
const route = useRoute()
const activeCategory = ref('')
const selectedIds = ref<string[]>([])
const expandedRowKeys = ref<string[]>([])
const tableRef = ref<any>(null)

// Sprint 4 Task 17.7: 审计逻辑图展开状态
const flowGraphExpanded = ref(false)
const projectId = computed(() => (route.params.projectId as string) || '')

// ─── 项目信息 + 适用性（composable: useAProgramData）───
const {
  projectInfo,
  applicableWhen,
  isNotApplicable,
  loadProjectInfo,
} = useAProgramData(projectId)

// ─── 程序行加载 + 弹窗完成状态 + A16 推荐版本 + 导出（composable: useAProgramPopups）───
const {
  programs,
  popupCompletionStatus,
  a16RecommendedCode,
  a16OtherExpanded,
  a16OtherVersions,
  isA16Seq2Row,
  initData,
  loadPopupCompletionStatus,
  fetchA16RecommendedVersion,
  exportProgramTable,
} = useAProgramPopups({
  wpId: () => props.wpId,
  sheetName: () => props.sheetName,
  projectId,
  htmlData: () => props.htmlData,
  applicableWhen,
  parseLinkedWorkpapers,
  statusLabel,
  getYear: () => parseInt(route.query.year as string) || new Date().getFullYear(),
})

// 子底稿弹窗状态
const showPopup = ref(false)
const popupWpCode = ref('')

// ─── 复核子码解析 + A17 版本适用性（composable: useAProgramReview）───
const {
  reviewTemplates,
  a17_5Versions,
  a17OtherExpanded,
  isA1Table,
  isA17Table,
  resolveReviewWpCode,
  reviewChipDisplayValue,
  isReviewChipDisabled,
  reviewChipBadge,
  chipCompletionKey,
  isA17_5Ref,
  isA17_5ChipDisabled,
  a17_5Badge,
  isA17Seq5Row,
  a17ApplicableRefs,
  a17InapplicableRefs,
  fetchReviewTemplates,
  fetchA17ApplicableVersions,
} = useAProgramReview({
  sheetName: () => props.sheetName,
  projectId,
  parseLinkedWorkpapers,
})

function isRowChipDisabled(row: ProgramRow): boolean {
  return row.status === 'not_applicable'
}

onMounted(() => {
  loadPopupCompletionStatus()
  fetchA16RecommendedVersion()
  fetchA17ApplicableVersions()
  fetchReviewTemplates()
  loadProjectInfo()
})

// Sprint 4 Task 14.1: 首次使用引导
const { showGuide, guideSteps, triggerGuide } = useWpOnboardingGuide('a-program-console')

// Trim dialog (single)
const trimDialogVisible = ref(false)
const trimForm = ref({
  programId: '',
  programDesc: '',
  reason: '',
})
const trimFormRef = ref<any>(null)
const trimRules = {
  reason: [{ required: true, message: '请输入裁剪理由', trigger: 'blur' }],
}

// Batch trim dialog
const batchTrimDialogVisible = ref(false)
const batchTrimForm = ref({
  reason: '',
})
const batchTrimFormRef = ref<any>(null)
const batchTrimRules = {
  reason: [{ required: true, message: '请输入批量裁剪理由', trigger: 'blur' }],
}

// Add program dialog
const addDialogVisible = ref(false)
const addForm = ref({
  desc: '',
  category: '常规★',
  linkedWorkpapers: '',
})
const addFormRef = ref<any>(null)
const addRules = {
  desc: [{ required: true, message: '请输入审计程序描述', trigger: 'blur' }],
}

// Auto-save debounce
let saveTimer: ReturnType<typeof setTimeout> | null = null

initData()

watch(() => props.htmlData, () => {
  initData()
}, { deep: true })

// ─── Self-load: 当 htmlData.programs 为空时从 render-config 加载 ───
async function selfLoad() {
  if (props.htmlData?.programs?.length) return
  try {
    const res = await api.get<any>(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=a-program-console`,
      { _silent: true } as any,
    )
    const data = res?.sheets?.[0]?.html_data
    if (data?.programs?.length) {
      programs.value = data.programs.map((p: any, i: number) => ({
        id: p.id || `row-${i + 1}`,
        program_no: p.program_no ?? i + 1,
        program_desc: p.program_desc || '',
        program_category: p.program_category || '',
        linked_workpapers: p.linked_workpapers || '',
        execution_summary: p.execution_summary || '',
        status: p.status || 'pending',
        trim_reason: p.trim_reason || '',
        summary: p.summary || '',
        sub_steps: p.sub_steps || [],
        assertions: p.assertions || {},
        phase: p.phase || '',
      }))
    }
  } catch { /* silent — 降级显示空态 */ }
}

onMounted(() => {
  selfLoad()
})

// ─── Computed ───
const availableCategories = computed(() => {
  const cats = new Set<string>()
  programs.value.forEach(p => {
    if (p.program_category) cats.add(p.program_category)
  })
  return Array.from(cats)
})

const filteredPrograms = computed(() => {
  if (!activeCategory.value) return programs.value
  return programs.value.filter(p => p.program_category === activeCategory.value)
})

const completedCount = computed(() =>
  programs.value.filter(p => p.status === 'completed').length
)

const trimmedCount = computed(() =>
  programs.value.filter(p => p.status === 'not_applicable').length
)

const inProgressCount = computed(() =>
  programs.value.filter(p => p.status === 'in_progress').length
)

const pendingCount = computed(() =>
  programs.value.filter(p => !p.status || p.status === 'pending').length
)

const progressPercentage = computed(() => {
  const total = programs.value.length
  if (total === 0) return 0
  const done = completedCount.value + trimmedCount.value
  return Math.round((done / total) * 100)
})

/** 当任意程序行有非空 assertions 时显示认定列，否则隐藏（A1 等总括程序表无认定列） */
const hasAssertions = computed(() =>
  programs.value.some(p => p.assertions && Object.values(p.assertions).some(Boolean))
)

/** 阶段分组标签映射 */
const PHASE_LABELS: Record<string, string> = {
  planning: '📋 计划阶段',
  execution: '⚙️ 执行阶段',
  completion: '📝 完成总结',
  signoff: '✍️ 复核签发',
}

/** 是否有 phase 数据（有则按分组渲染） */
const hasPhaseGroups = computed(() =>
  programs.value.some((p: any) => p.phase)
)

/** 按 phase 分组的程序行 */
const phaseGroups = computed(() => {
  if (!hasPhaseGroups.value) return []
  const order = ['planning', 'execution', 'completion', 'signoff']
  const grouped = new Map<string, ProgramRow[]>()
  for (const phase of order) {
    grouped.set(phase, [])
  }
  for (const p of programs.value) {
    const phase = (p as any).phase || 'completion'
    const list = grouped.get(phase)
    if (list) list.push(p)
    else grouped.set(phase, [p])
  }
  return order
    .filter(phase => (grouped.get(phase)?.length ?? 0) > 0)
    .map(phase => {
      const items = grouped.get(phase)!
      const done = items.filter(i => i.status === 'completed' || i.status === 'not_applicable').length
      return {
        phase,
        label: PHASE_LABELS[phase] || phase,
        items,
        progress: items.length > 0 ? Math.round((done / items.length) * 100) : 0,
      }
    })
})

/** 当任意程序行有历史决策记录或子步骤时显示展开列（sub_steps 为二级明细） */
const hasExpandContent = computed(() =>
  programs.value.some(p => (p.history && p.history.length > 0) || (p.sub_steps && p.sub_steps.length > 0))
)

/** 程序行为空时的网格兜底数据（替代程序检查表等非标准程序行结构，后端 grid_fallback 字段） */
const gridFallback = computed(() => {
  if (programs.value.length > 0) return null
  return props.htmlData?.grid_fallback ?? null
})

/** 当任意程序行有非空类别时显示类别列 */
const hasCategory = computed(() =>
  programs.value.some(p => p.program_category && p.program_category.trim() !== '')
)

// ─── Methods ───
function progressFormat(percentage: number): string {
  const total = programs.value.length
  const done = completedCount.value + trimmedCount.value
  return `${done}/${total} (${percentage}%)`
}

function categoryTagType(category: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  switch (category) {
    case '常规★': return 'primary'
    case 'IPO 加项': return 'warning'
    case '备选程序': return 'info'
    case '舞弊应对': return 'danger'
    default: return 'info'
  }
}

function statusTagType(status: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'not_applicable': return 'info'
    default: return 'primary'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '执行中'
    case 'not_applicable': return '已裁剪'
    default: return '待执行'
  }
}

function historyItemType(action: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (action.includes('完成')) return 'success'
  if (action.includes('裁剪')) return 'info'
  if (action.includes('执行')) return 'warning'
  return 'primary'
}

function isRowSelectable(row: ProgramRow): boolean {
  // Only allow selecting rows that are not already trimmed
  return row.status !== 'not_applicable' && row.status !== 'completed'
}

function parseLinkedWorkpapers(value: string): string[] {
  if (!value) return []
  // Split by common separators: / , ; or newline
  return value.split(/[/,;\n]/).map(s => s.trim()).filter(Boolean)
}

function handleExpandChange(row: ProgramRow, expandedRows: ProgramRow[]) {
  expandedRowKeys.value = expandedRows.map(r => r.id)
}

// Sprint 4 Task 17.7: 滚动到指定程序行
function scrollToProgramRow(programNo: number) {
  const row = programs.value.find(p => p.program_no === programNo)
  if (row && tableRef.value) {
    tableRef.value.setCurrentRow(row)
    // 尝试滚动到该行
    const el = tableRef.value.$el?.querySelector(`[data-row-key="${row.id}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }
}

function handleSelectionChange(selection: ProgramRow[]) {
  selectedIds.value = selection.map(r => r.id)
}

/** 执行说明失焦保存到 FieldOverrideService */
async function saveExecutionSummary(row: ProgramRow) {
  if (props.readonly) return
  persistProgramField(row.program_no, 'execution_summary', row.execution_summary || '')
}

/** 通用：持久化程序行字段到 FieldOverrideService */
async function persistProgramField(programNo: number, field: string, value: any) {
  const year = parseInt(route.query.year as string) || new Date().getFullYear()
  try {
    await api.post('/api/workpapers/field-overrides', {
      project_id: projectId.value,
      year,
      scope: `procedure_table:${props.sheetName || 'A1'}`,
      item_key: String(programNo),
      field,
      value,
    })
  } catch {
    // 静默
  }
}

function handleStatusChange(row: ProgramRow, newStatus: string) {
  if (newStatus === 'not_applicable') {
    // Open trim reason dialog
    trimForm.value = {
      programId: row.id,
      programDesc: row.program_desc?.slice(0, 80) + (row.program_desc?.length > 80 ? '...' : ''),
      reason: '',
    }
    trimDialogVisible.value = true
    return
  }

  // Direct status change (no reason required for non-trim)
  const idx = programs.value.findIndex(p => p.id === row.id)
  if (idx >= 0) {
    programs.value[idx].status = newStatus
    emit('program-status-change', { programId: row.id, status: newStatus })
    // 持久化到 FieldOverrideService（跨模块可读，如 A1 进度联动）
    persistProgramField(row.program_no, 'status', newStatus)
    debounceSave()
  }
}

function confirmTrim() {
  const { programId, reason } = trimForm.value
  if (!reason.trim()) return

  const idx = programs.value.findIndex(p => p.id === programId)
  if (idx >= 0) {
    programs.value[idx].status = 'not_applicable'
    programs.value[idx].trim_reason = reason.trim()
  }

  emit('program-trim', { programId, reason: reason.trim() })
  trimDialogVisible.value = false
  debounceSave()
}

function openBatchTrimDialog() {
  batchTrimForm.value.reason = ''
  batchTrimDialogVisible.value = true
}

function openAddDialog() {
  addForm.value = { desc: '', category: '常规★', linkedWorkpapers: '' }
  addDialogVisible.value = true
}

function confirmAdd() {
  const desc = addForm.value.desc.trim()
  if (!desc) return

  // 生成新程序行：序号取当前最大值 +1，id 用自定义前缀避免与模板行冲突
  const maxNo = programs.value.reduce((m, p) => Math.max(m, p.program_no || 0), 0)
  const newId = `custom-${Date.now()}`
  const newRow: ProgramRow = {
    id: newId,
    program_no: maxNo + 1,
    program_desc: desc,
    program_category: addForm.value.category || '常规★',
    assertions: {},
    linked_workpapers: addForm.value.linkedWorkpapers.trim(),
    status: 'pending',
  }
  programs.value.push(newRow)

  emit('program-add', { programId: newId, description: desc })
  addDialogVisible.value = false
  debounceSave()
}

function confirmBatchTrim() {
  const reason = batchTrimForm.value.reason.trim()
  if (!reason) return

  selectedIds.value.forEach(id => {
    const idx = programs.value.findIndex(p => p.id === id)
    if (idx >= 0) {
      programs.value[idx].status = 'not_applicable'
      programs.value[idx].trim_reason = reason
    }
    emit('program-trim', { programId: id, reason })
  })

  selectedIds.value = []
  batchTrimDialogVisible.value = false
  debounceSave()
}

function handleIndexChipClick(resolved: ResolvedIndexRef) {
  if (resolved.ns === 'wp' && resolved.target) {
    let target = resolved.target
    if (isA17_5Ref(target) && isA17_5ChipDisabled(target)) return
    if (isReviewRoleRef(target)) {
      if (isReviewChipDisabled(target)) return
      target = resolveReviewWpCode(target)
    }
    // 弹窗式子底稿：拦截跳转，改为弹窗展示
    if (INLINE_POPUP_WP_CODES.has(target)) {
      popupWpCode.value = target
      showPopup.value = true
      return
    }
    emit('jump-to-workpaper', target)
  }
}

/** 弹窗保存/关闭后刷新数据 */
function onPopupSave() {
  debounceSave()
  loadPopupCompletionStatus()
}

function openAttachment(row: ProgramRow) {
  emit('open-attachment', {
    wpId: props.wpId,
    sheetName: props.sheetName,
    rowRef: `${props.sheetName}:${row.program_no}`,
  })
}

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    const data: AProgramHtmlData = {
      programs: programs.value,
      trim_decisions: programs.value
        .filter(p => p.status === 'not_applicable' && p.trim_reason)
        .map(p => ({
          programId: p.id,
          reason: p.trim_reason!,
        })),
      signatures: props.htmlData?.signatures,
    }
    emit('save', data)
  }, 1500)
}
</script>

<style scoped>
.gt-a-program-console {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a-program-console__header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-a-program-console__progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-a-program-console__progress-detail {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.gt-a-program-console__phase-progress {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.gt-a-program-console__phase-progress .phase-chip {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #666);
}

.gt-a-program-console__phase-progress .phase-label {
  white-space: nowrap;
}

.gt-a-program-console__phase-progress .phase-pct {
  margin-left: 4px;
  font-weight: 600;
  font-size: 11px;
  color: var(--gt-purple, #4b2d77);
}

.gt-a-program-console__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-a-program-console__filters {
  flex: 1;
}

.gt-a-program-console__table {
  width: 100%;
}

/* 程序表专属行高——非密集数据表，需要舒适阅读体验 */
.gt-a-program-console__table :deep(th.el-table__cell) {
  background: #f3eef8;
  color: #4b2d77;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 0 !important;
  height: 38px !important;
}

.gt-a-program-console__table :deep(td.el-table__cell) {
  padding: 6px 0 !important;
  height: 36px !important;
}

.gt-a-program-console__table :deep(.cell) {
  padding: 4px 10px !important;
  line-height: 1.5 !important;
  font-size: 13px;
}

/* 序号列居中 */
.gt-a-program-console__table :deep(.el-table__body td:nth-child(1) .cell),
.gt-a-program-console__table :deep(.el-table__body td:nth-child(2) .cell) {
  text-align: center;
}

/* 状态列下拉样式优化 */
.gt-a-program-console__table :deep(.el-dropdown) {
  width: 100%;
}

/* 斑马纹（偶数行微灰底） */
.gt-a-program-console__table :deep(.el-table__row:nth-child(even) td) {
  background: #fafafa;
}

/* hover 行高亮 */
.gt-a-program-console__table :deep(.el-table__body tr:hover > td) {
  background-color: #f5f0fa !important;
}

.gt-a-program-console__check {
  color: var(--el-color-success);
  font-weight: bold;
  font-size: 16px;
}

.gt-a-program-console__status-tag {
  cursor: pointer;
}

.gt-a-program-console__trim-reason {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.gt-a-program-console__expand-content {
  padding: 12px 24px;
}

.gt-a-program-console__sub-steps {
  margin-bottom: 12px;
}

.gt-a-program-console__sub-steps h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.gt-a-program-console__sub-list {
  margin: 0;
  padding-left: 20px;
  list-style: decimal;
}

.gt-a-program-console__sub-item {
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
  padding: 2px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}

.gt-a-program-console__sub-item:last-child {
  border-bottom: none;
}

.gt-a-program-console__expand-content h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.gt-a-program-console__expand-content p {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.gt-a-program-console__expand-history {
  margin-top: 12px;
}

.gt-a-program-console__history-reason {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
