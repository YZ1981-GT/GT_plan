<template>
  <div class="gt-consol gt-fade-in">
    <div class="gt-consol-header">
      <h2 class="gt-page-title">合并报表</h2>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="集团架构" name="structure">
        <div class="gt-tab-content">
          <el-tree :data="groupTree" :props="{ label: 'name', children: 'children' }"
            default-expand-all node-key="id">
            <template #default="{ data }">
              <span class="gt-tree-node">
                <span>{{ data.name }}</span>
                <el-tag v-if="data.shareholding" size="small" type="info" style="margin-left: 8px">
                  {{ data.shareholding }}%
                </el-tag>
                <el-tag v-if="data.consol_level" size="small" style="margin-left: 4px">
                  L{{ data.consol_level }}
                </el-tag>
              </span>
            </template>
          </el-tree>
          <el-empty v-if="!groupTree.length" description="暂无集团架构数据" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="合并范围" name="scope">
        <div class="gt-tab-content">
          <el-table :data="scopeData" border stripe v-loading="loading">
            <el-table-column prop="company_name" label="企业名称" min-width="200" />
            <el-table-column prop="company_code" label="企业代码" width="120" />
            <el-table-column prop="shareholding" label="持股比例(%)" width="120" align="right" />
            <el-table-column prop="consol_method" label="合并方式" width="120" />
            <el-table-column prop="is_included" label="纳入合并" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_included ? 'success' : 'danger'" size="small">
                  {{ row.is_included ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="合并试算" name="trial">
        <div class="gt-tab-content">
          <el-button @click="loadTrial" :loading="loading" style="margin-bottom: 12px">加载数据</el-button>
          <el-table :data="trialData" border stripe v-loading="loading">
            <el-table-column prop="account_code" label="科目编码" width="120" />
            <el-table-column prop="account_name" label="科目名称" min-width="200" />
            <el-table-column prop="individual_sum" label="个别汇总" width="140" align="right" />
            <el-table-column prop="consol_elimination" label="抵消金额" width="140" align="right" />
            <el-table-column prop="consol_amount" label="合并数" width="140" align="right" />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="内部交易" name="trade">
        <div class="gt-tab-content">
          <el-button size="small" @click="loadTrades" :loading="loading" style="margin-bottom: 12px">加载数据</el-button>
          <el-table :data="tradeData" border stripe v-loading="loading" empty-text="暂无内部交易">
            <el-table-column prop="seller_company_code" label="销售方" width="120" />
            <el-table-column prop="buyer_company_code" label="购买方" width="120" />
            <el-table-column prop="trade_type" label="交易类型" width="100" />
            <el-table-column prop="trade_amount" label="交易金额" width="140" align="right" />
            <el-table-column prop="unrealized_profit" label="未实现利润" width="140" align="right" />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="少数股东" name="minority">
        <div class="gt-tab-content">
          <el-button size="small" @click="loadMinority" :loading="loading" style="margin-bottom: 12px">加载数据</el-button>
          <el-table :data="minorityData" border stripe v-loading="loading" empty-text="暂无少数股东数据">
            <el-table-column prop="company_name" label="子公司" min-width="200" />
            <el-table-column prop="minority_ratio" label="少数股东比例(%)" width="140" align="right" />
            <el-table-column prop="minority_equity" label="少数股东权益" width="140" align="right" />
            <el-table-column prop="minority_profit" label="少数股东损益" width="140" align="right" />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="合并附注" name="notes">
        <div class="gt-tab-content">
          <el-button size="small" @click="loadNotes" :loading="loading" style="margin-bottom: 12px">加载附注</el-button>
          <el-table :data="notesData" border stripe v-loading="loading" empty-text="暂无合并附注">
            <el-table-column prop="section_code" label="章节" width="120" />
            <el-table-column prop="section_title" label="标题" min-width="250" />
            <el-table-column prop="content_type" label="类型" width="100" />
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="合并报表" name="report">
        <div class="gt-tab-content">
          <el-button size="small" @click="loadReports" :loading="loading" style="margin-bottom: 12px">加载报表</el-button>
          <el-radio-group v-model="reportType" size="small" style="margin-bottom: 12px">
            <el-radio-button value="balance_sheet">资产负债表</el-radio-button>
            <el-radio-button value="income_statement">利润表</el-radio-button>
            <el-radio-button value="cash_flow">现金流量表</el-radio-button>
          </el-radio-group>
          <el-table :data="reportData" border stripe v-loading="loading" empty-text="暂无合并报表数据">
            <el-table-column prop="row_name" label="项目" min-width="250" />
            <el-table-column prop="amount" label="合并金额" width="160" align="right" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getConsolScope, getConsolTrial, getInternalTrades, getMinorityInterest, getConsolNotes, getConsolReports } from '@/services/consolidationApi'
import http from '@/utils/http'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

const activeTab = ref('structure')
const loading = ref(false)
const groupTree = ref<any[]>([])
const scopeData = ref<any[]>([])
const trialData = ref<any[]>([])
const tradeData = ref<any[]>([])
const minorityData = ref<any[]>([])
const notesData = ref<any[]>([])
const reportData = ref<any[]>([])
const reportType = ref('balance_sheet')

async function loadGroupTree() {
  try {
    // 从 projects 表查询集团层级
    const { data } = await http.get(`/api/projects`, { params: { parent_project_id: projectId.value } })
    const projects = data.data ?? data
    // 简化：构建扁平列表
    groupTree.value = Array.isArray(projects) ? projects.map((p: any) => ({
      id: p.id, name: p.client_name || p.name, consol_level: p.consol_level, shareholding: null, children: [],
    })) : []
  } catch { groupTree.value = [] }
}

async function loadScope() {
  loading.value = true
  try {
    scopeData.value = await getConsolScope(projectId.value)
    if (!Array.isArray(scopeData.value)) scopeData.value = []
  } catch { scopeData.value = [] }
  finally { loading.value = false }
}

async function loadTrial() {
  loading.value = true
  try {
    trialData.value = await getConsolTrial(projectId.value, year.value)
    if (!Array.isArray(trialData.value)) trialData.value = []
  } catch { trialData.value = [] }
  finally { loading.value = false }
}

async function loadTrades() {
  loading.value = true
  try {
    tradeData.value = await getInternalTrades(projectId.value, year.value)
    if (!Array.isArray(tradeData.value)) tradeData.value = []
  } catch { tradeData.value = [] }
  finally { loading.value = false }
}

async function loadMinority() {
  loading.value = true
  try {
    minorityData.value = await getMinorityInterest(projectId.value, year.value)
    if (!Array.isArray(minorityData.value)) minorityData.value = []
  } catch { minorityData.value = [] }
  finally { loading.value = false }
}

async function loadNotes() {
  loading.value = true
  try {
    notesData.value = await getConsolNotes(projectId.value, year.value)
    if (!Array.isArray(notesData.value)) notesData.value = []
  } catch { notesData.value = [] }
  finally { loading.value = false }
}

async function loadReports() {
  loading.value = true
  try {
    reportData.value = await getConsolReports(projectId.value, year.value)
    if (!Array.isArray(reportData.value)) reportData.value = []
  } catch { reportData.value = [] }
  finally { loading.value = false }
}

onMounted(async () => {
  await loadGroupTree()
  await loadScope()
})
</script>

<style scoped>
.gt-consol { padding: var(--gt-space-4); }
.gt-consol-header { margin-bottom: var(--gt-space-3); }
.gt-tab-content { padding: var(--gt-space-3) 0; }
.gt-tree-node { display: flex; align-items: center; }
</style>
