<!--
  RoleDataScopeManager.vue — 角色与数据权限管理（dept-role-data-permission Task 11.2）

  ⚠️ **未验证**：本组件尚未经 vitest 或浏览器实测（用户要求跳过测试执行）。

  职责：角色列表 CRUD + data_scope 配置。仅 admin 可见（外层 v-if="isAdmin"）。

  🔴 **三个容易写错的地方，都在代码里做了处理**：

  1. **data_scope 从 2 改成非 2 时必须清空项目关联**。若保留，日后改回 2
     会突然恢复一批旧项目 —— 静默越权。前端在提交时把非 2 的 project_ids
     显式传 `[]`（而非 undefined），与后端行为对齐、也让"清空"这件事在
     网络请求里可见。

  2. **编辑时 `project_ids` 只在真正改动过才传**。`undefined` = 不改，
     `[]` = 清空。若无脑传当前表单值，"只改角色名"会把项目配置抹掉。

  3. **data_scope 的校验不放在前端**。前端只做下拉限定（结构上就选不出非法值），
     真正的判据在后端 `role_service.validate_data_scope`（返回 400 +
     "数据权限范围取值非法"）。前端加 `ge/le` 之类的重复校验只会在两边口径
     漂移时制造"前端拦住了但后端没拦"的假安全感。
-->
<template>
  <div class="gt-rdm">
    <!-- 工具栏 -->
    <div class="gt-rdm-toolbar">
      <span class="gt-rdm-stats">
        角色总数：<span class="gt-amt">{{ roles.length }}</span>
      </span>
      <div class="gt-rdm-spacer" />
      <el-input
        v-model="keyword"
        size="small"
        placeholder="搜索角色名称 / 标识"
        clearable
        class="gt-rdm-search"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button size="small" round :loading="loading" @click="loadRoles">
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
      </el-button>
      <el-button size="small" type="primary" round @click="openCreate">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>新增角色
      </el-button>
    </div>

    <!-- 说明条：把三种范围的含义摆在界面上，别让人去猜 -->
    <div class="gt-rdm-hint">
      <el-icon><InfoFilled /></el-icon>
      <span>
        数据权限决定该角色的账号能看到哪些项目。同一账号绑定多个角色时，
        <strong>取范围最大的那个</strong>（数字越小范围越大）。
        最终可见项目 = 数据权限范围 <strong>与</strong> 项目成员关系的
        <strong>交集</strong> —— 即便配了「全部数据」，也仍需是项目成员才能看到。
      </span>
    </div>

    <el-card shadow="never" class="gt-rdm-card">
      <el-table
        v-loading="loading"
        :data="filtered"
        size="small"
        highlight-current-row
        empty-text="暂无角色"
      >
        <el-table-column prop="name" label="角色名称" min-width="140" />
        <el-table-column prop="role_key" label="角色标识" min-width="140">
          <template #default="{ row }">
            <code class="gt-rdm-key">{{ row.role_key }}</code>
          </template>
        </el-table-column>
        <el-table-column label="数据权限范围" min-width="150">
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
        <el-table-column label="自定义项目" min-width="120" align="right">
          <template #default="{ row }">
            <!-- 只有 scope=2 才有意义；其余显示「—」而不是 0，
                 显示 0 会让人以为"配了但一个都没选" -->
            <el-button
              v-if="row.data_scope === 2"
              link
              type="primary"
              size="small"
              @click="openEdit(row)"
            >
              查看/修改
            </el-button>
            <span v-else class="gt-rdm-na">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              :type="row.status === '0' ? 'success' : 'info'"
              size="small"
              effect="plain"
              round
            >
              {{ row.status === '0' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">
              编辑
            </el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑角色' : '新增角色'"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="110px"
        size="small"
      >
        <!-- ⚠️ `prop` 必须写，否则 el-form 的 `:rules` 找不到对应字段 = 死配置
             （只有视觉上的红星，提交时并不会拦） -->
        <el-form-item label="角色名称" prop="name" required>
          <el-input v-model="form.name" placeholder="如：项目组数据权限" />
        </el-form-item>
        <el-form-item label="角色标识" prop="role_key" required>
          <el-input
            v-model="form.role_key"
            placeholder="如：project_team_scope"
            :disabled="editing"
          />
          <div v-if="editing" class="gt-rdm-tip">
            角色标识创建后不可修改，避免已有绑定关系失去对应
          </div>
        </el-form-item>
        <el-form-item label="数据权限范围" required>
          <el-select v-model="form.data_scope" style="width: 100%">
            <el-option
              v-for="opt in DATA_SCOPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            >
              <span>{{ opt.label }}</span>
              <span class="gt-rdm-opt-hint">{{ opt.hint }}</span>
            </el-option>
          </el-select>
        </el-form-item>

        <!-- data_scope=2 才显示项目多选 -->
        <el-form-item v-if="form.data_scope === 2" label="可见项目" required>
          <el-select
            v-model="form.project_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="勾选该角色可见的项目"
            style="width: 100%"
            :loading="projectsLoading"
          >
            <el-option
              v-for="p in projectOptions"
              :key="p.id"
              :label="p.label"
              :value="p.id"
            />
          </el-select>
          <div class="gt-rdm-tip">
            未勾选任何项目时，该角色的账号将看不到任何项目
          </div>
        </el-form-item>

        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio label="0">启用</el-radio>
            <el-radio label="1">停用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button
          size="small"
          type="primary"
          :loading="saving"
          @click="onSubmit"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { InfoFilled, Plus, Refresh, Search } from '@element-plus/icons-vue'

import {
  DATA_SCOPE_OPTIONS,
  createRole,
  dataScopeLabel,
  deleteRole,
  getRoleProjects,
  listRoles,
  updateRole,
  type DataScope,
  type SysRole,
} from '@/services/systemRoleApi'
import { listProjects } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'

const roles = ref<SysRole[]>([])
const loading = ref(false)
const keyword = ref('')

const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref<SysRole | null>(null)

const projectOptions = ref<Array<{ id: string; label: string }>>([])
const projectsLoading = ref(false)

/** 打开编辑弹窗时已有的项目关联，用于判断是否真的改动过 */
const originalProjectIds = ref<string[]>([])

/** el-form 实例，用于 `validate()` —— 声明式规则要靠它触发 */
const formRef = ref<FormInstance>()

/**
 * 表单校验规则。
 *
 * ⚠️ 只写 `required` 属性是**纯视觉**的（只画红星），提交时不拦任何东西。
 *    必须 `el-form :rules` + `el-form-item prop` + `formRef.validate()` 三者齐备
 *    才真正生效 —— 缺任一个都是死配置。本文件曾只有手写的 `if (!f.name.trim())`
 *    兜底，被 `gt-audit/el-form-must-have-rules` 规则逮到。
 *
 * 🔴 **`data_scope` 不在这里校验**：它由下拉限定值域，真判据在后端
 *    `validate_data_scope`（400 + "数据权限范围取值非法"）。前端加重复校验
 *    只会在两边口径漂移时制造假安全感。
 */
const formRules: FormRules = {
  name: [
    { required: true, message: '请填写角色名称', trigger: 'blur' },
    { max: 100, message: '角色名称不超过 100 字', trigger: 'blur' },
  ],
  role_key: [
    { required: true, message: '请填写角色标识', trigger: 'blur' },
    {
      pattern: /^[a-z][a-z0-9_]*$/,
      message: '标识只能用小写字母、数字、下划线，且以字母开头',
      trigger: 'blur',
    },
  ],
}

const form = ref<{
  name: string
  role_key: string
  data_scope: DataScope
  status: string
  project_ids: string[]
}>({
  name: '',
  role_key: '',
  data_scope: 5,
  status: '0',
  project_ids: [],
})

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return roles.value
  return roles.value.filter(
    (r) =>
      r.name.toLowerCase().includes(kw) ||
      r.role_key.toLowerCase().includes(kw),
  )
})

function scopeTagType(scope: number): 'danger' | 'warning' | 'success' | 'info' {
  if (scope === 1) return 'danger' // 全部数据 —— 权限最大，视觉上要显眼
  if (scope === 2) return 'warning'
  if (scope === 5) return 'success'
  return 'info' // 脏值
}

async function loadRoles() {
  loading.value = true
  try {
    roles.value = await listRoles()
  } catch (e) {
    handleApiError(e, '加载角色列表失败')
  } finally {
    loading.value = false
  }
}

async function loadProjects() {
  if (projectOptions.value.length > 0) return
  projectsLoading.value = true
  try {
    const list = await listProjects()
    projectOptions.value = (list || []).map((p: any) => ({
      id: p.id,
      // 项目名优先用 client_name（审计场景里"被审计单位"才是识别依据）
      label: p.client_name || p.name || p.id,
    }))
  } catch (e) {
    handleApiError(e, '加载项目列表失败')
  } finally {
    projectsLoading.value = false
  }
}

// scope 切到 2 时才需要项目列表 —— 不必在页面加载时就拉
watch(
  () => form.value.data_scope,
  (scope) => {
    if (scope === 2) loadProjects()
  },
)

function openCreate() {
  editing.value = null
  originalProjectIds.value = []
  form.value = {
    name: '',
    role_key: '',
    data_scope: 5,
    status: '0',
    project_ids: [],
  }
  dialogVisible.value = true
}

async function openEdit(row: SysRole) {
  editing.value = row
  form.value = {
    name: row.name,
    role_key: row.role_key,
    // 库里可能有脏值（3/4）；下拉里没有对应项时 el-select 会回显裸数字。
    // 落到合法值上并提示，避免"看起来配了个 3"却无法保存。
    data_scope: ([1, 2, 5].includes(row.data_scope) ? row.data_scope : 5) as DataScope,
    status: row.status,
    project_ids: [],
  }
  if (row.data_scope !== form.value.data_scope) {
    ElMessage.warning(
      `该角色的数据权限范围为非法值 ${row.data_scope}，已按「仅本人数据」显示，保存后将更正`,
    )
  }
  dialogVisible.value = true

  if (row.data_scope === 2) {
    await loadProjects()
    try {
      const ids = await getRoleProjects(row.id)
      form.value.project_ids = ids
      originalProjectIds.value = [...ids]
    } catch (e) {
      handleApiError(e, '加载角色项目关联失败')
    }
  }
}

/** 判断项目勾选是否真的变了（顺序无关） */
function projectIdsChanged(): boolean {
  const a = [...originalProjectIds.value].sort()
  const b = [...form.value.project_ids].sort()
  return a.length !== b.length || a.some((x, i) => x !== b[i])
}

async function onSubmit() {
  const f = form.value

  // 声明式规则（主校验）。formRef 在测试里挂 stub 时可能为 undefined ⇒ 可选调用，
  // 下面的手写检查作为兜底始终生效。
  if (formRef.value) {
    try {
      await formRef.value.validate()
    } catch {
      return  // 校验未通过，el-form 已在各字段下显示原因
    }
  }

  // 兜底：formRef 缺失（stub 环境）时仍要拦住空值
  if (!f.name.trim()) {
    ElMessage.warning('请填写角色名称')
    return
  }
  if (!editing.value && !f.role_key.trim()) {
    ElMessage.warning('请填写角色标识')
    return
  }
  if (f.data_scope === 2 && f.project_ids.length === 0) {
    // 不直接拦死 —— 空列表是合法配置（该角色看不到项目），但要用户确认是有意的
    try {
      await ElMessageBox.confirm(
        '未勾选任何项目，该角色的账号将看不到任何项目。确认保存？',
        '确认',
        { type: 'warning', confirmButtonText: '确认保存', cancelButtonText: '返回修改' },
      )
    } catch {
      return
    }
  }

  saving.value = true
  try {
    if (editing.value) {
      // 🔴 只放真正改动的字段。`project_ids: undefined` = 不改该字段；
      //    切到非 2 时显式传 `[]` 让"清空"在请求里可见。
      const payload: Record<string, unknown> = {
        name: f.name.trim(),
        data_scope: f.data_scope,
        status: f.status,
      }
      if (f.data_scope !== 2) {
        payload.project_ids = []
      } else if (projectIdsChanged()) {
        payload.project_ids = f.project_ids
      }
      await updateRole(editing.value.id, payload as any)
      ElMessage.success('角色已更新，相关账号的权限缓存已失效')
    } else {
      await createRole({
        name: f.name.trim(),
        role_key: f.role_key.trim(),
        data_scope: f.data_scope,
        status: f.status,
        project_ids: f.data_scope === 2 ? f.project_ids : [],
      })
      ElMessage.success('角色已创建')
    }
    dialogVisible.value = false
    await loadRoles()
  } catch (e) {
    handleApiError(e, '保存角色失败')
  } finally {
    saving.value = false
  }
}

async function onDelete(row: SysRole) {
  try {
    await ElMessageBox.confirm(
      `删除角色「${row.name}」后，绑定该角色的账号将失去这份数据权限配置，`
        + `其可见范围回落到账号自身角色对应的默认范围。是否继续？`,
      '删除角色',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteRole(row.id)
    ElMessage.success('角色已删除，相关账号的权限缓存已失效')
    await loadRoles()
  } catch (e) {
    handleApiError(e, '删除角色失败')
  }
}

onMounted(loadRoles)

defineExpose({
  loadRoles,
  form,
  projectIdsChanged,
  projectOptions,
  openEdit,
  onSubmit,
  dialogVisible,
})
</script>

<style scoped>
.gt-rdm { padding: 4px 0; }

.gt-rdm-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.gt-rdm-spacer { flex: 1; }
.gt-rdm-search { width: 220px; }
.gt-rdm-stats { font-size: 13px; color: var(--gt-color-text-secondary, #606266); }
.gt-amt { font-variant-numeric: tabular-nums; font-weight: 600; }

.gt-rdm-hint {
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

.gt-rdm-card { border: none; }
.gt-rdm-key {
  padding: 1px 5px;
  font-size: 12px;
  background: #f5f5f5;
  border-radius: 3px;
}
.gt-rdm-na { color: var(--gt-color-text-tertiary, #909399); }
.gt-rdm-tip {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-rdm-opt-hint {
  float: right;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

:deep(.el-table) { font-size: 13px; }
:deep(.el-table td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
