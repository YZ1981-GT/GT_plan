<!--
  GtRefreshScopeDialog.vue — 合伙人全局一键刷新勾选弹窗（Req 19｜P0）

  设计：.kiro/specs/formula-management-library/design.md §13。

  组件同时承载两部分：
  1. **入口按钮**（Req 19.1/19.2）：合伙人可见的"全局一键刷新"按钮。仅当
     `usePermissionMatrix.currentRole ∈ {partner, signing_partner}` 才渲染
     （非合伙人不可见）。后端 `/draft-refresh` 走 `require_role(["partner",
     "signing_partner"])` 二次拦截（Req 1）——前端不可见只是体验层，权威门禁在后端。

     ⚠ 关键：`usePermissionMatrix.normalizeRole` 会把 `signing_partner` 归一为
     `partner`，故 `currentRole` 恒不出现 `signing_partner` 字面量；此处判定实际
     等价于 `currentRole === 'partner'`（覆盖 partner 与 signing_partner 两类真实
     角色），且 admin 不在集合内（与后端 require_role 不放行 admin 一致）。

  2. **勾选弹窗**（Req 19.3/19.4）：点击入口 → 弹窗，消费
     `GET /api/workpapers/refresh-scopes?project_id=&year=`（Task 17.1）渲染
     `el-tree show-checkbox`：
     - 顶层域 report / adjudication / note 为可整选/半选的叶子；
     - 底稿域 workpaper 展开为各循环子项 `workpaper:{cycle}`，可按循环勾选而非
       只能整选全部底稿（Req 19.4）。

  3. **空勾选阻断**（Req 19.5）：勾选为空 → 禁用"确认刷新" + 提示"请至少勾选一项
     刷新内容"，不发起任何请求。

  4. **确认刷新**（Req 19.6）：`POST /api/workpapers/draft-refresh
     { project_id, year, scopes:[...], confirm_overwrite }`（Task 16.2）→ 展示
     affected_count / preset_application / precheck_warnings 结果摘要。

  http 用项目既有 axios 封装（带 Authorization），响应 `{code,message,data}` 信封
  解包（`response.data?.data ?? response.data`）。

  Spec: .kiro/specs/formula-management-library/  Task: 18.1
  Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6
-->
<template>
  <!-- ① 入口按钮：仅合伙人可见（Req 19.1/19.2） -->
  <el-button
    v-if="isPartner"
    class="gt-rsd-entry"
    type="primary"
    :icon="Refresh"
    @click="openDialog"
  >
    全局一键刷新
  </el-button>

  <!-- ② 勾选弹窗（Req 19.3） -->
  <el-dialog
    v-model="visible"
    title="全局一键刷新 · 选择刷新范围"
    width="640px"
    top="8vh"
    append-to-body
    destroy-on-close
    class="gt-refresh-scope-dialog"
  >
    <div v-loading="scopesLoading" class="gt-rsd-body">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="gt-rsd-tip"
      >
        <template #title>
          勾选需要刷新的内容，从四表库未审数一键生成未审报表 / 底稿 / 附注初稿。
          底稿可按循环单独勾选。
        </template>
      </el-alert>

      <!-- 树形勾选（Req 19.4）：顶层域整选/半选 + 底稿域展开为各循环子项 -->
      <el-tree
        ref="treeRef"
        class="gt-rsd-tree"
        :data="treeData"
        show-checkbox
        node-key="key"
        default-expand-all
        :expand-on-click-node="false"
        :props="{ label: 'label', children: 'children' }"
        @check="onCheck"
      />

      <el-empty
        v-if="!scopesLoading && treeData.length === 0"
        :image-size="60"
        description="暂无可刷新范围（请确认项目与年度）"
      />

      <!-- 覆盖确认（Req 4.4，透传给后端 confirm_overwrite） -->
      <el-checkbox v-model="confirmOverwrite" class="gt-rsd-overwrite">
        确认覆盖团队人工编辑单元（不勾选则仅刷新未被人工编辑的单元）
      </el-checkbox>

      <!-- 空勾选提示（Req 19.5） -->
      <p v-if="checkedScopes.length === 0" class="gt-rsd-empty-hint">
        请至少勾选一项刷新内容
      </p>

      <!-- 结果摘要（Req 19.6） -->
      <div v-if="result" class="gt-rsd-result">
        <el-divider content-position="left">刷新结果</el-divider>
        <p class="gt-rsd-result-line">
          受影响单元：<strong>{{ result.affected_count }}</strong> 个
          <el-tag
            v-if="result.result_status"
            size="small"
            :type="result.result_status === 'success' ? 'success' : 'warning'"
            effect="plain"
          >
            {{ result.result_status }}
          </el-tag>
        </p>
        <p v-if="presetSummary" class="gt-rsd-result-line">
          套用预设：{{ presetSummary }}
        </p>
        <div v-if="result.precheck_warnings && result.precheck_warnings.length" class="gt-rsd-warns">
          <p class="gt-rsd-warns-title">前置校验告警（非阻断）：</p>
          <ul>
            <li v-for="(w, i) in result.precheck_warnings" :key="i">
              {{ w.message || w.detail || JSON.stringify(w) }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="checkedScopes.length === 0"
        @click="onConfirm"
      >
        确认刷新
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, type ElTree } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 后端发现端点 `/refresh-scopes` 返回的一条范围项。 */
interface RefreshScopeItem {
  key: string
  label: string
  group: string
  cycle?: string | null
}

/** el-tree 节点。 */
interface ScopeTreeNode {
  key: string
  label: string
  children?: ScopeTreeNode[]
}

/** `/draft-refresh` 结果摘要（信封解包后的 data）。 */
interface DraftRefreshResult {
  affected_count?: number
  result_status?: string
  preset_application?: Record<string, unknown> | null
  precheck_warnings?: Array<Record<string, unknown>>
  [k: string]: unknown
}

const props = defineProps<{
  /** 目标项目 id。 */
  projectId: string
  /** 目标年度。 */
  year: number
}>()

const emit = defineEmits<{
  /** 刷新成功后向宿主上报结果，供宿主刷新受影响视图。 */
  refreshed: [result: DraftRefreshResult]
}>()

// ─── 前端门禁：仅合伙人可见入口（Req 19.1/19.2） ───────────────────────────────
const { currentRole } = usePermissionMatrix()
// normalizeRole 已把 signing_partner 归一为 partner；两个字面量都保留以显式表达意图。
const PARTNER_ROLES = ['partner', 'signing_partner']
const isPartner = computed(() => PARTNER_ROLES.includes(currentRole.value))

// ─── 弹窗状态 ──────────────────────────────────────────────────────────────────
const visible = ref(false)
const scopesLoading = ref(false)
const submitting = ref(false)
const confirmOverwrite = ref(false)
const result = ref<DraftRefreshResult | null>(null)

const treeRef = ref<InstanceType<typeof ElTree>>()
const treeData = ref<ScopeTreeNode[]>([])
/** 当前勾选的叶子 key（即要发送的 scopes）。 */
const checkedScopes = ref<string[]>([])

// 底稿域合成父节点 key（非可发送的 scope，仅用于分组展开）。
const WORKPAPER_GROUP_KEY = '__workpaper_group__'

const presetSummary = computed<string>(() => {
  const pa = result.value?.preset_application
  if (!pa || typeof pa !== 'object') return ''
  const applied = (pa as Record<string, unknown>).applied_count
  const pages = (pa as Record<string, unknown>).page_count
  const parts: string[] = []
  if (typeof applied === 'number') parts.push(`公式 ${applied} 条`)
  if (typeof pages === 'number') parts.push(`页面 ${pages} 个`)
  return parts.join(' · ')
})

// ─── 打开弹窗 → 拉取可勾选范围（Req 19.3） ─────────────────────────────────────
async function openDialog() {
  visible.value = true
  result.value = null
  await loadScopes()
}

async function loadScopes() {
  scopesLoading.value = true
  try {
    const response = await http.get('/api/workpapers/refresh-scopes', {
      params: { project_id: props.projectId, year: props.year },
    })
    const payload = (response.data?.data ?? response.data) as { items?: RefreshScopeItem[] }
    const items = payload?.items ?? []
    treeData.value = buildTree(items)
    checkedScopes.value = []
  } catch (err: unknown) {
    ElMessage.error(extractError(err, '获取刷新范围失败'))
    treeData.value = []
  } finally {
    scopesLoading.value = false
  }
}

/**
 * 构建树：
 * - 顶层域 report/adjudication/note → 叶子节点（可整选/半选）。
 * - workpaper 域 → 合成父节点，各循环 `workpaper:{cycle}` 为子叶（Req 19.4）。
 */
function buildTree(items: RefreshScopeItem[]): ScopeTreeNode[] {
  const topNodes: ScopeTreeNode[] = []
  const workpaperChildren: ScopeTreeNode[] = []

  for (const it of items) {
    if (it.group === 'workpaper') {
      workpaperChildren.push({ key: it.key, label: it.label })
    } else {
      topNodes.push({ key: it.key, label: it.label })
    }
  }

  const nodes = [...topNodes]
  if (workpaperChildren.length) {
    nodes.push({
      key: WORKPAPER_GROUP_KEY,
      label: '底稿（按循环）',
      children: workpaperChildren,
    })
  }
  return nodes
}

// ─── 勾选变化 → 收集叶子 key（排除合成分组父节点） ─────────────────────────────
function onCheck() {
  const tree = treeRef.value
  if (!tree) return
  // leafOnly=true：只取叶子，天然排除 workpaper 合成父节点。
  const leafKeys = tree.getCheckedKeys(true) as string[]
  checkedScopes.value = leafKeys.filter((k) => k !== WORKPAPER_GROUP_KEY)
}

// ─── 确认刷新（Req 19.5 空勾选阻断 / Req 19.6 提交） ───────────────────────────
async function onConfirm() {
  // Req 19.5：空勾选不发起任何请求。
  if (checkedScopes.value.length === 0) {
    ElMessage.warning('请至少勾选一项刷新内容')
    return
  }
  submitting.value = true
  try {
    const response = await http.post('/api/workpapers/draft-refresh', {
      project_id: props.projectId,
      year: props.year,
      scopes: checkedScopes.value,
      confirm_overwrite: confirmOverwrite.value,
    })
    const data = (response.data?.data ?? response.data) as DraftRefreshResult
    result.value = data
    const n = data?.affected_count ?? 0
    ElMessage.success(`刷新完成，受影响单元 ${n} 个`)
    emit('refreshed', data)
  } catch (err: unknown) {
    ElMessage.error(extractError(err, '一键刷新失败'))
  } finally {
    submitting.value = false
  }
}

// ─── 错误信息提取（兼容后端 {detail} / {message} 与 422 precheck detail） ───────
function extractError(err: unknown, fallback: string): string {
  const e = err as {
    response?: { data?: { detail?: unknown; message?: unknown; data?: { detail?: unknown } } }
    message?: string
  }
  const detail = e?.response?.data?.detail ?? e?.response?.data?.message
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const msg = (detail as Record<string, unknown>).message
    if (typeof msg === 'string') return msg
  }
  if (e?.message) return e.message
  return fallback
}

defineExpose({ openDialog, isPartner, checkedScopes })
</script>

<style scoped>
.gt-rsd-body {
  min-height: 200px;
}
.gt-rsd-tip {
  margin-bottom: 12px;
}
.gt-rsd-tree {
  max-height: 46vh;
  overflow: auto;
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
  border-radius: 8px;
  padding: 8px;
}
.gt-rsd-overwrite {
  margin-top: 12px;
  white-space: normal;
  line-height: 1.5;
}
.gt-rsd-empty-hint {
  margin: 8px 0 0 0;
  font-size: 13px;
  color: var(--el-color-warning, #e6a23c);
}
.gt-rsd-result {
  margin-top: 12px;
}
.gt-rsd-result-line {
  margin: 4px 0;
  font-size: 13px;
  color: var(--gt-color-text-regular, #606266);
}
.gt-rsd-warns {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-color-warning, #e6a23c);
}
.gt-rsd-warns-title {
  margin: 4px 0 2px 0;
}
.gt-rsd-warns ul {
  margin: 0;
  padding-left: 18px;
}
</style>
