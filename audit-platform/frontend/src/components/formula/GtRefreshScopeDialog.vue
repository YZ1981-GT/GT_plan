<!--
  GtRefreshScopeDialog.vue — 合伙人全局一键刷新勾选弹窗（Req 13/19｜P15）

  设计：.kiro/specs/formula-runtime-convergence/design.md §12。

  Task 16: 挂载生产 UI 并统一响应展示
  - 消费 formulaRuntimeContract.ts 对齐 Task 15 OpenAPI contract
  - success/partial/failed/idempotent_hit 分态展示
  - failed/partial 必须列失败目标
  - 刷新后触发宿主数据重载 (emit refresh-complete)
  - rollback_available 时显示回滚按钮
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

      <!-- 树形勾选（Req 19.4） -->
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

      <!-- 覆盖确认 -->
      <el-checkbox v-model="confirmOverwrite" class="gt-rsd-overwrite">
        确认覆盖团队人工编辑单元（不勾选则仅刷新未被人工编辑的单元）
      </el-checkbox>

      <!-- 空勾选提示（Req 19.5） -->
      <p v-if="checkedScopes.length === 0" class="gt-rsd-empty-hint">
        请至少勾选一项刷新内容
      </p>

      <!-- ─── 结果分态展示（Task 16 核心） ─── -->
      <div v-if="parsedResult" class="gt-rsd-result">
        <el-divider content-position="left">刷新结果</el-divider>

        <!-- success 绿色 -->
        <el-alert
          v-if="parsedResult.status === 'success'"
          type="success"
          show-icon
          :closable="false"
          class="gt-rsd-status-banner"
        >
          <template #title>
            刷新成功：已应用 {{ parsedResult.applied_count }} 个单元
          </template>
          <template #default>
            <span v-if="presetSummary" class="gt-rsd-preset-info">预设套用：{{ presetSummary }}</span>
          </template>
        </el-alert>

        <!-- partial_success 黄色 -->
        <el-alert
          v-else-if="parsedResult.status === 'partial_success'"
          type="warning"
          show-icon
          :closable="false"
          class="gt-rsd-status-banner"
        >
          <template #title>
            部分成功：已应用 {{ parsedResult.applied_count }} 个，失败 {{ parsedResult.failed_count }} 个
          </template>
          <template #default>
            <div v-if="parsedResult.failures.length" class="gt-rsd-failure-list">
              <p class="gt-rsd-failure-title">失败目标：</p>
              <ul>
                <li v-for="(f, i) in parsedResult.failures" :key="i">{{ f }}</li>
              </ul>
            </div>
          </template>
        </el-alert>

        <!-- failed 红色 -->
        <el-alert
          v-else-if="parsedResult.status === 'failed'"
          type="error"
          show-icon
          :closable="false"
          class="gt-rsd-status-banner"
        >
          <template #title>
            刷新失败：{{ parsedResult.failed_count }} 个目标未能完成
          </template>
          <template #default>
            <div v-if="parsedResult.failures.length" class="gt-rsd-failure-list">
              <p class="gt-rsd-failure-title">失败详情：</p>
              <ul>
                <li v-for="(f, i) in parsedResult.failures" :key="i">{{ f }}</li>
              </ul>
            </div>
          </template>
        </el-alert>

        <!-- idempotent_hit 信息 -->
        <el-alert
          v-else-if="parsedResult.status === 'idempotent_hit'"
          type="info"
          show-icon
          :closable="false"
          class="gt-rsd-status-banner"
        >
          <template #title>
            幂等命中：相同请求已执行过，无新变更
          </template>
        </el-alert>

        <!-- warnings -->
        <div v-if="parsedResult.warnings.length" class="gt-rsd-warns">
          <p class="gt-rsd-warns-title">告警信息：</p>
          <ul>
            <li v-for="(w, i) in parsedResult.warnings" :key="i">{{ w }}</li>
          </ul>
        </div>

        <!-- rollback 按钮 -->
        <el-button
          v-if="parsedResult.rollback_available && parsedResult.status !== 'idempotent_hit'"
          type="danger"
          plain
          size="small"
          class="gt-rsd-rollback-btn"
          :loading="rollingBack"
          @click="onRollback"
        >
          回滚此次刷新
        </el-button>
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
// spec: formula-management-runtime-closure Task 14/16 - 端点收敛进 apiPaths（纯搬迁）
import { draftRefresh } from '@/services/apiPaths/formula'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import {
  parseDraftRefreshResponse,
  isSuccess,
  isPartialSuccess,
  type DraftRefreshResponse,
} from './formulaRuntimeContract'

// ─── Types ───────────────────────────────────────────────────────────────────

interface RefreshScopeItem {
  key: string
  label: string
  group: string
  cycle?: string | null
}

interface ScopeTreeNode {
  key: string
  label: string
  children?: ScopeTreeNode[]
}

const props = defineProps<{
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  /** 刷新成功/部分成功后通知宿主重载数据 */
  (e: 'refresh-complete', result: DraftRefreshResponse): void
}>()

// ─── 前端门禁 ──────────────────────────────────────────────────────────────────
const { currentRole } = usePermissionMatrix()
const PARTNER_ROLES = ['partner', 'signing_partner']
const isPartner = computed(() => PARTNER_ROLES.includes(currentRole.value))

// ─── 弹窗状态 ──────────────────────────────────────────────────────────────────
const visible = ref(false)
const scopesLoading = ref(false)
const submitting = ref(false)
const rollingBack = ref(false)
const confirmOverwrite = ref(false)
const parsedResult = ref<DraftRefreshResponse | null>(null)

const treeRef = ref<InstanceType<typeof ElTree>>()
const treeData = ref<ScopeTreeNode[]>([])
const checkedScopes = ref<string[]>([])

const WORKPAPER_GROUP_KEY = '__workpaper_group__'

const presetSummary = computed<string>(() => {
  if (!parsedResult.value) return ''
  const pa = parsedResult.value.preset_application
  const parts: string[] = []
  if (pa.preset_count > 0) parts.push(`公式 ${pa.preset_count} 条`)
  if (pa.presetted_pages.length > 0) parts.push(`页面 ${pa.presetted_pages.length} 个`)
  return parts.join(' · ')
})

// ─── 打开弹窗 ─────────────────────────────────────────────────────────────────
async function openDialog() {
  visible.value = true
  parsedResult.value = null
  await loadScopes()
}

async function loadScopes() {
  scopesLoading.value = true
  try {
    const response = await http.get(draftRefresh.scopes, {
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

// ─── 勾选变化 ─────────────────────────────────────────────────────────────────
function onCheck() {
  const tree = treeRef.value
  if (!tree) return
  const leafKeys = tree.getCheckedKeys(true) as string[]
  checkedScopes.value = leafKeys.filter((k) => k !== WORKPAPER_GROUP_KEY)
}

// ─── 确认刷新 ─────────────────────────────────────────────────────────────────
async function onConfirm() {
  if (checkedScopes.value.length === 0) {
    ElMessage.warning('请至少勾选一项刷新内容')
    return
  }
  submitting.value = true
  try {
    const response = await http.post(draftRefresh.execute, {
      project_id: props.projectId,
      year: props.year,
      scopes: checkedScopes.value,
      transaction_mode: 'all_or_nothing',
      confirm_overwrite: confirmOverwrite.value,
    })
    const rawData = response.data?.data ?? response.data
    const result = parseDraftRefreshResponse(rawData)
    parsedResult.value = result

    // 只有 success 或 partial_success 才弹成功提示并通知宿主重载
    if (isSuccess(result)) {
      ElMessage.success(`刷新成功，已应用 ${result.applied_count} 个单元`)
      emit('refresh-complete', result)
    } else if (isPartialSuccess(result)) {
      ElMessage.warning(`部分成功，已应用 ${result.applied_count} 个，失败 ${result.failed_count} 个`)
      emit('refresh-complete', result)
    }
    // failed / idempotent_hit 不弹 success toast（铁律：失败不弹成功）
  } catch (err: unknown) {
    ElMessage.error(extractError(err, '一键刷新失败'))
  } finally {
    submitting.value = false
  }
}

// ─── 回滚 ─────────────────────────────────────────────────────────────────────
async function onRollback() {
  if (!parsedResult.value?.run_id) return
  rollingBack.value = true
  try {
    const response = await http.post(
      draftRefresh.rollback(parsedResult.value.run_id),
    )
    const data = response.data?.data ?? response.data
    if (data?.status === 'rolled_back') {
      ElMessage.success(`回滚成功，已恢复 ${data.restored_count ?? 0} 个单元`)
      parsedResult.value = null
    } else {
      ElMessage.error(`回滚失败：${data?.error || '未知错误'}`)
    }
  } catch (err: unknown) {
    ElMessage.error(extractError(err, '回滚请求失败'))
  } finally {
    rollingBack.value = false
  }
}

// ─── 错误信息提取 ─────────────────────────────────────────────────────────────
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

defineExpose({ openDialog, isPartner, checkedScopes, parsedResult })
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
.gt-rsd-status-banner {
  margin-bottom: 8px;
}
.gt-rsd-preset-info {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
}
.gt-rsd-failure-list {
  margin-top: 4px;
}
.gt-rsd-failure-title {
  margin: 4px 0 2px 0;
  font-size: 12px;
  font-weight: 600;
}
.gt-rsd-failure-list ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--gt-color-text-regular, #606266);
}
.gt-rsd-warns {
  margin-top: 8px;
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
.gt-rsd-rollback-btn {
  margin-top: 10px;
}
</style>
