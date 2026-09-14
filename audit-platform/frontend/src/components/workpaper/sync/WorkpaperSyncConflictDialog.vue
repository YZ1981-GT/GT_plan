<!--
  WorkpaperSyncConflictDialog.vue — 冲突逐项裁决面板

  spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
  Requirements: 8.1, 8.2, 8.3, 8.4, 11.7
  Properties: P35（每条冲突双侧可追溯）/ P36（八项 fence 齐备才可提交）

  ═══ 三条不得违反的边界 ═══

  1. **关闭不应用**（AC 11.7）。关闭只做两件事：`update:visible(false)` 与清空选择。
     组件里唯一调用 `resolveConflicts` 的地方是「提交裁决」，且它自己也不落 HTTP ——
     由桥统一发。判据点遍每一种关闭方式并断言 `resolveConflicts` 零调用。
  2. **批量必须点出范围**（AC 8.3）。范围来自 `WP_SYNC_BULK_SCOPES` 封闭域，
     目标集由纯函数 `bulkScopeTargets` 算出，确认文案由 `describeBulkScope` 逐字点出
     「范围 + 条数 + 裁决」，并且要**再点一次**才真正落到选择上（二次确认）。
  3. **fence 齐备或可见失败**。`room_latest_durable_application_id/sequence` 无读取面，
     桥拒绝替调用方编造，因此本面板要求宿主显式提供；提供不了就禁用提交并逐项列出
     阻断原因 —— 绝不用 canonical application 顶替 room 的 latest durable。

  ═══ 覆盖层为什么不用 el-dialog ═══

  el-dialog 默认 teleport 到 body，DOM 判据必须跨越 teleport 边界才能断言。
  本 spec 的判据全部落在渲染出来的 DOM 上，故用带 `role="dialog"` 的原生覆盖层：
  可聚焦、可 ESC、可点遮罩，且 `wrapper.find` 直接可达。
-->
<template>
  <div
    v-if="visible"
    class="wp-sync-conflict"
    data-testid="wp-sync-conflict-dialog"
    :data-fence-ready="String(fenceReady)"
    :data-conflict-count="String(preview?.conflictCount ?? 0)"
  >
    <div
      class="wp-sync-conflict__mask"
      data-testid="wp-sync-conflict-mask"
      @click="onCloseRequested('mask')"
    />
    <div
      class="wp-sync-conflict__panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wp-sync-conflict-title"
      tabindex="-1"
      @keydown.esc="onCloseRequested('escape')"
    >
      <header class="wp-sync-conflict__header">
        <h3 id="wp-sync-conflict-title" class="wp-sync-conflict__title">
          回写冲突逐项裁决
        </h3>
        <el-tag size="small" type="warning" data-testid="wp-sync-conflict-count-tag">
          共 {{ preview?.conflictCount ?? 0 }} 条
        </el-tag>
        <button
          type="button"
          class="wp-sync-conflict__close"
          data-testid="wp-sync-conflict-close"
          aria-label="关闭冲突面板"
          @click="onCloseRequested('button')"
        >
          关闭
        </button>
      </header>

      <p
        v-if="loadError !== null"
        class="wp-sync-conflict__error"
        data-testid="wp-sync-conflict-load-error"
        :data-code="loadError.code"
      >
        {{ loadError.message }}
      </p>

      <p
        v-if="preview === null && loadError === null"
        class="wp-sync-conflict__empty"
        data-testid="wp-sync-conflict-empty"
      >
        尚未取到冲突预览。
      </p>

      <template v-if="preview !== null">
        <!-- frozen identity：预览是按哪份 bundle / authority model 渲染的 -->
        <div class="wp-sync-conflict__identity" data-testid="wp-sync-conflict-identity">
          <span>请求任务：{{ preview.requestedOperationId }}</span>
          <span>规范任务：{{ preview.canonicalOperationId }}</span>
          <span>规范 application：{{ preview.canonicalApplicationId }}</span>
          <span>授权模型：{{ preview.authorityModel }}</span>
          <span>bundle 摘要：{{ shortDigest(preview.definitionBundleSha256) }}</span>
          <span>契约：{{ preview.contractId }} @ {{ preview.contractSemanticVersion }}</span>
        </div>

        <!-- fence 阻断原因逐项列出（AC 8.5） -->
        <ul
          v-if="!fenceReady"
          class="wp-sync-conflict__blocking"
          data-testid="wp-sync-conflict-fence-blocking"
        >
          <li v-for="reason in fenceBlockingReasons" :key="reason" data-testid="wp-sync-conflict-fence-reason">
            {{ reason }}
          </li>
        </ul>

        <!-- 批量裁决：范围显式 + 二次确认 -->
        <el-card
          shadow="never"
          class="wp-sync-conflict__bulk"
          data-testid="wp-sync-conflict-bulk"
        >
          <div class="wp-sync-conflict__bulk-row">
            <span class="wp-sync-conflict__label">批量范围</span>
            <select
              v-model="bulkScope"
              class="wp-sync-conflict__select"
              data-testid="wp-sync-conflict-bulk-scope"
              aria-label="批量裁决范围"
            >
              <option v-for="scope in bulkScopes" :key="scope" :value="scope">
                {{ bulkScopeLabel[scope] }}
              </option>
            </select>
            <span class="wp-sync-conflict__label">锚点分组</span>
            <select
              v-model="bulkAnchorKey"
              class="wp-sync-conflict__select"
              data-testid="wp-sync-conflict-bulk-anchor"
              aria-label="批量裁决锚点分组"
            >
              <option value="">（未选）</option>
              <option v-for="group in preview.groups" :key="group.groupKey" :value="group.groupKey">
                {{ groupTitle(group) }}
              </option>
            </select>
            <span class="wp-sync-conflict__label">统一裁决为</span>
            <select
              v-model="bulkChoice"
              class="wp-sync-conflict__select"
              data-testid="wp-sync-conflict-bulk-choice"
              aria-label="批量裁决动作"
            >
              <option value="keep_current">保留当前</option>
              <option value="take_incoming">采用回传</option>
            </select>
            <el-button
              size="small"
              plain
              data-testid="wp-sync-conflict-bulk-preview"
              @click="onBulkPreview"
            >
              预览批量范围
            </el-button>
          </div>
          <p
            v-if="bulkError !== null"
            class="wp-sync-conflict__error"
            data-testid="wp-sync-conflict-bulk-error"
            :data-code="bulkError.code"
          >
            {{ bulkError.message }}
          </p>
          <div
            v-if="bulkPending !== null"
            class="wp-sync-conflict__bulk-confirm"
            data-testid="wp-sync-conflict-bulk-confirm"
            :data-target-count="String(bulkPending.targets.length)"
          >
            <span data-testid="wp-sync-conflict-bulk-confirm-text">{{ bulkPending.text }}</span>
            <el-button
              size="small"
              type="warning"
              data-testid="wp-sync-conflict-bulk-apply"
              @click="onBulkApply"
            >
              确认批量裁决
            </el-button>
            <el-button
              size="small"
              plain
              data-testid="wp-sync-conflict-bulk-cancel"
              @click="bulkPending = null"
            >
              取消
            </el-button>
          </div>
        </el-card>

        <!-- 分组：sheet / table / row 三级（AC 8.2） -->
        <el-card
          v-for="group in preview.groups"
          :key="group.groupKey"
          shadow="never"
          class="wp-sync-conflict__group"
          data-testid="wp-sync-conflict-group"
          :data-group-key="group.groupKey"
          :data-sheet-key="group.sheetKey"
          :data-table-key="group.tableKey"
          :data-row-key="group.rowKey"
        >
          <template #header>
            <span data-testid="wp-sync-conflict-group-title">{{ groupTitle(group) }}</span>
          </template>
          <table class="wp-sync-conflict__table">
            <thead>
              <tr>
                <th scope="col">业务字段</th>
                <th scope="col">分类</th>
                <th scope="col">保护策略</th>
                <th scope="col">定位</th>
                <th scope="col" class="is-right">打开时基线</th>
                <th scope="col" class="is-right">服务端当前</th>
                <th scope="col" class="is-right">OnlyOffice 回传</th>
                <th scope="col">裁决</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in group.items"
                :key="item.conflictId"
                data-testid="wp-sync-conflict-item"
                :data-conflict-id="item.conflictId"
                :data-value-type="item.valueType"
                :data-kind="item.kind"
                :data-adjudicable="String(item.adjudicableByValueChoice)"
                :data-protected="String(item.isProtected)"
                :data-choice="selections[item.conflictId]?.choice ?? ''"
              >
                <td>
                  <span data-testid="wp-sync-conflict-item-label">{{ item.businessLabel }}</span>
                  <small class="wp-sync-conflict__key">{{ item.stableFieldKey }}</small>
                </td>
                <td>
                  <el-tag size="small" :type="item.isProtected ? 'danger' : 'info'">
                    {{ conflictKindText[item.kind] ?? item.kind }}
                  </el-tag>
                </td>
                <td data-testid="wp-sync-conflict-item-protection">
                  {{ protectionText[item.protectionPolicy] ?? item.protectionPolicy }}
                </td>
                <td class="wp-sync-conflict__locator">
                  <span data-testid="wp-sync-conflict-item-pointer">{{ item.jsonPointer }}</span>
                  <span data-testid="wp-sync-conflict-item-oo">{{ item.ooLocation }}</span>
                </td>
                <td class="is-right" data-testid="wp-sync-conflict-item-base">
                  {{ renderValue(item, item.base) }}
                </td>
                <td class="is-right" data-testid="wp-sync-conflict-item-current">
                  {{ renderValue(item, item.current) }}
                </td>
                <td class="is-right" data-testid="wp-sync-conflict-item-incoming">
                  {{ renderValue(item, item.incoming) }}
                </td>
                <td>
                  <div v-if="item.adjudicableByValueChoice" class="wp-sync-conflict__choices">
                    <label>
                      <input
                        type="radio"
                        :name="`wp-sync-choice-${item.conflictId}`"
                        value="keep_current"
                        :checked="selections[item.conflictId]?.choice === 'keep_current'"
                        :data-testid="`wp-sync-choice-keep-${item.conflictId}`"
                        @change="onChoose(item, 'keep_current')"
                      />
                      保留当前
                    </label>
                    <label>
                      <input
                        type="radio"
                        :name="`wp-sync-choice-${item.conflictId}`"
                        value="take_incoming"
                        :checked="selections[item.conflictId]?.choice === 'take_incoming'"
                        :data-testid="`wp-sync-choice-incoming-${item.conflictId}`"
                        @change="onChoose(item, 'take_incoming')"
                      />
                      采用回传
                    </label>
                    <label v-if="item.valueType === 'text'">
                      <input
                        type="radio"
                        :name="`wp-sync-choice-${item.conflictId}`"
                        value="manual"
                        :checked="selections[item.conflictId]?.choice === 'manual'"
                        :data-testid="`wp-sync-choice-manual-${item.conflictId}`"
                        @change="onChoose(item, 'manual')"
                      />
                      手工合并
                    </label>
                    <input
                      v-if="selections[item.conflictId]?.choice === 'manual'"
                      type="text"
                      class="wp-sync-conflict__manual"
                      :value="String(selections[item.conflictId]?.value ?? '')"
                      :data-testid="`wp-sync-manual-input-${item.conflictId}`"
                      aria-label="手工合并值"
                      @input="onManualInput(item, $event)"
                    />
                  </div>
                  <span
                    v-else
                    class="wp-sync-conflict__structural"
                    data-testid="wp-sync-conflict-item-structural"
                  >
                    结构冲突，需先修复结构后重试，不可选边收敛
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </el-card>

        <footer class="wp-sync-conflict__footer">
          <span data-testid="wp-sync-conflict-selected-count">
            已选择 {{ resolutions.length }} 条裁决
          </span>
          <span
            v-if="undecidedCount > 0"
            data-testid="wp-sync-conflict-undecided"
          >
            仍有 {{ undecidedCount }} 条可选边冲突未裁决
          </span>
          <p
            v-if="submitError !== null"
            class="wp-sync-conflict__error"
            data-testid="wp-sync-conflict-submit-error"
            :data-code="submitError.code"
          >
            {{ submitError.message }}
          </p>
          <el-button
            size="small"
            type="primary"
            :disabled="!canSubmit"
            data-testid="wp-sync-conflict-submit"
            @click="onSubmit"
          >
            提交裁决
          </el-button>
          <el-button size="small" plain data-testid="wp-sync-conflict-cancel" @click="onCloseRequested('cancel')">
            取消
          </el-button>
        </footer>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'

import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { describeBridgeFailure, type WorkpaperSyncBridge } from './useWorkpaperSyncBridge'
import {
  WP_SYNC_BULK_SCOPES,
  WP_SYNC_BULK_SCOPE_LABEL,
  WP_SYNC_FENCE_MISSING_TEXT,
  bulkScopeTargets,
  buildResolveFence,
  describeBulkScope,
  formatConflictValue,
  parseConflictPreview,
  shortDigest,
  type WorkpaperSyncConflictGroup,
  type WorkpaperSyncConflictItem,
  type WorkpaperSyncConflictPreview,
  type WorkpaperSyncRoomDurableFence,
  type WorkpaperSyncValueEnvelope,
} from './workpaperSyncPresentation'

const props = withDefaults(
  defineProps<{
    /** Task 32 的桥实例：预览拉取与裁决提交都经它，本组件零 HTTP。 */
    bridge: WorkpaperSyncBridge
    visible: boolean
    /**
     * room 最新耐久 application / sequence。
     *
     * 🔴 两项都**没有读取面**（见 `WP_SYNC_TRACE_GAPS`），桥明文拒绝替调用方编造。
     * 因此必须由宿主显式提供；为 null 时提交禁用并逐项列出阻断原因。
     */
    roomDurableFence?: WorkpaperSyncRoomDurableFence | null
  }>(),
  { roomDurableFence: null },
)

const emit = defineEmits<{
  'update:visible': [boolean]
  resolved: [Record<string, unknown>]
  failed: [{ stage: string; code: string; message: string }]
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

interface Selection {
  readonly choice: 'keep_current' | 'take_incoming' | 'manual'
  readonly value?: unknown
}

interface Refusal {
  readonly code: string
  readonly message: string
}

const preview = ref<WorkpaperSyncConflictPreview | null>(null)
const loadError = ref<Refusal | null>(null)
const submitError = ref<Refusal | null>(null)
const bulkError = ref<Refusal | null>(null)
const selections = ref<Record<string, Selection>>({})
const bulkScope = ref<(typeof WP_SYNC_BULK_SCOPES)[number]>('row')
const bulkAnchorKey = ref('')
const bulkChoice = ref<'keep_current' | 'take_incoming'>('take_incoming')
const bulkPending = ref<{
  readonly text: string
  readonly targets: readonly WorkpaperSyncConflictItem[]
  readonly choice: 'keep_current' | 'take_incoming'
} | null>(null)

const bulkScopes = WP_SYNC_BULK_SCOPES
const bulkScopeLabel = WP_SYNC_BULK_SCOPE_LABEL

const conflictKindText: Readonly<Record<string, string>> = Object.freeze({
  value: '同字段异值',
  protected: '受保护字段被改',
  delete_update: '一侧删除一侧更新',
  schema: '结构/身份异常',
  duplicate_word_instance: 'Word 多实例异值',
})

const protectionText: Readonly<Record<string, string>> = Object.freeze({
  editable: '可编辑',
  read_only_formula: '只读（服务端公式）',
  read_only_auto_source: '只读（自动取数）',
  read_only_masked_cell: '只读（掩码单元格）',
  word_only: 'Word 正文（不受管）',
})

function describe(stage: string, error: unknown): Refusal {
  const described = describeBridgeFailure(stage, error)
  return { code: described.errorCode, message: described.message }
}

/** 打开时拉一次预览。关闭时清空全部本地选择 —— 关闭绝不应用任何一侧。 */
watch(
  () => props.visible,
  async (open) => {
    if (!open) {
      resetLocalState()
      return
    }
    loadError.value = null
    submitError.value = null
    try {
      const raw = await props.bridge.fetchConflicts()
      preview.value = parseConflictPreview(raw)
    } catch (error) {
      preview.value = null
      const refusal = describe('get_conflicts', error)
      loadError.value = refusal
      emit('failed', { stage: 'get_conflicts', ...refusal })
    }
  },
  { immediate: true },
)

function resetLocalState(): void {
  selections.value = {}
  bulkPending.value = null
  bulkError.value = null
  bulkAnchorKey.value = ''
}

/**
 * 关闭的**唯一**出口。四种触发（按钮 / 取消 / 遮罩 / ESC）都走这里，
 * 而这里除了收起面板与清空选择什么都不做（AC 11.7）。
 */
function onCloseRequested(_source: 'button' | 'cancel' | 'mask' | 'escape'): void {
  resetLocalState()
  emit('update:visible', false)
}

function groupTitle(group: WorkpaperSyncConflictGroup): string {
  const sheet = group.sheetKey || '（无工作表）'
  const table = group.tableKey || '（无表）'
  const row = group.rowKey || '（表级）'
  return `工作表 ${sheet} / 表 ${table} / 行 ${row}（${group.items.length} 条）`
}

function renderValue(
  item: WorkpaperSyncConflictItem,
  envelopeValue: WorkpaperSyncValueEnvelope | null,
): string {
  // 🔴 金额必须经 store 成员 `fmtAmount`（千分符 + 2 位小数 + 单位后缀）。
  return formatConflictValue(envelopeValue, item.valueType, (value) =>
    displayPrefs.fmtAmount(value),
  )
}

function onChoose(item: WorkpaperSyncConflictItem, choice: Selection['choice']): void {
  const next = { ...selections.value }
  if (choice === 'manual') {
    const existing = next[item.conflictId]
    next[item.conflictId] = { choice, value: existing?.value ?? '' }
  } else {
    next[item.conflictId] = { choice }
  }
  selections.value = next
}

function onManualInput(item: WorkpaperSyncConflictItem, event: Event): void {
  const target = event.target as HTMLInputElement | null
  const next = { ...selections.value }
  next[item.conflictId] = { choice: 'manual', value: target?.value ?? '' }
  selections.value = next
}

const anchorGroup = computed<WorkpaperSyncConflictGroup | null>(() => {
  const key = bulkAnchorKey.value
  if (key === '' || preview.value === null) return null
  return preview.value.groups.find((group) => group.groupKey === key) ?? null
})

/** 第一步：算出显式范围内的目标并给出点明范围与条数的确认文案。 */
function onBulkPreview(): void {
  bulkError.value = null
  bulkPending.value = null
  if (preview.value === null) return
  let targets: readonly WorkpaperSyncConflictItem[]
  try {
    targets = bulkScopeTargets(preview.value.groups, bulkScope.value, anchorGroup.value)
  } catch (error) {
    bulkError.value = describe('bulk_scope', error)
    return
  }
  if (targets.length === 0) {
    bulkError.value = {
      code: 'bulk_scope_empty',
      message: '该范围内没有可选边收敛的未裁决冲突',
    }
    return
  }
  const choiceLabel = bulkChoice.value === 'keep_current' ? '保留当前' : '采用回传'
  bulkPending.value = {
    text: describeBulkScope(bulkScope.value, anchorGroup.value, targets.length, choiceLabel),
    targets,
    choice: bulkChoice.value,
  }
}

/** 第二步：确认后才真正落到选择上。这一步仍然**不**提交给服务端。 */
function onBulkApply(): void {
  const pending = bulkPending.value
  if (pending === null) return
  const next = { ...selections.value }
  for (const item of pending.targets) {
    next[item.conflictId] = { choice: pending.choice }
  }
  selections.value = next
  bulkPending.value = null
}

const resolutions = computed(() =>
  Object.entries(selections.value).map(([conflictId, selection]) => ({
    conflictId,
    choice: selection.choice,
    ...(selection.choice === 'manual' ? { value: selection.value } : {}),
  })),
)

const undecidedCount = computed(() => {
  if (preview.value === null) return 0
  return preview.value.groups
    .flatMap((group) => group.items)
    .filter(
      (item) =>
        item.adjudicableByValueChoice &&
        !item.resolved &&
        selections.value[item.conflictId] === undefined,
    ).length
})

const fenceDraft = computed(() => {
  if (preview.value === null) return { fence: null, missing: [] as readonly string[] }
  return buildResolveFence({
    preview: preview.value,
    roomDurable: props.roomDurableFence,
  })
})

const fenceReady = computed(() => fenceDraft.value.fence !== null)

const fenceBlockingReasons = computed(() =>
  fenceDraft.value.missing.map(
    (key) => WP_SYNC_FENCE_MISSING_TEXT[key] ?? `缺乐观锁字段 ${key}`,
  ),
)

const canSubmit = computed(() => fenceReady.value && resolutions.value.length > 0)

async function onSubmit(): Promise<void> {
  submitError.value = null
  const fence = fenceDraft.value.fence
  if (fence === null || resolutions.value.length === 0) {
    // 按钮已 disabled，但程序化调用也必须可见地失败（不静默）。
    submitError.value = {
      code: 'conflict_submit_gate_closed',
      message: fenceReady.value
        ? '尚未选择任何裁决，无法提交'
        : fenceBlockingReasons.value.join('；'),
    }
    return
  }
  try {
    const outcome = await props.bridge.resolveConflicts({
      fence,
      resolutions: resolutions.value,
    })
    emit('resolved', outcome)
    resetLocalState()
    emit('update:visible', false)
  } catch (error) {
    const refusal = describe('resolve_conflicts', error)
    submitError.value = refusal
    emit('failed', { stage: 'resolve_conflicts', ...refusal })
  }
}

defineExpose({
  /**
   * 可 await 的提交入口（页面级宿主可程序化提交）。
   *
   * 🔴 它与按钮走**同一个** `onSubmit`：门若只长在 `:disabled` 上，程序化调用就能绕过。
   * 判据据此在「fence 缺项」与「零裁决」两种形态下直接调用它，断言写出具体码且零 HTTP。
   */
  submitAdjudication: onSubmit,
  /** 判据用的只读投影：全部来自解析后的预览与本地选择，无第二份状态。 */
  getAdjudication: () => ({
    conflictCount: preview.value?.conflictCount ?? 0,
    groupKeys: (preview.value?.groups ?? []).map((group) => group.groupKey),
    resolutions: resolutions.value,
    undecidedCount: undecidedCount.value,
    fenceReady: fenceReady.value,
    fenceMissing: fenceDraft.value.missing,
  }),
})
</script>

<style scoped>
.wp-sync-conflict {
  position: fixed;
  inset: 0;
  z-index: 2200;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--wp-font-size, 13px);
}

.wp-sync-conflict__mask {
  position: absolute;
  inset: 0;
  background: rgb(0 0 0 / 35%);
}

.wp-sync-conflict__panel {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(1180px, 94vw);
  max-height: 88vh;
  padding: 16px 20px;
  overflow: auto;
  background: #fff;
  border-radius: 4px;
}

.wp-sync-conflict__header {
  display: flex;
  gap: 10px;
  align-items: center;
}

.wp-sync-conflict__title {
  margin: 0;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.wp-sync-conflict__close {
  margin-left: auto;
  padding: 2px 10px;
  font-size: var(--wp-font-size, 13px);
  cursor: pointer;
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
}

.wp-sync-conflict__identity {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  padding: 6px 10px;
  color: #909399;
  background: #fafafa;
  border-left: 3px solid #e6a23c;
}

.wp-sync-conflict__blocking {
  margin: 0;
  padding-left: 20px;
  color: #c45656;
}

.wp-sync-conflict__bulk-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.wp-sync-conflict__bulk-confirm {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
  padding: 6px 10px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
}

.wp-sync-conflict__label {
  color: #909399;
}

.wp-sync-conflict__select,
.wp-sync-conflict__manual {
  padding: 2px 6px;
  font-size: var(--wp-font-size, 13px);
  border: 1px solid #dcdfe6;
  border-radius: 3px;
}

.wp-sync-conflict__table {
  width: 100%;
  font-size: var(--wp-font-size, 13px);
  border-collapse: collapse;
}

.wp-sync-conflict__table th,
.wp-sync-conflict__table td {
  padding: 4px 8px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid #ebeef5;
}

.wp-sync-conflict__table th.is-right,
.wp-sync-conflict__table td.is-right {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.wp-sync-conflict__key,
.wp-sync-conflict__locator {
  display: block;
  color: #a8abb2;
  word-break: break-all;
}

.wp-sync-conflict__choices {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.wp-sync-conflict__structural {
  color: #c45656;
}

.wp-sync-conflict__footer {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid #ebeef5;
}

.wp-sync-conflict__error {
  margin: 0;
  color: #c45656;
}

.wp-sync-conflict__empty {
  margin: 0;
  color: #909399;
}
</style>
