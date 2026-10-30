<!--
  权限管理中心 —— 账号权限 / 角色与数据权限 / 账号角色绑定三合一

  spec: .kiro/specs/nav-grouping-and-permission-center（Task 5.1）
  Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6

  ## 为什么合并

  改造前这三块散在两个入口：`/settings/users`（账号权限）一个菜单项，
  另外两块藏在「系统设置」的两个 admin Tab 里。同一件事（"谁能看到什么"）
  要在两个页面之间来回找，管理员配到一半会不确定该在哪里操作。

  ## 三处本仓适配（参考仓 D:\java\zt-gt-plan 的同名文件不能照抄）

  | 参考仓 | 本仓 |
  |---|---|
  | `@/views/RoleManagement.vue` | `@/components/system/RoleDataScopeManager.vue` |
  | `@/views/UserRoleManagement.vue` | `@/components/system/UserRoleBindingPanel.vue` |
  | Tab name `roles` | Tab name `role-scope` |

  前两项在本仓**不存在**（本仓对应物在 `components/system/` 下），照抄必编译失败。
  第三项对齐 `SystemSettings.vue` 既有的 `name="role-scope"` 命名 —— 那两个 Tab
  由 wave 5 迁出，沿用同名可减少认知切换，也让 wave 5 的迁移是"换宿主"而非"改协议"。

  ## 懒加载（Requirement 5.6）

  三个子组件都在 `onMounted` 里发请求（`listUsers` / `listProjects` / 角色列表）。
  若一次性全挂载，进页面就是 5+ 个并发请求，其中两个 Tab 的数据用户可能压根不看。
  故用 `loaded` 标记：只有被激活过的 Tab 才挂载子组件，且挂载后不再卸载
  （切回来不重新请求）。
-->
<template>
  <div class="gt-perm-center gt-fade-in">
    <el-tabs v-model="activeTab" class="gt-perm-center__tabs">
      <el-tab-pane label="账号权限" name="users">
        <UserManagement v-if="loaded.users" />
      </el-tab-pane>
      <el-tab-pane label="角色与数据权限" name="role-scope">
        <RoleDataScopeManager v-if="loaded['role-scope']" />
      </el-tab-pane>
      <el-tab-pane label="账号角色绑定" name="user-roles">
        <UserRoleBindingPanel v-if="loaded['user-roles']" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import UserManagement from '@/views/UserManagement.vue'
import RoleDataScopeManager from '@/components/system/RoleDataScopeManager.vue'
import UserRoleBindingPanel from '@/components/system/UserRoleBindingPanel.vue'

defineOptions({ name: 'PermissionCenter' })

type TabKey = 'users' | 'role-scope' | 'user-roles'
const VALID_TABS: TabKey[] = ['users', 'role-scope', 'user-roles']

const route = useRoute()
const router = useRouter()

/**
 * 从 query.tab 解析 Tab，非法值回退到 users（Requirement 5.4）。
 *
 * 不能直接 `activeTab = route.query.tab` —— query 是用户可随手改的，
 * 写进 `el-tabs` 的 v-model 后会得到"三个 Tab 都不高亮、内容区空白"的
 * 静默坏页面（不报错，故更难发现）。
 */
function resolveTab(raw: unknown): TabKey {
  return VALID_TABS.includes(raw as TabKey) ? (raw as TabKey) : 'users'
}

const activeTab = ref<TabKey>(resolveTab(route.query.tab))

/** 懒加载标记：仅首次切到某 Tab 时挂载其子组件（Requirement 5.6）。 */
const loaded = reactive<Record<TabKey, boolean>>({
  'users': false,
  'role-scope': false,
  'user-roles': false,
})
loaded[activeTab.value] = true

onMounted(() => {
  loaded[activeTab.value] = true
})

/**
 * Tab 切换 → 回写 `?tab=`（Requirement 5.5），使刷新与分享链接仍落在同一 Tab。
 *
 * 用 `replace` 而非 `push`：Tab 切换不是"导航"，压进 history 会让浏览器返回键
 * 在同一页面内反复横跳。`route.query.tab !== tab` 的守卫防止与下面那个
 * watch 形成回环。
 */
watch(activeTab, (tab) => {
  loaded[tab] = true
  if (route.query.tab !== tab) {
    router.replace({ query: { ...route.query, tab } })
  }
})

/** 外部改 query（如从别处带 `?tab=` 跳进来）时同步激活态。 */
watch(
  () => route.query.tab,
  (raw) => {
    const t = resolveTab(raw)
    if (t !== activeTab.value) activeTab.value = t
  },
)
</script>

<style scoped>
.gt-perm-center {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.gt-perm-center__tabs {
  height: 100%;
}
/* 子页面自带 GtPageHeader，这里让 Tab 内容区自然铺满 */
.gt-perm-center__tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
}
</style>
