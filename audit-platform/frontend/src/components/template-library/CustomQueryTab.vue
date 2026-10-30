<!--
  CustomQueryTab.vue — 自定义查询 Tab [template-library-coordination Sprint 6 Tasks 6.4-6.6]

  需求 22.1-22.9：
  - 可视化查询构建器：数据源选择 + 多条件筛选 + 字段选择
  - 8+ 数据源（底稿/试算表/调整分录/科目余额/序时账/附注/报表行次/工时）
  - 条件类型：等于/包含/大于/小于/范围/为空/不为空
  - 多条件 AND/OR 组合
  - 结果 el-table 展示 + 导出（全部：服务端；当前页：前端 xlsx）
  - 模板保存/加载（仅我可见 / 指定项目共享 / 公开）

  advanced-query-linkage-closure 任务 29（design §4.2）：条件以结构化 conditions + condition_logic 发送（原先拼成
  `{字段}_min` 之类的筛选键，后端不认）；年度只取项目审计年度、取不到留空要求选择（删去「今年 − 1」）；指标树带项目与
  年度加载「骨架 + 附注分支」并拍平；结果操作列「打开」「复制引用」、翻页、导出全部；保存模板三档（AQ-39）。

  依赖：
  - GET /api/custom-query/indicators       数据源指标库（depth=1 骨架 + branch=disclosure）
  - POST /api/custom-query/execute         执行查询
  - POST /api/custom-query/export          导出全部
  - GET /api/custom-query/templates        列出模板
  - POST /api/custom-query/templates       保存模板（QueryTemplateSaveDialog）
  - DELETE /api/custom-query/templates/:id 删除模板（进回收站）
-->
<template>
  <div class="gt-cqt">
    <!-- Capability_Guidance：两套入口能力差异说明（R11.5）；构建器准入的说法与 access 接口同口径（B9 浏览器复测交接） -->
    <el-alert
      class="gt-cqt-guidance"
      type="info"
      :closable="false"
      show-icon
    >
      <template #title>
        <span class="gt-cqt-guidance-title">查询入口能力说明</span>
      </template>
      <div class="gt-cqt-guidance-body">
        <p>
          <el-tag size="small" type="success" effect="plain" round>业务视图查询</el-tag>
          面向<strong>所有已认证角色</strong>：按单元格级跨模块寻址检索、保存模板、导出 Excel、结果下钻到来源底稿格。
        </p>
        <p>
          <el-tag size="small" type="warning" effect="plain" round>高级构建器</el-tag>
          仅限 <strong>管理员、合伙人、经理（含任一项目的项目经理）</strong>：提供白名单数据表的可视化条件、SQL 预览、聚合与关联查询。
        </p>
      </div>
    </el-alert>

    <!-- 顶部：项目年度选择 + 模板管理 -->
    <div class="gt-cqt-top">
      <el-form :model="formCtx" inline size="small" class="gt-cqt-ctx-form">
        <el-form-item label="项目">
          <el-select
            v-model="formCtx.project_id"
            filterable
            placeholder="选择项目"
            aria-label="项目"
            style="width: 240px"
            @change="onProjectChange"
          >
            <el-option
              v-for="p in projectList"
              :key="p.id"
              :label="`${p.code || ''} ${p.name || p.id}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="年度">
          <el-input-number
            v-model="formCtx.year"
            :min="2000"
            :max="2100"
            :step="1"
            :value-on-clear="null"
            placeholder="审计年度"
            aria-label="审计年度"
            controls-position="right"
            style="width: 120px"
          />
          <span v-if="formCtx.year == null" class="gt-cqt-year-hint" data-testid="cqt-year-hint">请选择审计年度</span>
        </el-form-item>
        <el-form-item label="数据源">
          <el-select
            v-model="formCtx.source"
            filterable
            placeholder="选择数据源"
            aria-label="数据源"
            style="width: 260px"
            @change="onSourceChange"
          >
            <el-option-group
              v-for="grp in indicatorTree"
              :key="grp.key"
              :label="grp.label"
            >
              <el-option
                v-for="child in grp.children"
                :key="child.key"
                :label="child.label"
                :value="child.key"
              />
            </el-option-group>
          </el-select>
        </el-form-item>
      </el-form>

      <div class="gt-cqt-top-actions">
        <el-button size="small" aria-label="我的模板" data-testid="cqt-templates" @click="templatesDialogVisible = true">
          <el-icon style="margin-right: 4px"><Folder /></el-icon>
          我的模板
        </el-button>
        <el-button size="small" type="primary" plain @click="onSaveTemplate">
          <el-icon style="margin-right: 4px"><DocumentAdd /></el-icon>
          保存为模板
        </el-button>
        <!-- 高级构建器入口：access 接口判不可用时禁用（可见不可点）+ 原因提示（R11.6） -->
        <el-tooltip
          :disabled="canUseBuilder"
          :content="builderDisabledReason"
          placement="top"
        >
          <!-- 包一层 span：禁用的 el-button 不触发 hover 事件，tooltip 需挂在可交互容器上 -->
          <span class="gt-cqt-builder-entry">
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="!canUseBuilder"
              @click="onOpenBuilder"
            >
              <el-icon style="margin-right: 4px"><MagicStick /></el-icon>
              高级构建器
            </el-button>
          </span>
        </el-tooltip>
      </div>
    </div>

    <!-- 主体：左侧条件筛选 + 字段选择，右侧结果 -->
    <el-row :gutter="12" class="gt-cqt-main">
      <!-- 左侧：查询构建器 -->
      <el-col :span="8" class="gt-cqt-left">
        <div class="gt-cqt-panel">
          <QueryConditionEditor
            v-model="conditionState"
            :fields="availableColumns"
            :source="formCtx.source"
            :disabled="!supportsConditions"
            :disabled-reason="conditionsDisabledReason"
          />
        </div>

        <div class="gt-cqt-panel" style="margin-top: 12px">
          <div class="gt-cqt-panel-header">
            <span>字段选择 ({{ selectedColumns.length }} / {{ availableColumns.length }})</span>
            <el-button size="small" link @click="toggleAllColumns">
              {{ selectedColumns.length === availableColumns.length ? '取消全选' : '全选' }}
            </el-button>
          </div>
          <el-checkbox-group v-model="selectedColumns" class="gt-cqt-fields" aria-label="返回字段">
            <el-checkbox
              v-for="col in availableColumns"
              :key="col"
              :label="columnLabel(col)"
              :value="col"
              size="small"
            >
              {{ columnLabel(col) }}
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <!-- ACNR 选字段树（复用 useAcnr，与公式选址同一棵树；面板与 acnr_targets 归 acnr D1，用户裁决 Q0，本 spec 不改） -->
        <div class="gt-cqt-panel" style="margin-top: 12px">
          <CustomQueryFieldPicker v-model="acnrFieldIds" />
          <div v-if="!formCtx.project_id" class="gt-cqt-empty-tip" data-testid="acnr-no-project">{{ BUSINESS_NO_PROJECT_HINT }}</div>
        </div>

        <div class="gt-cqt-panel-actions">
          <el-tooltip :disabled="!executeBlockedReason" :content="executeBlockedReason" placement="top">
            <span class="gt-cqt-run-wrap">
              <el-button
                type="primary"
                :loading="executing"
                :disabled="!!executeBlockedReason"
                aria-label="执行查询"
                data-testid="cqt-run"
                style="width: 100%"
                @click="onExecute()"
              >
                <el-icon style="margin-right: 4px"><Search /></el-icon>
                执行查询
              </el-button>
            </span>
          </el-tooltip>
          <div v-if="executeBlockedReason" class="gt-cqt-empty-tip" data-testid="cqt-run-reason">{{ executeBlockedReason }}</div>
        </div>
      </el-col>

      <!-- 右侧：结果展示 -->
      <el-col :span="16" class="gt-cqt-right">
        <div class="gt-cqt-result-header">
          <span class="gt-cqt-result-title">
            查询结果
            <el-tag
              v-if="result.rows.length > 0"
              size="small"
              type="success"
              effect="plain"
              round
              style="margin-left: 8px"
            >
              本页 {{ result.rows.length }} 条 / 共 {{ result.total ?? result.rows.length }} 条
            </el-tag>
          </span>
          <div class="gt-cqt-result-actions">
            <!-- 导出：全部（服务端按当前查询导出全量，R8.1）/ 当前页（前端，次选项 R8.3） -->
            <el-dropdown size="small" trigger="click" :disabled="!canExport" @command="onExportCommand">
              <el-button size="small" :disabled="!canExport" :loading="exporting" aria-label="导出查询结果" data-testid="cqt-export">
                <el-icon style="margin-right: 4px"><Download /></el-icon>
                导出 ▾
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="all" data-testid="cqt-export-all">导出全部（共 {{ result.total }} 条）</el-dropdown-item>
                  <el-dropdown-item command="page" data-testid="cqt-export-page">导出当前页</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <div class="gt-cqt-result-body">
          <AcnrTargetResults :block="result.acnr_results" :project-id="formCtx.project_id" />
          <el-empty
            v-if="!executing && result.rows.length === 0 && !queryError"
            :description="emptyHint || '点击 [执行查询] 开始检索'"
          >
            <template v-if="emptyHint" #default>
              <div class="gt-cqt-empty-hint">
                {{ emptyHint }}
                <div class="gt-cqt-empty-tip">
                  四表数据按年度存放。若确认条件无误，请检查左上「年度」是否为该项目的审计年度。
                </div>
              </div>
            </template>
          </el-empty>
          <!-- 查询失败：持久显示中文原因与追踪号（R11.1；不再显示 axios 英文或落到空态） -->
          <QueryErrorAlert v-if="queryError" :error="queryError" />
          <!-- 点表头排序：在数据库内对全量排序（空值在后）并回到第 1 页（R2.2），不是只排本页 -->
          <el-table
            v-if="result.rows.length > 0"
            ref="resultTableRef"
            v-loading="executing"
            :data="result.rows"
            size="small"
            border
            stripe
            max-height="600"
            :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
            :default-sort="tableDefaultSort"
            class="gt-cqt-table"
            @sort-change="onSortChange"
          >
            <!-- 操作列：打开权威页面 / 复制经地址库校验的引用（R7.1~R7.3）；结果区没有回写入口（R7.5） -->
            <el-table-column label="操作" width="130" fixed="left">
              <template #default="{ row }">
                <QueryRowActions :drill="rowLinks.drillOf(row)" :ref-text="rowLinks.refOf(row)"
                  :ref-usable="rowLinks.refUsable(row)" :ref-hint="rowLinks.refHint(row)"
                  @open="rowLinks.openRow(row)" @copy-ref="rowLinks.copyRef(row)" />
              </template>
            </el-table-column>
            <el-table-column
              v-for="col in displayColumns"
              :key="col.key"
              :prop="col.key"
              :label="col.title"
              min-width="140"
              sortable="custom"
              :show-overflow-tooltip="!col.drillable"
            >
              <template #default="{ row }">
                <!-- 可下钻列：显示值 + GtIndexChip（value=addr_id，经 resolveIndex 拿 jump_route 下钻，R4.3） -->
                <span
                  v-if="col.drillable && cellAddrId(row, col)"
                  class="gt-cqt-drill-cell"
                >
                  <span :class="{ 'gt-amt': isAmount(row[col.key], col.key) }">
                    {{ formatCellValue(row[col.key], col.key) }}
                  </span>
                  <GtIndexChip
                    :value="addrIdToIndexRef(cellAddrId(row, col)) || ''"
                    :context-project-id="formCtx.project_id"
                    :validate="false"
                    prevent-navigate
                    context="下钻到数据来源底稿格"
                    class="gt-cqt-drill-chip"
                    @click="drill(cellAddrId(row, col))"
                  />
                </span>
                <!-- 无 addr_id → 不可下钻普通文本列（R4.5） -->
                <span v-else :class="{ 'gt-amt': isAmount(row[col.key], col.key) }">
                  {{ formatCellValue(row[col.key], col.key) }}
                </span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 真实分页（R2.6）：每页 100 / 200 / 500 行，total 由后端在分页前计算 -->
          <QueryResultPager
            v-if="showPagination"
            v-model:page="page"
            v-model:page-size="pageSize"
            :total="result.total"
            @change="onPagerChange"
          />
          <el-alert
            v-for="w in result.warnings || []"
            :key="w"
            :title="w"
            type="warning"
            :closable="false"
            show-icon
            class="gt-cqt-warning"
          />
        </div>
      </el-col>
    </el-row>

    <!-- 查询模板：与弹窗「📑 模板」同一个选择组件（R9.4）；「载入」还原数据源、条件、列、排序、每页行数 -->
    <MyTemplatesDialog v-model="templatesDialogVisible" @load="(_cfg, tpl) => onTemplateLoad(tpl)" />

    <!-- 保存模板：三档可见范围，可分享项目取 template-share-targets（AQ-39，与弹窗 💾 同一组件） -->
    <QueryTemplateSaveDialog
      v-model="saveDialogVisible"
      :data-source="formCtx.source"
      :config="templateConfig"
      :projects="projectList"
    />

    <!-- 高级构建器弹窗：access 接口判可用才可打开（R11.6）；把当前项目与年度传给内嵌构建器（R3.5） -->
    <el-dialog
      v-model="builderDialogVisible"
      title="高级查询构建器"
      width="90%"
      top="5vh"
      class="gt-cqt-builder-dialog"
      destroy-on-close
    >
      <AdvancedQueryBuilder embedded :project-id="formCtx.project_id || undefined" :year="formCtx.year ?? undefined" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Download, Folder, DocumentAdd, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { customQuery as P_cq, projects as P_proj } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { resolveColumnLabel } from '@/components/query/queryColumnLabels'
import { exportQueryResultToXlsx } from '@/components/query/queryExport'
import { reportTypeOfSource } from '@/components/query/querySourceUri'
import { useQueryBuilderAccess } from '@/composables/useQueryBuilderAccess'
import CustomQueryFieldPicker from '@/components/custom-query/CustomQueryFieldPicker.vue'
import AcnrTargetResults, { type AcnrResultsBlock } from '@/components/custom-query/AcnrTargetResults.vue'
import {
  BUSINESS_NO_PROJECT_HINT, buildBusinessPayload, isKnownYear, readBlobErrorBody, type BusinessQueryInput, type QuerySort,
} from '@/components/custom-query/queryPayloads'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useAcnrDrill, normalizeColumns, cellAddrId, addrIdToIndexRef, type QueryColumnMeta } from '@/composables/useAcnrDrill'
import QueryConditionEditor from '@/components/query/QueryConditionEditor.vue'
import QueryErrorAlert from '@/components/query/QueryErrorAlert.vue'
import QueryResultPager from '@/components/query/QueryResultPager.vue'
import QueryRowActions from '@/components/query/QueryRowActions.vue'
import QueryTemplateSaveDialog from '@/components/query/QueryTemplateSaveDialog.vue'
import { conditionsIncompleteReason, toRequestConditions, type ConditionState } from '@/components/query/queryConditions'
import MyTemplatesDialog from '@/components/query/MyTemplatesDialog.vue'
import { restoreTemplateQuery, type QueryTemplateItem } from '@/components/query/queryTemplateRestore'
import { describeQueryError, queryErrorToast, type QueryErrorText } from '@/components/query/queryErrorText'
import { columnTypesOf, formatQueryCell, isAmountCell } from '@/components/query/queryCellFormat'
import { flattenIndicatorGroups, loadIndicatorTree, type IndicatorOptionGroup } from '@/components/query/queryIndicatorLoader'
import { buildExportBody, exportAllQueryRows } from '@/components/query/queryServerExport'
import { useQueryRowLinks } from '@/components/query/useQueryRowLinks'

interface QueryResult {
  rows: any[]
  // 后端可能返回 ColumnMeta[]（含 addr_id/drillable）或 legacy string[]，统一由 normalizeColumns 归一
  columns: Array<string | Record<string, any>>
  /** 分页前的真实总行数（R2.1）；改造前它等于本页行数，无法据此翻页 */
  total: number
  limit?: number
  offset?: number
  /** 非致命提示（没有生效数据集、全局配置表未按项目过滤等） */
  warnings?: string[]
  /** 可选键：引用校验上下文 ref_context、列类型 column_types、附注表清单 tables */
  meta?: Record<string, any>
  /** 单元格取值结果（只在请求带 acnr_targets 时出现） */
  acnr_results?: AcnrResultsBlock
}
interface ProjectItem {
  id: string
  code?: string
  name?: string
  /**
   * 项目审计年度（`GET /api/projects` 由 `resolve_project_audit_year` 派生下发）：「年度」默认取它，
   * 取不到时留空并要求选择（不按日历年推算，R10.2）。
   */
  audit_year?: number | null
}
// ─── 状态 ───
/** 数据源下拉：指标树（骨架 + 附注分支）拍平成「顶层组 → 叶子」 */
const indicatorTree = ref<IndicatorOptionGroup[]>([])
const projectList = ref<ProjectItem[]>([])

const formCtx = ref({
  project_id: '',
  /** 审计年度：项目审计年度，取不到为 null（要求选择；原先退回「今年 − 1」） */
  year: null as number | null,
  source: '',
})
/** 结构化条件与组合逻辑（与模板 config.conditions 同形，R6.1） */
const conditionState = ref<ConditionState>({ conditions: [], logic: 'and' })
const selectedColumns = ref<string[]>([])
const availableColumns = ref<string[]>([])
/** 当前数据源能否带条件（附注表格、合并工作底稿、底稿选区不能，R6.2） */
const supportsConditions = ref(true)
// ACNR 选字段：选中 cell 节点的 addr_id 列表（R2.4，作查询字段标识）
const acnrFieldIds = ref<string[]>([])
const result = ref<QueryResult>({ rows: [], columns: [], total: 0 })
const queryError = ref<QueryErrorText | null>(null)
const executing = ref(false)
const exporting = ref(false)
/** 0 行时的空态说明（含实际使用的年度，便于自查年度是否选错） */
const emptyHint = ref('')
// 分页（R2.6）：total 是后端在分页前算的真实行数，可据此翻页
const page = ref(1)
const pageSize = ref(100)
const showPagination = computed(() => (result.value.total ?? 0) > 0 && !queryError.value)
/** 本次结果所属的查询（操作列的下钻 / 引用与导出全部都按它，不按界面当前选择） */
const lastRun = ref<{ source: string; projectId: string; year: number | null; payload: Record<string, unknown> | null }>(
  { source: '', projectId: '', year: null, payload: null })
// 排序（R2.2）：点表头在数据库内对全量排序、空值在后，回到第 1 页；换数据源即清除（新源未必有该列）
const sortState = ref<QuerySort | null>(null)
const resultTableRef = ref<{ clearSort?: () => void } | null>(null)
// 表格随结果重新挂载后照样显示当前排序箭头（default-sort 只在挂载时生效，不触发 sort-change）
const tableDefaultSort = computed(() => (sortState.value
  ? { prop: sortState.value.field, order: sortState.value.direction === 'desc' ? 'descending' : 'ascending' } as const
  : undefined))
function onSortChange({ prop, order }: { prop?: string | null; order?: string | null }) {
  sortState.value = prop && order ? { field: String(prop), direction: order === 'descending' ? 'desc' : 'asc' } : null
  void onExecute()
}

// ─── 高级构建器入口权限门禁（R11.1/R11.2，与后端 query_builder.py RBAC 一致） ───
// 判据只在后端 GET /api/query/access（builder_access.resolve_builder_access，与构建器各端点的门禁同一实现），
// 前端不持有角色清单（原先此处注释写「与后端 _QUERY_BUILDER_ROLES 同源」，任务 30 起已改为 access 接口）。
const { canUseBuilder, builderDisabledReason } = useQueryBuilderAccess()
const builderDialogVisible = ref(false)

function onOpenBuilder() {
  // 双保险：不可用时即便按钮被绕过也不打开构建器（R11.6）
  if (!canUseBuilder.value) return
  builderDialogVisible.value = true
}

// 模板
const templatesDialogVisible = ref(false)
const saveDialogVisible = ref(false)

// 结果列下钻（R4.2/R4.4/R4.6/R4.7）：以当前查询上下文 project_id 解析 jump_route
const { drill } = useAcnrDrill(() => formCtx.value.project_id)

/** 列名按数据源取中文（R6.6：合并试算的 summary 是「汇总数」，序时账 / 辅助明细的是「摘要」） */
function columnLabel(key: string, title?: string): string {
  return resolveColumnLabel(key, title, lastRun.value.source || formCtx.value.source || undefined)
}

// 当前已展示列（结果优先用 result.columns，回退到用户选择）——归一为 QueryColumnMeta
const displayColumns = computed<QueryColumnMeta[]>(() => {
  const cols = normalizeColumns(result.value.columns).map(c => ({ ...c, title: columnLabel(c.key, c.title) }))
  if (cols.length > 0) {
    return selectedColumns.value.length > 0
      ? cols.filter((c) => selectedColumns.value.includes(c.key))
      : cols
  }
  return selectedColumns.value.map((k) => ({
    key: k,
    title: columnLabel(k),
    addrId: null,
    drillable: false,
    dtype: 'text',
  }))
})

// 金额格式化按列类型（响应 meta.column_types / 列对象的 dtype；内存源按值），不再按字符串长度
const columnTypes = computed<Record<string, string>>(() => {
  const fromColumns = Object.fromEntries(normalizeColumns(result.value.columns)
    .filter((c) => c.dtype && c.dtype !== 'text').map((c) => [c.key, String(c.dtype)]))
  return { ...columnTypesOf(result.value.meta), ...fromColumns }
})
function isAmount(v: unknown, key: string): boolean {
  return isAmountCell(v, key, columnTypes.value)
}
function formatCellValue(v: unknown, key?: string): string {
  return formatQueryCell(v, key, columnTypes.value)
}

// 操作列：打开权威页面 / 复制经地址库校验的引用（与弹窗同一组规则）
const rowLinks = useQueryRowLinks({
  source: () => lastRun.value.source,
  projectId: () => lastRun.value.projectId,
  year: () => lastRun.value.year,
  columns: () => normalizeColumns(result.value.columns).map((c) => c.key),
  templateType: () => result.value.meta?.ref_context?.template_type ?? null,
  tableIndex: () => Number(result.value.meta?.table_index ?? 0) || 0,
})

const conditionsDisabledReason = computed(() =>
  supportsConditions.value ? '' : '该数据源不支持条件筛选（附注表格、合并工作底稿、底稿选区按整表返回）')

/** 执行查询不可用的原因（按钮置灰并显示）；可执行时为空串 */
const executeBlockedReason = computed(() => {
  if (!formCtx.value.source) return '请先选择数据源'
  if (!formCtx.value.project_id) return '请先选择项目'
  if (!isKnownYear(formCtx.value.year)) return '请选择审计年度'
  if (supportsConditions.value) {
    return conditionsIncompleteReason(conditionState.value.conditions, (f) => columnLabel(f))
  }
  return ''
})

const canExport = computed(() => !queryError.value && result.value.rows.length > 0 && !!lastRun.value.payload)

/** 保存为模板的配置（与模板 config 同形：条件、组合逻辑、列、单元格取值目标） */
const templateConfig = computed<Record<string, unknown>>(() => ({
  project_id: formCtx.value.project_id,
  year: formCtx.value.year,
  condition_logic: conditionState.value.logic,
  conditions: toRequestConditions(conditionState.value.conditions),
  selected_columns: selectedColumns.value,
  available_columns: availableColumns.value,
  acnr_targets: acnrFieldIds.value,
  // 排序随模板保存（后端 config_to_request 把 sort_field / sort_order 译成请求的 sort）；每页行数随模板保存（R9.4）
  ...(sortState.value ? { sort_field: sortState.value.field, sort_order: sortState.value.direction } : {}),
  page_size: pageSize.value,
}))

// ─── 数据加载 ───
// 指标树（ADR-AQL-16）：带项目与年度加载「骨架 + 附注分支」并拍平（缓存键含附注版本，与弹窗同一缓存模块；
// 原先每次挂载都拉不带项目的全量树约 578 KB）。底稿组只有「底稿清单」，sheet 级查询从弹窗发起。
async function loadIndicators() {
  try {
    const tree = await loadIndicatorTree({
      projectId: formCtx.value.project_id || null, year: formCtx.value.year, shape: 'page',
    })
    indicatorTree.value = flattenIndicatorGroups(tree)
    // 数据源换了树形（如换项目后附注章节不同）：已选源不在新树里就清空（树为空时不动，可能只是暂时取不到）
    if (indicatorTree.value.length && formCtx.value.source && !findLeaf(formCtx.value.source)) {
      formCtx.value.source = ''
      onSourceChange()
    }
  } catch (e: any) {
    handleApiError(e, '加载查询指标库')
  }
}

function findLeaf(key: string) {
  for (const grp of indicatorTree.value) {
    const child = grp.children.find((c) => c.key === key)
    if (child) return child
  }
  return null
}

async function loadProjects() {
  try {
    const data = await api.get<any>(P_proj.list)
    const list = Array.isArray(data) ? data : (data?.items || [])
    projectList.value = list.map((p: any) => ({
      id: p.id,
      code: p.code || p.project_code,
      name: p.name || p.project_name,
      audit_year: p.audit_year ?? p.auditYear ?? null,
    }))
    // 已选项目（如从模板恢复）也要把年度对齐到该项目的审计年度
    if (formCtx.value.project_id) syncYearToProject(formCtx.value.project_id)
  } catch (e: any) {
    handleApiError(e, '加载项目列表')
  }
}

/**
 * 把「年度」对齐到所选项目的审计年度（后端 `resolve_project_audit_year`，`GET /api/projects` 下发 `audit_year`）。
 * 取不到时留空，界面提示「请选择审计年度」、执行查询不可用（原先退回「今年 − 1」：猜错年度会静默查别的年度）。
 */
function syncYearToProject(projectId: string) {
  const proj = projectList.value.find((p) => String(p.id) === String(projectId))
  const year = proj?.audit_year
  formCtx.value.year = isKnownYear(year) ? year : null
}

function onProjectChange(projectId: string) {
  syncYearToProject(projectId)
}

function onSourceChange() {
  // 切换数据源时重置条件、字段与排序（新源未必有该列）
  conditionState.value = { conditions: [], logic: conditionState.value.logic }
  sortState.value = null
  resultTableRef.value?.clearSort?.()
  const leaf = findLeaf(formCtx.value.source)
  availableColumns.value = leaf ? [...leaf.columns] : []
  selectedColumns.value = leaf ? [...leaf.columns] : []
  supportsConditions.value = leaf ? leaf.supportsConditions : true
}

function toggleAllColumns() {
  if (selectedColumns.value.length === availableColumns.value.length) {
    selectedColumns.value = []
  } else {
    selectedColumns.value = [...availableColumns.value]
  }
}

// ─── 执行查询 ───
/** 旧筛选键：只给报表叶子带报表类型（报表行次配置 report_lines 也以 report_ 开头，带上即 0 行）；条件走 conditions */
function requestFilters(source: string): Record<string, any> {
  const out: Record<string, any> = {}
  const reportType = reportTypeOfSource(source)
  if (reportType) out.report_type = reportType
  return out
}

async function onExecute(keepPage = false) {
  if (!formCtx.value.source) {
    ElMessage.warning('请先选择数据源')
    return
  }
  if (!formCtx.value.project_id) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!isKnownYear(formCtx.value.year)) {
    ElMessage.warning('未设置审计年度，请选择审计年度后再查询')
    return
  }
  const incomplete = supportsConditions.value ? conditionsIncompleteReason(conditionState.value.conditions, (f) => columnLabel(f)) : ''
  if (incomplete) {
    ElMessage.warning(incomplete)
    return
  }
  // 新条件从第 1 页开始；翻页时由 onPagerChange 保持页码
  if (!keepPage) page.value = 1
  executing.value = true
  queryError.value = null
  if (keepPage) {
    // 翻页：保留 total（分页条据此渲染），只清当前页行
    result.value = { ...result.value, rows: [] }
  } else {
    result.value = { rows: [], columns: [], total: 0 }
  }
  const source = formCtx.value.source
  const year = formCtx.value.year
  const conditions = supportsConditions.value ? toRequestConditions(conditionState.value.conditions) : []
  // 结构化条件 + 组合逻辑（R6.1）、所选列（R6.3）、offset 翻页；单元格取值目标只在有项目时发送
  const input: BusinessQueryInput = {
    projectId: formCtx.value.project_id, year, source,
    filters: requestFilters(source), columns: selectedColumns.value,
    ...(conditions.length ? { conditions, condition_logic: conditionState.value.logic } : {}),
    ...(sortState.value ? { sort: [sortState.value] } : {}),
    limit: pageSize.value, offset: (page.value - 1) * pageSize.value,
  }
  const targets = [...acnrFieldIds.value]
  try {
    // 请求体唯一构造处（T16 契约：execute 调用点的请求体必须直接是 buildBusinessPayload 调用）
    const data = await api.post<QueryResult>(P_cq.execute, buildBusinessPayload(input, targets), { _silent: true } as any)
    if (data) {
      result.value = data
      lastRun.value = { source, projectId: formCtx.value.project_id, year, payload: buildBusinessPayload(input, targets) }
      void rowLinks.validateRefs(data.rows || [])
      if ((data.total ?? 0) === 0) {
        // 0 行必须可诊断：年度对不上是最常见原因（四表按年度分区存），
        // 静默返回空结果会让人以为功能坏了。把实际用的年度写进提示。
        emptyHint.value = `年度 ${year} 下没有匹配数据`
        ElMessage.info(`查询完成，0 条 —— 当前年度为 ${year}，请确认年度是否正确`)
      } else {
        emptyHint.value = ''
        ElMessage.success(`查询完成，本页 ${data.rows?.length || 0} 条 / 共 ${data.total ?? 0} 条`)
      }
    }
  } catch (e: unknown) {
    // 调用方自管错误（_silent）：结果区持久显示后端中文原因与追踪号，确定性错误不自动重试（R11.1）
    result.value = { rows: [], columns: [], total: 0 }
    rowLinks.reset()
    queryError.value = describeQueryError(e)
  } finally {
    executing.value = false
  }
}

// ─── 分页（R2.6）─────────────────────────────────────────────────────────
function onPagerChange() {
  void onExecute(true)
}

// ─── 导出：全部（服务端）/ 当前页（前端 xlsx） ───
function onExportCommand(command: string) {
  if (command === 'all') void onExportAll()
  else void onExportPage()
}

function exportBaseName(): string {
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  return `高级查询_${lastRun.value.source || formCtx.value.source}_${ts}`
}

async function onExportPage() {
  if (result.value.rows.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    const cols = displayColumns.value
    await exportQueryResultToXlsx({
      columns: cols.map(c => c.key),
      rows: result.value.rows,
      labelFn: (key) => columnLabel(key, cols.find(c => c.key === key)?.title),
      fileName: exportBaseName(),
    })
    ElMessage.success('已导出当前页')
  } catch (e: any) {
    handleApiError(e, '导出 Excel')
  }
}

/** 导出全部：按本次查询（条件、列）服务端导出全量结果，表头为界面所见中文列名（R8.1） */
async function onExportAll() {
  const payload = lastRun.value.payload
  if (!payload) return
  exporting.value = true
  try {
    const headers = Object.fromEntries(displayColumns.value.map((c) => [c.key, c.title]))
    await exportAllQueryRows(buildExportBody(payload, headers, exportBaseName()))
    ElMessage.success(`已导出全部结果（共 ${result.value.total} 条）`)
  } catch (e: unknown) {
    ElMessage.warning(queryErrorToast('导出全部', describeQueryError(await readBlobErrorBody(e))))
  } finally {
    exporting.value = false
  }
}

// ─── 模板管理（列表、删除进回收站在共用的 MyTemplatesDialog）───
function onSaveTemplate() {
  if (!formCtx.value.source) {
    ElMessage.warning('请先选择数据源后再保存')
    return
  }
  saveDialogVisible.value = true
}

/**
 * 「载入」模板（R9.4，queryTemplateRestore）：还原数据源、条件（兼容旧写法）、列、排序、每页行数与单元格取值目标；
 * 项目与年度保持界面当前的（原先套用模板里存的年度，与模板执行「年度取请求年度」不一致，R9.3）。
 */
function onTemplateLoad(tpl: QueryTemplateItem) {
  const restored = restoreTemplateQuery(tpl)
  if (!restored) return
  formCtx.value.source = restored.source
  onSourceChange()
  if (restored.availableColumns.length) availableColumns.value = restored.availableColumns
  if (restored.columns.length) selectedColumns.value = restored.columns
  conditionState.value = restored.condition
  sortState.value = restored.sort
  if (restored.pageSize) pageSize.value = restored.pageSize
  page.value = 1
  acnrFieldIds.value = restored.acnrTargets
  ElMessage.success(`已载入模板「${tpl.name}」，点击「执行查询」查看结果`)
}

// 项目变化时清除结果；项目或年度变化时按新上下文重新取指标树（附注分支随项目年度变）
watch(() => formCtx.value.project_id, () => {
  result.value = { rows: [], columns: [], total: 0 }
  queryError.value = null
  rowLinks.reset()
})
watch(() => [formCtx.value.project_id, formCtx.value.year] as const, () => { void loadIndicators() })

onMounted(() => {
  loadIndicators()
  loadProjects()
})
</script>

<style scoped>
.gt-cqt {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.gt-cqt-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white);
  border-radius: 6px;
  border: 1px solid var(--gt-color-border-lighter);
}
.gt-cqt-ctx-form { margin-bottom: 0; flex: 1; }
.gt-cqt-ctx-form :deep(.el-form-item) { margin-bottom: 0; margin-right: 12px; }
.gt-cqt-top-actions { display: flex; gap: 8px; flex-shrink: 0; }
.gt-cqt-em { color: var(--gt-color-info); font-size: var(--gt-font-size-xs); }

/* Capability_Guidance 能力说明横幅（R11.5） */
.gt-cqt-guidance { border-radius: 6px; }
.gt-cqt-guidance-title { font-weight: 600; }
.gt-cqt-guidance-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
  font-size: var(--gt-font-size-xs);
  line-height: 1.6;
}
.gt-cqt-guidance-body p { margin: 0; }
.gt-cqt-guidance-body :deep(.el-tag) { margin-right: 6px; }
/* 禁用态构建器入口的 span 包裹：让 tooltip 在禁用按钮上仍可悬停触发 */
.gt-cqt-builder-entry { display: inline-flex; }

.gt-cqt-main {
  flex: 1;
  margin: 0 !important;
  min-height: 0;
}
.gt-cqt-left,
.gt-cqt-right {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
}

.gt-cqt-panel {
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
  padding: 12px;
}
.gt-cqt-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
  margin-bottom: 12px;
}


.gt-cqt-fields {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 4px 12px;
  max-height: 220px;
  overflow: auto;
  padding: 4px 0;
}
.gt-cqt-fields :deep(.el-checkbox) {
  margin-right: 0;
  height: 24px;
}

.gt-cqt-panel-actions {
  margin-top: 8px;
}

.gt-cqt-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
}
.gt-cqt-result-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.gt-cqt-result-actions { display: flex; gap: 8px; }
.gt-cqt-warning { margin-top: 8px; }
.gt-cqt-result-body {
  flex: 1;
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
  padding: 8px;
  min-height: 0;
  overflow: auto;
}
.gt-cqt-empty-hint {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
  text-align: center;
}
.gt-cqt-empty-tip {
  margin-top: 6px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}
.gt-cqt-table { font-size: var(--gt-font-size-xs); }
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.gt-cqt-drill-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}
.gt-cqt-drill-chip {
  flex-shrink: 0;
}
/* 年度为空时的提示（R10.2：不按日历年推算，要求选择） */
.gt-cqt-year-hint { margin-left: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-coral); }
/* 禁用的执行按钮外包一层：tooltip 挂在可交互容器上 */
.gt-cqt-run-wrap { display: block; }
</style>
