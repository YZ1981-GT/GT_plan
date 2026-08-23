<!--
  CustomQueryTab.vue — 自定义查询 Tab [template-library-coordination Sprint 6 Tasks 6.4-6.6]

  需求 22.1-22.9：
  - 可视化查询构建器：数据源选择 + 多条件筛选 + 字段选择
  - 8+ 数据源（底稿/试算表/调整分录/科目余额/序时账/附注/报表行次/工时）
  - 条件类型：等于/包含/大于/小于/范围/为空/不为空
  - 多条件 AND/OR 组合
  - 结果 el-table 展示 + Excel 导出（前端 xlsx）
  - 模板保存/加载（私有 + 全局共享）

  依赖：
  - GET /api/custom-query/indicators       数据源指标库
  - POST /api/custom-query/execute         执行查询
  - GET /api/custom-query/templates        列出模板
  - POST /api/custom-query/templates       保存模板
  - DELETE /api/custom-query/templates/:id 删除模板
-->
<template>
  <div class="gt-cqt">
    <!-- Capability_Guidance：两套入口能力差异说明（R11.5） -->
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
          仅限 <strong>管理员 / 经理 / 合伙人</strong>：提供白名单数据表的可视化条件、SQL 预览、聚合与关联查询。
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
            controls-position="right"
            style="width: 120px"
          />
        </el-form-item>
        <el-form-item label="数据源">
          <el-select
            v-model="formCtx.source"
            filterable
            placeholder="选择数据源"
            style="width: 220px"
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
        <el-button size="small" @click="loadTemplates" :loading="loadingTemplates">
          <el-icon style="margin-right: 4px"><Folder /></el-icon>
          我的模板 ({{ templates.length }})
        </el-button>
        <el-button size="small" type="primary" plain @click="onSaveTemplate">
          <el-icon style="margin-right: 4px"><DocumentAdd /></el-icon>
          保存为模板
        </el-button>
        <!-- 高级构建器入口：角色不足时禁用（可见不可点）+ 原因提示（R11.6） -->
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
          <div class="gt-cqt-panel-header">
            <span>条件筛选</span>
            <el-radio-group v-model="formCtx.condition_logic" size="small">
              <el-radio-button label="AND">全部满足 (AND)</el-radio-button>
              <el-radio-button label="OR">任一满足 (OR)</el-radio-button>
            </el-radio-group>
          </div>
          <div class="gt-cqt-conditions">
            <div
              v-for="(cond, idx) in conditions"
              :key="idx"
              class="gt-cqt-cond-row"
            >
              <el-select
                v-model="cond.field"
                size="small"
                placeholder="字段"
                style="width: 150px"
              >
                <el-option
                  v-for="f in availableColumns"
                  :key="f"
                  :label="f"
                  :value="f"
                />
              </el-select>
              <el-select
                v-model="cond.operator"
                size="small"
                placeholder="操作符"
                style="width: 110px"
              >
                <el-option
                  v-for="op in operatorOptions"
                  :key="op.value"
                  :label="op.label"
                  :value="op.value"
                />
              </el-select>
              <el-input
                v-if="!['is_null', 'is_not_null'].includes(cond.operator)"
                v-model="cond.value"
                size="small"
                :placeholder="cond.operator === 'between' ? '起,止' : '值'"
                style="flex: 1; min-width: 0"
              />
              <el-button
                size="small"
                link
                type="danger"
                @click="onRemoveCondition(idx)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <el-button
              size="small"
              link
              type="primary"
              @click="onAddCondition"
            >
              <el-icon style="margin-right: 4px"><Plus /></el-icon>
              添加条件
            </el-button>
          </div>
        </div>

        <div class="gt-cqt-panel" style="margin-top: 12px">
          <div class="gt-cqt-panel-header">
            <span>字段选择 ({{ selectedColumns.length }} / {{ availableColumns.length }})</span>
            <el-button size="small" link @click="toggleAllColumns">
              {{ selectedColumns.length === availableColumns.length ? '取消全选' : '全选' }}
            </el-button>
          </div>
          <el-checkbox-group v-model="selectedColumns" class="gt-cqt-fields">
            <el-checkbox
              v-for="col in availableColumns"
              :key="col"
              :label="col"
              :value="col"
              size="small"
            >
              {{ col }}
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <!-- ACNR 选字段树（复用 useAcnr，与公式选址同一棵树） -->
        <div class="gt-cqt-panel" style="margin-top: 12px">
          <CustomQueryFieldPicker v-model="acnrFieldIds" />
        </div>

        <div class="gt-cqt-panel-actions">
          <el-button
            type="primary"
            :loading="executing"
            @click="onExecute"
            :disabled="!formCtx.source || !formCtx.project_id"
            style="width: 100%"
          >
            <el-icon style="margin-right: 4px"><Search /></el-icon>
            执行查询
          </el-button>
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
            <el-button
              size="small"
              :disabled="result.rows.length === 0"
              @click="onExportExcel"
            >
              <el-icon style="margin-right: 4px"><Download /></el-icon>
              导出 Excel
            </el-button>
          </div>
        </div>

        <div class="gt-cqt-result-body">
          <el-empty
            v-if="!executing && result.rows.length === 0 && !result.error"
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
          <el-alert
            v-if="result.error"
            type="error"
            :closable="false"
            show-icon
          >
            <template #title>查询失败</template>
            <template #default>
              <pre class="gt-cqt-error">{{ result.error }}</pre>
            </template>
          </el-alert>
          <el-table
            v-if="result.rows.length > 0"
            v-loading="executing"
            :data="result.rows"
            size="small"
            border
            stripe
            max-height="600"
            :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
            class="gt-cqt-table"
          >
            <el-table-column
              v-for="col in displayColumns"
              :key="col.key"
              :prop="col.key"
              :label="col.title"
              min-width="140"
              :show-overflow-tooltip="!col.drillable"
            >
              <template #default="{ row }">
                <!-- 可下钻列：显示值 + GtIndexChip（value=addr_id，经 resolveIndex 拿 jump_route 下钻，R4.3） -->
                <span
                  v-if="col.drillable && cellAddrId(row, col)"
                  class="gt-cqt-drill-cell"
                >
                  <span :class="{ 'gt-amt': isNumericValue(row[col.key]) }">
                    {{ formatCellValue(row[col.key]) }}
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
                <span v-else :class="{ 'gt-amt': isNumericValue(row[col.key]) }">
                  {{ formatCellValue(row[col.key]) }}
                </span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 真实分页（R11.4）：total 由后端在分页前计算，不再是「本页行数」 -->
          <div v-if="showPagination" class="gt-cqt-pagination">
            <!-- v-model 双向绑定而非单向 :current-page：查询期间 result 被重置会让
                 showPagination 短暂为 false、组件销毁重建，单向 prop 下内部 currentPage
                 会回落到 1 —— 浏览器实测表现为「数据已是第 2 页而页码高亮第 1 页」。 -->
            <el-pagination
              v-model:current-page="page"
              v-model:page-size="pageSize"
              :total="result.total"
              :page-sizes="[50, 100, 200, 500]"
              layout="total, sizes, prev, pager, next, jumper"
              size="small"
              background
              @current-change="onPageChange"
              @size-change="onPageSizeChange"
            />
          </div>
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

    <!-- 模板列表对话框 -->
    <el-dialog
      v-model="templatesDialogVisible"
      title="查询模板"
      width="720px"
    >
      <el-table :data="templates" size="small" border>
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="data_source" label="数据源" width="140" />
        <el-table-column label="可见范围" width="100" align="center">
          <template #default="{ row }">
            <!-- legacy `global` 归一显示为 canonical「公开」（R11.5） -->
            <el-tag
              :type="normalizeTemplateScope(row.scope) === 'private' ? 'info' : 'warning'"
              size="small"
              effect="plain"
              round
            >
              {{ templateScopeLabel(row.scope) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="160">
          <template #default="{ row }">
            <span class="gt-cqt-em">
              {{ row.updated_at ? new Date(row.updated_at).toLocaleString() : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="onLoadTemplate(row)">
              加载
            </el-button>
            <el-button
              v-if="row.is_owner"
              size="small"
              link
              type="danger"
              @click="onDeleteTemplate(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 保存模板对话框 -->
    <el-dialog v-model="saveDialogVisible" title="保存查询模板" width="480px">
      <el-form
        ref="saveFormRef"
        :model="saveForm"
        :rules="saveRules"
        label-width="80px"
        size="small"
      >
        <el-form-item label="名称" prop="name" required>
          <el-input v-model="saveForm.name" placeholder="如 应收账款明细查询" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="saveForm.description"
            type="textarea"
            :rows="2"
            placeholder="可选"
          />
        </el-form-item>
        <el-form-item label="可见范围">
          <el-radio-group v-model="saveForm.scope">
            <el-radio label="private">{{ templateScopeLabel('private') }}</el-radio>
            <el-radio label="project" :disabled="!canShareTemplates">
              {{ templateScopeLabel('project') }}
            </el-radio>
            <el-radio label="public" :disabled="!canShareTemplates">
              {{ templateScopeLabel('public') }}
            </el-radio>
          </el-radio-group>
          <div v-if="!canShareTemplates" class="gt-cqt-scope-hint">
            当前无可编辑项目，仅可保存为「{{ templateScopeLabel('private') }}」
          </div>
        </el-form-item>
        <el-form-item v-if="saveForm.scope === 'project'" label="分享项目">
          <el-select
            v-model="saveForm.shared_project_ids"
            multiple
            filterable
            placeholder="选择可编辑的项目"
            style="width: 100%"
          >
            <el-option
              v-for="p in projectList.filter((item) => item.can_edit)"
              :key="p.id"
              :label="`${p.code || ''} ${p.name || p.id}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveDialogVisible = false" size="small">取消</el-button>
        <el-button
          type="primary"
          size="small"
          :loading="savingTemplate"
          :disabled="!canSaveTemplate"
          @click="onConfirmSaveTemplate"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 高级构建器弹窗（仅 admin/manager/partner 可打开，R11.6） -->
    <el-dialog
      v-model="builderDialogVisible"
      title="高级查询构建器"
      width="90%"
      top="5vh"
      class="gt-cqt-builder-dialog"
      destroy-on-close
    >
      <AdvancedQueryBuilder embedded />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Search, Plus, Delete, Download, Folder, DocumentAdd, MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
// http（axios 实例）而非 api 代理：需要读 X-Indicators-Schema-Version 响应头做缓存键
import http from '@/utils/http'
import { customQuery as P_cq, projects as P_proj } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { resolveColumnLabel } from '@/components/query/queryColumnLabels'
import { exportQueryResultToXlsx } from '@/components/query/queryExport'
import { useQueryBuilderAccess } from '@/composables/useQueryBuilderAccess'
import CustomQueryFieldPicker from '@/components/custom-query/CustomQueryFieldPicker.vue'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import {
  useAcnrDrill,
  normalizeColumns,
  cellAddrId,
  addrIdToIndexRef,
  type QueryColumnMeta,
} from '@/composables/useAcnrDrill'

interface IndicatorChild {
  key: string
  label: string
  columns: string[]
}
interface IndicatorGroup {
  key: string
  label: string
  icon?: string
  children: IndicatorChild[]
}
interface QueryCondition {
  field: string
  operator: 'eq' | 'contains' | 'gt' | 'lt' | 'between' | 'is_null' | 'is_not_null'
  value: string
}
interface QueryResult {
  rows: any[]
  // 后端可能返回 ColumnMeta[]（含 addr_id/drillable）或 legacy string[]，统一由 normalizeColumns 归一
  columns: Array<string | Record<string, any>>
  /** 分页前的真实总行数（R4.1）；改造前它等于本页行数，无法据此翻页 */
  total: number
  limit?: number
  offset?: number
  /** 非致命提示（取数达上限、全局配置表未按项目过滤等） */
  warnings?: string[]
  error?: string
}
interface ProjectItem {
  id: string
  code?: string
  name?: string
  /** 当前用户对该项目是否有编辑权限（决定能否作为模板分享目标） */
  can_edit?: boolean
  /**
   * 项目审计年度（`GET /api/projects` 由 `resolve_project_audit_year` 派生下发）。
   * 用于把「年度」输入框默认到**有数据的那一年**，而不是日历当年。
   */
  audit_year?: number | null
}
interface TemplateItem {
  id: string
  name: string
  description?: string | null
  data_source: string
  config: any
  scope: 'private' | 'global'
  created_by: string
  is_owner: boolean
  created_at: string
  updated_at: string
}

// ─── 状态 ───
const indicatorTree = ref<IndicatorGroup[]>([])
const projectList = ref<ProjectItem[]>([])
/** 审计年度兜底：审计做上一年度报表，日历当年在四表里通常没有数据。 */
function defaultAuditYear(): number {
  return new Date().getFullYear() - 1
}

const formCtx = ref({
  project_id: '',
  year: defaultAuditYear(),
  source: '',
  condition_logic: 'AND' as 'AND' | 'OR',
})
const conditions = ref<QueryCondition[]>([])
const selectedColumns = ref<string[]>([])
const availableColumns = ref<string[]>([])
// ACNR 选字段：选中 cell 节点的 addr_id 列表（R2.4，作查询字段标识）
const acnrFieldIds = ref<string[]>([])
const result = ref<QueryResult>({ rows: [], columns: [], total: 0 })
const executing = ref(false)
/** 0 行时的空态说明（含实际使用的年度，便于自查年度是否选错） */
const emptyHint = ref('')
// 分页状态（R11.4）：total 现在是后端在分页前算的真实行数，可据此翻页
const page = ref(1)
const pageSize = ref(100)
// 仅当确有多页时才显示分页条，避免单页结果下多出一排无用控件
const showPagination = computed(
  () => (result.value.total ?? 0) > pageSize.value || page.value > 1
)

// ─── 高级构建器入口权限门禁（R11.1/R11.2，与后端 query_builder.py RBAC 一致） ───
// 判据收敛到 useQueryBuilderAccess（与后端 _QUERY_BUILDER_ROLES 同源）。
// 此前用 canDo('edit','project_settings') 是资源级矩阵判据，与后端的角色白名单
// 判据不同源，两侧会漂移成「按钮可点但必 403」或「按钮禁用而其实有权」。
const { currentRole, canUseBuilder, builderDisabledReason } = useQueryBuilderAccess()
const builderDialogVisible = ref(false)

function onOpenBuilder() {
  // 双保险：角色不足时即便按钮被绕过也不打开构建器（R11.6）
  if (!canUseBuilder.value) return
  builderDialogVisible.value = true
}

// 模板
const templates = ref<TemplateItem[]>([])
const templatesDialogVisible = ref(false)
const saveDialogVisible = ref(false)
const loadingTemplates = ref(false)
const savingTemplate = ref(false)
type TemplateScope = 'private' | 'team' | 'project' | 'public'

const saveForm = ref({
  name: '',
  description: '',
  scope: 'private' as TemplateScope,
  shared_project_ids: [] as string[],
})

const saveRules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
}

// ─── 模板作用域治理（R11.5 / R11.6）─────────────────────────────────────────
// 与后端 `TemplateScopeAdapter` 同源：legacy `global` / `personal` 只作为**输入**
// 接受，展示恒为 canonical。前端不再各自维护别名表。
const TEMPLATE_SCOPE_ALIASES: Record<string, TemplateScope> = {
  global: 'public',
  personal: 'private',
}
const TEMPLATE_SCOPE_LABELS: Record<TemplateScope, string> = {
  private: '仅我可见',
  team: '团队共享',
  project: '指定项目共享',
  public: '公开',
}
/** 需要分享授权的 scope（后端会对每个目标项目逐个鉴权） */
const SHARE_REQUIRED_SCOPES: TemplateScope[] = ['team', 'project', 'public']

function normalizeTemplateScope(scope?: string | null): string {
  const raw = String(scope ?? '').trim().toLowerCase()
  return TEMPLATE_SCOPE_ALIASES[raw] ?? raw
}

function templateScopeLabel(scope?: string | null): string {
  const canonical = normalizeTemplateScope(scope) as TemplateScope
  return TEMPLATE_SCOPE_LABELS[canonical] ?? '未知'
}

/** 可作为分享目标的项目 —— 判据与后端 `require_project_access("edit")` 同源 */
const editableProjectIds = computed(
  () => new Set(projectList.value.filter((p) => p.can_edit).map((p) => String(p.id)))
)

/** 是否具备分享能力：存在至少一个可编辑项目（无则 fail-closed 只能存私人模板） */
const canShareTemplates = computed(() => editableProjectIds.value.size > 0)

/** 提交用的分享目标：去重 + 仅保留可编辑项目（越权目标在提交前就被剔除） */
function resolveSharedProjectIds(): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of saveForm.value.shared_project_ids || []) {
    const id = String(raw)
    if (seen.has(id) || !editableProjectIds.value.has(id)) continue
    seen.add(id)
    out.push(id)
  }
  return out
}

const canSaveTemplate = computed(() => {
  if (!saveForm.value.name.trim()) return false
  const scope = normalizeTemplateScope(saveForm.value.scope) as TemplateScope
  if (SHARE_REQUIRED_SCOPES.includes(scope) && !canShareTemplates.value) return false
  if (scope === 'project' && resolveSharedProjectIds().length === 0) return false
  return true
})

const operatorOptions = [
  { label: '等于 (=)', value: 'eq' },
  { label: '包含 (LIKE)', value: 'contains' },
  { label: '大于 (>)', value: 'gt' },
  { label: '小于 (<)', value: 'lt' },
  { label: '范围 (BETWEEN)', value: 'between' },
  { label: '为空 (IS NULL)', value: 'is_null' },
  { label: '不为空 (IS NOT NULL)', value: 'is_not_null' },
]

// 结果列下钻（R4.2/R4.4/R4.6/R4.7）：以当前查询上下文 project_id 解析 jump_route
const { drill } = useAcnrDrill(() => formCtx.value.project_id)

// 当前已展示列（结果优先用 result.columns，回退到用户选择）——归一为 QueryColumnMeta
const displayColumns = computed<QueryColumnMeta[]>(() => {
  const cols = normalizeColumns(result.value.columns).map(c => ({ ...c, title: resolveColumnLabel(c.key, c.title) }))
  if (cols.length > 0) {
    return selectedColumns.value.length > 0
      ? cols.filter((c) => selectedColumns.value.includes(c.key))
      : cols
  }
  return selectedColumns.value.map((k) => ({
    key: k,
    title: resolveColumnLabel(k),
    addrId: null,
    drillable: false,
    dtype: 'text',
  }))
})

function isNumericValue(v: any): boolean {
  if (typeof v === 'number') return true
  if (typeof v === 'string' && v.length > 0) {
    return /^-?\d+(\.\d+)?$/.test(v.trim())
  }
  return false
}

function formatCellValue(v: any): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString()
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// ─── 数据加载 ───
// 指标树缓存（R12.4）：与 CustomQueryDialog 同一套键规则，两处共享同一份缓存。
// 改造前本组件**完全无缓存**，每次 onMounted 都全量拉取（实测约 578,057 字符 /
// 3,391ms），而本 Tab 每次切回都会重新挂载。
const INDICATOR_CACHE_KEY_PREFIX = 'gt:custom-query:indicators:'
const INDICATOR_SCHEMA_HEADER = 'x-indicators-schema-version'

async function loadIndicators() {
  try {
    // 骨架探测单独 try：它只是缓存优化，失败不应阻断指标树加载
    let schemaVersion = 'unknown'
    try {
      const probe = await http.get(`${P_cq.indicators}?depth=1`, { _silent: true } as any)
      schemaVersion = (probe?.headers?.[INDICATOR_SCHEMA_HEADER] as string) || 'unknown'
      const cached = sessionStorage.getItem(
        `${INDICATOR_CACHE_KEY_PREFIX}${schemaVersion}:no-project`
      )
      if (cached) {
        indicatorTree.value = JSON.parse(cached)
        return
      }
    } catch { /* 探测失败 → 继续走全量拉取 */ }
    const cacheKey = `${INDICATOR_CACHE_KEY_PREFIX}${schemaVersion}:no-project`
    // 未命中 → 拉全量：本组件用 el-select + el-option-group 呈现，需要完整叶子集合
    const data = await api.get<IndicatorGroup[]>(P_cq.indicators)
    if (Array.isArray(data)) {
      indicatorTree.value = data
      try { sessionStorage.setItem(cacheKey, JSON.stringify(data)) } catch { /* ignore */ }
    }
  } catch (e: any) {
    handleApiError(e, '加载查询指标库')
  }
}

async function loadProjects() {
  try {
    const data = await api.get<any>(P_proj.list)
    const list = Array.isArray(data) ? data : (data?.items || [])
    projectList.value = list.map((p: any) => ({
      id: p.id,
      can_edit: p.can_edit ?? p.canEdit ?? false,
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
 * 把「年度」对齐到所选项目的审计年度。
 *
 * 为什么需要：年度输入框原来固定初始化为 `new Date().getFullYear()`（日历当年），
 * 而审计做的是**上一年度**报表 —— 2026 年打开页面默认查 2026，四表里只有 2025 的
 * 数据，于是任何查询都返回 0 行，且页面不提示原因，看起来像功能坏了。
 *
 * 真源是后端 `resolve_project_audit_year`（`GET /api/projects` 下发 `audit_year`），
 * 拿不到时退回 `当年 - 1`（与平台其余十余处视图同一约定），不再用日历当年。
 */
function syncYearToProject(projectId: string) {
  const proj = projectList.value.find((p) => String(p.id) === String(projectId))
  formCtx.value.year = proj?.audit_year ?? defaultAuditYear()
}

function onProjectChange(projectId: string) {
  syncYearToProject(projectId)
}

function onSourceChange() {
  // 切换数据源时重置条件和字段
  conditions.value = []
  for (const grp of indicatorTree.value) {
    const child = grp.children.find((c) => c.key === formCtx.value.source)
    if (child) {
      availableColumns.value = [...child.columns]
      selectedColumns.value = [...child.columns]
      return
    }
  }
  availableColumns.value = []
  selectedColumns.value = []
}

function toggleAllColumns() {
  if (selectedColumns.value.length === availableColumns.value.length) {
    selectedColumns.value = []
  } else {
    selectedColumns.value = [...availableColumns.value]
  }
}

function onAddCondition() {
  conditions.value.push({
    field: availableColumns.value[0] || '',
    operator: 'eq',
    value: '',
  })
}

function onRemoveCondition(idx: number) {
  conditions.value.splice(idx, 1)
}

// ─── 执行查询 ───
function buildFilters(): Record<string, any> {
  // 条件转换为后端 filters 格式（简化为字段→值映射，兼容当前后端按字段名识别）
  const out: Record<string, any> = {}
  for (const c of conditions.value) {
    if (!c.field) continue
    if (c.operator === 'is_null') {
      out[`${c.field}__is_null`] = true
    } else if (c.operator === 'is_not_null') {
      out[`${c.field}__is_not_null`] = true
    } else if (c.operator === 'between') {
      const parts = (c.value || '').split(/[,，]/).map((s) => s.trim())
      if (parts.length === 2) {
        out[`${c.field}_from`] = parts[0]
        out[`${c.field}_to`] = parts[1]
      }
    } else if (c.operator === 'contains') {
      out[c.field] = c.value
    } else if (c.operator === 'gt') {
      out[`${c.field}_min`] = c.value
    } else if (c.operator === 'lt') {
      out[`${c.field}_max`] = c.value
    } else {
      out[c.field] = c.value
    }
  }
  // 后端期望的常用字段
  if (formCtx.value.source === 'report' || formCtx.value.source.startsWith('report_')) {
    if (formCtx.value.source.startsWith('report_')) {
      out.report_type = formCtx.value.source.replace('report_', '')
    }
  }
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
  // 新条件从第 1 页开始；翻页时由 onPageChange 保持页码
  if (!keepPage) page.value = 1
  executing.value = true
  if (keepPage) {
    // 翻页：保留 total（分页条据此渲染），只清当前页行。
    // 若此处把 total 归零，showPagination 会瞬间变 false 使分页条销毁重建 ——
    // 既有视觉闪烁，也会丢掉组件内部页码状态。
    result.value = { ...result.value, rows: [] }
  } else {
    result.value = { rows: [], columns: [], total: 0 }
  }
  try {
    const data = await api.post<QueryResult>(P_cq.execute, {
      project_id: formCtx.value.project_id,
      year: formCtx.value.year,
      source: formCtx.value.source,
      filters: buildFilters(),
      columns: selectedColumns.value,
      // ACNR 选字段：以 addr_id 作为跨模块查询字段标识（R2.4）
      acnr_targets: acnrFieldIds.value,
      limit: pageSize.value,
      // 真实分页（R11.4）：改造前这里恒传 0 且后端把 offset 声明后从不使用，
      // 业务视图实际只有第 1 页。
      offset: (page.value - 1) * pageSize.value,
    })
    if (data) {
      result.value = data
      if (data.error) {
        ElMessage.warning('查询执行返回错误')
      } else if ((data.total ?? 0) === 0) {
        // 0 行必须可诊断：年度对不上是最常见原因（四表按年度分区存），
        // 静默返回空结果会让人以为功能坏了。把实际用的年度写进提示。
        emptyHint.value = `年度 ${formCtx.value.year} 下没有匹配数据`
        ElMessage.info(`查询完成，0 条 —— 当前年度为 ${formCtx.value.year}，请确认年度是否正确`)
      } else {
        emptyHint.value = ''
        ElMessage.success(`查询完成，本页 ${data.rows?.length || 0} 条 / 共 ${data.total ?? 0} 条`)
      }
    }
  } catch (e: any) {
    handleApiError(e, '执行查询')
    result.value = { rows: [], columns: [], total: 0, error: String(e?.message || e) }
  } finally {
    executing.value = false
  }
}

// ─── 分页（R11.4）─────────────────────────────────────────────────────────
function onPageChange(next: number) {
  page.value = next
  void onExecute(true)
}

function onPageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  void onExecute(true)
}

// ─── 导出 Excel（前端 xlsx） ───
async function onExportExcel() {
  if (result.value.rows.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    const cols = displayColumns.value
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    await exportQueryResultToXlsx({
      columns: cols.map(c => c.key),
      rows: result.value.rows,
      labelFn: (key) => resolveColumnLabel(key, cols.find(c => c.key === key)?.title),
      fileName: `高级查询_${formCtx.value.source}_${ts}`,
    })
    ElMessage.success('已导出')
  } catch (e: any) {
    handleApiError(e, '导出 Excel')
  }
}

// ─── 模板管理 ───
async function loadTemplates() {
  loadingTemplates.value = true
  try {
    const data = await api.get<{ templates: TemplateItem[]; total: number }>(P_cq.templates)
    templates.value = data?.templates || []
    templatesDialogVisible.value = true
  } catch (e: any) {
    handleApiError(e, '加载查询模板列表')
  } finally {
    loadingTemplates.value = false
  }
}

function onSaveTemplate() {
  if (!formCtx.value.source) {
    ElMessage.warning('请先选择数据源后再保存')
    return
  }
  saveForm.value.name = ''
  saveForm.value.description = ''
  saveForm.value.scope = 'private'
  saveForm.value.shared_project_ids = []
  saveDialogVisible.value = true
}

async function onConfirmSaveTemplate() {
  if (!saveForm.value.name.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  // fail-closed：无分享权限时不提交任何分享型 scope（R11.6）。
  // 后端仍会逐项目鉴权，此处提前拦截只为避免用户填完一屏才被 403。
  if (!canSaveTemplate.value) {
    const scope = normalizeTemplateScope(saveForm.value.scope) as TemplateScope
    ElMessage.warning(
      SHARE_REQUIRED_SCOPES.includes(scope) && !canShareTemplates.value
        ? '当前无可编辑项目，仅可保存为「仅我可见」'
        : '请选择至少一个可编辑的分享项目'
    )
    return
  }
  const scope = normalizeTemplateScope(saveForm.value.scope) as TemplateScope
  const sharedProjectIds = scope === 'project' ? resolveSharedProjectIds() : []
  savingTemplate.value = true
  try {
    await api.post(P_cq.templates, {
      name: saveForm.value.name.trim(),
      description: saveForm.value.description?.trim() || null,
      data_source: formCtx.value.source,
      config: {
        project_id: formCtx.value.project_id,
        year: formCtx.value.year,
        condition_logic: formCtx.value.condition_logic,
        conditions: conditions.value,
        selected_columns: selectedColumns.value,
        available_columns: availableColumns.value,
        acnr_targets: acnrFieldIds.value,
      },
      scope,
      shared_project_ids: sharedProjectIds,
    })
    ElMessage.success('模板已保存')
    saveDialogVisible.value = false
  } catch (e: any) {
    handleApiError(e, '保存查询模板')
  } finally {
    savingTemplate.value = false
  }
}

function onLoadTemplate(tpl: TemplateItem) {
  const cfg = tpl.config || {}
  formCtx.value.source = tpl.data_source
  if (cfg.year) formCtx.value.year = cfg.year
  if (cfg.condition_logic) formCtx.value.condition_logic = cfg.condition_logic
  if (Array.isArray(cfg.available_columns)) {
    availableColumns.value = cfg.available_columns
  } else {
    onSourceChange()
  }
  if (Array.isArray(cfg.selected_columns)) {
    selectedColumns.value = cfg.selected_columns
  }
  if (Array.isArray(cfg.conditions)) {
    conditions.value = cfg.conditions
  }
  acnrFieldIds.value = Array.isArray(cfg.acnr_targets) ? cfg.acnr_targets : []
  templatesDialogVisible.value = false
  ElMessage.success(`已加载模板：${tpl.name}`)
}

async function onDeleteTemplate(tpl: TemplateItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除模板「${tpl.name}」？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await api.delete(P_cq.templateDetail(tpl.id))
    ElMessage.success('已删除')
    await loadTemplates()
  } catch (e: any) {
    handleApiError(e, '删除查询模板')
  }
}

// 项目变化时清除结果
watch(() => formCtx.value.project_id, () => {
  result.value = { rows: [], columns: [], total: 0 }
})

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

.gt-cqt-conditions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gt-cqt-cond-row {
  display: flex;
  align-items: center;
  gap: 6px;
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
.gt-cqt-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 8px 4px 0;
}
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
.gt-cqt-error {
  margin: 0;
  font-size: var(--gt-font-size-xs);
  font-family: 'JetBrains Mono', Menlo, Consolas, monospace;
  white-space: pre-wrap;
  color: var(--gt-color-coral);
}
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
</style>
