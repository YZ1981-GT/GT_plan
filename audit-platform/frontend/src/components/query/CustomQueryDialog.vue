<!--
  自定义查询弹窗 — 全局多维度数据查询（统一入口）

  Tab 1 业务视图：树形指标 + 预设数据源 + 简单过滤 + 转置/复制/导出（全员可用）
  Tab 2 高级构建器：表选择 + 字段勾选 + 多条件 + SQL 预览 + 导出（仅 admin/manager/partner）
-->
<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    :width="fullscreen ? '100%' : '92%'"
    :top="fullscreen ? '0' : '3vh'"
    :fullscreen="fullscreen"
    :show-close="false"
    append-to-body
    destroy-on-close
    class="gt-cq-dialog"
  >
    <template #header="{ close }">
      <div class="gt-cq-dialog-header">
        <span class="gt-cq-dialog-title">🔍 高级查询</span>
        <span class="gt-cq-dialog-actions">
          <el-tooltip :content="fullscreen ? '退出全屏' : '全屏'" placement="bottom">
            <el-button text :icon="fullscreen ? Aim : FullScreen" @click="fullscreen = !fullscreen" />
          </el-tooltip>
          <el-button text :icon="Close" @click="close" />
        </span>
      </div>
    </template>
    <el-tabs v-model="activeTab" class="gt-cq-tabs" type="border-card">
      <el-tab-pane label="业务视图" name="basic">
        <div class="gt-cq-container">
          <!-- 左侧：指标树 -->
          <div class="gt-cq-sidebar">
            <div class="gt-cq-sidebar-title">
              数据源
              <el-tooltip :content="treeViewMode === 'source' ? '切换为按模板形态分组' : '切换为按数据源分类'" placement="top">
                <el-button
                  size="small"
                  circle
                  :type="treeViewMode === 'template' ? 'primary' : 'default'"
                  style="margin-left: auto; font-size: 12px"
                  @click="toggleTreeViewMode"
                >
                  {{ treeViewMode === 'source' ? '📂' : '📋' }}
                </el-button>
              </el-tooltip>
            </div>
            <el-tree
              ref="treeRef"
              :data="displayTree"
              :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
              node-key="key"
              highlight-current
              :expand-on-click-node="false"
              :default-expanded-keys="[]"
              @node-click="onIndicatorClick"
            >
              <template #default="{ data }">
                <span :class="['gt-cq-tree-node', { 'gt-cq-tree-node-disabled': data.disabled }]"
                  :title="data.disabled ? '该底稿在当前项目中已裁剪，不可选' : ''">
                  {{ data.label }}
                </span>
              </template>
            </el-tree>
          </div>
          <!-- 右侧：查询条件 + 结果 -->
          <div class="gt-cq-main">
            <div class="gt-cq-filter-bar">
              <!-- 项目选择（可选：不选 = 模板浏览模式） -->
              <el-select
                v-model="localProjectId"
                size="small"
                style="width:240px"
                placeholder="选择项目（可空 = 模板浏览）"
                aria-label="项目"
                filterable
                clearable
                :loading="projectsLoading"
                @change="onProjectPicked"
              >
                <el-option
                  v-for="p in projectOptions"
                  :key="p.id"
                  :label="`${p.name}${p.audit_year ? ' · ' + p.audit_year : '（未配置年度）'}`"
                  :value="p.id"
                />
              </el-select>
              <!-- 年度：路由 ?year → 所选项目审计年度 → 留空要求选择（R10.2，不按日历年推算） -->
              <el-input-number
                v-model="localYear"
                size="small"
                :min="2000"
                :max="2100"
                :step="1"
                :value-on-clear="null"
                placeholder="审计年度"
                aria-label="审计年度"
                style="width:120px"
                controls-position="right"
              />
              <span v-if="localYear == null" class="gt-cq-year-hint" data-testid="cq-year-hint">请选择审计年度</span>
              <!-- 数据源（受左树大类筛选） -->
              <el-select v-model="selectedSource" size="small" style="width:220px" aria-label="数据源"
                :placeholder="clickedCategory ? `${currentCategoryLabel} 下数据源` : '数据源'">
                <el-option v-for="s in sourceOptions" :key="s.key" :label="s.label" :value="s.key" />
              </el-select>
              <el-tooltip v-if="clickedCategory" content="清除大类筛选，显示全部数据源" placement="top">
                <el-button size="small" text :icon="RefreshLeft" aria-label="清除大类筛选" @click="resetCategoryFilter" />
              </el-tooltip>
              <el-input v-model="filterText" size="small" style="width:200px" placeholder="仅筛选本页" aria-label="仅筛选本页（不重新查询）" clearable />
              <el-tooltip :disabled="!queryBlockedReason" :content="queryBlockedReason" placement="top">
                <span class="gt-cq-btn-wrap">
                  <el-button size="small" type="primary" :disabled="!!queryBlockedReason" :loading="loading"
                    aria-label="查询" data-testid="cq-run" @click="executeQuery()">▶ 查询</el-button>
                </span>
              </el-tooltip>
              <span style="flex:1" />
              <el-dropdown v-if="queryHistory.length" size="small" trigger="click" @command="applyHistory">
                <el-button size="small">🕘 历史</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="(h, i) in queryHistory" :key="i" :command="h">
                      {{ h.sourceLabel }} · {{ h.projectLabel }}（{{ h.year }}）{{ h.filterText ? ' · ' + h.filterText : '' }}
                    </el-dropdown-item>
                    <el-dropdown-item v-if="queryHistory.length" divided :command="'__clear__'">
                      🗑️ 清空历史
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" aria-label="查询模板" data-testid="cq-templates" title="载入或执行已保存的查询模板"
                @click="templatesVisible = true">📑 模板</el-button>
              <el-button size="small" @click="openSaveDialog" :disabled="!selectedSource" title="保存当前选区/条件为查询模板">💾 保存</el-button>
              <el-button size="small" @click="transposed = !transposed">{{ transposed ? '↩ 还原' : '↔ 转置' }}</el-button>
              <el-button size="small" @click="copyResult">📋 复制</el-button>
              <!-- 导出：全部（服务端按当前查询导出全量，R8.1）/ 当前页（前端，次选项 R8.3） -->
              <el-dropdown size="small" trigger="click" :disabled="!canExport" @command="onExportCommand">
                <el-button size="small" :disabled="!canExport" :loading="exporting" aria-label="导出查询结果" data-testid="cq-export">
                  📤 导出 ▾
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="all" data-testid="cq-export-all">导出全部（共 {{ resultTotal }} 行）</el-dropdown-item>
                    <el-dropdown-item command="page" data-testid="cq-export-page">导出当前页</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <!-- 上下文 chip：让用户随时看到本次查询的项目+年度+源 -->
            <div v-if="hasQueried" class="gt-cq-context-chip">
              <el-tag size="small" effect="plain" round>
                项目: {{ currentProjectLabel }}
              </el-tag>
              <el-tag size="small" effect="plain" round type="info">
                年度: {{ localYear ?? '未选择' }}
              </el-tag>
              <el-tag size="small" effect="plain" round type="success">
                {{ currentSourceLabel }}
              </el-tag>
              <el-tag v-if="sheetCellRange" size="small" effect="dark" round type="warning"
                closable @close="sheetCellRange = ''" @click="reopenSheetPicker"
                style="cursor:pointer">
                选区: {{ sheetCellRange }} (点击重选)
              </el-tag>
              <!-- 附注章节有多张表时可切换（meta.tables，ADR-AQL-16） -->
              <el-select v-if="noteTables.length > 1" :model-value="noteTableIndex" size="small" style="width:220px"
                aria-label="切换附注表格" data-testid="cq-note-table" @update:model-value="onNoteTableChange">
                <el-option v-for="t in noteTables" :key="t.index" :value="t.index"
                  :label="`${t.name || `表 ${t.index + 1}`}（${t.row_count} 行）`" />
              </el-select>
            </div>
            <!-- 入口带来的说明（R10.5：附注模板落附注目录时提示编号体系不同）；换数据源即清除 -->
            <el-alert v-if="entryNotice" type="info" show-icon :title="entryNotice.text" class="gt-cq-entry-notice"
              data-testid="cq-entry-notice" @close="entryNotice = null" />
            <!-- 载入 / 执行的模板（R9.3 / R9.4）：弹窗不能编辑的条件与列照样随查询发送并在此写明；关闭即不再使用 -->
            <el-alert v-if="templateNotice" type="info" show-icon :title="templateNotice" class="gt-cq-entry-notice"
              data-testid="cq-template-notice" @close="clearTemplateState" />
            <!-- 查询失败：持久显示中文原因与追踪号，不落到「暂无数据」（R11.1） -->
            <QueryErrorAlert v-if="queryError" :error="queryError" />
            <!-- 结果表格 -->
            <!-- 点表头排序：在数据库内对全量排序（空值在后）并回到第 1 页（R2.2），不是只排本页 -->
            <el-table v-else-if="!transposed" ref="resultTableRef" :data="filteredRows" v-loading="loading" border size="small"
              max-height="calc(100vh - 300px)" style="width:100%" :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }"
              :default-sort="tableDefaultSort" @sort-change="onSortChange"
              @row-contextmenu="onRowContextMenu">
              <template #empty>
                <el-empty :description="emptyText" :image-size="60" />
              </template>
              <!-- 操作列：打开权威页面 / 复制经地址库校验的引用（R7.1~R7.3）；结果区没有回写入口（R7.5） -->
              <el-table-column v-if="resultColumns.length" label="操作" width="130" fixed="left">
                <template #default="{ row }">
                  <QueryRowActions :drill="rowLinks.drillOf(row)" :ref-text="rowLinks.refOf(row)"
                    :ref-usable="rowLinks.refUsable(row)" :ref-hint="rowLinks.refHint(row)"
                    @open="rowLinks.openRow(row)" @copy-ref="rowLinks.copyRef(row)" />
                </template>
              </el-table-column>
              <el-table-column v-for="col in resultColumns" :key="col" :prop="col" :label="columnLabel(col)" min-width="120"
                sortable="custom" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="col === 'cell_ref' && row.wp_code" class="gt-cq-cell-ref-link"
                    @click="rowLinks.openRow(row)" :title="`在底稿 ${row.wp_code} ${row.sheet_name || ''} 中定位单元格 ${row[col]}`">
                    {{ formatCell(row[col], col) }}
                  </span>
                  <span v-else :style="{ textAlign: isAmount(row[col], col) ? 'right' : 'left', display: 'block' }">
                    {{ formatCell(row[col], col) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
            <!-- 右键菜单（Req 14 AC 2: 跳模板溯源） -->
            <div
              v-if="ctxMenuVisible"
              class="gt-cq-ctx-menu"
              :style="{ left: ctxMenuPos.x + 'px', top: ctxMenuPos.y + 'px' }"
            >
              <div class="gt-cq-ctx-menu-item" @click="onTraceToTemplate">🔗 跳模板溯源</div>
            </div>
            <!-- 转置视图（原先 v-else 挂在右键菜单上，菜单没打开时与普通表格同时显示） -->
            <div v-if="transposed && !queryError" class="gt-cq-transposed" v-loading="loading">
              <el-alert v-if="filteredRows.length > 50" type="info" :closable="false" show-icon
                title="转置视图仅展示前 50 行（作为列），完整数据请切回非转置视图或导出" style="margin-bottom: 6px" />
              <el-table :data="transposedRows" border size="small" max-height="calc(100vh - 280px)" style="width:100%"
                :header-cell-style="{ background: '#f0edf5', whiteSpace: 'nowrap', fontSize: '12px' }">
                <template #empty>
                  <el-empty description="暂无数据" :image-size="60" />
                </template>
                <el-table-column prop="_field_label" label="字段" width="140" fixed="left" />
                <el-table-column v-for="(_, ci) in transposedDataCols" :key="ci" :prop="'_v' + ci" :label="'#' + (ci + 1)" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span style="display:block; text-align:right">{{ row['_v' + ci] }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <div v-if="hasQueried && !queryError" class="gt-cq-footer" data-testid="cq-footer">
              <span class="gt-cq-footer-count">本页 {{ resultRows.length }} 行 / 共 {{ resultTotal }} 行 × {{ resultColumns.length }} 列{{ filterText ? `（仅筛选本页：${filteredRows.length} 行）` : '' }}</span>
              <QueryResultPager v-model:page="page" v-model:page-size="pageSize" :total="resultTotal" @change="onPageChange" />
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 高级构建器：入口与后端准入同一判定（access 接口，R3.6）；无权时页签置灰并显示原因；只在打开时挂载 -->
      <el-tab-pane name="advanced" lazy :disabled="!canUseBuilder">
        <template #label>
          <el-tooltip :disabled="canUseBuilder" :content="builderDisabledReason" placement="bottom">
            <span data-testid="cq-builder-tab">高级构建器 <el-tag size="small" type="info" effect="plain" round style="margin-left:4px">SQL</el-tag></span>
          </el-tooltip>
        </template>
        <AdvancedQueryBuilder embedded :project-id="localProjectId || undefined" :year="localYear ?? undefined" />
      </el-tab-pane>
    </el-tabs>

    <!-- Sheet 单元格区域选择器（点 sheet 叶子时弹出）；年度由本弹窗传入，未选年度时选区器不预览 -->
    <SheetCellRangePicker
      v-model="sheetPickerVisible"
      :wp-code="sheetPickerCtx.wpCode"
      :sheet-name="sheetPickerCtx.sheetName"
      :project-id="localProjectId"
      :year="localYear"
      @confirm="onSheetRangeConfirm"
    />
    <!-- 💾 保存：三档可见范围，可分享项目与页面版同一来源（AQ-39） -->
    <QueryTemplateSaveDialog v-model="saveDialogVisible" :data-source="selectedSource" :config="templateConfig"
      :projects="projectOptions" :default-description="templateDescription" />
    <!-- 📑 模板：与页面版同一个选择组件；「执行」按当前项目经服务端模板执行端点（重新鉴权、可翻页） -->
    <MyTemplatesDialog v-model="templatesVisible" allow-run :run-blocked-reason="localProjectId ? '' : '请先选择项目'"
      @load="(_cfg, tpl) => applyTemplate(tpl, false)" @run="(tpl) => applyTemplate(tpl, true)" />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { FullScreen, Aim, Close, RefreshLeft } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { resolveColumnLabel } from './queryColumnLabels'
import { exportQueryResultToXlsx, sanitizeExportName } from './queryExport'
import { buildTraceUri, reportTypeOfSource, RESOLVE_FAIL_MSG } from './querySourceUri'
import { listProjectsWithProgress } from '@/services/commonApi'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'
import SheetCellRangePicker from '@/components/query/SheetCellRangePicker.vue'
import {
  buildBusinessPayload, isKnownYear, readBlobErrorBody, type BusinessQueryInput, type QuerySort,
} from '@/components/custom-query/queryPayloads'
import { useQueryBuilderAccess } from '@/composables/useQueryBuilderAccess'
import { describeQueryError, queryErrorToast, type QueryErrorText } from './queryErrorText'
import { columnTypesOf, formatQueryCell, isAmountCell } from './queryCellFormat'
import { loadIndicatorTree } from './queryIndicatorLoader'
import { buildExportBody, exportAllQueryRows } from './queryServerExport'
import { useQueryRowLinks } from './useQueryRowLinks'
import QueryErrorAlert from './QueryErrorAlert.vue'
import QueryResultPager from './QueryResultPager.vue'
import QueryRowActions from './QueryRowActions.vue'
import QueryTemplateSaveDialog from './QueryTemplateSaveDialog.vue'
import MyTemplatesDialog from './MyTemplatesDialog.vue'
import { toRequestConditions, type ConditionLogic, type RequestCondition } from './queryConditions'
import { restoreTemplateQuery, type QueryTemplateItem } from './queryTemplateRestore'
import { customQuery as P_cq } from '@/services/apiPaths'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  /** 项目年度；项目没填审计年度为 null（弹窗里由用户指定，不按日历猜） */
  year: number | null
  /** 初始 tab：'basic'（默认业务视图）/ 'advanced'（高级构建器） */
  initialTab?: 'basic' | 'advanced'
  /** 初始 source（侧栏按当前页预选、模板库按钮经 resolveTemplateLibrarySource 映射；每次打开都套用） */
  initialSource?: string
  /** 随初始 source 带来的说明（模板库附注按钮：模板章节号与项目附注编号不同），用户换数据源即清除 */
  initialNotice?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

// 全屏状态：弹窗每次打开重置为非全屏
const fullscreen = ref(false)
const dialogTitle = computed(() => '🔍 高级查询')
watch(visible, (v) => { if (!v) fullscreen.value = false })

const router = useRouter()
// 构建器页签：与后端准入同一判定（GET /api/query/access，ADR-AQL-08）；原先按系统角色 {admin, manager, partner} 自判
const { canUseBuilder, builderDisabledReason } = useQueryBuilderAccess()

const activeTab = ref<'basic' | 'advanced'>(props.initialTab || 'basic')
// 弹窗每次打开都按 initialTab 重置 active
watch(visible, (v) => { if (v) activeTab.value = props.initialTab || 'basic' })

// 项目 / 年度（R10.1 / R10.2，design §4.2）：每次打开都以路由项目为准，非项目页不预选任何项目（原先取项目列表第一项）；
// 年度依次取 props.year（路由 ?year）→ 所选项目审计年度 → 留空要求选择，不按日历年推算
const localProjectId = ref<string>(props.projectId || '')
const localYear = ref<number | null>(props.year ?? null)

interface ProjectOption { id: string; name: string; audit_year?: number | null }
const projectOptions = ref<ProjectOption[]>([])
const projectsLoading = ref(false)

function auditYearOf(pid: string): number | null {
  const y = projectOptions.value.find((x) => x.id === pid)?.audit_year
  return isKnownYear(y) ? y : null
}

/** 打开弹窗 / 路由项目或年度变了：项目 = 路由项目，年度 = 路由年度 ?? 该项目审计年度 ?? 空 */
function adoptRouteContext() {
  localProjectId.value = props.projectId || ''
  localYear.value = isKnownYear(props.year) ? props.year : auditYearOf(localProjectId.value)
}

/** 用户在下拉里换项目：年度跟随该项目审计年度（没有就留空） */
function onProjectPicked(pid: string) {
  localYear.value = auditYearOf(pid || '')
}

async function loadProjectList() {
  if (projectOptions.value.length > 0) return
  projectsLoading.value = true
  try {
    const list = await listProjectsWithProgress()
    projectOptions.value = list.map((p: any) => ({ id: p.id, name: p.name, audit_year: p.audit_year }))
    // 列表到了：年度仍空时补上所选项目的审计年度
    if (localYear.value == null) localYear.value = auditYearOf(localProjectId.value)
  } catch { projectOptions.value = [] } finally { projectsLoading.value = false }
}
// 弹窗打开时：采用路由上下文、按需加载项目列表与指标树
watch(visible, (v) => {
  if (!v) return
  adoptRouteContext()
  void loadProjectList()
}, { immediate: true })
watch(() => [props.projectId, props.year] as const, () => { if (visible.value) adoptRouteContext() })

const loading = ref(false)
const transposed = ref(false)
const filterText = ref('')
const selectedSource = ref('report_balance_sheet')
// 翻页（R2.6）：每页 100 / 200 / 500 行，total 是后端 COUNT（原先 200~2000 四档上限、无 offset、不显示 total）
const page = ref(1)
const pageSize = ref(100)
const resultTotal = ref(0)
const resultMeta = ref<Record<string, any> | null>(null)
const queryError = ref<QueryErrorText | null>(null)
/** 本次打开带来的说明与它所属的源（initialNotice） */
const entryNotice = ref<{ source: string; text: string } | null>(null)
const exporting = ref(false)
const saveDialogVisible = ref(false)
// 附注章节当前显示第几张表（meta.tables 多于 1 张时可切换）
const noteTableIndex = ref(0)
/** 本次结果所属的查询（操作列的下钻 / 引用、导出全部的筛选与文件名都按它，不按界面当前选择；B10 评审非阻塞 #1） */
interface QueryRun {
  source: string; projectId: string; year: number | null; sort: QuerySort[]
  filters: Record<string, unknown>; projectLabel: string; sourceLabel: string
  /** 载入的模板带来的条件 / 列（弹窗内不可编辑，照样随查询与导出发送） */
  extra: Pick<BusinessQueryInput, 'conditions' | 'condition_logic' | 'columns'>
}
const lastRun = ref<QueryRun>(
  { source: '', projectId: '', year: null, sort: [], filters: {}, projectLabel: '', sourceLabel: '', extra: {} })
// 📑 模板（R9.3 / R9.4）：与页面版同一个选择组件
const templatesVisible = ref(false)
/** 载入的模板里弹窗不能编辑的部分（条件 / 列）：随查询发送并在结果区上方写明；换数据源或关闭提示即清除 */
const templateQuery = ref<{
  name: string; source: string; conditions: RequestCondition[]; logic: ConditionLogic; columns: string[]
} | null>(null)
/** 本次结果来自「执行模板」：翻页仍走模板执行端点；手动查询、排序、换数据源即回到普通查询 */
const templateRun = ref<{ id: string; name: string } | null>(null)
// 排序（R2.2）：点表头在数据库内对全量排序、空值在后，回到第 1 页；换数据源即清除（新源未必有该列）
const sortState = ref<QuerySort | null>(null)
const resultTableRef = ref<{ clearSort?: () => void } | null>(null)
// 表格因失败 / 转置重新挂载后照样显示当前排序箭头（default-sort 只在挂载时生效，不触发 sort-change）
const tableDefaultSort = computed(() => (sortState.value
  ? { prop: sortState.value.field, order: sortState.value.direction === 'desc' ? 'descending' : 'ascending' } as const
  : undefined))
function onSortChange({ prop, order }: { prop?: string | null; order?: string | null }) {
  sortState.value = prop && order ? { field: String(prop), direction: order === 'descending' ? 'desc' : 'asc' } : null
  void executeQuery() // 模板执行端点不收排序：改排序即回到普通查询（载入的条件照常带上）
}

// 查询历史（最近 10 次，localStorage 持久，点击回填并重查）
interface QueryHistoryItem {
  // 年度：查询时用的是什么就记什么（模板浏览 / 项目没填年度时为 null，回填后照样不带年度查）
  projectId: string; projectLabel: string; year: number | null
  source: string; sourceLabel: string; filterText: string; cellRange: string; ts: number
}
const QUERY_HISTORY_KEY = 'gt:cq:history'
const queryHistory = ref<QueryHistoryItem[]>([])
function loadQueryHistory() {
  try { queryHistory.value = JSON.parse(localStorage.getItem(QUERY_HISTORY_KEY) || '[]') } catch { queryHistory.value = [] }
}
function pushQueryHistory() {
  const item: QueryHistoryItem = {
    projectId: localProjectId.value, projectLabel: currentProjectLabel.value, year: localYear.value,
    source: selectedSource.value, sourceLabel: currentSourceLabel.value,
    filterText: filterText.value, cellRange: sheetCellRange.value, ts: Date.now(),
  }
  const key = (h: QueryHistoryItem) => `${h.projectId}|${h.year}|${h.source}|${h.filterText}|${h.cellRange}`
  const dedup = queryHistory.value.filter(h => key(h) !== key(item))
  queryHistory.value = [item, ...dedup].slice(0, 10)
  try { localStorage.setItem(QUERY_HISTORY_KEY, JSON.stringify(queryHistory.value)) } catch { /* ignore quota */ }
}
async function applyHistory(item: QueryHistoryItem | string) {
  if (item === '__clear__') {
    queryHistory.value = []
    try { localStorage.removeItem(QUERY_HISTORY_KEY) } catch { /* ignore */ }
    ElMessage.success('查询历史已清空')
    return
  }
  const h = item as QueryHistoryItem
  if (h.projectId) localProjectId.value = h.projectId
  localYear.value = h.year
  selectedSource.value = h.source
  filterText.value = h.filterText || ''
  sheetCellRange.value = h.cellRange || ''
  await executeQuery()
}
const filterReportType = ref('balance_sheet')
const resultRows = ref<any[]>([])
const resultColumns = ref<string[]>([])
const indicatorTree = ref<any[]>([])
const treeRef = ref<any>(null)
// 是否已发起过查询（用于显示上下文 chip 与友好空态）
const hasQueried = ref(false)
// 左树点击的大类 key（null = 未点击大类，下拉显示全部）
const clickedCategory = ref<string | null>(null)

// ─── 树视图模式 (Req 14 AC 4): 按数据源分类 / 按模板形态分组 ─────────────────
type TreeViewMode = 'source' | 'template'
const treeViewMode = ref<TreeViewMode>(
  (sessionStorage.getItem('gt:cq:tree-view-mode') as TreeViewMode) || 'source'
)
function toggleTreeViewMode() {
  treeViewMode.value = treeViewMode.value === 'source' ? 'template' : 'source'
  sessionStorage.setItem('gt:cq:tree-view-mode', treeViewMode.value)
}

// 按模板形态分组视图：把 indicatorTree 重组为 4 大类（底稿/报表/附注/调整分录）
const templateGroupedTree = computed(() => {
  if (!indicatorTree.value.length) return []
  const groups: Record<string, any> = {
    workpaper: { key: '_tpl_workpaper', label: '📋 底稿模板', children: [] as any[] },
    report: { key: '_tpl_report', label: '📊 报表模板', children: [] as any[] },
    note: { key: '_tpl_note', label: '📝 附注模板', children: [] as any[] },
    other: { key: '_tpl_other', label: '🔧 其他（调整/试算）', children: [] as any[] },
  }
  for (const cat of indicatorTree.value) {
    const k = (cat.key || '').toLowerCase()
    if (k.includes('workpaper') || k.includes('底稿') || k.startsWith('wp_')) {
      groups.workpaper.children.push(cat)
    } else if (k.includes('report') || k.includes('报表')) {
      groups.report.children.push(cat)
    } else if (k.includes('disclosure') || k.includes('附注') || k.includes('note')) {
      groups.note.children.push(cat)
    } else {
      groups.other.children.push(cat)
    }
  }
  return Object.values(groups).filter(g => g.children.length > 0)
})

// 当前展示的树数据
const displayTree = computed(() =>
  treeViewMode.value === 'source' ? indicatorTree.value : templateGroupedTree.value
)

// Sheet 单元格区域选择器状态
const sheetPickerVisible = ref(false)
const sheetPickerCtx = ref<{ wpCode: string; sheetName?: string }>({ wpCode: '' })
const sheetCellRange = ref<string>('')  // 用户在 sheet picker 选中的 cell range（如 'A1:E5'）

// 当前项目/数据源的可读标签（chip 显示）
const currentProjectLabel = computed(() => {
  const p = projectOptions.value.find(x => x.id === localProjectId.value)
  return p ? p.name : '—'
})
const currentSourceLabel = computed(() => {
  return sourceOptions.value.find(s => s.key === selectedSource.value)?.label || selectedSource.value
})
const currentCategoryLabel = computed(() => {
  if (!clickedCategory.value) return ''
  // 递归找 clickedCategory 节点的 label（任意层）
  function findLabel(nodes: any[]): string | null {
    for (const n of nodes) {
      if (n.key === clickedCategory.value) return n.label || ''
      if (n.children?.length) {
        const r = findLabel(n.children)
        if (r !== null) return r
      }
    }
    return null
  }
  return findLabel(indicatorTree.value) || (clickedCategory.value as string)
})

// 空态文案：根据是否已查询给不同提示
const emptyText = computed(() => {
  if (!hasQueried.value) return '请选择数据源后点击「▶ 查询」（项目可选，未选时仅展示模板结构）'
  if (!localProjectId.value && _sourceRequiresProject(selectedSource.value)) return '该数据源需先选择项目'
  return localProjectId.value
    ? `当前项目「${currentProjectLabel.value}」${localYear.value} 年度暂无该数据源记录`
    : '模板浏览模式（未选项目）：仅显示报表/附注/底稿模板结构，不含项目实际值'
})

/** 判定 source 是否必须传 project_id（试算/账簿/底稿等业务数据必须，报表/附注/调整等模板可缺省） */
function _sourceRequiresProject(s: string): boolean {
  // 模板可浏览的源（无项目时返回模板默认）
  const TEMPLATE_OK_PREFIXES = ['report_', 'disclosure_note:', 'report_lines']
  const TEMPLATE_OK = ['report', 'disclosure', 'disclosure_note', 'report_lines']
  if (TEMPLATE_OK.includes(s)) return false
  if (TEMPLATE_OK_PREFIXES.some(p => s.startsWith(p))) return false
  return true  // 其他源（试算/账簿/底稿单元格/合并单位等）必须传 project_id
}

// 静态预设数据源（树未加载时的兜底 + 用于补全树里没有的旧 key）
const STATIC_SOURCES = [
  { key: 'report_balance_sheet', label: '📊 资产负债表', parentKey: 'report' },
  { key: 'report_income_statement', label: '📊 利润表', parentKey: 'report' },
  { key: 'report_cash_flow_statement', label: '📊 现金流量表', parentKey: 'report' },
  { key: 'tb_detail', label: '📋 试算平衡表（科目）', parentKey: 'trial_balance' },
  { key: 'tb_summary', label: '📋 试算平衡表', parentKey: 'trial_balance' },
  { key: 'disclosure', label: '📝 附注目录', parentKey: 'disclosure' },
  { key: 'adj_aje', label: '📐 审计调整分录(AJE)', parentKey: 'adjustment' },
  { key: 'adj_rje', label: '📐 重分类调整分录(RJE)', parentKey: 'adjustment' },
  { key: 'ws_info', label: '📑 基本信息表', parentKey: 'worksheet' },
  { key: 'ws_elimination', label: '📑 抵消分录', parentKey: 'worksheet' },
]

// 数据源全集：从 indicatorTree 递归扁平化派生（支持 N 层嵌套）
// 每个叶子带 ancestorKeys（从顶到自己的所有祖先 key 路径），用于按任意层过滤下拉
const allSources = computed(() => {
  if (!indicatorTree.value.length) return STATIC_SOURCES.map(s => ({ ...s, ancestorKeys: [s.parentKey] }))
  const list: { key: string; label: string; parentKey: string; ancestorKeys: string[] }[] = []
  function walk(node: any, ancestors: string[], prefix: string) {
    // 灰度节点跳过（不进入下拉数据源池）
    if (node.disabled) return
    const childList = node.children || []
    const myAncestors = [...ancestors, node.key]
    if (childList.length === 0) {
      // 叶子
      list.push({
        key: node.key,
        label: prefix ? `${prefix} / ${node.label}` : node.label,
        parentKey: ancestors[0] || node.key,
        ancestorKeys: myAncestors,
      })
      return
    }
    for (const child of childList) {
      const nextPrefix = prefix ? `${prefix} / ${node.label}` : node.label
      walk(child, myAncestors, nextPrefix)
    }
  }
  for (const cat of indicatorTree.value) {
    const icon = cat.icon || ''
    walk(cat, [], icon)
  }
  return list.length
    ? list
    : STATIC_SOURCES.map(s => ({ ...s, ancestorKeys: [s.parentKey] }))
})

// 下拉选项：受 clickedCategory 过滤（点击任意层时只显示该节点子树下叶子，未点击 = 显示全部）
const sourceOptions = computed(() => {
  if (!clickedCategory.value) return allSources.value
  return allSources.value.filter(s => s.ancestorKeys.includes(clickedCategory.value as string))
})

// 叶子 → 父大类反查表
const leafToCategory = computed(() => {
  const m: Record<string, string> = {}
  for (const s of allSources.value) m[s.key] = s.parentKey
  return m
})

const filteredRows = computed(() => {
  if (!filterText.value) return resultRows.value
  const kw = filterText.value.toLowerCase()
  return resultRows.value.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(kw)))
})

// 转置视图数据：每个原始列变成一行，每个原始行变成一列
const transposedDataCols = computed(() => filteredRows.value.slice(0, 50))
const transposedRows = computed(() => {
  const rows = transposedDataCols.value
  return resultColumns.value.map(col => {
    const entry: Record<string, any> = { _field_label: columnLabel(col) }
    rows.forEach((row, ci) => { entry['_v' + ci] = formatCell(row[col], col) })
    return entry
  })
})

// 列名按本次结果的数据源取（R6.6：合并试算的 summary 是「汇总数」，序时账 / 辅助明细的是「摘要」）
function columnLabel(col: string) { return resolveColumnLabel(col, undefined, lastRun.value.source || selectedSource.value) }
// 金额格式化按列类型（响应 meta.column_types / 列对象的 dtype；内存源按值），不再按字符串长度
const objectColumnTypes = ref<Record<string, string>>({})
const columnTypes = computed<Record<string, string>>(() => ({ ...columnTypesOf(resultMeta.value), ...objectColumnTypes.value }))
function isAmount(v: unknown, col: string) { return isAmountCell(v, col, columnTypes.value) }
function formatCell(v: unknown, col?: string) { return formatQueryCell(v, col, columnTypes.value) }

// 工具：递归找节点的第一个叶子（用于点大类自动选明细）
function findFirstLeaf(node: any): any | null {
  if (!node) return null
  if (!node.children?.length) return node
  for (const c of node.children) {
    const r = findFirstLeaf(c)
    if (r) return r
  }
  return null
}

// 工具：在 indicatorTree 中找节点 key 对应的顶层大类 key（disclosure/report/...）
function findTopCategoryOf(targetKey: string): string | null {
  for (const top of indicatorTree.value) {
    if (top.key === targetKey) return top.key
    function walk(n: any): boolean {
      if (n.key === targetKey) return true
      for (const c of (n.children || [])) {
        if (walk(c)) return true
      }
      return false
    }
    for (const c of (top.children || [])) {
      if (walk(c)) return top.key
    }
  }
  return null
}

function onIndicatorClick(data: any) {
  // 灰度节点不可选中
  if (data.disabled) {
    ElMessage.info('该底稿在当前项目中已裁剪，无法查询')
    return
  }
  if (data.children?.length) {
    // 大类/中间层节点：clickedCategory 直接设为该节点 key（精确过滤当前子树）
    clickedCategory.value = data.key
    const firstLeaf = findFirstLeaf(data)
    if (firstLeaf?.key) {
      selectedSource.value = firstLeaf.key
      if (firstLeaf.key.startsWith('report_')) filterReportType.value = firstLeaf.key.replace('report_', '')
    }
  } else if (data.key) {
    // 叶子节点：设 source，clickedCategory 设为该叶子的直接父节点（让下拉只显示同 sheet 范围）
    selectedSource.value = data.key
    if (data.key.startsWith('report_')) filterReportType.value = data.key.replace('report_', '')
    const src = allSources.value.find(s => s.key === data.key)
    if (src && src.ancestorKeys.length >= 2) {
      // 取叶子的直接父节点 key（ancestorKeys 倒数第二个，最后一个是叶子自己）
      clickedCategory.value = src.ancestorKeys[src.ancestorKeys.length - 2]
    } else {
      clickedCategory.value = leafToCategory.value[data.key] || findTopCategoryOf(data.key)
    }
    // 底稿 sheet 叶子（含 |）→ 弹出单元格区域选择器
    if (data.key.startsWith('workpaper:') && data.key.includes('|')) {
      const tail = data.key.slice('workpaper:'.length)
      const [wpCode, sheetName] = tail.split('|', 2)
      sheetPickerCtx.value = { wpCode, sheetName }
      sheetPickerVisible.value = true
    }
  }
}

function resetCategoryFilter() {
  clickedCategory.value = null
  if (treeRef.value) {
    try { treeRef.value.setCurrentKey(null) } catch { /* ignore */ }
  }
}

// selectedSource 改变时自动派生 filterReportType 并同步左侧树高亮
watch(selectedSource, (v) => {
  if (entryNotice.value && entryNotice.value.source !== v) entryNotice.value = null // 入口说明只属于带来的那个源
  if (templateQuery.value?.source !== v) clearTemplateState() // 载入的模板条件只属于模板的数据源
  noteTableIndex.value = 0 // 换数据源：附注表格回到第一张
  sortState.value = null // 换数据源：清除排序（新源未必有该列）
  resultTableRef.value?.clearSort?.()
  if (v.startsWith('report_')) filterReportType.value = v.replace('report_', '')
  // 反向高亮树节点
  if (treeRef.value && v) {
    try { treeRef.value.setCurrentKey(v) } catch { /* ignore */ }
  }
  // 用户在右侧下拉直接切换到 sheet 选项 → 同样弹出选区器
  if (v.startsWith('workpaper:') && v.includes('|')) {
    const tail = v.slice('workpaper:'.length)
    const [wpCode, sheetName] = tail.split('|', 2)
    // 不在弹窗已开时重复弹（避免左树点击时再开一次）
    if (!sheetPickerVisible.value || sheetPickerCtx.value.wpCode !== wpCode || sheetPickerCtx.value.sheetName !== sheetName) {
      sheetPickerCtx.value = { wpCode, sheetName }
      sheetPickerVisible.value = true
    }
    // 切换 sheet 时重置已选 cell range（旧选区不再适用）
    sheetCellRange.value = ''
  } else {
    // 切到非 sheet 选项时清空 range 上下文
    sheetCellRange.value = ''
  }
})

async function onSheetRangeConfirm(payload: { wp_code: string; sheet_name?: string; range: string }) {
  sheetCellRange.value = payload.range
  // 在结果表格区直接预览：把选区拆成 cell 清单（如 A1:C3 → A1,A2,A3,B1,...,C3）
  const cells = _expandRange(payload.range)
  resultColumns.value = ['index', 'wp_code', 'sheet_name', 'cell_ref', 'value']
  resultRows.value = cells.map((c, i) => ({
    index: i + 1,
    wp_code: payload.wp_code,
    sheet_name: payload.sheet_name || '',
    cell_ref: c,
    value: '— 待查询 —',
  }))
  hasQueried.value = true
  // 已选项目 → 直接取数（省去再点一次「查询」）；未选项目 → 保留占位并提示
  if (localProjectId.value) {
    ElMessage.success(`已锁定 ${payload.wp_code} / ${payload.sheet_name || ''} 选区 ${payload.range}（共 ${cells.length} 格），正在取数…`)
    await executeQuery()
  } else {
    ElMessage.success(`已锁定选区 ${payload.range}（共 ${cells.length} 格），请先选择项目再查询`)
  }
}

/** 展开 'A1:C3' / 'B5' 形式 range 为单元格清单 */
function _expandRange(range: string): string[] {
  const m = /^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/.exec(range)
  if (!m) return []
  const c1 = _colToIdx(m[1]); const r1 = parseInt(m[2], 10)
  const c2 = m[3] ? _colToIdx(m[3]) : c1
  const r2 = m[4] ? parseInt(m[4], 10) : r1
  const out: string[] = []
  const MAX = 500  // 防爆量
  for (let r = r1; r <= r2; r++) {
    for (let c = c1; c <= c2; c++) {
      out.push(`${_idxToCol(c)}${r}`)
      if (out.length >= MAX) return out
    }
  }
  return out
}
function _colToIdx(s: string): number {
  let n = 0
  for (let i = 0; i < s.length; i++) n = n * 26 + (s.charCodeAt(i) - 64)
  return n - 1
}
function _idxToCol(i: number): string {
  if (i < 26) return String.fromCharCode(65 + i)
  return String.fromCharCode(65 + Math.floor(i / 26) - 1) + String.fromCharCode(65 + (i % 26))
}

function reopenSheetPicker() {
  // chip 点击重选：当前 selectedSource 必须是 sheet 形式才能重开
  const v = selectedSource.value
  if (!v.startsWith('workpaper:') || !v.includes('|')) return
  const tail = v.slice('workpaper:'.length)
  const [wpCode, sheetName] = tail.split('|', 2)
  sheetPickerCtx.value = { wpCode, sheetName }
  sheetPickerVisible.value = true
}

/** 💾 保存：三档可见范围的保存对话框（AQ-39；原先 ElMessageBox.prompt 只问名称、固定存私有） */
const templateConfig = computed<Record<string, unknown>>(() => {
  const config: Record<string, unknown> = {
    project_id: localProjectId.value,
    year: localYear.value,
    source: selectedSource.value,
    filter_text: filterText.value,
  }
  if (sheetCellRange.value) config.cell_range = sheetCellRange.value
  if (sheetPickerCtx.value.sheetName) config.sheet_name = sheetPickerCtx.value.sheetName
  // 排序随模板保存（后端 config_to_request 把 sort_field / sort_order 译成请求的 sort）；每页行数随模板保存（R9.4）
  if (sortState.value) Object.assign(config, { sort_field: sortState.value.field, sort_order: sortState.value.direction })
  config.page_size = pageSize.value
  const tq = templateQuery.value // 载入的模板条件 / 列：另存时一并保存，不丢
  if (tq) Object.assign(config, { conditions: tq.conditions, condition_logic: tq.logic, selected_columns: tq.columns })
  return config
})
const templateDescription = computed(() =>
  `${currentSourceLabel.value}${sheetCellRange.value ? ' / ' + sheetCellRange.value : ''}`)
function openSaveDialog() {
  if (!selectedSource.value) return
  saveDialogVisible.value = true
}

/** 载入 / 执行的模板说明（结果区上方）：执行时写明按模板执行；有弹窗不能编辑的条件 / 列时逐项写明 */
const templateNotice = computed(() => {
  const tq = templateQuery.value
  const name = templateRun.value?.name ?? tq?.name
  if (!name) return ''
  const head = templateRun.value ? `按模板「${name}」执行（服务端按模板重新鉴权，翻页沿用模板）` : `已载入模板「${name}」`
  const parts = [
    tq?.conditions.length ? `${tq.conditions.length} 条筛选条件（${tq.logic === 'or' ? '满足任一' : '全部满足'}）` : '',
    tq?.columns.length ? `${tq.columns.length} 列` : '',
  ].filter(Boolean)
  return parts.length ? `${head}：${parts.join('、')}随查询发送（弹窗内不能编辑，可在页面版编辑；关闭本提示即不再使用）` : head
})
function clearTemplateState() {
  templateQuery.value = null
  templateRun.value = null
}

/**
 * 「载入」/「执行」模板（R9.3 / R9.4，queryTemplateRestore）：还原数据源、排序、每页行数、底稿选区与本页筛选；条件与列
 * 弹窗不能编辑，照样随查询发送。执行 = 还原后立即经服务端模板执行端点查第 1 页。项目与年度用弹窗当前的（不取模板里存的）。
 */
async function applyTemplate(tpl: QueryTemplateItem, run: boolean) {
  const restored = restoreTemplateQuery(tpl)
  if (!restored) {
    ElMessage.warning('模板没有数据源，无法载入')
    return
  }
  clearTemplateState()
  selectedSource.value = restored.source
  await nextTick() // 换数据源的 watch 先清掉排序 / 选区，再还原模板里的
  sortState.value = restored.sort
  if (restored.pageSize) pageSize.value = restored.pageSize
  filterText.value = restored.filterText
  sheetCellRange.value = restored.cellRange
  if (restored.cellRange) sheetPickerVisible.value = false
  const conditions = toRequestConditions(restored.condition.conditions)
  if (conditions.length || restored.columns.length) {
    templateQuery.value = {
      name: tpl.name, source: restored.source, conditions, logic: restored.condition.logic, columns: restored.columns,
    }
  }
  if (!run) {
    ElMessage.success(`已载入模板「${tpl.name}」，点击「▶ 查询」执行`)
    return
  }
  templateRun.value = { id: tpl.id, name: tpl.name }
  await executeQuery(true, true)
}

// 操作列：打开权威页面 / 复制引用（底稿单元格列的链接也走这里：新标签打开并定位 ?sheet=&cell=，原先同标签 ?highlight=）
const rowLinks = useQueryRowLinks({
  source: () => lastRun.value.source,
  projectId: () => lastRun.value.projectId,
  year: () => lastRun.value.year,
  columns: () => resultColumns.value,
  templateType: () => resultMeta.value?.ref_context?.template_type ?? null,
  tableIndex: () => noteTableIndex.value,
})

// ─── 右键菜单：跳模板溯源 (Req 14 AC 2) ─────────────────────────────────────
const ctxMenuVisible = ref(false)
const ctxMenuPos = ref({ x: 0, y: 0 })
const ctxMenuRow = ref<any>(null)

function onRowContextMenu(row: any, _col: any, event: MouseEvent) {
  event.preventDefault()
  ctxMenuRow.value = row
  ctxMenuPos.value = { x: event.clientX, y: event.clientY }
  ctxMenuVisible.value = true
  // 点击其他地方关闭
  const closeMenu = () => {
    ctxMenuVisible.value = false
    document.removeEventListener('click', closeMenu)
  }
  setTimeout(() => document.addEventListener('click', closeMenu), 0)
}

async function onTraceToTemplate() {
  ctxMenuVisible.value = false
  const row = ctxMenuRow.value
  if (!row) return

  // 行属于本次结果（不按界面当前选的数据源）；URI 按 address-resolve 认的模块前缀生成（ADR-AQL-17）
  const uri = buildTraceUri(row, lastRun.value.source || selectedSource.value)
  if (!uri) {
    ElMessage.warning(RESOLVE_FAIL_MSG.noUri)
    return
  }

  try {
    const resp = await api.get('/api/custom-query/address-resolve', { params: { uri }, _silent: true } as any) as any
    // 未登记的底稿编码、调整分录 / 试算类结果（没有模板定义）：提示原因，不跳转（原先底稿表不存在即 500，AQ-17）
    if (!resp?.registered || !resp.route_path) {
      ElMessage.warning(resp?.module === 'workpaper' ? RESOLVE_FAIL_MSG.notRegistered : RESOLVE_FAIL_MSG.noTemplate)
      return
    }
    visible.value = false
    router.push({ path: resp.route_path, query: resp.route_query })
  } catch (err: unknown) {
    ElMessage.warning(queryErrorToast('模板溯源', describeQueryError(err)))
  }
}

/** 查询不可用的原因（按钮置灰并提示）；可查询时为空串 */
const queryBlockedReason = computed(() => {
  if (!selectedSource.value) return '请先选择数据源'
  if (!localProjectId.value && _sourceRequiresProject(selectedSource.value)) return '该数据源需先选择项目'
  if (!isKnownYear(localYear.value)) return '请选择审计年度'
  return ''
})
const canExport = computed(() => hasQueried.value && !queryError.value && resultColumns.value.length > 0
  && isKnownYear(lastRun.value.year))
const noteTables = computed<{ index: number; name: string; row_count: number }[]>(() =>
  (Array.isArray(resultMeta.value?.tables) ? resultMeta.value!.tables : []))

/** 请求里的旧筛选键（报表类型、合并底稿 sheet、底稿选区、附注第几张表） */
function requestFilters(source: string): Record<string, unknown> {
  const filters: Record<string, unknown> = {}
  // 只给报表叶子带报表类型；报表行次配置（report_lines）也以 report_ 开头，带上即按 report_type='lines' 过滤得 0 行
  if (reportTypeOfSource(source)) filters.report_type = filterReportType.value
  if (source.startsWith('ws_')) filters.sheet_key = source.replace('ws_', '')
  if (sheetCellRange.value) filters.cell_range = sheetCellRange.value
  if (source.startsWith('disclosure_note:') && noteTableIndex.value > 0) filters.table_index = noteTableIndex.value
  return filters
}

/**
 * 执行查询（resetPage = 新条件从第 1 页开始；翻页时为 false）。viaTemplate = 「执行模板」：经服务端模板执行端点
 * （重新鉴权、按模板配置取数，R9.3）；之后翻页仍走它，其余从第 1 页起的查询（手动、排序、切表）回到普通查询。
 */
async function executeQuery(resetPage = true, viaTemplate = false) {
  if (resetPage && !viaTemplate) templateRun.value = null
  if (!localProjectId.value && _sourceRequiresProject(selectedSource.value)) {
    ElMessage.warning('该数据源需先选择项目（模板浏览模式仅支持报表/附注/底稿模板）')
    return
  }
  // 查询端点 year 必填：年度只取路由 / 项目审计年度，都没有就要求选择（不用日历年、不静默查别的年度）
  if (!isKnownYear(localYear.value)) {
    ElMessage.warning('未设置审计年度，请选择审计年度后再查询')
    return
  }
  if (resetPage) page.value = 1
  hasQueried.value = true
  loading.value = true
  queryError.value = null
  const source = selectedSource.value
  const tq = templateQuery.value
  const run: QueryRun = {
    source, projectId: localProjectId.value, year: localYear.value, sort: sortState.value ? [sortState.value] : [],
    filters: requestFilters(source), projectLabel: currentProjectLabel.value, sourceLabel: currentSourceLabel.value,
    extra: tq ? { conditions: tq.conditions, condition_logic: tq.logic, ...(tq.columns.length ? { columns: tq.columns } : {}) } : {},
  }
  const tplRun = templateRun.value
  const offset = (page.value - 1) * pageSize.value
  try {
    // 调用方自管错误（_silent）：失败在结果区显示后端原因与追踪号，确定性错误不自动重试（R11.1）；
    // 原先 validateStatus: s < 600 把 4xx / 5xx 的错误体当数据，落到「暂无该数据源记录」（AQ-09）
    const data = tplRun
      ? await api.post(P_cq.templateExecute(tplRun.id), {
        project_id: run.projectId, year: run.year, limit: pageSize.value, offset,
      }, { _silent: true } as any) as any
      : await api.post('/api/custom-query/execute', buildBusinessPayload({
        projectId: run.projectId, year: run.year, source, filters: run.filters, ...run.extra,
        ...(run.sort.length ? { sort: run.sort } : {}),
        limit: pageSize.value, offset,
      }), { _silent: true } as any) as any
    const cols: unknown[] = Array.isArray(data?.columns) ? data.columns : []
    resultRows.value = Array.isArray(data?.rows) ? data.rows : []
    resultColumns.value = cols.length
      ? cols.map((c: any) => (typeof c === 'string' ? c : String(c?.key ?? ''))).filter(Boolean)
      : (resultRows.value.length ? Object.keys(resultRows.value[0]).filter((k) => !k.startsWith('_')) : [])
    objectColumnTypes.value = Object.fromEntries(cols.filter((c: any) => c && typeof c === 'object' && c.key && c.dtype)
      .map((c: any) => [String(c.key), String(c.dtype)]))
    resultTotal.value = typeof data?.total === 'number' ? data.total : resultRows.value.length
    resultMeta.value = data?.meta && typeof data.meta === 'object' ? data.meta : null
    lastRun.value = run
    pushQueryHistory()
    void rowLinks.validateRefs(resultRows.value)
  } catch (err: unknown) {
    resultRows.value = []
    resultColumns.value = []
    resultTotal.value = 0
    resultMeta.value = null
    rowLinks.reset()
    queryError.value = describeQueryError(err)
  } finally { loading.value = false }
}

function onPageChange() { void executeQuery(false) }

function onNoteTableChange(index: number) {
  noteTableIndex.value = Number(index) || 0
  void executeQuery()
}

function copyResult() {
  if (!resultRows.value.length) { ElMessage.warning('无数据'); return }
  const headers = resultColumns.value.map(c => columnLabel(c))
  const dataRows = filteredRows.value.map(r => resultColumns.value.map(c => r[c] ?? ''))
  const text = [headers.join('\t'), ...dataRows.map(r => r.join('\t'))].join('\n')
  const html = `<table border="1"><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>${dataRows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([text], { type: 'text/plain' }) })])
    ElMessage.success(`已复制 ${filteredRows.value.length} 行`)
  } catch { navigator.clipboard?.writeText(text); ElMessage.success('已复制为文本') }
}

function exportBaseName() {
  const run = lastRun.value
  const projName = (run.projectLabel || '查询').replace(/[\\/:*?"<>|]/g, '_')
  const srcName = (run.sourceLabel || run.source).replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}\s]/gu, '')
  return sanitizeExportName(`${projName}_${srcName}_${run.year ?? ''}`)
}

function onExportCommand(command: string) {
  if (command === 'all') void exportAll()
  else void exportCurrentPage()
}

/** 导出当前页（前端生成；表头按本次结果的数据源取中文列名，R6.6） */
async function exportCurrentPage() {
  if (!resultRows.value.length) { ElMessage.warning('无数据'); return }
  await exportQueryResultToXlsx({
    columns: resultColumns.value,
    rows: filteredRows.value,
    labelFn: (key) => columnLabel(key),
    fileName: exportBaseName(),
  })
  ElMessage.success('已导出当前页')
}

/** 导出全部（服务端按本次查询导出全量结果，表头为界面所见中文列名；R8.1） */
async function exportAll() {
  const run = lastRun.value
  if (!isKnownYear(run.year)) return
  exporting.value = true
  try {
    const payload = buildBusinessPayload({
      projectId: run.projectId, year: run.year, source: run.source, filters: run.filters, ...run.extra,
      ...(run.sort.length ? { sort: run.sort } : {}),
    })
    const headers = Object.fromEntries(resultColumns.value.map((c) => [c, columnLabel(c)]))
    await exportAllQueryRows(buildExportBody(payload, headers, exportBaseName()))
    ElMessage.success(`已导出全部结果（共 ${resultTotal.value} 行）`)
  } catch (e: unknown) {
    ElMessage.warning(queryErrorToast('导出全部', describeQueryError(await readBlobErrorBody(e))))
  } finally { exporting.value = false }
}

// 指标树：带项目与审计年度加载（附注分支按该项目该年度章节），缓存键含附注版本（queryIndicatorCache，R10.4）
async function loadIndicators(pid: string | undefined) {
  try {
    indicatorTree.value = await loadIndicatorTree({ projectId: pid, year: localYear.value, shape: 'full' })
  } catch {
    // 兜底：用 STATIC_SOURCES 重建一棵简易树（按 parentKey 分组）
    const grouped: Record<string, any[]> = {}
    for (const s of STATIC_SOURCES) {
      (grouped[s.parentKey] ||= []).push({ key: s.key, label: s.label })
    }
    indicatorTree.value = Object.entries(grouped).map(([k, children]) => ({ key: k, label: k, children }))
  }
}

// 弹窗打开、项目或年度变了 → 重新取树（命中缓存时只发一次骨架探测）
watch([visible, localProjectId, localYear], ([open]) => {
  if (open) void loadIndicators(localProjectId.value || undefined)
}, { immediate: true })
// 加载查询历史（localStorage 持久）
loadQueryHistory()

// ─── 入口预选（R10.3 / R10.5）：每次打开都套用 initialSource（原先只在它变化时套用：同一页再开一次、或用户换过源后再开，
// 预选不生效）；数据源立即选中，树里的高亮与展开等树加载完再做（原先连选中也等树，树取不到时预选整个丢失）──
watch(() => [visible.value, props.initialSource, props.initialNotice] as const, ([open, source, notice]) => {
  if (!open) { entryNotice.value = null; return }
  entryNotice.value = source && notice ? { source, text: notice } : null
  if (source) revealSource(source)
}, { immediate: true })

function revealSource(source: string) {
  selectedSource.value = source
  const doReveal = () => {
    // 在树中查找匹配节点并展开 + 选中
    if (treeRef.value) {
      treeRef.value.setCurrentKey(source)
      // 尝试展开祖先节点
      const node = treeRef.value.getNode(source)
      if (node) {
        let parent = node.parent
        while (parent && parent.key) {
          parent.expanded = true
          parent = parent.parent
        }
        // scroll into view
        setTimeout(() => {
          const el = treeRef.value?.$el?.querySelector('.is-current')
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }, 100)
      }
    }
  }
  if (indicatorTree.value.length) {
    doReveal()
  } else {
    // 树尚未加载，等加载完成后 reveal
    const stop = watch(indicatorTree, (tree) => {
      if (tree.length) {
        stop()
        setTimeout(doReveal, 50)
      }
    })
  }
}
</script>

<style scoped>
.gt-cq-container { display: flex; gap: 12px; height: calc(100vh - 140px); }
.gt-cq-sidebar { width: 200px; flex-shrink: 0; border-right: 1px solid var(--gt-color-border-purple); padding-right: 8px; overflow-y: auto; }
.gt-cq-sidebar-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary); margin-bottom: 8px; display: flex; align-items: center; }
.gt-cq-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.gt-cq-filter-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.gt-cq-context-chip {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  padding: 4px 0;
}
.gt-cq-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.gt-cq-dialog-title {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
}
.gt-cq-dialog-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.gt-cq-footer { padding: 6px 0; }
.gt-cq-transposed { overflow: auto; flex: 1; }

/* 树节点：灰度（项目裁剪后不存在的底稿）*/
.gt-cq-tree-node { font-size: var(--gt-font-size-xs); }
.gt-cq-tree-node-disabled {
  color: var(--gt-color-text-tertiary, #b0b0b0) !important;
  text-decoration: line-through;
  font-style: italic;
  cursor: not-allowed;
}

/* 结果表格 cell_ref 列穿透跳转链接 */
.gt-cq-cell-ref-link {
  color: var(--gt-color-primary);
  cursor: pointer;
  text-decoration: underline;
  font-family: 'Consolas', 'Monaco', monospace;
}
.gt-cq-cell-ref-link:hover {
  color: var(--gt-color-primary-dark, #5a2db8);
  text-decoration: none;
  background: rgba(124, 58, 237, 0.08);
  padding: 0 4px;
  border-radius: 3px;
}

/* 右键菜单 (Req 14 AC 2) */
.gt-cq-ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-lighter, #e4e7ed);
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  padding: 4px 0;
  min-width: 140px;
}
.gt-cq-ctx-menu-item {
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.gt-cq-ctx-menu-item:hover {
  background: var(--gt-color-primary-bg, #f5f0ff);
  color: var(--gt-color-primary, #7c3aed);
}
</style>
