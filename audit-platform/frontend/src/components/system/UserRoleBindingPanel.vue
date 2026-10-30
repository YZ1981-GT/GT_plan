<!--
  UserRoleBindingPanel.vue — 账号角色绑定（dept-role-data-permission Task 11.3）

  职责：给账号绑定一个或多个数据权限角色（覆盖写）。仅 admin 可见。

  🔴 **三处容易写错的语义，都在界面上明确表达了**：

  1. **清空绑定不等于「没有权限」**。`role_ids: []` 是合法操作 —— 此后该账号的
     数据权限由 `users.role` 枚举对应的**种子角色**决定（admin/partner 是
     「全部数据」，其余是「仅本人数据」）。所以按钮文案用「清空自定义角色」，
     并在确认框里说清回落到哪，避免让人误以为该账号从此什么都看不到。

  2. **多角色取范围最大的那个**（data_scope 数字越小范围越大）。绑两个角色不是
     "两份权限相加"，而是 argmin。界面上把每个角色的范围标签摆出来，并在选中
     多个时实时算出**生效范围**，避免管理员误以为"多绑几个更保险"。

  3. **最终可见项目 = 数据权限范围 ∩ 项目成员关系**。即便给了「全部数据」，
     不是项目成员照样看不到。不写清这条，管理员会反复来问"我都给全部数据了
     为什么他还看不见"。

  ⚠️ `/api/users/` 返回的字段是 `id / username / full_name / email / role /
     parent_partner_id / dept_id` —— **没有 `is_active`**，不要绑它（Vue 绑
     不存在的字段是静默渲染空串，四层检查都查不出）。
-->
<template>
  <div class="gt-urb">
    <!-- 说明条 -->
    <div class="gt-urb-hint">
      <el-icon><InfoFilled /></el-icon>
      <span>
        为账号绑定数据权限角色。绑定多个时<strong>取范围最大的那个</strong>生效。
        最终可见项目 = 数据权限范围 <strong>与</strong> 项目成员关系的
        <strong>交集</strong> —— 即便配了「全部数据」，不是项目成员仍看不到。
      </span>
    </div>

    <!-- 6 与 5 的区别：不写清楚管理员会反复配错这两档 -->
    <div class="gt-urb-hint gt-urb-hint-scope">
      <el-icon><InfoFilled /></el-icon>
      <span>
        <strong>「我参与的项目」与「仅本人数据」的区别</strong>：
        前者含<strong>被指派</strong>的项目（项目经理／现场负责人／签字合伙人／
        项目成员）以及本人创建的；后者<strong>只</strong>含本人
        <strong>创建</strong>的项目。
        被指派为项目经理但项目不是自己建的账号，配「仅本人数据」会
        <strong>什么都看不到</strong>。
        范围从宽到窄：全部数据 &gt; 自定义项目 &gt; 我参与的项目 &gt; 仅本人数据。
      </span>
    </div>

    <div class="gt-urb-body">
      <!-- 左：账号列表 -->
      <el-card shadow="never" class="gt-urb-left">
        <template #header>
          <div class="gt-urb-card-head">
            <span>账号</span>
            <el-input
              v-model="keyword"
              size="small"
              placeholder="搜索账号 / 姓名"
              clearable
              class="gt-urb-search"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
          </div>
        </template>

        <el-table
          v-loading="usersLoading"
          :data="filteredUsers"
          size="small"
          highlight-current-row
          height="420"
          empty-text="暂无账号"
          @current-change="onSelectUser"
        >
          <el-table-column prop="username" label="账号" min-width="120" />
          <el-table-column label="姓名" min-width="100">
            <template #default="{ row }">
              <!-- full_name 可为 NULL（历史账号未填）⇒ 显示「—」而非空白，
                   空白会让人以为是渲染错误 -->
              <span v-if="row.full_name">{{ row.full_name }}</span>
              <span v-else class="gt-urb-na">—</span>
            </template>
          </el-table-column>
          <el-table-column label="系统角色" width="110">
            <template #default="{ row }">
              <el-tag size="small" type="info" effect="plain" round>
                {{ userRoleLabel(row.role) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 右：该账号的角色绑定 -->
      <el-card shadow="never" class="gt-urb-right">
        <template #header>
          <div class="gt-urb-card-head">
            <span v-if="selected">
              角色绑定 ——
              <strong>{{ selected.full_name || selected.username }}</strong>
            </span>
            <span v-else class="gt-urb-na">请从左侧选择账号</span>
          </div>
        </template>

        <el-empty
          v-if="!selected"
          description="选择一个账号以查看和修改其数据权限角色"
        />

        <div v-else v-loading="bindingLoading">
          <el-select
            v-model="picked"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择要绑定的角色（可多选）"
            style="width: 100%"
            :loading="rolesLoading"
          >
            <el-option
              v-for="r in roleOptions"
              :key="r.id"
              :label="r.name"
              :value="r.id"
            >
              <span>{{ r.name }}</span>
              <span class="gt-urb-opt-scope">
                {{ dataScopeLabel(r.data_scope) }}
              </span>
            </el-option>
          </el-select>

          <!-- 生效范围实时预览：多角色取最宽，这一步不展示管理员会误判 -->
          <div class="gt-urb-effective">
            <span class="gt-urb-eff-label">生效数据权限范围</span>
            <el-tag
              :type="effectiveTagType"
              size="small"
              effect="light"
              round
            >
              {{ effectiveLabel }}
            </el-tag>
            <span v-if="picked.length > 1" class="gt-urb-eff-note">
              已选 {{ picked.length }} 个角色，取范围最大者生效
            </span>
            <span v-else-if="picked.length === 0" class="gt-urb-eff-note">
              未绑定自定义角色，按系统角色
              「{{ userRoleLabel(selected.role) }}」的默认范围
            </span>
          </div>

          <div class="gt-urb-actions">
            <el-button
              size="small"
              type="primary"
              :loading="saving"
              :disabled="!changed"
              @click="onSave"
            >
              保存绑定
            </el-button>
            <el-button
              size="small"
              :disabled="!changed"
              @click="resetPicked"
            >
              撤销改动
            </el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="original.length === 0"
              @click="onClear"
            >
              清空自定义角色
            </el-button>
          </div>

          <!-- 当前已生效的绑定（回查结果，不是表单值）-->
          <div class="gt-urb-current">
            <div class="gt-urb-current-title">当前已保存的绑定</div>
            <el-empty
              v-if="bound.length === 0"
              :image-size="60"
              description="该账号未绑定任何自定义角色"
            />
            <el-table v-else :data="bound" size="small">
              <el-table-column prop="name" label="角色名称" min-width="140" />
              <el-table-column prop="role_key" label="标识" min-width="130">
                <template #default="{ row }">
                  <code class="gt-urb-key">{{ row.role_key }}</code>
                </template>
              </el-table-column>
              <el-table-column label="数据权限范围" min-width="130">
                <template #default="{ row }">
                  <el-tag
                    :type="scopeTagType(row.data_scope)"
                    size="small"
                    effect="light"
                    round
                  >
                    {{ dataScopeLabel(row.data_scope) }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled, Search } from '@element-plus/icons-vue'

import {
  assignUserRoles,
  dataScopeLabel,
  getUserRoles,
  listRoles,
  type BoundRole,
  type SysRole,
} from '@/services/systemRoleApi'
import { listUsers } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'

interface UserRow {
  id: string
  username: string
  full_name: string | null
  email: string
  role: string
}

const users = ref<UserRow[]>([])
const usersLoading = ref(false)
const keyword = ref('')

const roleOptions = ref<SysRole[]>([])
const rolesLoading = ref(false)

const selected = ref<UserRow | null>(null)
const bound = ref<BoundRole[]>([])
const bindingLoading = ref(false)
const saving = ref(false)

/** 表单值 */
const picked = ref<number[]>([])
/** 已保存的绑定 id（用于判断是否改动过） */
const original = ref<number[]>([])

/**
 * 系统角色（users.role 枚举）的中文标签。
 *
 * ⚠️ `manager`=「项目经理」与 `site_lead`=「现场经理」是**两个不同角色**
 *    （权限相同、可填不同的人），两个名字不可互换。
 *    此前本表把 manager 标成「现场经理」，与 `UserManagement.vue` 的
 *    ROLE_OPTIONS（已于 2026-08-26 改为「项目经理」）不一致 ——
 *    同一个账号在两个界面显示成两个角色名，会让管理员以为配错了。
 *    这里一并对齐到「项目经理」。
 */
const USER_ROLE_LABELS: Record<string, string> = {
  admin: '系统管理员',
  partner: '业务合伙人',
  manager: '项目经理',
  site_lead: '现场经理',
  auditor: '审计助理',
  qc: '质量控制',
  eqcr: 'EQCR 复核',
  readonly: '只读',
}

function userRoleLabel(role: string): string {
  return USER_ROLE_LABELS[role] ?? role
}

/**
 * 系统角色对应的种子 data_scope（与后端 `_SEED_SCOPE_BY_ENUM_ROLE` 一致）。
 *
 * ⚠️ 这是**展示用的镜像**，不是判定真源 —— 真正生效的范围由后端
 *    `assemble_login_user` 计算（含 admin/partner 的权限地板）。这里只为
 *    "未绑定自定义角色时该显示什么"提供文案。
 */
const SEED_SCOPE: Record<string, number> = {
  admin: 1,
  partner: 1,
  // 🔴 manager / site_lead = 6「我参与的项目」（2026-08-31 改，原为 5「仅本人」）
  //    spec `data-scope-participant-visibility`，配套后端迁移 V162 +
  //    `_SEED_SCOPE_BY_ENUM_ROLE`。
  //    改因：被指派为项目经理但不是创建人的账号，在 scope=5 下最终可见集为空
  //    （最终可见 = 项目级 ∩ 数据权限，而 scope=5 只认 created_by）。
  manager: 6,
  // site_lead 与 manager 同档。后端真源同样登记在 `_SEED_SCOPE_BY_ENUM_ROLE`
  // 字面量里，两侧由 `RoleDataScopeManager.spec.ts` 的 D 层守卫做精确相等比对。
  site_lead: 6,
  // 🔴 auditor / qc / eqcr = 6「我参与的项目」（2026-09-03 改，原为 5「仅本人」）
  //    配套后端迁移 V163 + `_SEED_SCOPE_BY_ENUM_ROLE`。
  //    改因与 manager/site_lead 同一缺陷：scope=5 只认 created_by，而审计员
  //    从不是项目创建人 ⇒ 最终可见集恒空 ⇒ 工作台项目数为 0（收到委派通知却没项目）。
  auditor: 6,
  qc: 6,
  eqcr: 6,
  // ⚠️ readonly 刻意仍为 5：「只读观察者」无「参与项目」语义，本轮不放宽。
  readonly: 5,
}

const filteredUsers = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return users.value
  return users.value.filter(
    (u) =>
      u.username.toLowerCase().includes(kw) ||
      (u.full_name || '').toLowerCase().includes(kw),
  )
})

/** 表单是否与已保存状态不同（顺序无关） */
const changed = computed(() => {
  const a = [...original.value].sort((x, y) => x - y)
  const b = [...picked.value].sort((x, y) => x - y)
  return a.length !== b.length || a.some((x, i) => x !== b[i])
})

/**
 * 生效范围 = 所选角色里 data_scope 最小值（数字越小范围越大）。
 * 一个都没选时回落到系统角色的种子范围。
 */
const effectiveScope = computed<number>(() => {
  if (picked.value.length === 0) {
    return SEED_SCOPE[selected.value?.role ?? ''] ?? 5
  }
  const scopes = picked.value
    .map((id) => roleOptions.value.find((r) => r.id === id)?.data_scope)
    .filter((s): s is number => typeof s === 'number')
  return scopes.length > 0 ? Math.min(...scopes) : 5
})

const effectiveLabel = computed(() => dataScopeLabel(effectiveScope.value))
const effectiveTagType = computed(() => scopeTagType(effectiveScope.value))

/**
 * data_scope → 标签配色。**颜色按范围从宽到窄递减警示强度**。
 *
 * ⚠️ 四个合法档位必须各有**不同**的类型，`info` 只留给非法/未配置值 ——
 *    若某个合法档位落到 `info` 兜底，界面上就与"没配"无法区分。
 */
function scopeTagType(
  scope: number,
): 'danger' | 'warning' | 'primary' | 'success' | 'info' {
  if (scope === 1) return 'danger'   // 全部数据 —— 最需警示
  if (scope === 2) return 'warning'  // 自定义项目
  if (scope === 6) return 'primary'  // 我参与的项目（2026-08-31 新增档位）
  if (scope === 5) return 'success'  // 仅本人数据 —— 最窄
  return 'info'                      // 非法/未配置（如库里的历史脏值 3/4）
}

async function loadUsers() {
  usersLoading.value = true
  try {
    const list = await listUsers()
    users.value = (list || []).map((u: any) => ({
      id: u.id,
      username: u.username,
      full_name: u.full_name ?? null,
      email: u.email,
      role: typeof u.role === 'string' ? u.role : String(u.role ?? ''),
    }))
  } catch (e) {
    handleApiError(e, '加载账号列表失败')
  } finally {
    usersLoading.value = false
  }
}

async function loadRoles() {
  rolesLoading.value = true
  try {
    roleOptions.value = await listRoles()
  } catch (e) {
    handleApiError(e, '加载角色列表失败')
  } finally {
    rolesLoading.value = false
  }
}

async function onSelectUser(row: UserRow | null) {
  if (!row) return
  selected.value = row
  await loadBinding(row.id)
}

async function loadBinding(userId: string) {
  bindingLoading.value = true
  try {
    const list = await getUserRoles(userId)
    bound.value = list
    original.value = list.map((r) => r.id)
    picked.value = [...original.value]
  } catch (e) {
    handleApiError(e, '加载账号角色绑定失败')
  } finally {
    bindingLoading.value = false
  }
}

function resetPicked() {
  picked.value = [...original.value]
}

async function onSave() {
  if (!selected.value) return
  const name = selected.value.full_name || selected.value.username

  // 从有绑定改成空 = 清空，语义重要，单独确认
  if (picked.value.length === 0 && original.value.length > 0) {
    const ok = await confirmClear(name)
    if (!ok) return
  }

  saving.value = true
  try {
    await assignUserRoles(selected.value.id, picked.value)
    ElMessage.success(
      picked.value.length > 0
        ? `已为「${name}」绑定 ${picked.value.length} 个角色，其登录缓存已失效`
        : `已清空「${name}」的自定义角色，其登录缓存已失效`,
    )
    await loadBinding(selected.value.id)
  } catch (e) {
    handleApiError(e, '保存角色绑定失败')
  } finally {
    saving.value = false
  }
}

async function confirmClear(name: string): Promise<boolean> {
  const fallback = dataScopeLabel(
    SEED_SCOPE[selected.value?.role ?? ''] ?? 5,
  )
  try {
    await ElMessageBox.confirm(
      `将清空「${name}」的全部自定义角色。\n\n`
        + `清空后该账号并非没有权限 —— 其数据权限范围将回落到系统角色`
        + `「${userRoleLabel(selected.value?.role ?? '')}」的默认值：${fallback}。`,
      '清空自定义角色',
      {
        type: 'warning',
        confirmButtonText: '确认清空',
        cancelButtonText: '取消',
      },
    )
    return true
  } catch {
    return false
  }
}

async function onClear() {
  picked.value = []
  await onSave()
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadRoles()])
})

defineExpose({
  loadUsers,
  loadRoles,
  picked,
  original,
  changed,
  effectiveScope,
  onSelectUser,
})
</script>

<style scoped>
.gt-urb { padding: 4px 0; }

.gt-urb-hint {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.7;
  color: #7a5b00;
  background: #fffbe6;
  border-left: 3px solid #e6a23c;
  border-radius: 3px;
}

/* 档位说明用中性蓝，与上方橙色警示条区分（那条讲"交集"陷阱，这条讲档位语义） */
.gt-urb-hint-scope {
  color: #1f4e79;
  background: #ecf5ff;
  border-left-color: #409eff;
}

.gt-urb-body {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.gt-urb-left { flex: 0 0 46%; border: none; }
.gt-urb-right { flex: 1; border: none; }

.gt-urb-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}
.gt-urb-search { width: 190px; }

.gt-urb-effective {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin-top: 10px;
  background: var(--gt-color-fill-light, #fafafa);
  border-radius: 3px;
}
.gt-urb-eff-label { font-size: 12px; color: var(--gt-color-text-secondary, #606266); }
.gt-urb-eff-note { font-size: 12px; color: var(--gt-color-text-tertiary, #909399); }

.gt-urb-actions { display: flex; gap: 8px; margin-top: 12px; }

.gt-urb-current { margin-top: 16px; }
.gt-urb-current-title {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-text-secondary, #606266);
}

.gt-urb-key {
  padding: 1px 5px;
  font-size: 12px;
  background: #f5f5f5;
  border-radius: 3px;
}
.gt-urb-na { color: var(--gt-color-text-tertiary, #909399); }
.gt-urb-opt-scope {
  float: right;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

:deep(.el-table) { font-size: 13px; }
:deep(.el-card__header) { padding: 10px 14px; }
</style>
