<template>
  <div class="gt-consol gt-fade-in">
    <!-- 横幅 -->
    <div class="gt-page-banner gt-page-banner--purple">
      <div class="gt-page-banner__content">
        <h2 class="gt-page-banner__title">合并报表</h2>
        <p class="gt-page-banner__desc">集团架构 · 差额表 · 穿透查询 · 自定义分析</p>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="gt-consol-tabs">
      <!-- Tab 1: 集团架构 -->
      <el-tab-pane label="集团架构" name="structure">
        <div class="gt-tab-content gt-structure-layout">
          <div class="gt-structure-tree">
            <el-tree
              :data="groupTree"
              :props="{ label: 'company_name', children: 'children' }"
              default-expand-all
              node-key="company_code"
              highlight-current
              @node-click="onTreeNodeClick"
            >
              <template #default="{ data }">
                <span class="gt-tree-node">
                  <span>{{ data.company_name || data.name }}</span>
                  <el-tag v-if="data.shareholding" size="small" type="info" style="margin-left:8px">
                    {{ data.shareholding }}%
                  </el-tag>
                </span>
              </template>
            </el-tree>
            <el-empty v-if="!groupTree.length" description="暂无集团架构数据" />
          </div>
          <div v-if="selectedNode" class="gt-structure-card">
            <el-descriptions :column="1" border size="small" title="节点信息">
              <el-descriptions-item label="企业名称">{{ selectedNode.company_name }}</el-descriptions-item>
              <el-descriptions-item label="企业代码">{{ selectedNode.company_code }}</el-descriptions-item>
              <el-descriptions-item label="持股比例" v-if="selectedNode.shareholding">{{ selectedNode.shareholding }}%</el-descriptions-item>
            </el-descriptions>
            <el-button type="primary" size="small" style="margin-top:12px" @click="goToProject(selectedNode)">
              跳转项目
            </el-button>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 差额表 -->
      <el-tab-pane label="差额表" name="worksheet">
        <div class="gt-tab-content">
          <div style="display:flex;gap:12px;margin-bottom:12px;align-items:center">
            <el-radio-group v-model="aggMode" size="small">
              <el-radio-button value="self">本级</el-radio-button>
              <el-radio-button value="children">直接下级</el-radio-button>
              <el-radio-button value="descendants">全部下级</el-radio-button>
            </el-radio-group>
            <el-button type="warning" size="small" :loading="recalcLoading" @click="doRecalc">
              重算差额表
            </el-button>
          </div>
          <el-table :data="worksheetData" border stripe v-loading="loading" empty-text="暂无差额表数据" max-height="600">
            <el-table-column prop="account_code" label="科目编码" width="120" fixed />
            <el-table-column prop="account_name" label="科目名称" min-width="180" fixed />
            <el-table-column prop="children_amount_sum" label="下级汇总" width="130" align="right" />
            <el-table-column prop="adjustment_debit" label="调整借方" width="120" align="right" />
            <el-table-column prop="adjustment_credit" label="调整贷方" width="120" align="right" />
            <el-table-column prop="elimination_debit" label="抵消借方" width="120" align="right" />
            <el-table-column prop="elimination_credit" label="抵消贷方" width="120" align="right" />
            <el-table-column prop="net_difference" label="差额净额" width="120" align="right" />
            <el-table-column prop="consolidated_amount" label="合并数" width="130" align="right">
              <template #default="{ row }">
                <span style="font-weight:600">{{ fmtAmt(row.consolidated_amount) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 穿透 -->
      <el-tab-pane label="穿透" name="drilldown">
        <div class="gt-tab-content">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-for="(bc, idx) in drillBreadcrumb" :key="idx">
              <a v-if="idx < drillBreadcrumb.length - 1" href="#" @click.prevent="drillBack(idx)">{{ bc.label }}</a>
              <span v-else>{{ bc.label }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>

          <!-- 层1: 企业构成 -->
          <el-table v-if="drillLevel === 'companies'" :data="drillCompanies" border stripe v-loading="loading"
            empty-text="请先在集团架构中选择节点" style="margin-top:12px">
            <el-table-column prop="company_code" label="企业代码" width="120" />
            <el-table-column prop="company_name" label="企业名称" min-width="200" />
            <el-table-column prop="amount" label="金额" width="160" align="right" />
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="drillToElim(row)">抵消分录</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 层2: 抵消分录 -->
          <el-table v-if="drillLevel === 'eliminations'" :data="drillEliminations" border stripe v-loading="loading"
            empty-text="暂无抵消分录" style="margin-top:12px">
            <el-table-column prop="entry_no" label="分录编号" width="140" />
            <el-table-column prop="description" label="摘要" min-width="200" />
            <el-table-column prop="debit_amount" label="借方" width="130" align="right" />
            <el-table-column prop="credit_amount" label="贷方" width="130" align="right" />
          </el-table>

          <!-- 层3: 试算表跳转 -->
          <div v-if="drillLevel === 'trial'" style="margin-top:12px">
            <el-result icon="info" title="跳转到末端企业试算表">
              <template #extra>
                <el-button type="primary" @click="goToTrialBalance">查看试算表</el-button>
              </template>
            </el-result>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 自定义查询 -->
      <el-tab-pane label="自定义查询" name="pivot">
        <div class="gt-tab-content">
          <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
            <el-select v-model="pivotRowDim" size="small" style="width:130px" placeholder="行维度">
              <el-option label="科目" value="account" />
              <el-option label="企业" value="company" />
            </el-select>
            <el-select v-model="pivotColDim" size="small" style="width:130px" placeholder="列维度">
              <el-option label="企业" value="company" />
              <el-option label="科目" value="account" />
            </el-select>
            <el-select v-model="pivotValueField" size="small" style="width:150px" placeholder="值字段">
              <el-option label="合并数" value="consolidated_amount" />
              <el-option label="下级汇总" value="children_amount_sum" />
              <el-option label="差额净额" value="net_difference" />
            </el-select>
            <el-switch v-model="pivotTranspose" active-text="转置" size="small" />
            <el-button type="primary" size="small" :loading="loading" @click="doPivot">查询</el-button>
            <el-button size="small" @click="doExportExcel">Excel 导出</el-button>
          </div>

          <!-- 模板管理 -->
          <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center">
            <el-input v-model="templateName" size="small" placeholder="模板名称" style="width:180px" />
            <el-button size="small" @click="doSaveTemplate" :disabled="!templateName.trim()">保存模板</el-button>
            <el-select v-model="selectedTemplateId" size="small" style="width:200px" placeholder="加载模板" clearable
              @change="onLoadTemplate">
              <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </div>

          <el-table v-if="pivotResult" :data="pivotResult.rows" border stripe v-loading="loading" max-height="500">
            <el-table-column v-for="h in pivotResult.headers" :key="h" :prop="h" :label="h" min-width="120" align="right" />
          </el-table>
          <el-empty v-if="!pivotResult && !loading" description="点击查询按钮执行透视分析" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getWorksheetTree, recalcWorksheet, getWorksheetAggregate,
  drillToCompanies, drillToEliminations, drillToTrialBalance,
  executePivotQuery, exportPivotExcel, saveQueryTemplate, listQueryTemplates,
  type WorksheetNode, type PivotResult, type QueryTemplate,
} from '@/services/consolidationApi'
import { listChildProjects } from '@/services/commonApi'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

const activeTab = ref('structure')
const loading = ref(false)
const recalcLoading = ref(false)

// ─── Tab 1: 集团架构 ─────────────────────────────────────────────────────────
const groupTree = ref<any[]>([])
const selectedNode = ref<any>(null)

async function loadGroupTree() {
  try {
    const res = await getWorksheetTree(projectId.value)
    if (res?.tree) {
      groupTree.value = [res.tree]
    } else {
      const projects = await listChildProjects(projectId.value)
      groupTree.value = projects.map((p: any) => ({
        company_code: p.company_code || p.id,
        company_name: p.client_name || p.name,
        children: [],
      }))
    }
  } catch { groupTree.value = [] }
}

function onTreeNodeClick(data: any) {
  selectedNode.value = data
}

function goToProject(node: any) {
  if (node.project_id) {
    router.push(`/projects/${node.project_id}/trial-balance`)
  } else {
    ElMessage.info('该节点未关联项目')
  }
}

// ─── Tab 2: 差额表 ──────────────────────────────────────────────────────────
const worksheetData = ref<any[]>([])
const aggMode = ref('self')

async function loadWorksheet() {
  if (!selectedNode.value?.company_code) {
    worksheetData.value = []
    return
  }
  loading.value = true
  try {
    const res = await getWorksheetAggregate(projectId.value, year.value, selectedNode.value.company_code, aggMode.value)
    worksheetData.value = Array.isArray(res?.data) ? res.data : []
  } catch { worksheetData.value = [] }
  finally { loading.value = false }
}

async function doRecalc() {
  recalcLoading.value = true
  try {
    await recalcWorksheet(projectId.value, year.value)
    ElMessage.success('差额表重算完成')
    await loadWorksheet()
  } catch (e: any) {
    ElMessage.error(e?.message || '重算失败')
  } finally { recalcLoading.value = false }
}

watch(aggMode, () => loadWorksheet())

// ─── Tab 3: 穿透 ────────────────────────────────────────────────────────────
const drillLevel = ref<'companies' | 'eliminations' | 'trial'>('companies')
const drillCompanies = ref<any[]>([])
const drillEliminations = ref<any[]>([])
const drillTrialUrl = ref('')
const drillBreadcrumb = ref<{ label: string; level: string }[]>([{ label: '合并数', level: 'companies' }])

async function loadDrillCompanies() {
  if (!selectedNode.value?.company_code) return
  loading.value = true
  try {
    const res = await drillToCompanies(projectId.value, year.value, selectedNode.value.company_code)
    drillCompanies.value = Array.isArray(res?.data) ? res.data : []
    drillLevel.value = 'companies'
    drillBreadcrumb.value = [{ label: '合并数', level: 'companies' }]
  } catch { drillCompanies.value = [] }
  finally { loading.value = false }
}

async function drillToElim(row: any) {
  loading.value = true
  try {
    const res = await drillToEliminations(projectId.value, year.value, row.company_code)
    drillEliminations.value = Array.isArray(res?.data) ? res.data : []
    drillLevel.value = 'eliminations'
    drillBreadcrumb.value = [
      { label: '合并数', level: 'companies' },
      { label: row.company_name || row.company_code, level: 'eliminations' },
    ]
  } catch { drillEliminations.value = [] }
  finally { loading.value = false }
}

function drillBack(idx: number) {
  const bc = drillBreadcrumb.value[idx]
  drillLevel.value = bc.level as any
  drillBreadcrumb.value = drillBreadcrumb.value.slice(0, idx + 1)
}

function goToTrialBalance() {
  if (drillTrialUrl.value) {
    router.push(drillTrialUrl.value)
  }
}

// ─── Tab 4: 自定义查询 ──────────────────────────────────────────────────────
const pivotRowDim = ref('account')
const pivotColDim = ref('company')
const pivotValueField = ref('consolidated_amount')
const pivotTranspose = ref(false)
const pivotResult = ref<PivotResult | null>(null)
const templates = ref<QueryTemplate[]>([])
const templateName = ref('')
const selectedTemplateId = ref('')

async function doPivot() {
  loading.value = true
  try {
    pivotResult.value = await executePivotQuery(projectId.value, year.value, {
      row_dimension: pivotRowDim.value,
      col_dimension: pivotColDim.value,
      value_field: pivotValueField.value,
      transpose: pivotTranspose.value,
      node_company_code: selectedNode.value?.company_code,
      aggregation_mode: aggMode.value,
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '查询失败')
  } finally { loading.value = false }
}

function doExportExcel() {
  exportPivotExcel(projectId.value, year.value, {
    row_dimension: pivotRowDim.value,
    col_dimension: pivotColDim.value,
    value_field: pivotValueField.value,
    transpose: pivotTranspose.value,
    aggregation_mode: aggMode.value,
  })
}

async function doSaveTemplate() {
  try {
    await saveQueryTemplate(projectId.value, templateName.value, {
      row_dimension: pivotRowDim.value,
      col_dimension: pivotColDim.value,
      value_field: pivotValueField.value,
      transpose: pivotTranspose.value,
      aggregation_mode: aggMode.value,
    })
    ElMessage.success('模板已保存')
    templateName.value = ''
    await loadTemplates()
  } catch { ElMessage.error('保存失败') }
}

async function loadTemplates() {
  try { templates.value = await listQueryTemplates(projectId.value) }
  catch { templates.value = [] }
}

function onLoadTemplate(id: string) {
  const t = templates.value.find(x => x.id === id)
  if (!t) return
  pivotRowDim.value = t.row_dimension
  pivotColDim.value = t.col_dimension
  pivotValueField.value = t.value_field
  pivotTranspose.value = t.transpose
  aggMode.value = t.aggregation_mode
}

function fmtAmt(v: any): string {
  if (v == null) return '-'
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 生命周期 ────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadGroupTree()
  await loadTemplates()
})

watch(activeTab, (tab) => {
  if (tab === 'worksheet') loadWorksheet()
  if (tab === 'drilldown') loadDrillCompanies()
})
</script>

<style scoped>
.gt-consol { padding: var(--gt-space-4); }
.gt-consol-tabs { margin-top: var(--gt-space-3); }
.gt-tab-content { padding: var(--gt-space-3) 0; }
.gt-structure-layout { display: flex; gap: 24px; }
.gt-structure-tree { flex: 1; min-width: 300px; }
.gt-structure-card { width: 320px; flex-shrink: 0; }
.gt-tree-node { display: flex; align-items: center; }
</style>
