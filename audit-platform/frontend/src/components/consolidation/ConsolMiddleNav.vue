<template>
  <div class="cm-nav">
    <div class="cm-nav-header">
      <span class="cm-nav-title">树形</span>
      <div style="display:flex;gap:4px">
        <el-button size="small" type="primary" @click="showAddDialog = true">+ 添加</el-button>
        <el-tooltip content="从项目数据同步合并范围企业" placement="bottom">
          <el-button size="small" @click="syncFromProject" :loading="loading">🔄 同步</el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- 集团架构树 -->
    <div class="cm-tree">
      <el-tree :data="treeData" :props="{ label: 'label', children: 'children' }"
        node-key="key" default-expand-all highlight-current
        @node-click="onNodeClick" @node-contextmenu="onNodeContextMenu">
        <template #default="{ data }">
          <span class="cm-tree-node" :class="{ 'cm-tree-node--diff': data.isDiff, 'cm-tree-node--report': data.isReport }">
            <span class="cm-tree-icon">{{ data.icon }}</span>
            <span class="cm-tree-label">{{ data.label }}</span>
            <el-tag v-if="data.ratio" size="small" type="info" style="margin-left:4px;font-size:10px">{{ data.ratio }}%</el-tag>
            <!-- 企业节点刷新按钮（hover 显示） -->
            <el-button v-if="data.companyCode && !data.isDiff" size="small" link class="cm-refresh-btn"
              @click.stop="openRefreshDialog(data)" title="刷新该单位数据">
              🔄
            </el-button>
          </span>
        </template>
      </el-tree>
      <el-empty v-if="!treeData.length" description="暂无合并范围数据" :image-size="40" />
    </div>

    <!-- 树形右键菜单 -->
    <Teleport to="body">
      <Transition name="cm-ctx-fade">
        <div v-if="treeContextMenu.visible" class="cm-context-menu"
          :style="{ left: treeContextMenu.x + 'px', top: treeContextMenu.y + 'px' }"
          @contextmenu.prevent>
          <div class="cm-ctx-header">{{ treeContextMenu.nodeName }}</div>
          <div class="cm-ctx-divider" />
          <div class="cm-ctx-item" @click="treeCtxAggregateDirect"><span class="cm-ctx-icon">Σ</span> 直接下级汇总</div>
          <div class="cm-ctx-item" @click="treeCtxAggregateCustom"><span class="cm-ctx-icon">📊</span> 自定义汇总</div>
          <div class="cm-ctx-divider" />
          <div class="cm-ctx-item" @click="treeCtxRefresh"><span class="cm-ctx-icon">🔄</span> 刷新数据</div>
          <div class="cm-ctx-item" @click="treeCtxViewReport"><span class="cm-ctx-icon">📋</span> 查看报表</div>
          <div class="cm-ctx-item" @click="treeCtxViewNote"><span class="cm-ctx-icon">📝</span> 查看附注</div>
        </div>
      </Transition>
    </Teleport>

    <!-- 添加企业弹窗 -->
    <el-dialog v-model="showAddDialog" title="添加合并范围企业" width="500px" append-to-body>
      <el-form label-width="110px" size="small">
        <el-form-item label="企业名称" required>
          <el-input v-model="addForm.name" placeholder="输入企业全称" />
        </el-form-item>
        <el-form-item label="企业代码" required>
          <el-input v-model="addForm.code" placeholder="如 91500000MA5UQXXX0X（统一社会信用代码）" />
        </el-form-item>
        <el-form-item label="上级单位">
          <el-input v-model="addForm.parentName" placeholder="输入上级单位名称" />
        </el-form-item>
        <el-form-item label="上级单位代码">
          <el-input v-model="addForm.parentCode" placeholder="如 91500000MA5UQXXX0X" />
        </el-form-item>
        <el-form-item label="最终控制方">
          <el-input v-model="addForm.ultimateController" placeholder="如 重庆医药（集团）股份有限公司" />
        </el-form-item>
        <el-form-item label="最终控制方代码">
          <el-input v-model="addForm.ultimateControllerCode" placeholder="如 91500000203XXXXX0X" />
        </el-form-item>
        <el-form-item label="持股比例">
          <el-input-number v-model="addForm.ratio" :precision="6" :min="0" :max="100" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="doAddCompany">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- 刷新范围选择弹窗 -->
    <el-dialog v-model="showRefreshDialog" :title="`刷新 — ${refreshTarget.name}`" width="420px" append-to-body>
      <p style="font-size:13px;color:#666;margin-bottom:12px">
        选择要从项目数据中刷新的内容（从子企业单体数据重新汇总）：
      </p>
      <div class="cm-refresh-options">
        <el-checkbox v-model="refreshOptions.allReports" @change="onAllReportsChange">全部报表（6张）</el-checkbox>
        <div v-show="!refreshOptions.allReports" class="cm-refresh-sub">
          <el-checkbox v-model="refreshOptions.balance_sheet">资产负债表</el-checkbox>
          <el-checkbox v-model="refreshOptions.income_statement">利润表</el-checkbox>
          <el-checkbox v-model="refreshOptions.cash_flow_statement">现金流量表</el-checkbox>
          <el-checkbox v-model="refreshOptions.equity_statement">权益变动表</el-checkbox>
          <el-checkbox v-model="refreshOptions.cash_flow_supplement">现金流附表</el-checkbox>
          <el-checkbox v-model="refreshOptions.impairment_provision">资产减值准备表</el-checkbox>
        </div>
        <el-checkbox v-model="refreshOptions.notes">全部附注</el-checkbox>
        <el-checkbox v-model="refreshOptions.worksheet">差额表</el-checkbox>
      </div>
      <template #footer>
        <el-button @click="showRefreshDialog = false">取消</el-button>
        <el-button type="primary" @click="doRefresh" :loading="refreshing">开始刷新</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getConsolScope, getWorksheetTree } from '@/services/consolidationApi'
import { eventBus } from '@/utils/eventBus'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const loading = ref(false)
const rawTree = ref<any[]>([])
const showAddDialog = ref(false)
const addForm = reactive({ name: '', code: '', parentName: '', parentCode: '', ultimateController: '', ultimateControllerCode: '', ratio: 0 })
const manualCompanies = ref<any[]>([])

// 已有企业列表（用于上级单位下拉）
const _existingCompanies = computed(() => {
  const list: { name: string; code: string }[] = []
  function collect(node: any) {
    if (node.company_code) list.push({ name: node.company_name || node.name, code: node.company_code })
    if (node.children) for (const ch of node.children) collect(ch)
  }
  for (const root of rawTree.value) collect(root)
  for (const mc of manualCompanies.value) list.push({ name: mc.name, code: mc.code })
  return list
})
const selectedYear = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

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
    return {
      key: node.company_code || 'root',
      label: node.company_name || node.name,
      icon: children.length ? '🏢' : '🏠',
      ratio: node.shareholding,
      companyCode: node.company_code,
      children: children.length ? children : undefined,
    }
  }

  if (rawTree.value.length) {
    const root = buildNode(rawTree.value[0])
    // 追加手动添加的企业（按 parentCode 插入到对应父节点下）
    for (const mc of manualCompanies.value) {
      const mcNode: any = {
        key: mc.code, label: mc.name, icon: '🏠',
        ratio: mc.ratio, companyCode: mc.code,
        parentCode: mc.parentCode,
      }
      // 找到父节点插入
      const parentNode = mc.parentCode ? findNode(root, mc.parentCode) : null
      if (parentNode && parentNode.children) {
        // 插入到差额表之前
        const diffIdx = parentNode.children.findIndex((c: any) => c.isDiff)
        if (diffIdx >= 0) parentNode.children.splice(diffIdx, 0, mcNode)
        else parentNode.children.unshift(mcNode)
      } else {
        // 没有父节点，插入到根节点下
        const diffIdx = root.children?.findIndex((c: any) => c.isDiff) ?? -1
        if (diffIdx >= 0) root.children.splice(diffIdx, 0, mcNode)
        else if (root.children) root.children.unshift(mcNode)
      }
    }
    return [root]
  }
  return []
})

// 递归查找节点
function findNode(node: any, code: string): any {
  if (node.companyCode === code || node.key === code) return node
  if (node.children) {
    for (const ch of node.children) {
      const found = findNode(ch, code)
      if (found) return found
    }
  }
  return null
}

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
  } catch { /* ignore */ }
  finally { loading.value = false }
  // 如果后端没数据，尝试从基本信息表同步
  if (!rawTree.value.length || (rawTree.value[0]?.children?.length === 0 && !manualCompanies.value.length)) {
    await syncFromProject()
  }
}

// 从右侧基本信息表同步企业数据到树形
async function syncFromProject() {
  loading.value = true
  try {
    // 通过 API 获取已保存的基本信息表数据
    const { loadWorksheetData } = await import('@/services/consolWorksheetDataApi')
    const saved = await loadWorksheetData(projectId.value, selectedYear.value, 'info')
    const rows = saved?.rows || []
    if (Array.isArray(rows) && rows.length) {
      const companies = rows.filter((r: any) => r.company_name)
      if (companies.length) {
        // 获取项目名称作为根节点
        let rootName = '集团合并'
        let rootCode = 'root'
        try {
          const { data } = await import('@/utils/http').then(m => m.default.get(`/api/projects/${projectId.value}`, { validateStatus: (s: number) => s < 600 }))
          const p = data
          rootName = p?.client_name || p?.name || rootName
        } catch { /* ignore */ }

        // 尝试从最终控制方信息获取根节点
        const firstWithController = companies.find((r: any) => r.ultimate_controller)
        if (firstWithController) {
          rootName = firstWithController.ultimate_controller || rootName
          rootCode = firstWithController.ultimate_controller_code || rootCode
        }

        // 构建层级关系：按 parent_code 分组
        const codeMap: Record<string, any> = {}
        const allNodes: any[] = []
        for (const r of companies) {
          const node: any = {
            company_name: r.company_name,
            company_code: r.company_code,
            shareholding: r.non_common_ratio || r.common_ratio || r.no_consol_ratio || 0,
            holding_type: r.holding_type || '直接',
            indirect_holder: r.indirect_holder || '',
            parent_code: r.parent_code || '',
            children: [],
          }
          codeMap[r.company_code] = node
          allNodes.push(node)
        }

        // 构建树：有 parent_code 的挂到父节点下，否则挂到根节点
        const rootChildren: any[] = []
        for (const node of allNodes) {
          if (node.parent_code && codeMap[node.parent_code]) {
            codeMap[node.parent_code].children.push(node)
          } else {
            rootChildren.push(node)
          }
        }

        rawTree.value = [{
          company_name: rootName, company_code: rootCode,
          children: rootChildren,
        }]
        ElMessage.success(`已从基本信息表同步 ${companies.length} 家企业`)
      }
    }
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function onNodeClick(data: any) {
  // 通过事件总线通知父组件（ConsolidationIndex）
  eventBus.emit('consol-tree-select', data)
}

// ─── 树形右键菜单 ────────────────────────────────────────────────────────────
const treeContextMenu = reactive({ visible: false, x: 0, y: 0, nodeName: '', nodeData: null as any })

function onNodeContextMenu(e: MouseEvent, data: any) {
  e.preventDefault()
  e.stopPropagation()
  if (!data.companyCode || data.isDiff) return
  treeContextMenu.nodeName = data.label || ''
  treeContextMenu.nodeData = data
  setTimeout(() => {
    treeContextMenu.x = e.clientX
    treeContextMenu.y = e.clientY
    treeContextMenu.visible = true
  }, 0)
}

function closeTreeCtxMenu() { treeContextMenu.visible = false }

function treeCtxAggregateDirect() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  eventBus.emit('consol-tree-aggregate', {
    mode: 'direct', companyCode: data.companyCode, companyName: data.label
  })
}

function treeCtxAggregateCustom() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  eventBus.emit('consol-tree-aggregate', {
    mode: 'custom', companyCode: data.companyCode, companyName: data.label
  })
}

function treeCtxRefresh() {
  closeTreeCtxMenu()
  if (treeContextMenu.nodeData) openRefreshDialog(treeContextMenu.nodeData)
}

function treeCtxViewReport() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  eventBus.emit('consol-tree-select', {
    companyCode: data.companyCode, label: data.label, isReport: true, reportType: 'balance_sheet'
  })
}

function treeCtxViewNote() {
  closeTreeCtxMenu()
  const data = treeContextMenu.nodeData
  if (!data) return
  // 切换到该企业 + 切换到附注 tab
  eventBus.emit('consol-tree-select', {
    companyCode: data.companyCode, label: data.label, switchTab: 'consol_note'
  })
}

// 点击其他地方关闭
function onDocClickTree(e: MouseEvent) {
  if (!(e.target as HTMLElement)?.closest('.cm-context-menu')) closeTreeCtxMenu()
}

// ─── 刷新功能 ────────────────────────────────────────────────────────────────
const showRefreshDialog = ref(false)
const refreshing = ref(false)
const refreshTarget = reactive({ code: '', name: '' })
const refreshOptions = reactive({
  allReports: true,
  balance_sheet: true, income_statement: true, cash_flow_statement: true,
  equity_statement: true, cash_flow_supplement: true, impairment_provision: true,
  notes: true, worksheet: true,
})

function openRefreshDialog(data: any) {
  refreshTarget.code = data.companyCode || ''
  refreshTarget.name = data.label || ''
  // 重置选项
  refreshOptions.allReports = true
  refreshOptions.balance_sheet = true; refreshOptions.income_statement = true
  refreshOptions.cash_flow_statement = true; refreshOptions.equity_statement = true
  refreshOptions.cash_flow_supplement = true; refreshOptions.impairment_provision = true
  refreshOptions.notes = true; refreshOptions.worksheet = true
  showRefreshDialog.value = true
}

function onAllReportsChange(val: boolean) {
  refreshOptions.balance_sheet = val; refreshOptions.income_statement = val
  refreshOptions.cash_flow_statement = val; refreshOptions.equity_statement = val
  refreshOptions.cash_flow_supplement = val; refreshOptions.impairment_provision = val
}

async function doRefresh() {
  refreshing.value = true
  const types: string[] = []
  if (refreshOptions.allReports) {
    types.push('all_reports')
  } else {
    for (const k of ['balance_sheet','income_statement','cash_flow_statement','equity_statement','cash_flow_supplement','impairment_provision'] as const) {
      if (refreshOptions[k]) types.push(k)
    }
  }
  if (refreshOptions.notes) types.push('notes')
  if (refreshOptions.worksheet) types.push('worksheet')

  // 通知 ConsolidationIndex 执行刷新
  eventBus.emit('consol-refresh-entity', {
    companyCode: refreshTarget.code,
    companyName: refreshTarget.name,
    types,
  })

  // 模拟等待（实际由 ConsolidationIndex 处理）
  await new Promise(r => setTimeout(r, 500))
  refreshing.value = false
  showRefreshDialog.value = false
  ElMessage.success(`已发起刷新：${refreshTarget.name}（${types.length} 项）`)
}

function doAddCompany() {
  if (!addForm.name || !addForm.code) { ElMessage.warning('请填写企业名称和代码'); return }
  manualCompanies.value.push({
    name: addForm.name, code: addForm.code, ratio: addForm.ratio,
    parentCode: addForm.parentCode, ultimateController: addForm.ultimateController,
    ultimateControllerCode: addForm.ultimateControllerCode,
  })
  // 重置表单
  addForm.name = ''; addForm.code = ''; addForm.parentName = ''; addForm.parentCode = ''
  addForm.ultimateController = ''; addForm.ultimateControllerCode = ''; addForm.ratio = 0
  showAddDialog.value = false
  ElMessage.success('已添加到合并范围')
}

onMounted(() => {
  loadTree()
  document.addEventListener('click', onDocClickTree)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClickTree)
})
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
.cm-refresh-btn { opacity: 0; transition: opacity 0.15s; margin-left: auto; font-size: 11px; padding: 0 2px; }
.cm-tree-node:hover .cm-refresh-btn { opacity: 1; }
.cm-refresh-options { display: flex; flex-direction: column; gap: 8px; padding: 4px 0; }
.cm-refresh-sub { padding-left: 24px; display: flex; flex-direction: column; gap: 4px; }
.cm-nav-footer { padding: 8px 12px; border-top: 1px solid var(--gt-color-border-light, #e8e4f0); flex-shrink: 0; }

/* 树形右键菜单 */
.cm-context-menu {
  position: fixed; z-index: 10001; background: #fff;
  border-radius: 8px; box-shadow: 0 6px 24px rgba(0,0,0,0.15); padding: 6px 0; min-width: 180px;
  border: 1px solid #e8e4f0;
}
.cm-ctx-header { padding: 6px 14px; font-size: 11px; color: #999; }
.cm-ctx-divider { height: 1px; background: #f0edf5; margin: 2px 0; }
.cm-ctx-item {
  padding: 8px 14px; font-size: 13px; cursor: pointer; color: #333;
  display: flex; align-items: center; gap: 6px; transition: background 0.1s;
}
.cm-ctx-item:hover { background: #f0edf5; color: #4b2d77; }
.cm-ctx-icon { width: 18px; text-align: center; }
.cm-ctx-fade-enter-active { transition: opacity 0.1s, transform 0.1s; }
.cm-ctx-fade-leave-active { transition: opacity 0.08s; }
.cm-ctx-fade-enter-from { opacity: 0; transform: scale(0.95); }
.cm-ctx-fade-leave-to { opacity: 0; }
</style>
