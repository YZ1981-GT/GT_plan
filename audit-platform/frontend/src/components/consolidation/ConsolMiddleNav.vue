<template>
  <div class="cm-nav">
    <div class="cm-nav-header">
      <span class="cm-nav-title">合并节点</span>
      <div style="display:flex;gap:4px">
        <el-button size="small" type="primary" @click="showAddDialog = true">+ 添加</el-button>
        <el-button size="small" @click="loadTree" :loading="loading">🔄</el-button>
      </div>
    </div>

    <!-- 集团架构树 -->
    <div class="cm-tree">
      <el-tree :data="treeData" :props="{ label: 'label', children: 'children' }"
        node-key="key" default-expand-all highlight-current
        @node-click="onNodeClick">
        <template #default="{ data }">
          <span class="cm-tree-node" :class="{ 'cm-tree-node--diff': data.isDiff, 'cm-tree-node--report': data.isReport }">
            <span class="cm-tree-icon">{{ data.icon }}</span>
            <span class="cm-tree-label">{{ data.label }}</span>
            <el-tag v-if="data.ratio" size="small" type="info" style="margin-left:4px;font-size:10px">{{ data.ratio }}%</el-tag>
          </span>
        </template>
      </el-tree>
      <el-empty v-if="!treeData.length" description="暂无合并范围数据" :image-size="40" />
    </div>

    <!-- 年度切换 -->
    <div class="cm-nav-footer">
      <el-select v-model="selectedYear" size="small" style="width:100%" @change="loadTree">
        <el-option v-for="y in yearOptions" :key="y" :label="`${y} 年度`" :value="y" />
      </el-select>
    </div>

    <!-- 添加企业弹窗 -->
    <el-dialog v-model="showAddDialog" title="添加合并范围企业" width="400px" append-to-body>
      <el-form label-width="80px" size="small">
        <el-form-item label="企业名称">
          <el-input v-model="addForm.name" placeholder="输入企业全称" />
        </el-form-item>
        <el-form-item label="企业代码">
          <el-input v-model="addForm.code" placeholder="如 CQ001" />
        </el-form-item>
        <el-form-item label="持股比例">
          <el-input-number v-model="addForm.ratio" :precision="2" :min="0" :max="100" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="doAddCompany">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getConsolScope, getWorksheetTree } from '@/services/consolidationApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const loading = ref(false)
const rawTree = ref<any[]>([])
const showAddDialog = ref(false)
const addForm = reactive({ name: '', code: '', ratio: 0 })
const manualCompanies = ref<any[]>([])

const currentYear = new Date().getFullYear() - 1
const selectedYear = ref(currentYear)
const yearOptions = computed(() => {
  const years = []
  for (let y = currentYear; y >= currentYear - 5; y--) years.push(y)
  return years
})

// 构建树形数据：集团架构 + 差额表 + 报表类型
const treeData = computed(() => {
  if (!rawTree.value.length && !manualCompanies.value.length) return []

  function buildNode(node: any): any {
    const children: any[] = []
    if (node.children?.length) {
      for (const child of node.children) children.push(buildNode(child))
      // 合并节点自动加差额表
      children.push({
        key: `diff_${node.company_code || 'root'}`,
        label: '差额表',
        icon: '📝', isDiff: true,
        companyCode: node.company_code,
      })
    }
    // 每个节点下加报表类型
    const reportChildren = [
      { key: `${node.company_code}_bs`, label: '资产负债表', icon: '📋', isReport: true, reportType: 'balance_sheet', companyCode: node.company_code },
      { key: `${node.company_code}_is`, label: '利润表', icon: '📈', isReport: true, reportType: 'income_statement', companyCode: node.company_code },
      { key: `${node.company_code}_cf`, label: '现金流量表', icon: '💰', isReport: true, reportType: 'cash_flow_statement', companyCode: node.company_code },
      { key: `${node.company_code}_eq`, label: '权益变动表', icon: '📊', isReport: true, reportType: 'equity_statement', companyCode: node.company_code },
    ]
    return {
      key: node.company_code || 'root',
      label: node.company_name || node.name,
      icon: children.length ? '🏢' : '🏠',
      ratio: node.shareholding,
      companyCode: node.company_code,
      children: [...children, ...reportChildren],
    }
  }

  if (rawTree.value.length) {
    const root = buildNode(rawTree.value[0])
    // 追加手动添加的企业
    for (const mc of manualCompanies.value) {
      root.children.unshift({
        key: mc.code, label: mc.name, icon: '🏠',
        ratio: mc.ratio, companyCode: mc.code,
        children: [
          { key: `${mc.code}_bs`, label: '资产负债表', icon: '📋', isReport: true, reportType: 'balance_sheet', companyCode: mc.code },
          { key: `${mc.code}_is`, label: '利润表', icon: '📈', isReport: true, reportType: 'income_statement', companyCode: mc.code },
        ],
      })
    }
    return [root]
  }
  return []
})

async function loadTree() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await getWorksheetTree(projectId.value)
    if (res?.tree) {
      rawTree.value = [res.tree]
    } else {
      // 降级：从合并范围获取
      const items = await getConsolScope(projectId.value, selectedYear.value)
      if (Array.isArray(items) && items.length) {
        rawTree.value = [{
          company_name: '集团合并', company_code: 'root',
          children: items.filter((s: any) => s.is_included).map((s: any) => ({
            company_name: s.company_name || s.company_code,
            company_code: s.company_code,
            shareholding: s.ownership_ratio,
            children: [],
          })),
        }]
      }
    }
  } catch { rawTree.value = [] }
  finally { loading.value = false }
}

function onNodeClick(data: any) {
  // 通过自定义事件通知父组件（ConsolidationIndex）
  window.dispatchEvent(new CustomEvent('consol-tree-select', { detail: data }))
}

function doAddCompany() {
  if (!addForm.name || !addForm.code) { ElMessage.warning('请填写企业名称和代码'); return }
  manualCompanies.value.push({ ...addForm })
  addForm.name = ''; addForm.code = ''; addForm.ratio = 0
  showAddDialog.value = false
  ElMessage.success('已添加到合并范围')
}

onMounted(() => loadTree())
</script>

<style scoped>
.cm-nav { display: flex; flex-direction: column; height: 100%; }
.cm-nav-header {
  padding: 10px 12px; border-bottom: 1px solid var(--gt-color-border-light, #e8e4f0);
  display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
}
.cm-nav-title { font-size: 14px; font-weight: 700; color: #4b2d77; }
.cm-tree { flex: 1; overflow-y: auto; padding: 6px; }
.cm-tree-node { display: flex; align-items: center; font-size: 12px; gap: 4px; }
.cm-tree-icon { font-size: 14px; }
.cm-tree-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cm-tree-node--diff { color: #e6a23c; font-style: italic; }
.cm-tree-node--diff .cm-tree-label { color: #e6a23c; }
.cm-tree-node--report { color: #999; font-size: 11px; }
.cm-tree-node--report .cm-tree-icon { font-size: 12px; }
.cm-nav-footer { padding: 8px 12px; border-top: 1px solid var(--gt-color-border-light, #e8e4f0); flex-shrink: 0; }
</style>
