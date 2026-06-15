<template>
  <div class="gt-projects gt-fade-in">
    <!-- 紧凑头部 -->
    <div class="gt-projects-header">
      <h2 class="gt-projects-title">项目列表</h2>
      <div class="gt-projects-actions">
        <el-button type="primary" size="small" @click="goToCreateProject">
          <el-icon><Plus /></el-icon> 新建项目
        </el-button>
        <el-button size="small" plain @click="showBatchImport = true">
          <el-icon><Upload /></el-icon> 批量建项
        </el-button>
        <el-button size="small" text @click="$router.push('/projects')">
          返回三栏
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="gt-projects-filter-bar">
      <el-radio-group v-model="viewMode" size="small" style="margin-right: 12px">
        <el-radio-button value="list">列表</el-radio-button>
        <el-radio-button value="client">按客户</el-radio-button>
        <el-radio-button value="tree">树形</el-radio-button>
      </el-radio-group>
      <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width: 120px">
        <el-option label="活跃" value="active" />
        <el-option label="已归档" value="archived" />
        <el-option label="全部" value="" />
      </el-select>
      <el-select v-model="filterTag" placeholder="标签" clearable size="small" style="width: 120px; margin-left: 8px">
        <el-option v-for="t in availableTags" :key="t" :label="t" :value="t" />
      </el-select>
      <el-input v-model="searchText" placeholder="搜索项目/客户..." clearable size="small" style="width: 200px; margin-left: 8px" />
      <span style="margin-left: auto; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">共 {{ projects.length }} 个项目</span>
    </div>

    <!-- 列表视图 -->
    <el-table
      v-if="viewMode === 'list'"
      :data="projects"
      v-loading="loading"
      stripe
      border
      size="small"
      :header-cell-style="{ fontWeight: 600, background: 'var(--gt-color-primary-bg, #f4f0fa)' }"
      empty-text="暂无项目，点击上方「新建项目」开始"
      style="width: 100%"
      @row-click="(row) => openProject(row.id)"
      :row-style="{ cursor: 'pointer' }"
    >
      <el-table-column prop="name" label="项目名称" min-width="220">
        <template #default="{ row }">
          <div style="display: flex; align-items: center; gap: 6px">
            <span class="project-dot" :class="'dot-' + (row.status || 'created')"></span>
            <span style="font-weight: 500">{{ getProjectDisplayName(row, projects, consolidatedKeys) || '—' }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="short_name" label="简称" width="120">
        <template #default="{ row }">
          <span style="color: var(--gt-color-primary)">{{ row.short_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="client_name" label="客户名称" min-width="180">
        <template #default="{ row }">
          <span class="gt-text-secondary">{{ row.client_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="project_type" label="项目类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getProjectTypeTag(row.project_type)" size="small" effect="light" round>
            {{ getProjectTypeLabel(row.project_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getStatusTag(row.status)" size="small" effect="plain" round>
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="120" align="center">
        <template #default="{ row }">
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">{{ formatDate(row.created_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click.stop="openImport(row.id)">账套导入</el-button>
          <el-button type="primary" size="small" text @click.stop="openProject(row.id)">进入</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 按客户分组视图 -->
    <div v-else-if="viewMode === 'client'" v-loading="loading">
      <el-collapse v-if="clientGroups.length > 0">
        <el-collapse-item v-for="group in clientGroups" :key="group.client" :name="group.client">
          <template #title>
            <span style="font-weight: 600; color: var(--gt-color-primary)">{{ group.client }}</span>
            <el-tag size="small" style="margin-left: 8px">{{ group.projects.length }} 个项目</el-tag>
          </template>
          <div v-for="p in group.projects" :key="p.id" class="gt-client-project-item" @click="openProject(p.id)">
            <span class="project-dot" :class="'dot-' + (p.status || 'created')"></span>
            <span style="flex: 1; font-weight: 500">{{ p.short_name || p.name }}</span>
            <el-tag :type="getStatusTag(p.status)" size="small" effect="plain" round>{{ getStatusLabel(p.status) }}</el-tag>
            <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 12px">{{ formatDate(p.created_at) }}</span>
            <el-button type="primary" size="small" text style="margin-left: 8px" @click.stop="openProject(p.id)">进入</el-button>
          </div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else description="暂无项目" />
    </div>

    <!-- 树形视图（集团架构） -->
    <div v-else-if="viewMode === 'tree'" v-loading="treeLoading">
      <el-empty v-if="!treeLoading && treeError" :description="treeError" :image-size="120">
        <el-button type="primary" @click="loadTree">重试</el-button>
      </el-empty>

      <el-empty
        v-else-if="!treeLoading && !hasAnyTreeData"
        description="暂无集团架构数据"
        :image-size="120"
      >
        <template #description>
          <p style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-sm)">
            还没有填写企业代码的项目
          </p>
          <p style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs)">
            在项目中维护企业代码 / 上级企业代码 / 最终控制方代码后即可展示集团树
          </p>
        </template>
      </el-empty>

      <template v-else>
        <!-- 无搜索匹配 -->
        <el-empty
          v-if="searchText.trim() && !hasSearchMatch"
          description="未找到匹配企业"
          :image-size="100"
        />

        <template v-else>
          <!-- 每个 ultimate 分组一棵集团树 -->
          <div v-for="tree in trees" :key="tree.ultimateCode" class="gt-tree-card">
            <div class="gt-tree-root">
              <div class="gt-tree-root-avatar">
                <el-icon :size="18"><OfficeBuilding /></el-icon>
              </div>
              <div class="gt-tree-root-info">
                <span class="gt-tree-root-name">{{ tree.ultimateName || '最终控制方' }}</span>
                <span class="gt-tree-root-code">{{ tree.ultimateCode || '—' }}</span>
              </div>
              <el-tag size="small" effect="light" round>最终控制方</el-tag>
            </div>
            <el-tree
              :ref="(el: any) => registerTreeRef(tree.ultimateCode, el)"
              class="gt-tree"
              :data="tree.children"
              node-key="id"
              :props="treeProps"
              :filter-node-method="filterNodeMethod"
              :expand-on-click-node="false"
              default-expand-all
              @node-click="onTreeNodeClick"
            >
              <template #default="{ data }">
                <span class="gt-node" :class="nodeClass(data)">
                  <span class="gt-node-name"><template v-for="(seg, i) in hlSegs(data.companyName || data.label)" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <span class="gt-node-code"><template v-for="(seg, i) in hlSegs(data.companyCode || '—')" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <el-tag :type="getStatusTag(data.status)" size="small" effect="plain" round>
                    {{ getStatusLabel(data.status) }}
                  </el-tag>
                  <span v-if="formatShareholding(data.shareholding)" class="gt-share-badge">{{ formatShareholding(data.shareholding) }}</span>
                  <el-tag v-if="consolMethodLabel(data.consolMethod)" class="gt-method-tag" size="small" effect="plain" round>{{ consolMethodLabel(data.consolMethod) }}</el-tag>
                  <el-tag v-if="data.isDetached" type="warning" size="small" effect="plain" round>脱挂</el-tag>
                  <el-tag v-if="data.isCycleBreak" type="danger" size="small" effect="plain" round>循环引用</el-tag>
                </span>
              </template>
            </el-tree>
          </div>

          <!-- 独立节点分组 -->
          <div v-if="independents.length > 0" class="gt-tree-card gt-tree-card--indep">
            <div class="gt-tree-root gt-tree-root--indep">
              <div class="gt-tree-root-avatar gt-tree-root-avatar--indep">
                <el-icon :size="18"><Document /></el-icon>
              </div>
              <div class="gt-tree-root-info">
                <span class="gt-tree-root-name">独立节点</span>
                <span class="gt-tree-root-code">无最终控制方或缺企业代码</span>
              </div>
            </div>
            <el-tree
              :ref="(el: any) => registerTreeRef('__independent__', el)"
              class="gt-tree"
              :data="independents"
              node-key="id"
              :props="treeProps"
              :filter-node-method="filterNodeMethod"
              :expand-on-click-node="false"
              default-expand-all
              @node-click="onTreeNodeClick"
            >
              <template #default="{ data }">
                <span class="gt-node">
                  <span class="gt-node-name"><template v-for="(seg, i) in hlSegs(data.companyName || data.label)" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <span class="gt-node-code"><template v-for="(seg, i) in hlSegs(data.companyCode || '—')" :key="i"><span v-if="seg.match" class="gt-hl">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
                  <el-tag :type="getStatusTag(data.status)" size="small" effect="plain" round>
                    {{ getStatusLabel(data.status) }}
                  </el-tag>
                  <el-tag v-if="data.hasNoCompanyCode" type="info" size="small" effect="plain" round>缺代码</el-tag>
                </span>
              </template>
            </el-tree>
          </div>
        </template>
      </template>
    </div>

    <!-- 批量建项弹窗 -->
    <BatchImportDialog
      v-model="showBatchImport"
      @success="loadProjectList"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects } from '@/services/commonApi'
import { Plus, Upload, OfficeBuilding, Document } from '@element-plus/icons-vue'
import { getProjectDisplayName, buildConsolidatedKeySet } from '@/utils/project_display'
import BatchImportDialog from '@/components/wizard/BatchImportDialog.vue'
import { useGroupTree, highlightSegments, consolMethodLabel, formatShareholding, type TreeNode } from '@/composables/useGroupTree'

const router = useRouter()
const loading = ref(false)
const projects = ref<any[]>([])
const showBatchImport = ref(false)

// 预计算合并项目 key 集合，避免每行 O(N) 扫描
const consolidatedKeys = computed(() => buildConsolidatedKeySet(projects.value))

// ─── 视图模式（复用 useGroupTree 的持久化 viewMode，key: gt-project-view-mode）───
const {
  trees,
  independents,
  loading: treeLoading,
  error: treeError,
  searchQuery: treeSearchQuery,
  hasTrees,
  hasSearchMatch,
  viewMode,
  fetchTree,
  filterNode,
} = useGroupTree()

const filterStatus = ref('')
const filterTag = ref('')
const searchText = ref('')
const availableTags = ref(['年审', '季审', '上市准备', '内审', '专项', '税审', '国企', '上市公司'])

// 按客户分组
const clientGroups = computed(() => {
  const map = new Map<string, any[]>()
  for (const p of projects.value) {
    const key = p.client_name || '未归类'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(p)
  }
  return [...map.entries()].map(([client, items]) => ({ client, projects: items }))
})

onMounted(() => {
  loadProjectList()
  // 持久化模式恢复为树形时，挂载即加载树
  if (viewMode.value === 'tree') loadTree()
})

async function loadProjectList() {
  loading.value = true
  try {
    projects.value = await listProjects()
  } catch { /* ignore */ }
  finally { loading.value = false }
}

// ─── 树形视图 ────────────────────────────────────────────────────────────────
const treeProps = { label: 'label', children: 'children' }
let treeLoaded = false

function loadTree() {
  // Projects.vue 树形视图展示全部项目（不限合并），按 ultimate 分组
  treeLoaded = true
  fetchTree('all')
}

const hasAnyTreeData = computed(() => hasTrees.value || independents.value.length > 0)

// 切换到树形视图时懒加载
watch(viewMode, (mode) => {
  if (mode === 'tree' && !treeLoaded) loadTree()
})

// 搜索框（searchText）驱动树形过滤（高亮完整逻辑见 Task 5.1）
const treeRefs = new Map<string, any>()
function registerTreeRef(key: string, el: any) {
  if (el) treeRefs.set(key, el)
  else treeRefs.delete(key)
}
watch(searchText, (q) => {
  treeSearchQuery.value = q
  if (viewMode.value === 'tree') {
    treeRefs.forEach((tree) => tree?.filter?.(q))
  }
})

function filterNodeMethod(value: string, data: any): boolean {
  return filterNode(value, data as TreeNode)
}

function nodeClass(data: TreeNode) {
  return {
    'gt-node--detached': data.isDetached,
    'gt-node--cycle': data.isCycleBreak,
  }
}

// 搜索高亮分段（企业名称 + 代码，大小写不敏感）——搜索串取 searchText
function hlSegs(text: string | null | undefined) {
  return highlightSegments(text, searchText.value)
}

function onTreeNodeClick(data: TreeNode) {
  if (data?.id) openProject(data.id)
}

function goToCreateProject() { router.push('/projects/new') }
function openProject(id: string) { router.push({ name: 'ProjectEntry', params: { projectId: id } }) }
function openImport(id: string) {
  router.push({ path: `/projects/${id}/ledger-import` })
}

function formatDate(d: string) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function getProjectTypeTag(t: string) {
  return ({ annual: '', special: 'warning', ipo: 'success', internal_control: 'info' } as any)[t] || ''
}
function getProjectTypeLabel(t: string) {
  return ({ annual: '年度审计', special: '专项审计', ipo: 'IPO审计', internal_control: '内控审计' } as any)[t] || t || '—'
}
function getStatusTag(s: string) {
  return ({ created: 'info', planning: 'warning', execution: '', completion: 'success', archived: 'info' } as any)[s] || ''
}
function getStatusLabel(s: string) {
  return ({ created: '已创建', planning: '计划中', execution: '执行中', completion: '已完成', archived: '已归档' } as any)[s] || s || '—'
}
</script>

<style scoped>
.gt-projects {
  max-width: 1400px;
  margin: 0 auto;
  padding: 16px 24px;
}
.gt-projects-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.gt-projects-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
  margin: 0;
}
.gt-projects-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-projects-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-radius: 8px;
}

/* 状态圆点 */
.project-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-created { background: var(--gt-color-text-tertiary); }
.dot-planning { background: var(--gt-color-wheat); }
.dot-execution { background: var(--gt-color-primary); animation: gtPulse 2s ease-in-out infinite; }
.dot-completion { background: var(--gt-color-success); }
.dot-archived { background: var(--gt-color-border); }

@keyframes gtPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 按客户分组 - 项目行 */
.gt-client-project-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
  transition: background 0.15s;
}
.gt-client-project-item:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}
.gt-client-project-item:last-child {
  border-bottom: none;
}

/* ── 集团树形视图 ── */
.gt-tree-card {
  background: var(--gt-color-bg-white, #fff);
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--gt-color-border-purple, #d8b8ee);
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}
.gt-tree-root {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-bottom: 1px solid var(--gt-color-border-purple, #d8b8ee);
}
.gt-tree-root--indep {
  background: var(--gt-color-fill-light, #f5f5f5);
}
.gt-tree-root-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  flex-shrink: 0;
  background: linear-gradient(135deg, #4b2d77, #7c5caa);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gt-color-text-inverse, #fff);
}
.gt-tree-root-avatar--indep {
  background: linear-gradient(135deg, #909399, #c0c4cc);
}
.gt-tree-root-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.gt-tree-root-name {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
}
.gt-tree-root-code {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  font-family: var(--gt-font-mono, monospace);
}
.gt-tree {
  padding: 8px 12px 12px;
}
.gt-node {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: var(--gt-font-size-sm);
}
.gt-node-name {
  color: var(--gt-color-text);
  font-weight: 500;
}
.gt-node-code {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
  font-family: var(--gt-font-mono, monospace);
}
.gt-node--detached .gt-node-name {
  color: var(--gt-color-warning, #e6a23c);
}
.gt-node--cycle .gt-node-name {
  color: var(--gt-color-danger, #f56c6c);
}

/* 搜索匹配高亮：琥珀黄底深色字（行 hover 紫底时仍清晰，禁用 Element 蓝） */
.gt-hl {
  background: #ffe9a8;
  color: #5a3d00;
  font-weight: 700;
  border-radius: 2px;
  padding: 0 1px;
}

/* 持股比例 badge + 合并方式 tag（紫色系，Task 14.1）—— 禁用 Element 默认蓝 */
.gt-share-badge {
  display: inline-flex; align-items: center;
  height: 20px; padding: 0 7px;
  font-size: var(--gt-font-size-xs); font-weight: 600; line-height: 1;
  color: var(--gt-color-text-inverse);
  background: linear-gradient(135deg, #4b2d77, #7c5caa);
  border-radius: 10px;
  font-family: var(--gt-font-mono, monospace);
}
.gt-method-tag.el-tag {
  --el-tag-text-color: var(--gt-color-primary);
  --el-tag-bg-color: var(--gt-color-primary-bg);
  --el-tag-border-color: var(--gt-color-border-purple);
  color: var(--gt-color-primary);
  background-color: var(--gt-color-primary-bg);
  border-color: var(--gt-color-border-purple);
}

/* el-tag primary 紫色覆盖（禁用 Element 默认蓝 #409eff） */
:deep(.el-tag--primary) {
  --el-tag-text-color: var(--gt-color-primary);
  --el-tag-bg-color: var(--gt-color-primary-bg);
  --el-tag-border-color: var(--gt-color-border-purple);
  color: var(--gt-color-primary);
  background-color: var(--gt-color-primary-bg);
  border-color: var(--gt-color-border-purple);
}

/* el-tree hover 用紫色而非默认蓝 */
:deep(.el-tree-node__content:hover) {
  background-color: var(--gt-color-primary-bg);
}
:deep(.el-tree-node:focus > .el-tree-node__content) {
  background-color: var(--gt-color-primary-bg);
}
</style>
