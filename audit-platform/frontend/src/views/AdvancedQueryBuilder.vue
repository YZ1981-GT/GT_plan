<!--
  AdvancedQueryBuilder.vue — S-3 高级查询构建器

  spec proposal-remaining-18 task 5.1；advanced-query-linkage-closure 任务 30（AQ-18 / 20 / 21 / 28 / 29 前端）

  嵌在高级查询弹窗与页面版（/custom-query）的对话框里使用。
  准入：与后端同一判定（GET /api/query/access，useQueryBuilderAccess）——系统管理员 / 合伙人 / 经理，或任一项目的
  项目经理 / 合伙人（edit 级）；不可用时显示接口给的原因并禁用操作（后端门禁仍是安全边界）。

  能力：
  - 查询范围：在项目里打开（父组件传入或路由带项目）时默认限定当前项目与审计年度，可切到「跨项目」
  - 表选择：从后端 /api/query/schema 加载白名单
  - 字段勾选：复选框选取要返回的列
  - 过滤条件：多行 field/op/value 构造，AND/OR 逻辑
  - 排序、分组、聚合、每页行数与翻页（total 为全量行数）
  - SQL 预览：调用 /api/query/preview 渲染只读 SQL
  - 执行查询：调用 /api/query/execute 显示结果表格；单项目结果可逐行「打开」（下钻）与「复制引用」（经地址库校验）
  - 导出 Excel：调用 /api/query/export-excel 导出全部结果（表头为界面所见中文列名）
-->
<template>
  <div class="gt-aqb gt-fade-in" :class="{ 'gt-aqb--embedded': embedded }">
    <div v-if="!embedded" class="gt-aqb-header">
      <h2 class="gt-aqb-title">高级查询构建器</h2>
      <span class="gt-aqb-subtitle" data-testid="aqb-subtitle">
        可视化条件 · SQL 预览 · 结果导出<template v-if="accessSummary"> · {{ accessSummary }}</template>
      </span>
    </div>

    <el-alert
      v-if="accessBlocked && !accessLoading"
      :title="builderDisabledReason"
      type="warning"
      :closable="false"
      show-icon
      class="gt-aqb-access-alert"
      data-testid="aqb-access-blocked"
    />

    <div class="gt-aqb-body">
      <!-- 左：构造器 -->
      <div class="gt-aqb-builder">
        <el-form :model="dsl" label-position="top" size="small">
          <!-- 查询范围：在项目里打开时默认当前项目与审计年度（R3.5） -->
          <el-form-item v-if="contextProjectId" label="查询范围">
            <div class="gt-aqb-scope-row">
              <span data-testid="aqb-scope-current">{{ scopedToProject ? currentScopeText : '跨项目：可访问的全部项目' }}</span>
              <el-switch
                v-if="canCrossProject"
                v-model="crossProject"
                size="small"
                active-text="跨项目"
                aria-label="切换跨项目查询"
                data-testid="aqb-cross-project"
              />
            </div>
          </el-form-item>

          <!-- 表选择 -->
          <el-form-item label="数据表">
            <el-select
              v-model="dsl.table"
              placeholder="选择白名单表"
              filterable
              @change="onTableChange"
              style="width: 100%"
            >
              <el-option
                v-for="t in schema?.tables || []"
                :key="t.name"
                :label="`${t.label} （${t.name}）`"
                :value="t.name"
              />
            </el-select>
          </el-form-item>

          <!-- 字段勾选：按业务/个人信息/技术三层分组，业务列在前 -->
          <el-form-item v-if="currentTable" label="返回字段（默认业务字段）">
            <div class="gt-aqb-field-grid">
              <el-checkbox-group v-model="dsl.fields">
                <template v-for="grp in fieldGroups" :key="grp.label">
                  <div class="gt-aqb-field-group-label">{{ grp.label }}</div>
                  <el-checkbox
                    v-for="f in grp.fields"
                    :key="f"
                    :label="f"
                    :value="f"
                    size="small"
                  >{{ f }}</el-checkbox>
                </template>
              </el-checkbox-group>
            </div>
            <div class="gt-aqb-field-hint">
              不勾选时返回业务字段（{{ defaultFieldCount }} 个），不含 id / 时间戳等技术字段
            </div>
          </el-form-item>

          <!-- ACNR 选字段树（复用 useAcnr，与公式选址同一棵树；跨模块 cell 级字段） -->
          <el-form-item label="ACNR 选字段（跨模块单元格）">
            <CustomQueryFieldPicker v-model="acnrFieldIds" />
            <div v-if="!contextProjectId" class="gt-aqb-field-hint" data-testid="acnr-no-project">{{ BUILDER_NO_PROJECT_HINT }}</div>
          </el-form-item>

          <!-- 过滤条件 -->
          <el-form-item v-if="currentTable" label="过滤条件">
            <div class="gt-aqb-filter-logic">
              <el-radio-group v-model="dsl.filter_logic" size="small">
                <el-radio-button label="and">AND（全部满足）</el-radio-button>
                <el-radio-button label="or">OR（任一满足）</el-radio-button>
              </el-radio-group>
              <el-button type="primary" link @click="addFilter" size="small">
                + 添加条件
              </el-button>
            </div>
            <div class="gt-aqb-filter-rows">
              <div
                v-for="(f, idx) in dsl.filters"
                :key="idx"
                class="gt-aqb-filter-row"
              >
                <el-select v-model="f.field" placeholder="字段" size="small" filterable class="gt-aqb-filter-field">
                  <el-option
                    v-for="fld in currentTable.fields"
                    :key="fld"
                    :label="fld"
                    :value="fld"
                  />
                </el-select>
                <el-select v-model="f.op" placeholder="操作符" size="small" class="gt-aqb-filter-op">
                  <el-option
                    v-for="op in schema?.operators || []"
                    :key="op"
                    :label="opLabel(op)"
                    :value="op"
                  />
                </el-select>
                <!-- 值框最小 120px、行可换行：嵌在弹窗窄栏里时字段与操作符下拉曾把它挤成 0 宽（B3 浏览器复测） -->
                <el-input
                  v-if="needsValue(f.op)"
                  v-model="f.value"
                  :placeholder="valuePlaceholder(f.op)"
                  size="small"
                  class="gt-aqb-filter-value"
                  aria-label="条件值"
                />
                <span v-else class="gt-aqb-filter-noval">无需值</span>
                <el-button link type="danger" @click="removeFilter(idx)" size="small">
                  删除
                </el-button>
              </div>
              <div v-if="!dsl.filters.length" class="gt-aqb-empty">
                未添加过滤条件
              </div>
            </div>
          </el-form-item>

          <!-- 排序 -->
          <el-form-item v-if="currentTable" label="排序">
            <div class="gt-aqb-filter-logic">
              <el-button type="primary" link @click="addOrder" size="small">
                + 添加排序
              </el-button>
            </div>
            <div class="gt-aqb-filter-rows">
              <div
                v-for="(o, idx) in dsl.order_by"
                :key="idx"
                class="gt-aqb-filter-row"
              >
                <el-select v-model="o.field" size="small" filterable style="width: 200px">
                  <el-option
                    v-for="fld in currentTable.fields"
                    :key="fld"
                    :label="fld"
                    :value="fld"
                  />
                </el-select>
                <el-select v-model="o.direction" size="small" style="width: 100px">
                  <el-option label="升序" value="asc" />
                  <el-option label="降序" value="desc" />
                </el-select>
                <el-button link type="danger" @click="removeOrder(idx)" size="small">
                  删除
                </el-button>
              </div>
            </div>
          </el-form-item>

          <!-- 关联表（JOIN，从 schema 的 joins 自动列出） -->
          <el-form-item v-if="currentTable && availableJoins.length" label="关联表（JOIN）">
            <div class="gt-aqb-filter-logic">
              <el-button type="primary" link @click="addJoin" size="small">
                + 添加关联
              </el-button>
            </div>
            <div class="gt-aqb-filter-rows">
              <div
                v-for="(j, idx) in dsl.joins"
                :key="idx"
                class="gt-aqb-filter-row"
              >
                <el-select v-model="j.table" placeholder="目标表" size="small" filterable style="width: 240px" @change="onJoinTableChange(idx)">
                  <el-option
                    v-for="t in availableJoins"
                    :key="t.target_table"
                    :label="t.target_label + '（' + t.target_table + '）'"
                    :value="t.target_table"
                  />
                </el-select>
                <el-select v-model="j.type" size="small" style="width: 110px">
                  <el-option label="INNER" value="inner" />
                  <el-option label="LEFT" value="left" />
                </el-select>
                <span class="gt-aqb-filter-noval" style="flex:1">
                  ON {{ joinOnSummary(j) || '（自动按 schema）' }}
                </span>
                <el-button link type="danger" @click="removeJoin(idx)" size="small">
                  删除
                </el-button>
              </div>
            </div>
          </el-form-item>

          <!-- 聚合（SUM / COUNT / AVG / MIN / MAX） -->
          <el-form-item v-if="currentTable" label="聚合（可选）">
            <div class="gt-aqb-filter-logic">
              <el-button type="primary" link @click="addAggregate" size="small">
                + 添加聚合
              </el-button>
            </div>
            <div class="gt-aqb-filter-rows">
              <div
                v-for="(a, idx) in dsl.aggregates"
                :key="idx"
                class="gt-aqb-filter-row"
              >
                <el-select v-model="a.func" size="small" style="width: 110px">
                  <el-option v-for="fn in (schema?.aggregates || [])" :key="fn" :label="fn.toUpperCase()" :value="fn" />
                </el-select>
                <el-select v-model="a.field" size="small" filterable class="gt-aqb-filter-field">
                  <el-option label="*（行数）" value="*" />
                  <el-option v-for="fld in currentTable.fields" :key="fld" :label="fld" :value="fld" />
                </el-select>
                <el-input v-model="a.alias" size="small" placeholder="别名" class="gt-aqb-filter-value" aria-label="聚合别名" />
                <el-button link type="danger" @click="removeAggregate(idx)" size="small">
                  删除
                </el-button>
              </div>
            </div>
          </el-form-item>

          <!-- 分组 GROUP BY -->
          <el-form-item v-if="currentTable && dsl.aggregates.length" label="分组 GROUP BY">
            <el-select v-model="dsl.group_by" size="small" filterable multiple style="width: 100%">
              <el-option v-for="fld in currentTable.fields" :key="fld" :label="fld" :value="fld" />
            </el-select>
          </el-form-item>

          <!-- 每页行数（翻页查看其余结果；导出不受此限） -->
          <el-form-item label="每页行数">
            <el-input-number v-model="dsl.limit" :min="1" :max="1000" size="small" aria-label="每页行数" />
            <span style="margin-left:8px;color:#888;font-size:12px">
              （1~1000；翻页查看其余结果，「导出 Excel」导出全部结果）
            </span>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" @click="doPreview" :loading="loadingPreview" :disabled="accessBlocked">
              生成 SQL 预览
            </el-button>
            <el-button type="success" @click="doExecute" :loading="loadingExecute" :disabled="accessBlocked">
              执行查询
            </el-button>
            <el-button
              @click="doExport"
              :loading="loadingExport"
              :disabled="!result || accessBlocked"
              aria-label="导出全部结果为 Excel"
            >
              导出 Excel
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 右：预览 + 结果 -->
      <div class="gt-aqb-result">
        <div class="gt-aqb-section">
          <div class="gt-aqb-section-title">SQL 预览</div>
          <pre v-if="sqlPreview" class="gt-aqb-sql">{{ sqlPreview }}</pre>
          <div v-else class="gt-aqb-empty">
            选择表后点击"生成 SQL 预览"或"执行查询"
          </div>
        </div>

        <div class="gt-aqb-section">
          <div class="gt-aqb-section-title">
            查询结果 <span v-if="result" class="gt-aqb-result-count">共 {{ result.total }} 行</span>
            <span v-if="resultScopeText" class="gt-aqb-scope-tag" data-testid="aqb-result-scope">{{ resultScopeText }}</span>
            <el-checkbox
              v-if="result && result.rows.length"
              v-model="showTechnicalColumns"
              size="small"
              class="gt-aqb-tech-toggle"
            >显示技术字段<template v-if="hiddenTechnicalCount > 0">（已隐藏 {{ hiddenTechnicalCount }} 列）</template></el-checkbox>
          </div>
          <!-- 查询失败：持久显示中文原因与追踪号（R11.1；不落到「查询返回 0 行」） -->
          <el-alert
            v-if="queryError"
            type="error"
            :closable="false"
            show-icon
            class="gt-aqb-warning"
            data-testid="aqb-query-error"
          >
            <template #title>{{ queryError.message }}</template>
            <div v-if="queryError.correlationId" class="gt-aqb-error-trace">
              追踪号：{{ queryError.correlationId }}
              <el-button link type="primary" size="small" aria-label="复制追踪号" @click="copyCorrelationId">复制追踪号</el-button>
            </div>
          </el-alert>
          <el-alert
            v-for="w in result?.warnings || []"
            :key="w"
            :title="w"
            type="warning"
            :closable="false"
            show-icon
            class="gt-aqb-warning"
          />
          <AcnrTargetResults :block="result?.acnr_results" :project-id="contextProjectId" />
          <el-table
            v-if="result && result.rows.length"
            :data="result.rows"
            stripe
            border
            size="small"
            max-height="500"
          >
            <!-- 单项目结果：逐行下钻到权威页面与复制经地址库校验的引用（R7.1~R7.3；跨项目结果不下钻） -->
            <el-table-column v-if="rowActionsEnabled" label="操作" width="150" fixed="left">
              <template #default="{ row, $index }">
                <el-button
                  v-if="drillOf(row)"
                  link
                  type="primary"
                  size="small"
                  :title="drillOf(row)?.label"
                  :aria-label="drillOf(row)?.label"
                  data-testid="aqb-row-open"
                  @click="onOpenRow(row)"
                >打开</el-button>
                <el-tooltip v-if="refOf($index)" :content="refHint($index)" placement="top">
                  <span class="gt-aqb-ref-wrap">
                    <el-button
                      link
                      type="primary"
                      size="small"
                      :disabled="!refUsable($index)"
                      :aria-label="`复制引用 ${refOf($index)}`"
                      data-testid="aqb-row-copy-ref"
                      @click="copyFormulaRef($index)"
                    >复制引用</el-button>
                  </span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column
              v-for="col in resultColumns"
              :key="col.key"
              :prop="col.key"
              :label="col.title"
              :show-overflow-tooltip="!col.drillable"
              min-width="140"
            >
              <template #default="{ row }">
                <!-- 可下钻列：显示值 + GtIndexChip（value=addr_id，经 resolveIndex 拿 jump_route 下钻，R4.3） -->
                <span
                  v-if="col.drillable && cellAddrId(row, col)"
                  class="gt-aqb-drill-cell"
                >
                  <span>{{ row[col.key] }}</span>
                  <GtIndexChip
                    :value="addrIdToIndexRef(cellAddrId(row, col)) || ''"
                    :context-project-id="contextProjectId"
                    :validate="false"
                    prevent-navigate
                    context="下钻到数据来源底稿格"
                    class="gt-aqb-drill-chip"
                    @click="drill(cellAddrId(row, col))"
                  />
                </span>
                <!-- 无 addr_id → 不可下钻普通文本列（R4.5） -->
                <span v-else>{{ row[col.key] }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-else-if="result" class="gt-aqb-empty">查询返回 0 行</div>
          <div v-else-if="!queryError" class="gt-aqb-empty">尚未执行查询</div>
          <!-- 翻页（offset）：total 是全量行数（分组时为组数），R2.6 -->
          <nav v-if="result && (result.total > dsl.limit || page > 1)" class="gt-aqb-pager" aria-label="查询结果翻页">
            <el-pagination
              v-model:current-page="page"
              :page-size="dsl.limit"
              :total="result.total"
              layout="total, prev, pager, next, jumper"
              size="small"
              background
              @current-change="onPageChange"
            />
          </nav>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import api from '@/services/apiProxy'
import { queryBuilder as P_qb } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { resolveColumnLabel } from '@/components/query/queryColumnLabels'
import { sanitizeExportName } from '@/components/query/queryExport'
import { describeQueryError, queryErrorToast, type QueryErrorText } from '@/components/query/queryErrorText'
import { buildRowDrill, openRowDrill, validatePageRefs, type RefCheck, type RowDrill } from '@/components/query/queryResultLinks'
import {
  defaultFieldsOf,
  filterVisibleColumns,
  groupFieldsByTier,
} from '@/components/query/queryFieldTiers'
import CustomQueryFieldPicker from '@/components/custom-query/CustomQueryFieldPicker.vue'
import AcnrTargetResults, { type AcnrResultsBlock } from '@/components/custom-query/AcnrTargetResults.vue'
import {
  BUILDER_NO_PROJECT_HINT, buildBuilderPayload, isKnownYear, readBlobErrorBody,
} from '@/components/custom-query/queryPayloads'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useProjectStore } from '@/stores/project'
import { useAuthStore } from '@/stores/auth'
import { useQueryBuilderAccess } from '@/composables/useQueryBuilderAccess'
import { useAcnrDrill, normalizeColumns, cellAddrId, addrIdToIndexRef, type QueryColumnMeta } from '@/composables/useAcnrDrill'

/**
 * projectId / year：宿主（高级查询弹窗、页面版）当前的项目与审计年度。没传时取路由项目，年度依次取路由 `?year`、
 * 该项目的审计年度（项目 store），都取不到为空（不按日历年兜底）。
 */
const props = withDefaults(defineProps<{
  embedded?: boolean
  projectId?: string | null
  year?: number | null
}>(), { embedded: false, projectId: null, year: null })

interface TableMetaTiers {
  default_fields?: string[]
  technical_fields?: string[]
  pii_fields?: string[]
}
interface TableMeta extends TableMetaTiers {
  name: string
  label: string
  fields: string[]
  joins?: { target_table: string; target_label: string; on: { left_field: string; right_field: string }[] }[]
}
interface Schema {
  tables: TableMeta[]
  operators: string[]
  aggregates: string[]
}
interface FilterRow {
  field: string
  op: string
  value: string | null
}
interface OrderRow {
  field: string
  direction: 'asc' | 'desc'
}
interface JoinRow {
  table: string
  type: 'inner' | 'left'
}
interface AggregateRow {
  func: string
  field: string
  alias: string
}
interface QueryResult {
  rows: Record<string, any>[]
  // 后端可能返回 ColumnMeta[]（含 addr_id/drillable）或 legacy string[]，统一由 normalizeColumns 归一
  columns: Array<string | Record<string, any>>
  total: number
  count_token?: string
  count_reused?: boolean
  table: string
  sql: string
  formula_refs?: (string | null)[]
  /** 本次生效的项目作用域（R2.2：跨项目查询要让用户知道自己在跨项目；requested_project_id = 限定了单个项目） */
  scope?: { all_projects: boolean; project_count: number | null; unscoped_tables: string[]; requested_project_id?: string | null }
  /** 非致命提示（全局配置表未按项目过滤、无项目分派等） */
  warnings?: string[]
  /** 单元格取值结果（只在请求带 acnr_targets 时出现） */
  acnr_results?: AcnrResultsBlock
}

const schema = ref<Schema | null>(null)
// ACNR 选字段：选中 cell 节点的 addr_id 列表（R2.4，作跨模块查询字段标识）
const acnrFieldIds = ref<string[]>([])
// schema 缓存（sessionStorage，按登录用户分开：字段按角色隐去 PII，换人登录不沿用上一个人的字段表）
// schema 版本号随「下发列分层」升位：旧缓存不含 default_fields/technical_fields，
// 沿用会让字段下拉退化为不分组、结果表也无从隐藏技术列。
const SCHEMA_CACHE_KEY = 'gt:query-builder:schema-v2'
const sqlPreview = ref<string>('')
const result = ref<QueryResult | null>(null)
const countToken = ref('')
/** 最近一次查询失败（结果区持久显示） */
const queryError = ref<QueryErrorText | null>(null)

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const authStore = useAuthStore()

// ─── 项目上下文与查询范围（R3.5，AQ-18） ──────────────────────────────────────────
const routeProjectId = computed(() => (route.params.projectId as string) || '')
/** 宿主传入的项目优先，其次路由项目（构建器嵌在项目页的弹窗里） */
const contextProjectId = computed(() => props.projectId || routeProjectId.value)
const contextYear = computed<number | null>(() => {
  if (isKnownYear(props.year)) return props.year
  const routeYear = Number(route.query?.year)
  if (isKnownYear(routeYear)) return routeYear
  const pid = contextProjectId.value
  return pid && projectStore.projectId === pid && isKnownYear(projectStore.auditYear) ? projectStore.auditYear : null
})
const {
  canUseBuilder, builderDisabledReason, allProjects, accessibleProjectCount, loading: accessLoading,
} = useQueryBuilderAccess()
/** 不可用（无权 / 作用域为空 / 尚未确认）时禁用操作；原因见顶部提示 */
const accessBlocked = computed(() => !canUseBuilder.value)
const accessSummary = computed(() => {
  if (canUseBuilder.value) return allProjects.value ? '可查询全部项目' : `可查询 ${accessibleProjectCount.value ?? 0} 个项目`
  return accessLoading.value ? '' : builderDisabledReason.value
})
/** 显式切到跨项目查询（只有可访问项目多于 1 个，或 admin / partner 时才出现） */
const crossProject = ref(false)
const canCrossProject = computed(() =>
  !!contextProjectId.value && (allProjects.value || (accessibleProjectCount.value ?? 0) > 1),
)
const scopedToProject = computed(() => !!contextProjectId.value && !(crossProject.value && canCrossProject.value))
const currentScopeText = computed(() =>
  `当前项目${contextYear.value ? `（${contextYear.value} 年度）` : '（审计年度未确定，不按年度筛选）'}`,
)
/** 本次结果的查询上下文（翻页、下钻与引用校验都按执行时的项目与年度，不随表单后来的改动漂移） */
const lastQuery = reactive<{ projectId: string | null; year: number | null }>({ projectId: null, year: null })

// 结果列下钻（R4.2/R4.4/R4.6/R4.7）：project 上下文与请求同一个
const { drill } = useAcnrDrill(() => contextProjectId.value)
// 归一结果列为 QueryColumnMeta（含 addr_id/drillable）
// ─── 列分层（R7.2 / R11.3）：真源在后端 table_whitelist，前端只分组不硬编码列名 ───
const fieldGroups = computed(() => groupFieldsByTier(currentTable.value))
const defaultFieldCount = computed(() => defaultFieldsOf(currentTable.value).length)
const showTechnicalColumns = ref(false)
const hiddenTechnicalCount = computed(() => {
  if (showTechnicalColumns.value) return 0
  return allResultColumns.value.length - resultColumns.value.length
})

const allResultColumns = computed<QueryColumnMeta[]>(() =>
  normalizeColumns(result.value?.columns).map(c => ({ ...c, title: resolveColumnLabel(c.key, c.title) })),
)

// 结果表默认隐藏技术列（数据仍完整返回，开关即可查看，无需重查）
const resultColumns = computed<QueryColumnMeta[]>(() =>
  filterVisibleColumns(allResultColumns.value, currentTable.value, showTechnicalColumns.value),
)

const resultScopeText = computed(() => {
  const s = result.value?.scope
  if (!s) return ''
  if (s.requested_project_id) return `范围：当前项目${lastQuery.year ? `（${lastQuery.year} 年度）` : ''}`
  return s.all_projects ? '范围：全部项目' : `范围：${s.project_count} 个项目`
})

const loadingPreview = ref(false)
const loadingExecute = ref(false)
const loadingExport = ref(false)
/** 当前页（offset = (page - 1) × 每页行数） */
const page = ref(1)

const dsl = reactive<{
  table: string
  fields: string[]
  filters: FilterRow[]
  filter_logic: 'and' | 'or'
  order_by: OrderRow[]
  joins: JoinRow[]
  aggregates: AggregateRow[]
  group_by: string[]
  limit: number
}>({
  table: '',
  fields: [],
  filters: [],
  filter_logic: 'and',
  order_by: [],
  joins: [],
  aggregates: [],
  group_by: [],
  limit: 100,
})

const currentTable = computed<TableMeta | null>(() => {
  if (!schema.value || !dsl.table) return null
  return schema.value.tables.find((t) => t.name === dsl.table) || null
})

const availableJoins = computed(() => currentTable.value?.joins || [])

function joinOnSummary(j: JoinRow): string {
  if (!j.table || !currentTable.value) return ''
  const meta = currentTable.value.joins?.find(x => x.target_table === j.table)
  if (!meta) return ''
  return meta.on.map(p => `${dsl.table}.${p.left_field} = ${j.table}.${p.right_field}`).join(' AND ')
}

onMounted(async () => {
  const cacheKey = `${SCHEMA_CACHE_KEY}:${authStore.user?.id || 'anon'}`
  // 先尝试 schema 缓存（登录会话内只拉一次）
  try {
    const cached = sessionStorage.getItem(cacheKey)
    if (cached) {
      schema.value = JSON.parse(cached)
      return
    }
  } catch { /* ignore */ }
  try {
    schema.value = await api.get<Schema>(P_qb.schema)
    try { sessionStorage.setItem(cacheKey, JSON.stringify(schema.value)) } catch { /* ignore */ }
  } catch (e: any) {
    handleApiError(e, '加载查询元信息')
  }
})

function onTableChange() {
  // 切表后重置字段/条件，避免引用旧表的字段名
  dsl.fields = []
  dsl.filters = []
  dsl.order_by = []
  dsl.joins = []
  dsl.aggregates = []
  dsl.group_by = []
  sqlPreview.value = ''
  result.value = null
  queryError.value = null
  page.value = 1
}

function addJoin() {
  const first = availableJoins.value[0]
  if (!first) return
  dsl.joins.push({ table: first.target_table, type: 'left' })
}
function removeJoin(idx: number) { dsl.joins.splice(idx, 1) }
function onJoinTableChange(_idx: number) { /* type/table 切换无副作用，预留 */ }

function addAggregate() {
  if (!currentTable.value || !schema.value) return
  const fn = (schema.value.aggregates || ['count'])[0] || 'count'
  dsl.aggregates.push({
    func: fn,
    field: '*',
    alias: `${fn}_value`,
  })
}
function removeAggregate(idx: number) { dsl.aggregates.splice(idx, 1) }

function addFilter() {
  if (!currentTable.value) return
  dsl.filters.push({
    field: currentTable.value.fields[0] || '',
    op: 'eq',
    value: '',
  })
}

function removeFilter(idx: number) {
  dsl.filters.splice(idx, 1)
}

function addOrder() {
  if (!currentTable.value) return
  dsl.order_by.push({
    field: currentTable.value.fields[0] || '',
    direction: 'asc',
  })
}

function removeOrder(idx: number) {
  dsl.order_by.splice(idx, 1)
}

function needsValue(op: string): boolean {
  return op !== 'is_null' && op !== 'is_not_null'
}

function valuePlaceholder(op: string): string {
  if (op === 'in' || op === 'not_in') return '逗号分隔多个值，如 a,b,c'
  if (op === 'between') return '低值,高值，如 100,1000'
  if (op === 'like' || op === 'not_like') return '模糊关键字'
  return '值'
}

function opLabel(op: string): string {
  return ({
    eq: '= 等于',
    neq: '!= 不等于',
    gt: '> 大于',
    gte: '>= 大于等于',
    lt: '< 小于',
    lte: '<= 小于等于',
    like: 'LIKE 包含',
    not_like: 'NOT LIKE 不包含',
    in: 'IN 在列表中',
    not_in: 'NOT IN 不在列表中',
    is_null: 'IS NULL 为空',
    is_not_null: 'IS NOT NULL 非空',
    between: 'BETWEEN 区间',
  } as Record<string, string>)[op] || op
}

/**
 * 请求体（唯一构造处 queryPayloads.buildBuilderPayload）：在项目里默认限定当前项目与审计年度，「跨项目」时只有单元格
 * 取值目标才带项目（T16 规则）；offset 翻页。
 */
function buildPayload() {
  return buildBuilderPayload(dsl, acnrFieldIds.value, {
    projectId: contextProjectId.value, year: contextYear.value, scopeToProject: scopedToProject.value,
    offset: (page.value - 1) * dsl.limit,
    countToken: page.value > 1 ? countToken.value : undefined,
  })
}

/** 导出请求体：同一查询（不分页）+ 界面所见的中文表头（R8.1） */
function buildExportPayload() {
  return buildBuilderPayload(dsl, acnrFieldIds.value, {
    projectId: contextProjectId.value, year: contextYear.value, scopeToProject: scopedToProject.value,
    headers: exportHeaders(),
  })
}

/** 列名 → 界面所见中文表头（已有结果时按结果列；未执行时按所选字段），后端 ExportDSL.headers 最多 200 项 */
function exportHeaders(): Record<string, string> {
  const pairs: [string, string][] = result.value
    ? allResultColumns.value.map((c) => [c.key, c.title])
    : dsl.fields.map((f) => [f, resolveColumnLabel(f)])
  const out: Record<string, string> = {}
  for (const [key, title] of pairs.slice(0, 200)) if (key && title) out[key] = title
  return out
}

async function doPreview() {
  if (!dsl.table) {
    ElMessage.warning('请先选择数据表')
    return
  }
  loadingPreview.value = true
  try {
    const resp = await api.post<{ sql: string; columns: string[] }>(
      '/api/query/preview',
      buildPayload(),
      { _silent: true } as any,
    )
    sqlPreview.value = resp.sql
  } catch (e: any) {
    ElMessage.warning(queryErrorToast('生成 SQL 预览', describeQueryError(e)))
  } finally {
    loadingPreview.value = false
  }
}

/** 执行查询：从第 1 页开始 */
async function doExecute() {
  page.value = 1
  countToken.value = ''
  await runQuery()
}

/** 翻页：同一查询换 offset */
function onPageChange(p: number) {
  page.value = p
  void runQuery()
}

async function runQuery() {
  if (!dsl.table) {
    ElMessage.warning('请先选择数据表')
    return
  }
  loadingExecute.value = true
  queryError.value = null
  // 记下本次发送的项目与年度（纯函数，与下面请求体同一份输入；请求体须直接是构造函数调用，见 queryPayloads 契约）
  const sent = buildPayload()
  try {
    // 调用方自管错误提示（_silent）：失败时结果区显示后端原因与追踪号，确定性错误不自动重试（R11.1）
    const resp = await api.post<QueryResult>('/api/query/execute', buildPayload(), { _silent: true } as any)
    lastQuery.projectId = typeof sent.project_id === 'string' ? sent.project_id : null
    lastQuery.year = isKnownYear(sent.year) ? sent.year : null
    result.value = resp
    if (resp.count_token) countToken.value = resp.count_token
    sqlPreview.value = resp.sql
    void validateRefs()
  } catch (e: any) {
    result.value = null
    queryError.value = describeQueryError(e)
  } finally {
    loadingExecute.value = false
  }
}

async function doExport() {
  if (!dsl.table) return
  // 大量数据导出前提示（导出全部：按全量行数提示）
  const expectedRows = result.value?.total ?? dsl.limit
  if (expectedRows > 500) {
    try {
      await ElMessageBox.confirm(
        `本次将导出约 ${expectedRows} 行数据，可能耗时 10-30 秒。是否继续？`,
        '导出确认',
        { confirmButtonText: '继续导出', cancelButtonText: '取消', type: 'warning' },
      )
    } catch { return /* cancelled */ }
  }
  loadingExport.value = true
  try {
    // 调用方自管错误提示（_silent）：被拒时错误体是 Blob，读成 JSON 后逐项显示原因（T16 / RV7.5-03）
    const response = await http.post('/api/query/export-excel', buildExportPayload(), { responseType: 'blob', _silent: true } as any)
    const blob = new Blob([response.data])
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    // 文件名带表 label 更易识别
    const tableLabel = sanitizeExportName(currentTable.value?.label || dsl.table)
    link.download = `${tableLabel}_${Date.now()}.xlsx`
    link.click()
    URL.revokeObjectURL(link.href)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.warning(queryErrorToast('导出 Excel', describeQueryError(await readBlobErrorBody(e))))
  } finally {
    loadingExport.value = false
  }
}

function copyCorrelationId() {
  const id = queryError.value?.correlationId
  if (!id) return
  navigator.clipboard.writeText(id).then(
    () => { ElMessage.success('已复制追踪号') },
    () => { ElMessage.warning('复制失败，请手动复制') },
  )
}

// ─── 行操作：下钻与复制引用（单项目结果；ADR-AQL-01 / 18） ─────────────────────────────

/** 本次结果限定在单个项目：才可下钻与复制引用（跨项目结果不下钻） */
const rowActionsEnabled = computed(() => !!lastQuery.projectId && !!result.value?.scope?.requested_project_id)

function drillOf(row: Record<string, unknown>): RowDrill | null {
  if (!result.value) return null
  return buildRowDrill({ kind: 'table', key: result.value.table, projectId: lastQuery.projectId, year: lastQuery.year }, row)
}

async function onOpenRow(row: Record<string, unknown>) {
  const target = drillOf(row)
  if (!target || !router) return
  const reason = await openRowDrill(target, router)
  if (reason) ElMessage.warning(reason)
}

/** 引用由后端按行给出（试算表行 TB(标准码,'审定数')），复制前按本页批量经地址库校验（R7.3） */
const refChecks = ref<Map<string, RefCheck>>(new Map())
const refsPending = ref(false)
let refRound = 0

function refOf(index: number): string | null {
  return result.value?.formula_refs?.[index] ?? null
}

async function validateRefs() {
  const round = ++refRound
  refChecks.value = new Map()
  const refs = rowActionsEnabled.value ? (result.value?.formula_refs ?? []) : []
  if (!refs.some(Boolean)) {
    refsPending.value = false
    return
  }
  refsPending.value = true
  const pid = lastQuery.projectId
  const checks = await validatePageRefs(refs, {
    projectId: pid, year: lastQuery.year, templateType: projectStore.projectId === pid ? projectStore.standard : null,
  })
  if (round !== refRound) return
  refChecks.value = checks
  refsPending.value = false
}

function refUsable(index: number): boolean {
  const ref = refOf(index)
  return !!ref && !refsPending.value && !!refChecks.value.get(ref)?.ok
}

function refHint(index: number): string {
  const ref = refOf(index)
  if (!ref) return ''
  const check = refsPending.value ? undefined : refChecks.value.get(ref)
  if (!check) return '正在校验引用…'
  return check.ok ? `复制 ${ref}` : (check.reason || '该引用不可用')
}

/** 复制公式引用：只复制经地址库校验通过的引用 */
function copyFormulaRef(index: number) {
  const ref = refOf(index)
  if (!ref) return
  if (!refUsable(index)) {
    ElMessage.warning(refHint(index))
    return
  }
  navigator.clipboard.writeText(ref).then(() => {
    ElMessage.success(`已复制: ${ref}`)
  }).catch(() => {
    ElMessage.warning('复制失败，请手动复制')
  })
}
</script>

<style scoped>
.gt-aqb {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 12px;
  overflow: hidden;
  background: var(--gt-color-bg, #f5f5f7);
}
/* 嵌入到弹窗时去掉外层背景与 padding，由 dialog/tab 自己控制 */
.gt-aqb--embedded { padding: 0; background: transparent; }
.gt-aqb-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  margin-bottom: 12px;
}
.gt-aqb-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--gt-color-primary, #5b3aa8);
}
.gt-aqb-subtitle {
  font-size: 12px;
  color: #888;
}
.gt-aqb-access-alert {
  margin-bottom: 12px;
}
.gt-aqb-body {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(420px, 1fr) 2fr;
  gap: 12px;
  min-height: 0;
}
.gt-aqb-builder,
.gt-aqb-result {
  background: var(--gt-color-bg-white, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  padding: 16px;
  overflow: auto;
}
.gt-aqb-result {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.gt-aqb-section-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}
.gt-aqb-sql {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow: auto;
  margin: 0;
}
.gt-aqb-empty {
  color: #aaa;
  font-size: 12px;
  padding: 12px;
  text-align: center;
}
.gt-aqb-field-grid {
  max-height: 200px;
  overflow-y: auto;
  border: 1px solid #eee;
  padding: 8px;
  border-radius: 4px;
}
.gt-aqb-field-grid :deep(.el-checkbox) {
  margin-right: 12px;
  margin-bottom: 4px;
}
.gt-aqb-filter-logic {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.gt-aqb-filter-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gt-aqb-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.gt-aqb-filter-field {
  width: 180px;
}
.gt-aqb-filter-op {
  width: 130px;
}
/* 条件值与聚合别名：至少 120px，空间不够时整行换行而不是被挤成 0 宽（R6.4 同口径） */
.gt-aqb-filter-value {
  flex: 1 1 120px;
  min-width: 120px;
}
.gt-aqb-filter-noval {
  color: #888;
  font-size: 12px;
  flex: 1;
}
.gt-aqb-field-group-label {
  width: 100%;
  margin: 6px 0 2px;
  font-size: 12px;
  color: #909399;
  font-weight: 600;
}

.gt-aqb-field-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.gt-aqb-scope-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #606266;
}

.gt-aqb-scope-tag {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}

.gt-aqb-tech-toggle {
  margin-left: auto;
}

.gt-aqb-warning {
  margin-bottom: 8px;
}

.gt-aqb-error-trace {
  font-size: 12px;
  color: #909399;
}

.gt-aqb-result-count {
  font-size: 12px;
  color: #666;
  font-weight: normal;
  margin-left: 8px;
}
.gt-aqb-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
.gt-aqb-ref-wrap {
  display: inline-block;
  margin-left: 6px;
}
.gt-aqb-drill-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}
.gt-aqb-drill-chip {
  flex-shrink: 0;
}
</style>
