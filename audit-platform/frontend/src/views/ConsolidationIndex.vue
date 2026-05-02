<template>
  <div class="gt-consol gt-fade-in">
    <!-- 横幅：单位名称 + 年度 + 准则类型 -->
    <div class="gt-consol-bar">
      <el-button text class="gt-consol-bar-back" @click="$router.push('/consolidation')">← 返回</el-button>
      <div class="gt-consol-bar-info">
        <span class="gt-consol-bar-name">{{ projectInfo.clientName || '加载中...' }}</span>
        <el-tag size="small" effect="plain" round style="margin-left:10px">{{ projectInfo.year }} 年度</el-tag>
        <el-tag size="small" :type="projectInfo.standard === 'listed' ? 'warning' : ''" effect="light" round style="margin-left:6px">
          {{ projectInfo.standard === 'listed' ? '上市版' : '国企版' }}
        </el-tag>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="gt-consol-tabs">
      <!-- Tab 0: 合并工作底稿 -->
      <el-tab-pane label="合并工作底稿" name="worksheets">
        <ConsolWorksheetTabs />
      </el-tab-pane>

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

      <!-- Tab 5: 合并报表 -->
      <el-tab-pane label="合并报表" name="consol_report">
        <div class="gt-tab-content">
          <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap">
            <el-select v-model="consolReportTemplateType" size="small" style="width:100px" @change="loadConsolReport">
              <el-option label="国企版" value="soe" />
              <el-option label="上市版" value="listed" />
            </el-select>
            <el-select v-model="consolReportType" size="small" style="width:140px" @change="loadConsolReport">
              <el-option label="资产负债表" value="balance_sheet" />
              <el-option label="利润表" value="income_statement" />
              <el-option label="现金流量表" value="cash_flow_statement" />
              <el-option label="权益变动表" value="equity_statement" />
              <el-option label="现金流附表" value="cash_flow_supplement" />
              <el-option label="资产减值准备表" value="impairment_provision" />
            </el-select>
            <el-button size="small" type="primary" @click="loadConsolReport" :loading="consolReportLoading">🔄 刷新</el-button>
            <el-button size="small" @click="showConsolConversion = true">🔄 转换规则</el-button>
            <el-button size="small" @click="exportConsolReport">📤 导出</el-button>
          </div>
          <el-table v-if="consolReportRows.length" :data="consolReportRows" border size="small" max-height="calc(100vh - 320px)" style="width:100%"
            :header-cell-style="{ background: '#f8f6fb', fontSize: '12px' }"
            :row-class-name="consolReportRowClass">
            <el-table-column prop="row_code" label="行次" width="90" />
            <el-table-column prop="row_name" label="项目" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px', fontWeight: row.is_total_row ? 700 : 400 }">{{ row.row_name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="合并本期" width="140" align="right">
              <template #default="{ row }">{{ fmtAmt(row.current_period_amount) }}</template>
            </el-table-column>
            <el-table-column label="合并上期" width="140" align="right">
              <template #default="{ row }">{{ fmtAmt(row.prior_period_amount) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else-if="!consolReportLoading" description="选择报表类型后点击刷新" />
        </div>
      </el-tab-pane>

      <!-- Tab 6: 合并附注 -->
      <el-tab-pane label="合并附注" name="consol_note">
        <div class="gt-tab-content">
          <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center">
            <el-select v-model="consolNoteTemplateType" size="small" style="width:100px" @change="loadConsolNoteTree">
              <el-option label="国企版" value="soe" />
              <el-option label="上市版" value="listed" />
            </el-select>
            <el-button size="small" @click="showConsolNoteConversion = true">🔄 转换规则</el-button>
            <el-button size="small" @click="loadConsolNoteTree" :loading="consolNoteLoading">🔄 刷新</el-button>
          </div>
          <div style="display:flex;gap:16px;min-height:400px">
            <div style="width:260px;flex-shrink:0;border:1px solid #e8e4f0;border-radius:8px;overflow-y:auto;padding:8px">
              <el-input v-model="noteTreeSearch" size="small" placeholder="搜索..." clearable style="margin-bottom:6px" />
              <el-tree :data="consolNoteTree" :props="{ label: 'label', children: 'children' }"
                :filter-node-method="filterNoteNode" ref="noteTreeRef"
                highlight-current default-expand-all @node-click="onNoteNodeClick">
                <template #default="{ data }">
                  <span style="font-size:12px">{{ data.label }}
                    <el-tag v-if="data.table_count" size="small" type="info" style="margin-left:4px">{{ data.table_count }}表</el-tag>
                  </span>
                </template>
              </el-tree>
            </div>
            <div style="flex:1;min-width:0">
              <div v-if="selectedNoteSection">
                <h4 style="margin:0 0 8px">{{ selectedNoteSection.title }}</h4>
                <el-tag v-if="selectedNoteSection.scope && selectedNoteSection.scope !== 'both'" :type="selectedNoteSection.scope === 'consolidated_only' ? 'warning' : 'info'" size="small" style="margin-bottom:8px">
                  {{ selectedNoteSection.scope === 'consolidated_only' ? '仅合并' : '仅单体' }}
                </el-tag>
                <el-tabs v-if="selectedNoteSection.tables?.length > 1" v-model="activeNoteTable" type="card" size="small">
                  <el-tab-pane v-for="(tbl, idx) in selectedNoteSection.tables" :key="idx" :label="tbl.name || `表${idx+1}`" :name="String(idx)">
                    <el-table :data="tbl.rows || []" border size="small" max-height="350" style="width:100%"
                      :header-cell-style="{ background: '#f8f6fb', fontSize: '11px' }">
                      <el-table-column v-for="(h, hi) in (tbl.headers || [])" :key="hi" :label="h" min-width="120" align="right">
                        <template #default="{ row }">{{ row.values?.[hi] ?? '-' }}</template>
                      </el-table-column>
                    </el-table>
                  </el-tab-pane>
                </el-tabs>
                <el-table v-else-if="selectedNoteSection.tables?.length === 1" :data="selectedNoteSection.tables[0].rows || []" border size="small" max-height="350" style="width:100%"
                  :header-cell-style="{ background: '#f8f6fb', fontSize: '11px' }">
                  <el-table-column v-for="(h, hi) in (selectedNoteSection.tables[0].headers || [])" :key="hi" :label="h" min-width="120" align="right">
                    <template #default="{ row }">{{ row.values?.[hi] ?? '-' }}</template>
                  </el-table-column>
                </el-table>
                <el-empty v-else description="该章节暂无表格" />
              </div>
              <el-empty v-else description="请在左侧选择章节" />
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 报表转换规则弹窗 -->
    <el-dialog v-model="showConsolConversion" title="国企/上市报表转换规则" width="80%" top="4vh" append-to-body destroy-on-close>
      <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
        <span style="font-size:12px;color:#999">{{ consolReportTemplateType === 'soe' ? '国企版 → 上市版' : '上市版 → 国企版' }}</span>
        <el-button size="small" @click="loadConsolMappingPreset" :loading="consolMappingLoading">一键加载预设</el-button>
        <el-button size="small" type="primary" @click="applyConsolConversion" :loading="consolMappingLoading">应用转换</el-button>
      </div>
      <el-table :data="consolMappingRules" border size="small" max-height="60vh" style="width:100%"
        :header-cell-style="{ background: '#f8f6fb', fontSize: '12px' }">
        <el-table-column label="源行次" prop="source_code" width="100" />
        <el-table-column label="源项目" prop="source_name" min-width="200" show-overflow-tooltip />
        <el-table-column label="→" width="40" align="center"><template #default><span>→</span></template></el-table-column>
        <el-table-column label="目标行次" width="100">
          <template #default="{ row }"><el-input v-model="row.target_code" size="small" /></template>
        </el-table-column>
        <el-table-column label="目标项目" min-width="200">
          <template #default="{ row }"><el-input v-model="row.target_name" size="small" /></template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 附注转换弹窗 -->
    <el-dialog v-model="showConsolNoteConversion" title="国企/上市附注模板切换" width="400px" append-to-body>
      <p style="font-size:13px;color:#666;margin-bottom:16px">
        切换模板后附注章节结构会更新。国企版约165章节，上市版约174章节。
      </p>
      <el-button type="primary" @click="switchNoteTemplate">
        切换为{{ consolNoteTemplateType === 'soe' ? '上市版' : '国企版' }}
      </el-button>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getWorksheetTree, recalcWorksheet, getWorksheetAggregate,
  drillToCompanies, drillToEliminations, drillToTrialBalance,
  executePivotQuery, exportPivotExcel, saveQueryTemplate, listQueryTemplates,
  type WorksheetNode, type PivotResult, type QueryTemplate,
} from '@/services/consolidationApi'
import { listChildProjects } from '@/services/commonApi'
import http from '@/utils/http'
import ConsolWorksheetTabs from '@/components/consolidation/worksheets/ConsolWorksheetTabs.vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

const activeTab = ref('worksheets')
const loading = ref(false)
const recalcLoading = ref(false)

// ─── 项目基本信息 ─────────────────────────────────────────────────────────────
const projectInfo = reactive({
  clientName: '',
  year: new Date().getFullYear() - 1,
  standard: 'soe' as 'soe' | 'listed',
})

async function loadProjectInfo() {
  try {
    const { data } = await http.get(`/api/projects/${projectId.value}`, { validateStatus: (s: number) => s < 600 })
    const p = data?.data ?? data
    if (p) {
      projectInfo.clientName = p.client_name || p.name || ''
      projectInfo.year = p.audit_year || year.value
      projectInfo.standard = (p.applicable_standard || '').includes('listed') ? 'listed' : 'soe'
    }
  } catch { /* ignore */ }
}

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

// ─── Tab 5: 合并报表 ─────────────────────────────────────────────────────────
const consolReportTemplateType = ref('soe')
const consolReportType = ref('balance_sheet')
const consolReportLoading = ref(false)
const consolReportRows = ref<any[]>([])
const showConsolConversion = ref(false)
const consolMappingLoading = ref(false)
const consolMappingRules = ref<any[]>([])

function consolReportRowClass({ row }: { row: any }) {
  if (row.is_total_row) return 'gt-total-row'
  return ''
}

async function loadConsolReport() {
  consolReportLoading.value = true
  try {
    const standard = `${consolReportTemplateType.value}_consolidated`
    const { data } = await http.get('/api/report-config', {
      params: { report_type: consolReportType.value, applicable_standard: standard, project_id: projectId.value },
      validateStatus: (s: number) => s < 600,
    })
    const rows = data?.data ?? data ?? []
    consolReportRows.value = Array.isArray(rows) ? rows : []
  } catch { consolReportRows.value = [] }
  finally { consolReportLoading.value = false }
}

async function loadConsolMappingPreset() {
  consolMappingLoading.value = true
  try {
    const { data } = await http.get('/api/report-mapping/preset', {
      params: { report_type: consolReportType.value },
      validateStatus: (s: number) => s < 600,
    })
    consolMappingRules.value = data?.data ?? data ?? []
  } catch { consolMappingRules.value = [] }
  finally { consolMappingLoading.value = false }
}

async function applyConsolConversion() {
  consolMappingLoading.value = true
  try {
    // 切换模板类型
    consolReportTemplateType.value = consolReportTemplateType.value === 'soe' ? 'listed' : 'soe'
    await loadConsolReport()
    showConsolConversion.value = false
    ElMessage.success('已切换为' + (consolReportTemplateType.value === 'soe' ? '国企版' : '上市版'))
  } finally { consolMappingLoading.value = false }
}

function exportConsolReport() {
  const standard = `${consolReportTemplateType.value}_consolidated`
  window.open(`/api/reports/${projectId.value}/${year.value}/export?report_type=${consolReportType.value}&applicable_standard=${standard}`, '_blank')
}

function getConsolReportConfigData(): Record<string, any> {
  return { rows: consolReportRows.value, template_type: consolReportTemplateType.value, report_type: consolReportType.value }
}

function onConsolReportTemplateApplied(_data: Record<string, any>) {
  loadConsolReport()
}

// ─── Tab 6: 合并附注 ─────────────────────────────────────────────────────────
const consolNoteTemplateType = ref('soe')
const consolNoteLoading = ref(false)
const consolNoteTree = ref<any[]>([])
const selectedNoteSection = ref<any>(null)
const activeNoteTable = ref('0')
const noteTreeSearch = ref('')
const noteTreeRef = ref<any>(null)
const showConsolNoteConversion = ref(false)

async function loadConsolNoteTree() {
  consolNoteLoading.value = true
  try {
    const { data } = await http.get(`/api/note-templates/${consolNoteTemplateType.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const sections = data?.data ?? data ?? []
    if (!Array.isArray(sections)) { consolNoteTree.value = []; return }

    // 按章节分组构建树
    const chapterMap: Record<string, { label: string; children: any[] }> = {}
    const chapterOrder = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
    const chapterLabels: Record<string, string> = {
      '一': '一、公司概况', '二': '二、编制基础', '三': '三、会计政策',
      '四': '四、税项', '五': '五、报表科目注释', '六': '六、其他',
    }

    for (const sec of sections) {
      const sectionId = sec.section_id || sec.note_section || ''
      const title = sec.section_title || sec.title || ''
      const chapterMatch = sectionId.match(/^([一二三四五六七八九十]+)/)
      const chapter = chapterMatch ? chapterMatch[1] : '其他'

      if (!chapterMap[chapter]) {
        chapterMap[chapter] = { label: chapterLabels[chapter] || `${chapter}、其他`, children: [] }
      }
      chapterMap[chapter].children.push({
        key: sectionId,
        label: title.length > 25 ? title.slice(0, 25) + '...' : title,
        title: title,
        section_id: sectionId,
        scope: sec.scope || 'both',
        tables: sec.tables || (sec.table_template ? [sec.table_template] : []),
        table_count: (sec.tables || []).length || (sec.table_template ? 1 : 0),
      })
    }

    const tree: any[] = []
    for (const ch of chapterOrder) {
      if (chapterMap[ch]) {
        tree.push({ key: `chapter_${ch}`, label: chapterMap[ch].label, children: chapterMap[ch].children })
      }
    }
    if (chapterMap['其他']) {
      tree.push({ key: 'chapter_other', label: '其他', children: chapterMap['其他'].children })
    }
    consolNoteTree.value = tree
  } catch { consolNoteTree.value = [] }
  finally { consolNoteLoading.value = false }
}

function filterNoteNode(value: string, data: any) {
  if (!value) return true
  return (data.label || '').includes(value) || (data.title || '').includes(value)
}

function onNoteNodeClick(data: any) {
  if (data.section_id) {
    selectedNoteSection.value = data
    activeNoteTable.value = '0'
  }
}

function switchNoteTemplate() {
  consolNoteTemplateType.value = consolNoteTemplateType.value === 'soe' ? 'listed' : 'soe'
  selectedNoteSection.value = null
  loadConsolNoteTree()
  showConsolNoteConversion.value = false
  ElMessage.success('已切换为' + (consolNoteTemplateType.value === 'soe' ? '国企版' : '上市版'))
}

function getConsolNoteConfigData(): Record<string, any> {
  return { template_type: consolNoteTemplateType.value }
}

function onConsolNoteTemplateApplied(_data: Record<string, any>) {
  loadConsolNoteTree()
}

watch(noteTreeSearch, (val) => {
  noteTreeRef.value?.filter(val)
})

// ─── 生命周期 ────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadProjectInfo()
  await loadGroupTree()
  await loadTemplates()
})

watch(activeTab, (tab) => {
  if (tab === 'worksheet') loadWorksheet()
  if (tab === 'drilldown') loadDrillCompanies()
  if (tab === 'consol_report') loadConsolReport()
  if (tab === 'consol_note' && !consolNoteTree.value.length) loadConsolNoteTree()
})
</script>

<style scoped>
.gt-consol { padding: var(--gt-space-4); }
.gt-consol-tabs { margin-top: var(--gt-space-3); }

/* ── 顶部信息栏 ── */
.gt-consol-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; margin: -16px -16px 12px;
  background: linear-gradient(135deg, #4b2d77 0%, #7c5caa 60%, #a78bcc 100%);
  border-radius: 0 0 10px 10px;
}
.gt-consol-bar-back {
  color: rgba(255,255,255,0.85) !important; font-size: 13px; padding: 4px 8px;
  border-radius: 4px; transition: background 0.15s;
}
.gt-consol-bar-back:hover { background: rgba(255,255,255,0.12) !important; color: #fff !important; }
.gt-consol-bar-info { display: flex; align-items: center; }
.gt-consol-bar-name { font-size: 16px; font-weight: 600; color: #fff; }
.gt-tab-content { padding: var(--gt-space-3) 0; }
.gt-structure-layout { display: flex; gap: 24px; }
.gt-structure-tree { flex: 1; min-width: 300px; }
.gt-structure-card { width: 320px; flex-shrink: 0; }
.gt-tree-node { display: flex; align-items: center; }
</style>
