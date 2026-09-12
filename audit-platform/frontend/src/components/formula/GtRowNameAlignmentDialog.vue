<!--
  GtRowNameAlignmentDialog.vue — 行名对齐确认弹窗
  spec: formula-row-name-alignment-confirmation Task 9

  两栏：左=底稿行名（状态 tag）/ 右=候选账套明细名（金额 + 相似度提示 + 排序）。
  支持 1:N / N:1 / N:M 建立映射；多对一必须弹口径确认再落库（Requirement 2.4）。
  确认后关闭并通知宿主重算；取消**零写入**（Property 4，不发任何 confirm 请求）。

  🔴 不合并、不复制 GtRefreshScopeDialog 的 scope 树（红基线 2）——本弹窗解决
  「名字怎么对上」，与「刷哪些作用域」是不同关注点。
-->
<template>
  <el-dialog
    v-model="visible"
    title="行名对齐确认 · 把对不上的账套明细名手动确认"
    width="960px"
    top="6vh"
    append-to-body
    destroy-on-close
    class="gt-rna-dialog"
    @closed="onClosed"
  >
    <el-alert type="info" :closable="false" show-icon class="gt-rna-tip">
      <template #title>
        左侧是底稿固定行名，右侧是账套（四表库）当前明细名。为每个待确认行勾选对应的账套明细
        （可一对多、多对一）。未确认的行保持「未匹配」，不会伪造数值。
      </template>
    </el-alert>

    <div class="gt-rna-body">
      <!-- 左栏：底稿行名 -->
      <div class="gt-rna-col gt-rna-col--rows">
        <div class="gt-rna-col__head">底稿行名（{{ pendingRows.length }} 行待确认 / 共 {{ rows.length }}）</div>
        <div class="gt-rna-rowlist">
          <div
            v-for="r in rows"
            :key="r.row_key"
            class="gt-rna-rowitem"
            :class="{ 'is-active': activeRowKey === r.row_key }"
            @click="activeRowKey = r.row_key"
          >
            <div class="gt-rna-rowitem__label">{{ r.row_label || r.row_key }}</div>
            <div class="gt-rna-rowitem__meta">
              <el-tag :type="stateTagType(r.match_state)" size="small" effect="light">
                {{ stateLabel(r.match_state) }}
              </el-tag>
              <el-tag v-if="selectionCount(r.row_key) > 0" size="small" type="success" effect="plain">
                已选 {{ selectionCount(r.row_key) }}
              </el-tag>
              <span v-if="r.stale_reason" class="gt-rna-stale" :title="r.stale_reason">失效</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏：候选账套明细名 -->
      <div class="gt-rna-col gt-rna-col--cands">
        <div class="gt-rna-col__head">
          候选账套明细名<span v-if="activeRow"> · {{ activeRow.row_label || activeRow.row_key }}</span>
        </div>
        <div v-if="!activeRow" class="gt-rna-empty">
          <el-empty :image-size="48" description="请先在左侧选择一行" />
        </div>
        <div v-else-if="activeRow.candidates.length === 0" class="gt-rna-empty">
          <el-empty :image-size="48" description="该行在账套中无候选明细（账套可能未导入或科目无数据）" />
        </div>
        <div v-else class="gt-rna-candlist">
          <label
            v-for="c in activeRow.candidates"
            :key="c.target_identity.dimension_key"
            class="gt-rna-canditem"
          >
            <el-checkbox
              :model-value="isSelected(activeRow.row_key, c.target_identity.dimension_key)"
              @change="(v: boolean) => toggleSelection(activeRow!.row_key, c, v)"
            />
            <span class="gt-rna-canditem__name">{{ c.display_name }}</span>
            <span class="gt-rna-canditem__amt">{{ fmtAmount(c.amount) }}</span>
            <el-tag size="small" effect="plain" :type="simTagType(c.similarity)">
              相似 {{ Math.round(c.similarity * 100) }}%
            </el-tag>
            <span
              v-if="isMultiReferenced(c.target_identity.dimension_key)"
              class="gt-rna-dup"
              title="该账套明细已被其它底稿行引用（多对一）"
            >多对一</span>
          </label>
        </div>
      </div>
    </div>

    <!-- 多对一告警条（Requirement 2.4） -->
    <el-alert
      v-if="multiToOneRows.length > 0"
      type="warning"
      :closable="false"
      show-icon
      class="gt-rna-dup-warn"
    >
      <template #title>
        存在多对一映射：同一账套明细被多个底稿行引用，该明细金额将在这些行**分别计入**（不自动去重），
        可能造成合计重复。确认前请核对口径。
      </template>
    </el-alert>

    <template #footer>
      <span class="gt-rna-footer-hint">取消不会写入任何映射</span>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!hasAnySelection"
        @click="onConfirm"
      >
        确认映射并重算
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  eventBus,
  type OpenRowNameAlignmentPayload,
  type RowNameAlignmentRowWire,
  type RowNameAlignmentCandidateWire,
  type RowNameAlignmentTargetWire,
} from '@/utils/eventBus'
import { DisplayPrefs_Key } from '@/components/workpaper/composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// 🔴 fmtAmount 是 store 成员、不是模块导出（memory 铁律）
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
function fmtAmount(v: string | number | null): string {
  const n = typeof v === 'string' ? Number(v) : (v ?? 0)
  return displayPrefs.fmtAmount(Number.isFinite(n) ? n : 0)
}

const visible = ref(false)
const submitting = ref(false)

const ctx = ref<OpenRowNameAlignmentPayload | null>(null)
const rows = ref<RowNameAlignmentRowWire[]>([])
const activeRowKey = ref<string>('')

/** 用户选择：row_key → dimension_key → 目标身份（含 base_mapping_version 用行 wire 的） */
const selections = ref<Record<string, Map<string, RowNameAlignmentTargetWire>>>({})

const activeRow = computed<RowNameAlignmentRowWire | null>(
  () => rows.value.find((r) => r.row_key === activeRowKey.value) ?? null,
)

const pendingRows = computed(() =>
  rows.value.filter((r) => r.match_state === 'unmatched' || r.match_state === 'ambiguous'),
)

const hasAnySelection = computed(() =>
  Object.values(selections.value).some((m) => m.size > 0),
)

// ─── 状态标签 ─────────────────────────────────────────────────────────────
function stateLabel(s: string): string {
  return (
    {
      auto_matched: '自动匹配',
      ambiguous: '待确认（多候选）',
      unmatched: '未匹配',
      user_confirmed: '已确认',
    } as Record<string, string>
  )[s] ?? s
}
function stateTagType(s: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  return (
    {
      auto_matched: 'success',
      ambiguous: 'warning',
      unmatched: 'danger',
      user_confirmed: 'success',
    } as Record<string, 'success' | 'warning' | 'danger'>
  )[s] ?? 'info'
}
function simTagType(sim: number): '' | 'success' | 'warning' | 'info' {
  if (sim >= 0.8) return 'success'
  if (sim >= 0.55) return 'warning'
  return 'info'
}

// ─── 选择管理 ─────────────────────────────────────────────────────────────
function selectionCount(rowKey: string): number {
  return selections.value[rowKey]?.size ?? 0
}
function isSelected(rowKey: string, dimKey: string): boolean {
  return selections.value[rowKey]?.has(dimKey) ?? false
}
function toggleSelection(rowKey: string, c: RowNameAlignmentCandidateWire, on: boolean) {
  const m = selections.value[rowKey] ?? new Map<string, RowNameAlignmentTargetWire>()
  if (on) m.set(c.target_identity.dimension_key, c.target_identity)
  else m.delete(c.target_identity.dimension_key)
  selections.value = { ...selections.value, [rowKey]: m }
}

/** 某 dimension_key 被多少个 row 选中（多对一检测）。 */
function referenceCount(dimKey: string): number {
  let n = 0
  for (const m of Object.values(selections.value)) {
    if (m.has(dimKey)) n += 1
  }
  return n
}
function isMultiReferenced(dimKey: string): boolean {
  return referenceCount(dimKey) > 1
}
const multiToOneRows = computed<string[]>(() => {
  const dupDims = new Set<string>()
  const dimToRows: Record<string, Set<string>> = {}
  for (const [rk, m] of Object.entries(selections.value)) {
    for (const dim of m.keys()) {
      ;(dimToRows[dim] ??= new Set()).add(rk)
    }
  }
  const affected = new Set<string>()
  for (const [dim, rowSet] of Object.entries(dimToRows)) {
    if (rowSet.size > 1) {
      dupDims.add(dim)
      rowSet.forEach((rk) => affected.add(rk))
    }
  }
  return [...affected]
})

// ─── 打开（eventBus 触发） ─────────────────────────────────────────────────
function open(payload: OpenRowNameAlignmentPayload) {
  ctx.value = payload
  rows.value = payload.rows ?? []
  selections.value = {}
  // 预选已确认行的既有映射（供修正入口），并默认激活第一个待确认行
  for (const r of rows.value) {
    if (r.match_state === 'user_confirmed' && r.target_identity.length) {
      const m = new Map<string, RowNameAlignmentTargetWire>()
      for (const t of r.target_identity) m.set(t.dimension_key, t)
      selections.value[r.row_key] = m
    }
  }
  activeRowKey.value = pendingRows.value[0]?.row_key ?? rows.value[0]?.row_key ?? ''
  visible.value = true
}

// ─── 确认（写映射，单事务） ────────────────────────────────────────────────
async function onConfirm() {
  const c = ctx.value
  if (!c) return

  // 多对一口径二次确认（Requirement 2.4）
  if (multiToOneRows.value.length > 0) {
    try {
      await ElMessageBox.confirm(
        '存在多对一映射：同一账套明细被多个底稿行引用，其金额将在这些行分别计入（不自动去重），' +
          '可能造成合计重复。是否确认按此口径落库？',
        '多对一口径确认',
        { type: 'warning', confirmButtonText: '确认落库', cancelButtonText: '返回修改' },
      )
    } catch {
      return // 用户取消 → 不写入
    }
  }

  const payloadRows = Object.entries(selections.value)
    .filter(([, m]) => m.size > 0)
    .map(([rowKey, m]) => {
      const rowWire = rows.value.find((r) => r.row_key === rowKey)
      return {
        row_key: rowKey,
        targets: [...m.values()],
        base_mapping_version: rowWire?.mapping_version ?? null,
      }
    })
  if (payloadRows.length === 0) {
    ElMessage.warning('请至少为一行选择账套明细')
    return
  }

  submitting.value = true
  try {
    await http.post(`/api/workpapers/${c.wpId}/row-name-mapping/confirm`, {
      sheet_code: c.sheetCode,
      rows: payloadRows,
      idempotency_key: `rna-${c.wpId}-${c.sheetCode}-${Date.now()}`,
      dataset_id: c.datasetId ?? null,
    })
    ElMessage.success(`已确认 ${payloadRows.length} 行映射，正在重算`)
    visible.value = false
    // 通知宿主用新映射重算受影响行
    eventBus.emit('row-name-alignment:confirmed', {
      wpId: c.wpId,
      sheetCode: c.sheetCode,
    })
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { detail?: { message?: string } } } }
    if (e?.response?.status === 409) {
      ElMessage.error(
        e.response.data?.detail?.message || '映射版本冲突，请重新刷新后再确认',
      )
    } else {
      ElMessage.error(e?.response?.data?.detail?.message || '确认映射失败')
    }
  } finally {
    submitting.value = false
  }
}

function onClosed() {
  // 关闭即丢弃本地草稿（取消零写入：无 http.post 发出）
  ctx.value = null
  rows.value = []
  selections.value = {}
  activeRowKey.value = ''
}

// 🔴 生命周期内注册/反注册 —— setup 顶层 eventBus.on 无 off 会随宿主重挂累积监听器，
//    同一事件触发多个陈旧弹窗实例（复盘 #1 修复）。
onMounted(() => {
  eventBus.on('open-row-name-alignment', open)
})
onUnmounted(() => {
  eventBus.off('open-row-name-alignment', open)
})

defineExpose({ open, visible, rows, selections, multiToOneRows, toggleSelection, onConfirm })
</script>

<style scoped>
.gt-rna-tip {
  margin-bottom: 12px;
}
.gt-rna-body {
  display: flex;
  gap: 12px;
  min-height: 360px;
}
.gt-rna-col {
  flex: 1 1 50%;
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.gt-rna-col__head {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  background: #fafafa;
  border-bottom: 1px solid var(--gt-color-border-lighter, #ebeef5);
}
.gt-rna-rowlist,
.gt-rna-candlist {
  flex: 1 1 auto;
  overflow: auto;
  max-height: 46vh;
}
.gt-rna-rowitem {
  padding: 8px 12px;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.gt-rna-rowitem:hover {
  background: #f5f9ff;
}
.gt-rna-rowitem.is-active {
  background: #ecf5ff;
}
.gt-rna-rowitem__label {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-rna-rowitem__meta {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-shrink: 0;
}
.gt-rna-stale {
  font-size: 12px;
  color: var(--el-color-danger, #f56c6c);
}
.gt-rna-canditem {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
}
.gt-rna-canditem:hover {
  background: #f5f9ff;
}
.gt-rna-canditem__name {
  flex: 1 1 auto;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-rna-canditem__amt {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--gt-color-text-regular, #606266);
}
.gt-rna-dup {
  font-size: 12px;
  color: var(--el-color-warning, #e6a23c);
}
.gt-rna-empty {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-rna-dup-warn {
  margin-top: 12px;
}
.gt-rna-footer-hint {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
  margin-right: auto;
}
</style>
