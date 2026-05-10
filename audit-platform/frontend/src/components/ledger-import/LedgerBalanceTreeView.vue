<!--
LedgerBalanceTreeView.vue — 科目余额树形视图（Layer 2 v2 / Sprint 8）

三层嵌套渲染：
  父科目节点 (_nodeType: 'account')
  └── 维度组节点 (_nodeType: 'group', aux_type=xxx)   ← 按 aux_type 分组聚合
      └── 具体 aux 明细 (_nodeType: 'aux')             ← tb_aux_balance 原始行

关键设计（见 docs/adr/ADR-001-auxiliary-dimension-redundant-storage.md）：
  - 一行多维度在 tb_aux_balance 冗余存 N 条，每条都记原行金额
  - 按单一 aux_type 分组求和 = 主表 closing（冗余但自洽）
  - 禁止平铺所有 aux 行求和（= 父 × N 误导）
  - 维度组节点的 closing_balance 是该组 sum，用于快速发现组内异常

过滤器语义对照表：
  筛选项              服务端/本地  作用
  keyword             服务端       account_code/name 模糊匹配（ilike）
  filterMode=all      —            不过滤
  filterMode=with_activity    服务端 有金额活动（损益类只看 debit/credit）
  filterMode=with_children    服务端 仅返回有辅助维度的科目
  filterMode=aggregated 本地（在当前页结果上再筛） 只看"虚拟汇总"行（raw_extra._aggregated_from_aux=true）
  filterMode=mismatch    本地（在当前页结果上再筛） 只看 summary.mismatches 涉及的 account_code

  分页：page + page_size（最多 200）均走服务端

交互：
  - 切换 filterMode 会重新 fetch（服务端类过滤）或本地 filter
  - 展开/折叠全部递归处理（3 层都展开）
  - 支持 el-table show-summary 本页列求和 + 导出 Excel

Props:
  - projectId: 项目 UUID
  - year: 年度
  - companyCode?: 公司代码（合并账套用），缺省合并全部

Expose:
  - refresh(): 手动刷新
-->
<template>
  <div class="ledger-balance-tree-view" v-loading="loading">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索科目编码/名称"
        clearable
        size="small"
        style="width: 240px"
        prefix-icon="Search"
        @change="onSearch"
        @clear="onSearch"
      />
      <el-radio-group
        v-model="filterMode"
        size="small"
        style="margin-left: 12px"
        @change="onFilterModeChange"
      >
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="with_activity">
          <el-tooltip
            content="有金额活动的科目（损益类只看借贷发生额，其他类型看所有金额字段）"
            placement="top"
          >
            <span>有金额</span>
          </el-tooltip>
        </el-radio-button>
        <el-radio-button value="with_children">仅含辅助</el-radio-button>
        <el-radio-button value="aggregated">聚合生成</el-radio-button>
        <el-radio-button value="mismatch">差异</el-radio-button>
      </el-radio-group>
      <el-button size="small" style="margin-left: 12px" @click="onExpandAll">
        展开全部
      </el-button>
      <el-button size="small" @click="onCollapseAll">折叠全部</el-button>
      <el-button size="small" type="primary" @click="fetchData">刷新</el-button>
      <el-button
        size="small"
        :disabled="!tree.length"
        @click="onExportExcel"
      >
        导出当前页
      </el-button>

      <div class="summary" v-if="resp">
        <el-tag>本页 {{ resp.summary.account_count }}</el-tag>
        <el-tag type="info" style="margin-left: 4px">
          总 {{ resp.pagination.total }}
        </el-tag>
        <el-tag type="info" style="margin-left: 4px">
          含辅助 {{ resp.summary.with_children_count }}
        </el-tag>
        <el-tag
          v-if="resp.summary.aggregated_count > 0"
          type="success"
          style="margin-left: 4px"
        >
          聚合 {{ resp.summary.aggregated_count }}
        </el-tag>
        <el-tag
          v-if="resp.summary.mismatches.length > 0"
          type="danger"
          style="margin-left: 4px"
          effect="dark"
        >
          差异 {{ resp.summary.mismatches.length }}
        </el-tag>
      </div>
    </div>

    <!-- 差异提示 -->
    <el-alert
      v-if="resp && resp.summary.mismatches.length > 0"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 8px"
    >
      <template #title>
        以下"科目 + 辅助维度"的维度组之和 ≠ 科目余额（&gt;1 元，按单一维度类型聚合应等于主表），请核查：
        <span
          v-for="m in resp.summary.mismatches.slice(0, 5)"
          :key="`${m.account_code}-${m.aux_type}`"
          style="margin-right: 12px"
        >
          <b>{{ m.account_code }}</b>
          / {{ m.aux_type }} 差 {{ fmtAmount(m.diff) }}
        </span>
        <span v-if="resp.summary.mismatches.length > 5">
          … 共 {{ resp.summary.mismatches.length }} 条
        </span>
      </template>
    </el-alert>

    <!-- 树形表格（三层：父科目 > 维度组 > 具体明细） -->
    <el-table
      ref="tableRef"
      :data="filteredTree"
      row-key="_rowKey"
      :tree-props="{ children: 'children', hasChildren: 'has_children' }"
      :default-expand-all="false"
      border
      size="small"
      stripe
      show-summary
      :summary-method="getSummary"
      highlight-current-row
      style="width: 100%"
      max-height="calc(100vh - 340px)"
      :row-class-name="rowClassName"
    >
      <el-table-column label="科目 / 维度 / 明细" min-width="320" fixed>
        <template #default="{ row }">
          <!-- 第 3 层：具体 aux 明细 -->
          <span v-if="row._nodeType === 'aux'" class="aux-label">
            <span class="aux-code">{{ row.aux_code || '—' }}</span>
            <span v-if="row.aux_name" class="aux-name">{{ row.aux_name }}</span>
          </span>
          <!-- 第 2 层：维度组 -->
          <span v-else-if="row._nodeType === 'group'" class="group-label">
            <el-tag size="small" type="info" effect="plain">{{ row.aux_type }}</el-tag>
            <span class="group-meta">{{ row.record_count }} 条</span>
          </span>
          <!-- 第 1 层：父科目 -->
          <span v-else>
            <b>{{ row.account_code }}</b>
            <span style="color: #606266; margin-left: 8px">
              {{ row.account_name }}
            </span>
            <el-tooltip
              v-if="row.aggregated_from_aux"
              content="此行由辅助明细聚合生成（原 Excel 无汇总行）"
              placement="top"
            >
              <el-tag size="small" type="success" effect="plain" style="margin-left: 6px">
                聚合
              </el-tag>
            </el-tooltip>
            <span
              v-if="row.aux_types && row.aux_types.length"
              class="dim-types"
            >
              {{ row.aux_types.join(' / ') }}
            </span>
          </span>
        </template>
      </el-table-column>

      <el-table-column label="期初余额" width="140" align="right">
        <template #default="{ row }">
          <span class="gt-amount">{{ fmtAmount(row.opening_balance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期借方" width="140" align="right">
        <template #default="{ row }">
          <span class="gt-amount">{{ fmtAmount(row.debit_amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期贷方" width="140" align="right">
        <template #default="{ row }">
          <span class="gt-amount">{{ fmtAmount(row.credit_amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" width="140" align="right">
        <template #default="{ row }">
          <span
            class="gt-amount"
            :class="{ 'negative': (row.closing_balance ?? 0) < 0 }"
          >
            {{ fmtAmount(row.closing_balance) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="级次" width="60" align="center">
        <template #default="{ row }">
          <span v-if="row._nodeType === 'account'">{{ row.level || '' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="维度 / 明细行数" width="140" align="center">
        <template #default="{ row }">
          <!-- 父科目：显示维度类型数 + 总明细行数 -->
          <span
            v-if="row._nodeType === 'account' && row.aux_types && row.aux_types.length"
          >
            {{ row.aux_types.length }} 维度 / {{ row.aux_rows_total }} 行
          </span>
          <!-- 维度组：显示该维度明细数 -->
          <span v-else-if="row._nodeType === 'group'">
            {{ row.record_count }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页条 -->
    <div class="pagination-row" v-if="resp">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="resp.pagination.total"
        :page-sizes="[20, 50, 100, 200]"
        :max="200"
        background
        size="small"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="onPageChange"
        @size-change="onPageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getLedgerBalanceTree,
  type LedgerBalanceTreeResponse,
} from '@/services/commonApi'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{
  projectId: string
  year: number
  companyCode?: string
}>()

const loading = ref(false)
const resp = ref<LedgerBalanceTreeResponse | null>(null)
const keyword = ref('')
const filterMode = ref<'all' | 'with_activity' | 'with_children' | 'aggregated' | 'mismatch'>('with_activity')
const tableRef = ref<any>(null)

// 分页状态（P3 / 2026-05-10 支持用户自定义 page_size，最多 200）
const page = ref(1)
const pageSize = ref(100)

/** 构造三层 row-key 树。 */
const tree = computed<any[]>(() => {
  if (!resp.value) return []
  return resp.value.tree.map((node) => {
    const parentKey = `acc:${node.company_code}:${node.account_code}`
    return {
      ...node,
      _rowKey: parentKey,
      _nodeType: 'account' as const,
      children: node.children.map((group, gi) => ({
        ...group,
        _rowKey: `${parentKey}:grp:${group.aux_type}:${gi}`,
        _nodeType: 'group' as const,
        children: group.children.map((c, ci) => ({
          ...c,
          _rowKey: `${parentKey}:grp:${group.aux_type}:${gi}:aux:${c.aux_code || ci}`,
          _nodeType: 'aux' as const,
          has_children: false,
          account_code: node.account_code,
          account_name: node.account_name,
        })),
      })),
    }
  })
})

const mismatchCodes = computed(() => {
  if (!resp.value) return new Set<string>()
  return new Set(resp.value.summary.mismatches.map((m) => m.account_code))
})

const mismatchKeys = computed(() => {
  if (!resp.value) return new Set<string>()
  return new Set(
    resp.value.summary.mismatches.map((m) => `${m.account_code}::${m.aux_type}`),
  )
})

const filteredTree = computed(() => {
  // 服务端已按 keyword + only_with_children 过滤；仅本地处理 aggregated/mismatch 模式
  return tree.value.filter((node) => {
    if (filterMode.value === 'aggregated' && !node.aggregated_from_aux) return false
    if (filterMode.value === 'mismatch' && !mismatchCodes.value.has(node.account_code)) return false
    return true
  })
})

function rowClassName({ row }: { row: any }): string {
  if (row._nodeType === 'aux') return 'aux-row'
  if (row._nodeType === 'group') {
    const key = `${row.account_code}::${row.aux_type}`
    return mismatchKeys.value.has(key) ? 'mismatch-group-row' : 'group-row'
  }
  if (row.aggregated_from_aux) return 'aggregated-row'
  if (mismatchCodes.value.has(row.account_code)) return 'mismatch-row'
  return ''
}

function _expandRecursive(row: any, expand: boolean) {
  if (!tableRef.value) return
  if (row.has_children && row.children && row.children.length) {
    tableRef.value.toggleRowExpansion(row, expand)
    row.children.forEach((c: any) => _expandRecursive(c, expand))
  }
}

function onExpandAll() {
  if (!tableRef.value) return
  filteredTree.value.forEach((row: any) => _expandRecursive(row, true))
}

function onCollapseAll() {
  if (!tableRef.value) return
  filteredTree.value.forEach((row: any) => _expandRecursive(row, false))
}

async function fetchData() {
  if (!props.projectId || !props.year) return
  loading.value = true
  try {
    resp.value = await getLedgerBalanceTree(props.projectId, {
      year: props.year,
      companyCode: props.companyCode,
      page: page.value,
      pageSize: Math.min(pageSize.value, 200),
      keyword: keyword.value.trim() || undefined,
      onlyWithChildren: filterMode.value === 'with_children' || undefined,
      onlyWithActivity: filterMode.value === 'with_activity' || undefined,
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '加载科目余额树失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  fetchData()
}

function onFilterModeChange() {
  page.value = 1
  fetchData()
}

function onPageChange(newPage: number) {
  page.value = newPage
  fetchData()
}

function onPageSizeChange(newSize: number) {
  pageSize.value = Math.min(newSize, 200)
  page.value = 1
  fetchData()
}

/** 仅对父科目行求和（维度组行是重复冗余聚合不能再加）。*/
function getSummary({ columns }: { columns: any[] }): string[] {
  const totals: Record<string, number> = {
    opening_balance: 0,
    debit_amount: 0,
    credit_amount: 0,
    closing_balance: 0,
  }
  // 只累加父科目行（避免维度组重复计入）
  filteredTree.value.forEach((node: any) => {
    if (node._nodeType !== 'account') return
    for (const k of Object.keys(totals)) {
      const v = node[k]
      if (typeof v === 'number' && !Number.isNaN(v)) totals[k] += v
    }
  })

  return columns.map((_col, idx) => {
    if (idx === 0) return '合计'
    const label = _col.label || ''
    if (label.includes('期初')) return fmtAmount(totals.opening_balance)
    if (label.includes('借方') && label.includes('本期')) return fmtAmount(totals.debit_amount)
    if (label.includes('贷方') && label.includes('本期')) return fmtAmount(totals.credit_amount)
    if (label.includes('期末')) return fmtAmount(totals.closing_balance)
    return ''
  })
}

async function onExportExcel() {
  // 动态 import xlsx 避免首屏体积
  const XLSX = await import('xlsx')
  const rows: any[] = []
  filteredTree.value.forEach((node: any) => {
    // 父行
    rows.push({
      科目编码: node.account_code,
      科目名称: node.account_name,
      维度: '',
      明细编码: '',
      明细名称: '',
      期初余额: node.opening_balance,
      本期借方: node.debit_amount,
      本期贷方: node.credit_amount,
      期末余额: node.closing_balance,
      级次: node.level,
      聚合生成: node.aggregated_from_aux ? '是' : '',
    })
    ;(node.children || []).forEach((grp: any) => {
      rows.push({
        科目编码: node.account_code,
        科目名称: node.account_name,
        维度: grp.aux_type,
        明细编码: `【${grp.aux_type} 组】${grp.record_count} 条`,
        明细名称: '',
        期初余额: grp.opening_balance,
        本期借方: grp.debit_amount,
        本期贷方: grp.credit_amount,
        期末余额: grp.closing_balance,
        级次: '',
        聚合生成: '',
      })
      ;(grp.children || []).forEach((c: any) => {
        rows.push({
          科目编码: node.account_code,
          科目名称: node.account_name,
          维度: grp.aux_type,
          明细编码: c.aux_code || '',
          明细名称: c.aux_name || '',
          期初余额: c.opening_balance,
          本期借方: c.debit_amount,
          本期贷方: c.credit_amount,
          期末余额: c.closing_balance,
          级次: '',
          聚合生成: '',
        })
      })
    })
  })

  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '科目余额树形')
  const filename = `余额树形_${props.year}_第${page.value}页.xlsx`
  XLSX.writeFile(wb, filename)
  ElMessage.success(`已导出 ${rows.length} 行到 ${filename}`)
}

watch(
  () => [props.projectId, props.year, props.companyCode],
  () => {
    page.value = 1
    fetchData()
  },
)
onMounted(fetchData)

defineExpose({ refresh: fetchData })
</script>

<style scoped>
.ledger-balance-tree-view {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.summary {
  margin-left: auto;
  display: flex;
  align-items: center;
}
.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
  padding: 4px 0;
}
.group-label {
  padding-left: 4px;
}
.group-meta {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
.aux-label {
  padding-left: 12px;
  color: #303133;
}
.aux-code {
  font-family: monospace;
  color: #606266;
}
.aux-name {
  margin-left: 8px;
}
.dim-types {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
.negative {
  color: var(--el-color-danger);
}
:deep(.group-row) {
  background-color: #f4f4f5;
}
:deep(.mismatch-group-row) {
  background-color: #fef0f0;
}
:deep(.aux-row) {
  background-color: var(--el-fill-color-lighter) !important;
}
:deep(.aggregated-row) {
  background-color: #f0f9eb;
}
:deep(.mismatch-row) {
  background-color: #fef0f0;
}
:deep(.el-table__expand-icon) {
  color: var(--el-color-primary);
}
</style>
