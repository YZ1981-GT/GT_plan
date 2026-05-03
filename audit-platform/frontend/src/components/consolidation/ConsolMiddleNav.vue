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

    <!-- 添加企业弹窗 -->
    <el-dialog v-model="showAddDialog" title="添加合并范围企业" width="500px" append-to-body>
      <el-form label-width="110px" size="small">
        <el-form-item label="企业名称" required>
          <el-input v-model="addForm.name" placeholder="输入企业全称" />
        </el-form-item>
        <el-form-item label="企业代码" required>
          <el-input v-model="addForm.code" placeholder="如 CQ001" />
        </el-form-item>
        <el-form-item label="上级单位">
          <el-select v-model="addForm.parentCode" size="small" style="width:100%" placeholder="选择上级单位" filterable clearable>
            <el-option v-for="c in existingCompanies" :key="c.code" :label="`${c.name} (${c.code})`" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="上级单位代码">
          <el-input v-model="addForm.parentCode" placeholder="自动填充或手动输入" disabled />
        </el-form-item>
        <el-form-item label="最终控制方">
          <el-input v-model="addForm.ultimateController" placeholder="如 重庆医药集团" />
        </el-form-item>
        <el-form-item label="最终控制方代码">
          <el-input v-model="addForm.ultimateControllerCode" placeholder="如 ROOT" />
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
const addForm = reactive({ name: '', code: '', parentCode: '', ultimateController: '', ultimateControllerCode: '', ratio: 0 })
const manualCompanies = ref<any[]>([])

// 已有企业列表（用于上级单位下拉）
const existingCompanies = computed(() => {
  const list: { name: string; code: string }[] = []
  function collect(node: any) {
    if (node.company_code) list.push({ name: node.company_name || node.name, code: node.company_code })
    if (node.children) for (const ch of node.children) collect(ch)
  }
  for (const root of rawTree.value) collect(root)
  for (const mc of manualCompanies.value) list.push({ name: mc.name, code: mc.code })
  return list
})
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
  } catch { rawTree.value = [] }
  finally { loading.value = false }
}

function onNodeClick(data: any) {
  // 通过自定义事件通知父组件（ConsolidationIndex）
  window.dispatchEvent(new CustomEvent('consol-tree-select', { detail: data }))
}

function doAddCompany() {
  if (!addForm.name || !addForm.code) { ElMessage.warning('请填写企业名称和代码'); return }
  manualCompanies.value.push({
    name: addForm.name, code: addForm.code, ratio: addForm.ratio,
    parentCode: addForm.parentCode, ultimateController: addForm.ultimateController,
    ultimateControllerCode: addForm.ultimateControllerCode,
  })
  // 重置表单
  addForm.name = ''; addForm.code = ''; addForm.parentCode = ''
  addForm.ultimateController = ''; addForm.ultimateControllerCode = ''; addForm.ratio = 0
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
.cm-nav-footer { padding: 8px 12px; border-top: 1px solid var(--gt-color-border-light, #e8e4f0); flex-shrink: 0; }
</style>
