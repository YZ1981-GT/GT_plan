<!--
  UserProjectRoleTree.vue — 用户 → 项目 → 角色 三层树
  （project-data-permission-isolation Task 6.2）

  职责：**只读**展示账号的跨项目角色分布，并标注数据权限实际让它看到哪些项目。
  仅 admin 可见（外层 v-if="isAdmin"）。

  🔴 **四个容易写错的地方，都在代码里做了处理**：

  1. **懒加载两段式**：根层只拉账号（`has_children` 由后端一次聚合算出），
     展开某账号时才拉它的子树。6000 账号规模下不能一次拉全量层级。
     `el-tree` 的 `lazy` + `:load` 必须配 `node-key`，否则展开状态无法保持。

  2. **`has_children=false` 的账号必须是叶子**（`isLeaf: true`）。若统一给
     `false`，前端会给无项目账号也画展开箭头，点开后拿到空数组 ⇒
     el-tree 留下一个**永远转圈的加载态**（它认为数据还没到）。

  3. **`out_of_scope` 只是视觉标记，不是过滤**。那些项目**照常显示**，
     只是加"不在可见范围"的提示 —— 这个"配了角色却看不到"的矛盾状态
     正是本功能要暴露给管理员的东西。若把它们过滤掉，管理员就再也发现
     不了配置矛盾。

  4. **搜索走后端而非前端过滤**。根层是分页的，前端过滤只能过滤当前页 ⇒
     搜索结果会漏掉其他页的匹配项，而且 total 也不对。

  ⚠️ 本组件**不提供任何写操作**（Req 6.1）。要改项目角色分配，走"前往项目
     成员管理"跳转（Req 6.2），不在树上新建写路径。
-->
<template>
  <div class="gt-uprt">
    <!-- 工具栏 -->
    <div class="gt-uprt-toolbar">
      <span class="gt-uprt-stats">
        账号总数：<span class="gt-amt">{{ total }}</span>
      </span>
      <div class="gt-uprt-spacer" />
      <el-input
        v-model="keyword"
        size="small"
        placeholder="搜索用户名 / 邮箱"
        clearable
        class="gt-uprt-search"
        @keyup.enter="onSearch"
        @clear="onSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button size="small" round :loading="loading" @click="reload">
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <!-- 树 -->
    <el-tree
      ref="treeRef"
      :key="treeKey"
      class="gt-uprt-tree"
      lazy
      :load="loadNode"
      :props="treeProps"
      node-key="nodeKey"
      :expand-on-click-node="false"
      empty-text="暂无账号"
    >
      <template #default="{ data }">
        <!-- 第 1 层：账号 -->
        <span v-if="data.kind === 'user'" class="gt-uprt-node">
          <el-icon class="gt-uprt-avatar"><UserFilled /></el-icon>
          <span class="gt-uprt-name">{{ data.raw.username }}</span>
          <span v-if="data.raw.full_name" class="gt-uprt-sub">
            （{{ data.raw.full_name }}）
          </span>
          <el-tag size="small" :type="roleTagType(data.raw.system_role)">
            {{ systemRoleLabel(data.raw.system_role) }}
          </el-tag>
          <el-tag v-if="!data.raw.is_active" size="small" type="info">已停用</el-tag>
          <!--
            数据权限范围标签：**展开后才有值**（它来自子树接口）。
            未展开时不显示占位，避免管理员误以为"这个账号没有范围"。
          -->
          <el-tag
            v-if="scopeLabelOf(data.raw.id)"
            size="small"
            type="warning"
            effect="plain"
          >
            {{ scopeLabelOf(data.raw.id) }}
          </el-tag>
          <span v-if="!data.raw.has_children" class="gt-uprt-empty-hint">
            未分配任何项目
          </span>
        </span>

        <!-- 第 2 层：项目 -->
        <span v-else-if="data.kind === 'project'" class="gt-uprt-node">
          <el-icon class="gt-uprt-ico"><Folder /></el-icon>
          <span class="gt-uprt-name">{{ data.raw.name }}</span>
          <span class="gt-uprt-sub">{{ data.raw.client_name }}</span>
          <el-tag size="small" effect="plain">
            {{ projectStatusLabel(data.raw.status) }}
          </el-tag>
          <!--
            🔴 out_of_scope 的提示措辞要说清「为什么」——
            只画个红点管理员不知道是数据错了还是权限配置如此。
          -->
          <el-tooltip
            v-if="data.raw.out_of_scope"
            content="该账号在此项目有角色，但数据权限范围未覆盖此项目，实际无法访问"
            placement="top"
          >
            <el-tag size="small" type="danger" effect="dark">
              <el-icon style="margin-right: 2px"><WarningFilled /></el-icon>
              不在可见范围
            </el-tag>
          </el-tooltip>
        </span>

        <!-- 第 3 层：角色（叶子） -->
        <span v-else class="gt-uprt-node">
          <el-icon class="gt-uprt-ico"><Postcard /></el-icon>
          <el-tag size="small" type="success">
            {{ projectRoleLabel(data.raw.role) }}
          </el-tag>
          <el-tag size="small" :type="levelTagType(data.raw.permission_level)">
            {{ permissionLevelLabel(data.raw.permission_level) }}
          </el-tag>
          <span v-if="validityText(data.raw)" class="gt-uprt-sub">
            {{ validityText(data.raw) }}
          </span>
          <span v-if="data.raw.scope_cycles" class="gt-uprt-sub">
            循环：{{ data.raw.scope_cycles }}
          </span>
          <span v-if="data.raw.scope_accounts" class="gt-uprt-sub">
            科目：{{ data.raw.scope_accounts }}
          </span>
        </span>
      </template>
    </el-tree>

    <!-- 分页（根层） -->
    <div v-if="total > pageSize" class="gt-uprt-pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        small
        @current-change="reload"
      />
    </div>

    <!-- 只读边界提示（Req 6.2） -->
    <div class="gt-uprt-footer">
      <el-icon><InfoFilled /></el-icon>
      本视图为只读。如需调整账号的项目角色，请前往「项目 - 成员管理」。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Folder,
  InfoFilled,
  Postcard,
  Refresh,
  Search,
  UserFilled,
  WarningFilled,
} from '@element-plus/icons-vue'

import {
  getUserSubtree,
  listUserNodes,
  type ProjectNode,
  type RoleNode,
  type UserNode,
} from '@/services/projectRoleTreeApi'

const PAGE_SIZE = 50

const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(PAGE_SIZE)
const total = ref(0)
const treeRef = ref()

/**
 * 用于强制重建 el-tree。
 *
 * ⚠️ el-tree 在 lazy 模式下**没有公开的"重新加载根层"API**。改 key 强制
 *    重建是本仓既有做法 —— 直接调 `treeRef.value.updateKeyChildren(null, ...)`
 *    对根层无效（root 节点不在 nodeKey 体系里）。
 */
const treeKey = ref(0)

/** 已展开账号的数据权限范围标签（`user_id` → 中文标签）。 */
const scopeLabels = ref<Record<string, string>>({})

const treeProps = {
  label: 'label',
  children: 'children',
  isLeaf: 'isLeaf',
} as const

interface TreeNodeData {
  nodeKey: string
  kind: 'user' | 'project' | 'role'
  isLeaf?: boolean
  raw: UserNode | ProjectNode | RoleNode
}

function scopeLabelOf(userId: string): string {
  return scopeLabels.value[userId] || ''
}

/**
 * el-tree 的懒加载回调。
 *
 * 三段：
 *   - `node.level === 0` → 根层账号（走分页 + 搜索）
 *   - `kind === 'user'`  → 该账号的项目层（顺带记下 scope 标签）
 *   - `kind === 'project'` → 该项目下的唯一角色节点
 */
async function loadNode(node: any, resolve: (d: TreeNodeData[]) => void) {
  try {
    if (node.level === 0) {
      loading.value = true
      const res = await listUserNodes({
        search: keyword.value.trim() || undefined,
        page: page.value,
        page_size: pageSize.value,
      })
      total.value = res.total
      resolve(
        res.items.map((u) => ({
          nodeKey: `u:${u.id}`,
          kind: 'user' as const,
          // 🔴 无项目账号必须标成叶子，否则展开箭头点开是永久加载态
          isLeaf: !u.has_children,
          raw: u,
        })),
      )
      return
    }

    const data = node.data as TreeNodeData

    if (data.kind === 'user') {
      const u = data.raw as UserNode
      const sub = await getUserSubtree(u.id)
      scopeLabels.value = {
        ...scopeLabels.value,
        [u.id]: sub.effective_data_scope_label,
      }
      resolve(
        sub.projects.map((p) => ({
          nodeKey: `p:${u.id}:${p.project_id}`,
          kind: 'project' as const,
          isLeaf: false,
          raw: p,
        })),
      )
      return
    }

    if (data.kind === 'project') {
      const p = data.raw as ProjectNode
      // project_users 对 (project_id, user_id) 有唯一索引 ⇒ 恒好一个角色节点
      resolve([
        {
          nodeKey: `r:${data.nodeKey}`,
          kind: 'role' as const,
          isLeaf: true,
          raw: p.role,
        },
      ])
      return
    }

    resolve([])
  } catch (e: any) {
    // ⚠️ 失败时 resolve 空数组而不是不调 resolve —— 后者会让节点永久转圈
    resolve([])
    const status = e?.response?.status
    if (status === 403) {
      ElMessage.error('无权限查看用户项目角色树（仅管理员可用）')
    } else if (status === 404) {
      ElMessage.warning('该账号已不存在或已被删除')
    } else {
      ElMessage.error(e?.message || '加载用户项目角色树失败')
    }
  } finally {
    loading.value = false
  }
}

function reload() {
  scopeLabels.value = {}
  treeKey.value += 1
}

function onSearch() {
  page.value = 1
  reload()
}

// ─── 中文标签映射（Req 4.8 全中文化） ────────────────────────────────────────

/**
 * ⚠️ 所有映射都用 `?? 原值` 兜底而非抛错/显示空白：
 *    库里可能存在后端 ORM 枚举尚未收录的历史值（本仓 ProjectUserRole 就因
 *    V109 补过 eqcr）。显示原始英文值虽不美观，但比显示空白或崩掉好 ——
 *    管理员至少知道"这里有个值我不认识"。
 */
const SYSTEM_ROLE_LABELS: Record<string, string> = {
  admin: '系统管理员',
  partner: '合伙人',
  manager: '项目经理',
  // 🔴 site_lead 是 `UserRole` 的第 8 个值（迁移 V158 补入 DB userrole 枚举）。
  //    缺了它，上面 `?? v` 的兜底会把裸英文 `site_lead` 显示给管理员
  //    （实测截图确认过）。⚠️ manager=「项目经理」、site_lead=「现场经理」
  //    是两个不同角色，两个中文名不可互换。
  site_lead: '现场经理',
  auditor: '审计员',
  qc: '质控',
  eqcr: 'EQCR 复核',
  readonly: '只读',
}

// ⚠️ **刻意不含 `site_lead`** —— `ProjectUserRole` 枚举实测只有 6 个值
//    （partner/manager/auditor/qc/eqcr/readonly），没有 site_lead。
//    在这里加它就是永远命不中的死代码。项目级的「现场负责人」是
//    `project_members.role = 'field_lead'`，走的是另一张表，不在本映射内。
const PROJECT_ROLE_LABELS: Record<string, string> = {
  partner: '签字合伙人',
  manager: '项目经理',
  auditor: '审计员',
  qc: '质控',
  eqcr: 'EQCR 复核',
  readonly: '只读',
}

const PERMISSION_LEVEL_LABELS: Record<string, string> = {
  edit: '可编辑',
  review: '可复核',
  readonly: '只读',
}

const PROJECT_STATUS_LABELS: Record<string, string> = {
  created: '已创建',
  planning: '计划中',
  execution: '执行中',
  completion: '完成阶段',
  reporting: '报告阶段',
  archived: '已归档',
}

function systemRoleLabel(v: string): string {
  return SYSTEM_ROLE_LABELS[v] ?? v
}
function projectRoleLabel(v: string): string {
  return PROJECT_ROLE_LABELS[v] ?? v
}
function permissionLevelLabel(v: string): string {
  return PERMISSION_LEVEL_LABELS[v] ?? v
}
function projectStatusLabel(v: string): string {
  return PROJECT_STATUS_LABELS[v] ?? v
}

function roleTagType(v: string): string {
  if (v === 'admin') return 'danger'
  if (v === 'partner') return 'warning'
  return 'info'
}

function levelTagType(v: string): string {
  if (v === 'edit') return 'warning'
  if (v === 'review') return 'primary'
  return 'info'
}

/** 有效期文案。两端都空时返回空串（不显示"—— ~ ——"这种噪声）。 */
function validityText(r: RoleNode): string {
  if (!r.valid_from && !r.valid_to) return ''
  return `有效期：${r.valid_from || '不限'} ~ ${r.valid_to || '不限'}`
}
</script>

<style scoped>
.gt-uprt {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-uprt-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-uprt-spacer {
  flex: 1;
}

.gt-uprt-search {
  width: 220px;
}

.gt-uprt-stats {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.gt-amt {
  font-weight: 600;
  color: var(--el-color-primary);
}

.gt-uprt-tree {
  min-height: 200px;
}

.gt-uprt-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.gt-uprt-avatar,
.gt-uprt-ico {
  color: var(--el-color-primary);
}

.gt-uprt-name {
  font-weight: 500;
}

.gt-uprt-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.gt-uprt-empty-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  font-style: italic;
}

.gt-uprt-pager {
  display: flex;
  justify-content: flex-end;
}

.gt-uprt-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-top: 4px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
