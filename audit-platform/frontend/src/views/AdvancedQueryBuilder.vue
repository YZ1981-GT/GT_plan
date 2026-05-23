<!--
  AdvancedQueryBuilder.vue — S-3 高级查询构建器

  spec proposal-remaining-18 task 5.1

  路由：/advanced-query
  权限：仅 admin / manager / partner（与后端 RBAC 一致）

  能力：
  - 表选择：从后端 /api/query/schema 加载白名单
  - 字段勾选：复选框选取要返回的列
  - 过滤条件：多行 field/op/value 构造，AND/OR 逻辑
  - 排序、分组、聚合、limit
  - SQL 预览：调用 /api/query/preview 渲染只读 SQL
  - 执行查询：调用 /api/query/execute 显示结果表格
  - 导出 Excel：调用 /api/query/export-excel 下载 xlsx
-->
<template>
  <div class="gt-aqb gt-fade-in" :class="{ 'gt-aqb--embedded': embedded }">
    <div v-if="!embedded" class="gt-aqb-header">
      <h2 class="gt-aqb-title">高级查询构建器</h2>
      <span class="gt-aqb-subtitle">
        可视化条件 · SQL 预览 · 结果导出 · 仅 admin / manager 可访问
      </span>
    </div>

    <div class="gt-aqb-body">
      <!-- 左：构造器 -->
      <div class="gt-aqb-builder">
        <el-form :model="dsl" label-position="top" size="small">
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

          <!-- 字段勾选 -->
          <el-form-item v-if="currentTable" label="返回字段（默认全部）">
            <div class="gt-aqb-field-grid">
              <el-checkbox-group v-model="dsl.fields">
                <el-checkbox
                  v-for="f in currentTable.fields"
                  :key="f"
                  :label="f"
                  :value="f"
                  size="small"
                >{{ f }}</el-checkbox>
              </el-checkbox-group>
            </div>
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
                <el-select v-model="f.field" placeholder="字段" size="small" filterable style="width: 200px">
                  <el-option
                    v-for="fld in currentTable.fields"
                    :key="fld"
                    :label="fld"
                    :value="fld"
                  />
                </el-select>
                <el-select v-model="f.op" placeholder="操作符" size="small" style="width: 130px">
                  <el-option
                    v-for="op in schema?.operators || []"
                    :key="op"
                    :label="opLabel(op)"
                    :value="op"
                  />
                </el-select>
                <el-input
                  v-if="needsValue(f.op)"
                  v-model="f.value"
                  :placeholder="valuePlaceholder(f.op)"
                  size="small"
                  style="flex: 1"
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
                <el-select v-model="a.field" size="small" filterable style="width: 200px">
                  <el-option label="*（行数）" value="*" />
                  <el-option v-for="fld in currentTable.fields" :key="fld" :label="fld" :value="fld" />
                </el-select>
                <el-input v-model="a.alias" size="small" placeholder="别名" style="flex: 1" />
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

          <!-- 高级：limit -->
          <el-form-item label="结果限制">
            <el-input-number v-model="dsl.limit" :min="1" :max="1000" size="small" />
            <span style="margin-left:8px;color:#888;font-size:12px">
              （上限 1000，避免拉爆数据库）
            </span>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" @click="doPreview" :loading="loadingPreview">
              生成 SQL 预览
            </el-button>
            <el-button type="success" @click="doExecute" :loading="loadingExecute">
              执行查询
            </el-button>
            <el-button @click="doExport" :loading="loadingExport" :disabled="!result">
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
          </div>
          <el-table
            v-if="result && result.rows.length"
            :data="result.rows"
            stripe
            border
            size="small"
            max-height="500"
          >
            <el-table-column
              v-for="col in result.columns"
              :key="col"
              :prop="col"
              :label="col"
              show-overflow-tooltip
              min-width="140"
            />
          </el-table>
          <div v-else-if="result" class="gt-aqb-empty">查询返回 0 行</div>
          <div v-else class="gt-aqb-empty">尚未执行查询</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import api from '@/services/apiProxy'

withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

interface TableMeta {
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
  columns: string[]
  total: number
  table: string
  sql: string
}

const schema = ref<Schema | null>(null)
// schema 缓存（sessionStorage）
const SCHEMA_CACHE_KEY = 'gt:query-builder:schema-v1'
const sqlPreview = ref<string>('')
const result = ref<QueryResult | null>(null)
const loadingPreview = ref(false)
const loadingExecute = ref(false)
const loadingExport = ref(false)

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
  // 先尝试 schema 缓存（登录会话内只拉一次）
  try {
    const cached = sessionStorage.getItem(SCHEMA_CACHE_KEY)
    if (cached) {
      schema.value = JSON.parse(cached)
      return
    }
  } catch { /* ignore */ }
  try {
    schema.value = await api.get<Schema>('/api/query/schema')
    try { sessionStorage.setItem(SCHEMA_CACHE_KEY, JSON.stringify(schema.value)) } catch { /* ignore */ }
  } catch (e: any) {
    if (e?.response?.status === 403) {
      ElMessage.error('当前角色无权访问高级查询构建器（仅 admin / manager / partner）')
    } else {
      ElMessage.error('加载查询元信息失败')
    }
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

/** 把前端字符串值转成后端期望的类型/数组。 */
function buildPayload() {
  return {
    table: dsl.table,
    fields: dsl.fields,
    filters: dsl.filters
      .filter((f) => f.field && f.op)
      .map((f) => {
        const op = f.op
        let v: any = f.value
        if (op === 'is_null' || op === 'is_not_null') {
          v = null
        } else if (op === 'in' || op === 'not_in') {
          v = String(f.value || '')
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean)
        } else if (op === 'between') {
          const [lo, hi] = String(f.value || '')
            .split(',')
            .map((s) => s.trim())
          v = [tryNumber(lo), tryNumber(hi)]
        } else if (['gt', 'gte', 'lt', 'lte', 'eq', 'neq'].includes(op)) {
          // 数字优先，失败保留字符串
          v = tryNumber(String(f.value ?? ''))
        }
        return { field: f.field, op, value: v }
      }),
    filter_logic: dsl.filter_logic,
    order_by: dsl.order_by.filter((o) => o.field),
    joins: dsl.joins.filter((j) => j.table).map((j) => ({ table: j.table, type: j.type })),
    aggregates: dsl.aggregates.filter((a) => a.func && a.field).map((a) => ({
      func: a.func,
      field: a.field,
      alias: a.alias || `${a.func}_${a.field}`,
    })),
    group_by: dsl.group_by,
    limit: dsl.limit,
  }
}

function tryNumber(v: string): any {
  if (v === '' || v === null || v === undefined) return v
  const n = Number(v)
  return Number.isFinite(n) && /^-?\d+(\.\d+)?$/.test(v) ? n : v
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
    )
    sqlPreview.value = resp.sql
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(detail?.message || '生成 SQL 预览失败')
  } finally {
    loadingPreview.value = false
  }
}

async function doExecute() {
  if (!dsl.table) {
    ElMessage.warning('请先选择数据表')
    return
  }
  loadingExecute.value = true
  try {
    const resp = await api.post<QueryResult>('/api/query/execute', buildPayload())
    result.value = resp
    sqlPreview.value = resp.sql
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(detail?.message || '查询执行失败')
  } finally {
    loadingExecute.value = false
  }
}

async function doExport() {
  if (!dsl.table) return
  // 大量数据导出前提示（result.total > 1000 或 limit > 500）
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
    const response = await http.post('/api/query/export-excel', buildPayload(), {
      responseType: 'blob',
    })
    const blob = new Blob([response.data])
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    // 文件名带表 label 更易识别
    const tableLabel = (currentTable.value?.label || dsl.table).replace(/[\\/:*?"<>|]/g, '_')
    link.download = `${tableLabel}_${Date.now()}.xlsx`
    link.click()
    URL.revokeObjectURL(link.href)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error('导出 Excel 失败')
  } finally {
    loadingExport.value = false
  }
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
  gap: 8px;
  align-items: center;
}
.gt-aqb-filter-noval {
  color: #888;
  font-size: 12px;
  flex: 1;
}
.gt-aqb-result-count {
  font-size: 12px;
  color: #666;
  font-weight: normal;
  margin-left: 8px;
}
</style>
