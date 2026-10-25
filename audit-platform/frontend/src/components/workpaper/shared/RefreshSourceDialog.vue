<!--
  RefreshSourceDialog.vue — 刷新取数：来源选择弹窗
  spec: workpaper-sync-adopt-overwrite-and-refresh-source Task 10（方案 D）

  把三条取数路径的选择权交给用户（design §4.4）：
    ① 上游业务数据（走既有 onRowNameAlignmentRefresh，函数体一字不改）
    ② 以在线编辑侧为准，覆盖表单（adopt-substrate，破坏性，需二次确认）
    ③ 以表单为准，同步到在线编辑（说明项，不可选，零请求）

  🔴 entry_id 来源（方案 D）：由宿主 GtWpRenderer 经 activeComponentRef?.syncEntryId 读出后
     以 prop 传入。缺它 ⇒ 不是「能覆盖但没算好」，而是「本底稿没接双模式」⇒ ② 直接禁用
     （复用 Requirement 5.7 / Task 10.3 的禁用态语义）。

  🔴 数字全部取自 dry_run 响应字段，前端不自行重算（Requirement 5.3 / Property 12）。
  🔴 http.post 已由 utils/http 拦截器解信封（response.data = envelope.data）⇒ 直接读业务字段。
-->
<template>
  <el-dialog
    v-model="visible"
    title="刷新取数 · 选择数据来源"
    width="620px"
    top="8vh"
    append-to-body
    destroy-on-close
    class="gt-rsd"
    @closed="onClosed"
  >
    <div v-if="loading" class="gt-rsd__loading" data-testid="rsd-loading">
      <el-skeleton :rows="3" animated />
    </div>

    <template v-else>
      <!-- 摘要：两侧行数 + 增删改条数（全部取自响应字段） -->
      <div v-if="plan" class="gt-rsd__summary" data-testid="rsd-summary">
        <div class="gt-rsd__summary-line">
          <span class="gt-rsd__badge">表单 {{ plan.store_row_count }} 行</span>
          <span class="gt-rsd__sep">｜</span>
          <span class="gt-rsd__badge gt-rsd__badge--oo">在线编辑侧 {{ plan.substrate_row_count }} 行</span>
        </div>
        <div class="gt-rsd__summary-delta">
          若以在线编辑侧覆盖：将新增 <b>{{ totalAdded }}</b> 行、删除
          <b class="gt-rsd__del">{{ totalDeleted }}</b> 行、更新 <b>{{ totalUpdated }}</b> 行
        </div>
      </div>
    </template>

    <!-- 三项来源 -->
    <div class="gt-rsd__options">
      <!-- ① 上游业务数据 -->
      <button
        class="gt-rsd__opt"
        type="button"
        data-testid="rsd-opt-upstream"
        :disabled="acting"
        @click="onChooseUpstream"
      >
        <div class="gt-rsd__opt-title">① 以上游业务数据为准，刷新本表</div>
        <div class="gt-rsd__opt-desc">按行名/科目从账套与四表库重取（既有「刷新取数」行为，不删除在线编辑侧数据）。</div>
      </button>

      <!-- ② 以在线编辑侧为准，覆盖表单（破坏性） -->
      <button
        class="gt-rsd__opt gt-rsd__opt--danger"
        type="button"
        data-testid="rsd-opt-overwrite"
        :disabled="!canOverwrite || acting"
        @click="onChooseOverwrite"
      >
        <div class="gt-rsd__opt-title">② 以在线编辑侧为准，覆盖表单</div>
        <div class="gt-rsd__opt-desc">
          用在线编辑（OnlyOffice）当前受管行覆盖本表；表单侧多余行将被删除。破坏性操作，需二次确认。
        </div>
        <div v-if="overwriteDisabledReason" class="gt-rsd__opt-blocked" data-testid="rsd-overwrite-blocked">
          {{ overwriteDisabledReason }}
        </div>
      </button>

      <!-- ③ 说明项：不可选，零请求 -->
      <div class="gt-rsd__opt gt-rsd__opt--note" data-testid="rsd-opt-note">
        <div class="gt-rsd__opt-title">③ 以表单为准，同步到在线编辑</div>
        <div class="gt-rsd__opt-desc">
          该方向请点工具栏「在线编辑」按钮，在 OnlyOffice 中打开本表后编辑并保存即可同步，此处不提供入口。
        </div>
      </div>
    </div>

    <template #footer>
      <el-button data-testid="rsd-close" @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { WP_SYNC_USER_PREFIX_TEMPLATE } from '@/components/workpaper/sync/workpaperSyncContract.generated'

/**
 * 逐 item delta（取自 dry_run 响应 deltas[]）。字段名与后端 `_plan_wire_form` 逐字一致。
 * 🔴 计数一律用后端给的 rows_*_count，绝不 rows_added.length 自算（Property 12）。
 */
interface OverwriteDelta {
  item_id: string
  rows_added_count: number
  rows_deleted_count: number
  rows_updated_count: number
}
interface OverwritePlanWire {
  plan_digest: string
  store_row_count: number
  substrate_row_count: number
  expected_revision: number
  deltas: OverwriteDelta[]
}

const props = defineProps<{
  modelValue: boolean
  wpId: string
  projectId: string
  /** 方案 D：宿主经 activeComponentRef?.syncEntryId 读出；null = 本底稿未接双模式。 */
  entryId: string | null
  /** 第一项「上游业务数据」的处理器 = 宿主既有 onRowNameAlignmentRefresh（函数体一字不改）。 */
  upstreamRefresh: () => void | Promise<void>
  /** 覆盖成功后宿主重载（reload）。 */
  reload: () => void | Promise<void>
}>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const visible = computed<boolean>({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const acting = ref(false)
const plan = ref<OverwritePlanWire | null>(null)
/** dry_run 若因 not_published / contract_required 失败，记原因文案（就地显示 + 禁用②）。 */
const blockedReason = ref<string>('')

// 🔴 计数取自响应字段并跨 item 求和 —— 前端只做「加总」不做「计数」，逐 item 数来自后端。
const totalAdded = computed(() => (plan.value?.deltas ?? []).reduce((s, d) => s + d.rows_added_count, 0))
const totalDeleted = computed(() => (plan.value?.deltas ?? []).reduce((s, d) => s + d.rows_deleted_count, 0))
const totalUpdated = computed(() => (plan.value?.deltas ?? []).reduce((s, d) => s + d.rows_updated_count, 0))

/** 没有 entry_id（未接双模式）或 dry_run 被 block ⇒ 不能覆盖。 */
const canOverwrite = computed(() => !!props.entryId && !!plan.value && !blockedReason.value)
const overwriteDisabledReason = computed(() => {
  if (!props.entryId) return '本底稿未接入在线编辑双模式，无「在线编辑侧」可覆盖。'
  if (blockedReason.value) return blockedReason.value
  return ''
})

/** 拼 adopt-substrate URL。🔴 entry_id 含 `/`，Starlette `:path` 转换器接收，不得 percent-encode。 */
function adoptUrl(): string {
  const base = WP_SYNC_USER_PREFIX_TEMPLATE
    .replace('{project_id}', props.projectId)
    .replace('{wp_id}', props.wpId)
    .replace('{entry_id}', String(props.entryId))
  return `${base}/adopt-substrate`
}

function errorCodeOf(e: any): string {
  return e?.response?.data?.detail?.error_code || ''
}
function errorMsgOf(e: any): string {
  return e?.response?.data?.detail?.message || e?.message || '请稍后重试'
}

/** 打开即请求 dry_run；无 entry_id 时跳过（②会以禁用态显示原因）。 */
async function loadDryRun(): Promise<void> {
  plan.value = null
  blockedReason.value = ''
  if (!props.entryId) return
  loading.value = true
  try {
    const { data } = await http.post(adoptUrl(), { dry_run: true })
    plan.value = data as OverwritePlanWire
  } catch (e: any) {
    const code = errorCodeOf(e)
    if (code === 'adopt_substrate_not_published') {
      blockedReason.value = '在线编辑侧尚无已发布底稿可采纳，无法覆盖。'
    } else if (code === 'adopt_contract_required') {
      blockedReason.value = '本底稿的双模式契约未就绪，无法覆盖。'
    } else {
      blockedReason.value = '差异预览失败：' + errorMsgOf(e)
    }
  } finally {
    loading.value = false
  }
}

/** ① 上游业务数据：直接调宿主既有处理器，随后关闭弹窗。 */
async function onChooseUpstream(): Promise<void> {
  acting.value = true
  try {
    await props.upstreamRefresh()
    visible.value = false
  } finally {
    acting.value = false
  }
}

/** ② 覆盖表单：二次确认（明示破坏性 + 删除行数）→ dry_run:false（带 digest + revision）。 */
async function onChooseOverwrite(): Promise<void> {
  if (!canOverwrite.value || !plan.value) return
  try {
    await ElMessageBox.confirm(
      `此操作将以在线编辑侧的受管行覆盖本表单，其中 ${totalDeleted.value} 行将被删除、` +
        `${totalAdded.value} 行将被新增。此操作具有破坏性，是否继续？`,
      '覆盖表单确认',
      { confirmButtonText: '确认覆盖', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消 ⇒ 零写入
  }
  acting.value = true
  try {
    const { data } = await http.post(adoptUrl(), {
      dry_run: false,
      plan_digest: plan.value.plan_digest,
      expected_revision: plan.value.expected_revision,
    })
    // 🔴 提示实际增删条数：取自执行响应，不复用 dry_run 的数（Requirement 5.10）。
    const changed = (data as any)?.changed_item_count ?? 0
    ElMessage.success(`已按在线编辑侧覆盖表单，共变更 ${changed} 个数据项，正在重载`)
    visible.value = false
    await props.reload()
  } catch (e: any) {
    if (errorCodeOf(e) === 'adopt_plan_digest_mismatch') {
      // 两侧在「看摘要」与「按确认」之间变化过 ⇒ 重取 dry_run 让用户重看差异。
      ElMessage.warning('两侧数据已变化，差异摘要已过期，正在重新加载最新差异')
      await loadDryRun()
    } else {
      ElMessage.error('覆盖表单失败：' + errorMsgOf(e))
    }
  } finally {
    acting.value = false
  }
}

function onClosed(): void {
  plan.value = null
  blockedReason.value = ''
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void loadDryRun()
  },
  // 🔴 immediate：弹窗可能**挂载时就是打开态**（父级 v-model 初值为 true）。
  //    不加它，那种情形下 dry_run 永远不会发 —— 摘要区恒空而没有任何报错。
  { immediate: true },
)
</script>

<style scoped>
.gt-rsd__summary {
  margin-bottom: 16px;
  padding: 12px 14px;
  background: var(--gt-color-fill-light, #f5f3fa);
  border-radius: 8px;
}
.gt-rsd__summary-line { font-size: 15px; font-weight: 600; }
.gt-rsd__badge--oo { color: var(--gt-color-primary, #4b2d77); }
.gt-rsd__sep { margin: 0 8px; color: #bbb; }
.gt-rsd__summary-delta { margin-top: 8px; font-size: 13px; color: #666; }
.gt-rsd__del { color: #d9534f; }
.gt-rsd__options { display: flex; flex-direction: column; gap: 10px; }
.gt-rsd__opt {
  width: 100%;
  text-align: left;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color, #dcdfe6);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.gt-rsd__opt:hover:not(:disabled) { border-color: var(--gt-color-primary, #4b2d77); background: #faf9fd; }
.gt-rsd__opt:disabled { cursor: not-allowed; opacity: 0.55; }
.gt-rsd__opt--danger:hover:not(:disabled) { border-color: #d9534f; background: #fdf5f5; }
.gt-rsd__opt--note { cursor: default; background: #fafafa; color: #888; }
.gt-rsd__opt-title { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.gt-rsd__opt-desc { font-size: 12px; color: #777; line-height: 1.5; }
.gt-rsd__opt-blocked { margin-top: 6px; font-size: 12px; color: #d9534f; }
.gt-rsd__loading { padding: 20px 8px; }
</style>
