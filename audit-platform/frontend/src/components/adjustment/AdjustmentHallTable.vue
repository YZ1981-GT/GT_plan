<template>
  <Teleport to="body" :disabled="!isFullscreen">
    <div ref="rootRef" class="gt-adj-hall-table" :class="{ 'gt-fullscreen': isFullscreen }">
      <div v-if="isFullscreen" class="gt-adj-hall-fs-bar">
        <span>调整分录（ESC 退出全屏）</span>
        <el-button size="small" @click="toggleFullscreen">退出全屏</el-button>
      </div>
      <el-table
        ref="tableRef"
        v-loading="loading"
        :data="rows"
        row-key="entry_group_id"
        border
        size="small"
        :max-height="isFullscreen ? 'calc(100vh - 60px)' : 'calc(100vh - 300px)'"
        :class="`gt-tb-font-${displayPrefs.fontSize}`"
        :row-class-name="rowClass"
        empty-text="暂无分录"
        @selection-change="(sel: any[]) => emit('selection-change', sel)"
      >
        <el-table-column type="selection" width="36" />
        <el-table-column type="expand" width="32">
          <template #default="{ row }">
            <div class="gt-adj-expand-detail">
              <table class="gt-adj-line-table">
                <thead>
                  <tr><th>科目编码</th><th>科目名称</th><th class="c">方向</th><th class="r">借方金额</th><th class="r">贷方金额</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(li, idx) in row.line_items || []" :key="idx">
                    <td>{{ li.standard_account_code }}<span v-if="li.detail_account_code" class="gt-adj-detail-code"> / {{ li.detail_account_code }}</span></td>
                    <td>{{ li.account_name }}</td>
                    <td class="c"><span :class="isDebit(li) ? 'gt-adj-dir-dr' : 'gt-adj-dir-cr'">{{ isDebit(li) ? '借' : '贷' }}</span></td>
                    <td class="r gt-amt"><GtAmountCell v-if="isDebit(li)" :value="li.debit_amount" /></td>
                    <td class="r gt-amt"><GtAmountCell v-if="!isDebit(li)" :value="li.credit_amount" /></td>
                  </tr>
                </tbody>
              </table>
              <div class="gt-adj-expand-footer">
                <span>创建：{{ fmtDate(row.created_at) }}</span>
                <span v-if="row.description">📝 {{ row.description }}</span>
                <span v-if="row.review_status === S.REJECTED && row.rejection_reason" class="gt-adj-reject">驳回原因：{{ row.rejection_reason }}</span>
                <span v-if="row.reviewer_name">复核人：{{ row.reviewer_name }}{{ row.reviewed_at ? ` · ${fmtDateTime(row.reviewed_at)}` : '' }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="编号" prop="adjustment_no" width="104" />
        <el-table-column label="类型" width="84">
          <template #default="{ row }">
            <el-tag :type="isAje(row) ? 'danger' : 'warning'" size="small" class="gt-adj-type-tag">{{ isAje(row) ? '审计调整' : '重分类' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="摘要" prop="description" min-width="130" show-overflow-tooltip />
        <el-table-column label="主要科目" min-width="190">
          <template #default="{ row }">
            <div class="gt-adj-voucher">
              <template v-for="(li, idx) in row.line_items || []" :key="idx">
                <div v-if="isDirectionSwitch(row.line_items, idx)" class="gt-adj-voucher-divider" />
                <div class="gt-adj-voucher-row">
                  <span class="gt-adj-voucher-code">{{ li.standard_account_code }}</span>
                  <span class="gt-adj-voucher-name">{{ li.account_name || '—' }}</span>
                </div>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" width="110" align="right">
          <template #default="{ row }">
            <div class="gt-adj-voucher">
              <template v-for="(li, idx) in row.line_items || []" :key="idx">
                <div v-if="isDirectionSwitch(row.line_items, idx)" class="gt-adj-voucher-divider" />
                <div class="gt-adj-voucher-amt gt-amt"><GtAmountCell v-if="isDebit(li)" :value="li.debit_amount" /></div>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="110" align="right">
          <template #default="{ row }">
            <div class="gt-adj-voucher">
              <template v-for="(li, idx) in row.line_items || []" :key="idx">
                <div v-if="isDirectionSwitch(row.line_items, idx)" class="gt-adj-voucher-divider" />
                <div class="gt-adj-voucher-amt gt-amt"><GtAmountCell v-if="!isDebit(li)" :value="li.credit_amount" /></div>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="编制人" width="84">
          <template #default="{ row }">{{ row.creator_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="来源" width="104">
          <template #default="{ row }">
            <template v-if="row.origin === 'workpaper'">
              <el-tag v-if="row.source_missing" type="warning" size="small" effect="plain" title="来源底稿已删除，可在这里删除这笔草稿">底稿已删除</el-tag>
              <el-tag v-else type="success" size="small" class="gt-adj-link" :title="`打开来源底稿 ${row.source_wp_code || ''}`"
                @click="emit('action', 'source', row)">底稿 {{ row.source_wp_code || '' }}</el-tag>
            </template>
            <el-tag v-else type="info" size="small" effect="plain">手工</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150" fixed="right">
          <template #default="{ row }">
            <div class="gt-adj-status-cell">
              <GtStatusTag dict-key="adjustment_status" :value="row.review_status" />
              <el-tag v-if="row.has_active_collaboration" type="primary" size="small" effect="plain" class="gt-adj-link"
                title="存在进行中的协作补充，点击查看" @click="emit('action', 'collab', row)">🤝协作中</el-tag>
              <el-tag v-if="row.converted_to_misstatement_id" type="warning" size="small" effect="plain">已转错报</el-tag>
              <StaleIndicator v-if="row.converted_to_misstatement_id && staleMisstatementIds.has(row.converted_to_misstatement_id)"
                :stale="true" tooltip="错报阈值已变更，建议重新评估" size="small" />
            </div>
            <div v-if="row.review_status === S.REJECTED && row.rejection_reason" class="gt-adj-reject gt-adj-ellipsis" :title="row.rejection_reason">
              驳回：{{ row.rejection_reason }}
            </div>
            <div v-else-if="row.reviewer_name && row.review_status === S.APPROVED" class="gt-adj-meta">
              {{ row.reviewer_name }} · {{ fmtDate(row.reviewed_at) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="236" fixed="right">
          <template #default="{ row }">
            <div class="gt-adj-action-cell">
              <template v-for="b in primaryButtons(row)" :key="b.action">
                <el-button size="small" link :type="b.type" :loading="busy === `${b.action}:${row.entry_group_id}`"
                  :disabled="!!busy" @click="emit('action', b.action, row)">{{ b.label }}</el-button>
              </template>
              <el-dropdown trigger="click" @command="(cmd: string) => emit('action', cmd, row)">
                <el-button size="small" link type="info">更多 ▾</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-for="m in moreItems(row)" :key="m.action" :command="m.action" :divided="m.divided">{{ m.label }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * 调整大厅分录列表（spec adjustment-hall-entry-review-closure 需求 5）：勾选批量、展开明细、按状态与权限显示操作，
 * 低频操作收进「更多」；`reveal(id)` 供 `?focus=` 深链定位（展开 + 滚到可见 + 高亮）。
 * 原先用的 GtEditableTable 在只读模式下不显示勾选列（批量复核栏从未出现），也不能按行展开 / 高亮。
 */
import { nextTick, ref } from 'vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtStatusTag from '@/components/common/GtStatusTag.vue'
import StaleIndicator from '@/components/StaleIndicator.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useFullscreen } from '@/composables/useFullscreen'
import { fmtDate, fmtDateTime } from '@/utils/formatters'
import { ADJUSTMENT_STATUS as S } from '@/constants/statusEnum'
import { rowActions, type HallAction, type HallEntry, type HallPerms } from '@/composables/useAdjustmentHallActions'

const props = withDefaults(defineProps<{
  rows: any[]
  loading?: boolean
  perms: HallPerms
  /** useAdjustmentHallActions 的进行中操作键 */
  busy?: string
  /** 需要高亮的分录组 id（?focus= 深链） */
  focusId?: string
  staleMisstatementIds?: Set<string>
}>(), { loading: false, busy: '', focusId: '', staleMisstatementIds: () => new Set<string>() })

const emit = defineEmits<{
  'selection-change': [rows: any[]]
  action: [action: string, row: any]
}>()

const displayPrefs = useDisplayPrefsStore()
const { isFullscreen, toggleFullscreen } = useFullscreen()
const rootRef = ref<HTMLElement | null>(null)
const tableRef = ref<any>(null)

const isAje = (row: HallEntry) => String(row.adjustment_type || '').toLowerCase() === 'aje'
const isDebit = (li: { debit_amount: unknown }) => Number(li.debit_amount) > 0

function isDirectionSwitch(items: Array<{ debit_amount: unknown }>, idx: number): boolean {
  return idx > 0 && isDebit(items[idx - 1]) !== isDebit(items[idx])
}

function rowClass({ row }: { row: HallEntry }): string {
  return props.focusId && row.entry_group_id === props.focusId ? 'gt-adj-row-focus' : ''
}

type ButtonType = 'primary' | 'success' | 'warning' | 'danger' | 'info'
const PRIMARY: Array<{ action: HallAction; label: (row: HallEntry) => string; type: ButtonType; when?: (row: HallEntry) => boolean }> = [
  { action: 'edit', label: () => '编辑', type: 'primary' },
  { action: 'submit', label: (r) => (r.review_status === S.REJECTED ? '重新提交' : '提交复核'), type: 'primary' },
  { action: 'approve', label: () => '通过', type: 'success', when: (r) => r.review_status === S.PENDING_REVIEW },
  { action: 'reject', label: () => '驳回', type: 'danger' },
  { action: 'withdraw', label: () => '撤回提交', type: 'warning' },
  { action: 'revoke', label: () => '撤回复核', type: 'warning' },
  { action: 'delete', label: () => '删除', type: 'danger' },
]

function primaryButtons(row: HallEntry) {
  const allowed = rowActions(row, props.perms)
  return PRIMARY.filter((b) => allowed.has(b.action) && (!b.when || b.when(row)))
    .map((b) => ({ action: b.action, label: b.label(row), type: b.type }))
}

function moreItems(row: HallEntry & { origin?: string | null }) {
  const allowed = rowActions(row, props.perms)
  const items: Array<{ action: string; label: string; divided?: boolean }> = []
  if (allowed.has('approve') && row.review_status === S.DRAFT) items.push({ action: 'approve', label: '直接通过（不经提交）' })
  if (allowed.has('convert')) items.push({ action: 'convert', label: '转为未更正错报' })
  if (row.converted_to_misstatement_id) items.push({ action: 'misstatement', label: '查看已转错报' })
  if (row.origin === 'workpaper') items.push({ action: 'source', label: '打开来源底稿' })
  items.push(
    { action: 'collab', label: '协作补充', divided: items.length > 0 },
    { action: 'related', label: '关联底稿' },
    { action: 'impact', label: '影响范围（报表行 / 底稿）' },
    { action: 'trust', label: '数字信任度' },
    { action: 'history', label: '变更历史' },
    { action: 'status-machine', label: '状态流转说明' },
  )
  return items
}

/** 定位一行：展开、滚到可见（高亮由 focusId 控制） */
async function reveal(entryGroupId: string): Promise<void> {
  const row = props.rows.find((r) => r.entry_group_id === entryGroupId)
  if (!row) return
  await nextTick()
  tableRef.value?.toggleRowExpansion?.(row, true)
  await nextTick()
  rootRef.value?.querySelector('.gt-adj-row-focus')?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
}

function clearSelection() {
  tableRef.value?.clearSelection?.()
}

defineExpose({ reveal, clearSelection, toggleFullscreen, isFullscreen })
</script>

<style scoped>
.gt-adj-hall-fs-bar { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; font-weight: 600; }
.gt-adj-hall-table :deep(.gt-adj-row-focus > td.el-table__cell) { animation: gt-adj-focus-flash 2.4s ease-out 2; background: var(--gt-color-primary-bg); }
@keyframes gt-adj-focus-flash { 0%, 60% { background: var(--gt-color-wheat-light); } 100% { background: var(--gt-color-primary-bg); } }
.gt-adj-link { cursor: pointer; }
/* 表格字号跟随个人设置，标签不许折行（折行会把「审计调整」压成两行、看着像被截断） */
.gt-adj-type-tag { white-space: nowrap; }
.gt-adj-status-cell { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.gt-adj-action-cell { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.gt-adj-action-cell :deep(.el-button) { margin-left: 0; }
.gt-adj-action-cell :deep(.el-dropdown) { display: inline-flex; flex: 0 0 auto; }
.gt-adj-meta { margin-top: 2px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-adj-reject { color: var(--gt-color-coral); font-size: var(--gt-font-size-xs); }
.gt-adj-ellipsis { margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-adj-detail-code { color: var(--gt-color-text-tertiary); }
.gt-adj-voucher { display: flex; flex-direction: column; max-width: 100%; }
.gt-adj-voucher-row, .gt-adj-voucher-amt {
  display: flex; align-items: center; gap: 6px;
  font-size: var(--gt-font-size-sm); line-height: 1.7; min-height: calc(var(--gt-font-size-sm) * 1.7);
  white-space: nowrap; overflow: hidden;
}
.gt-adj-voucher-amt { justify-content: flex-end; }
.gt-adj-voucher-code { flex-shrink: 0; font-family: var(--gt-font-family-mono, monospace); font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-adj-voucher-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; color: var(--gt-color-text); }
.gt-adj-voucher-divider { height: 9px; margin: 4px 0; border-top: 1px dashed var(--gt-color-border); }
.gt-adj-expand-detail { padding: 8px 16px 8px 48px; background: var(--gt-color-primary-bg); }
.gt-adj-line-table { width: 100%; border-collapse: collapse; font-size: var(--gt-font-size-xs); }
.gt-adj-line-table th { padding: 4px 8px; font-weight: 600; text-align: left; border-bottom: 1px solid var(--gt-color-border-purple); }
.gt-adj-line-table td { padding: 4px 8px; border-bottom: 1px solid var(--gt-color-border-light); }
.gt-adj-line-table .c { text-align: center; width: 60px; }
.gt-adj-line-table .r { text-align: right; width: 150px; }
.gt-adj-expand-footer { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular); }
.gt-adj-dir-dr { color: var(--gt-color-coral); font-weight: 600; }
.gt-adj-dir-cr { color: var(--gt-color-teal); font-weight: 600; }
</style>
