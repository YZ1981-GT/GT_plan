<template>
<div class="d7-disclosure">
    <!-- 同步状态条 -->
    <GtWpDisclosureSyncBar :project-id="projectId" :year="auditYear" :wp-code="'D7'" :sheet-name="activeVariant === 'soe' ? '附注披露信息(国企)' : '附注披露信息(上市公司)'" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 合同负债（科目2205）附注依据 CAS14 收入准则披露，按上市公司版 / 国企版分别列报。</p>
        <p>2. 分类表期末/期初数取自 D7-1 审定表（浅蓝背景为跨sheet自动取数），请与审定数核对一致。</p>
        <p>3. 上市公司版需披露性质分类、账龄超1年重要合同负债及本期重大变动事项；国企版按财务决算报告附注要求披露分类信息。</p>
        <p>4. 披露文本将双向回写至附注模块，请与审定表、明细表保持一致。</p>
      </div>
    </details>

    <!-- 上市/国企版切换 + 同步到附注 / 跳转回附注 -->
    <div class="variant-toolbar">
      <el-segmented v-model="activeVariant" :options="variantOptions" size="small" />
      <el-button type="primary" plain size="small" :loading="isSyncing" :disabled="isReadonly"
        title="将披露表的表格与文本框内容同步到附注模块（五、39/八、39 合同负债）"
        @click="syncToDisclosureNotes">同步到附注</el-button>
      <el-dropdown split-button type="default" size="small" :disabled="!projectId"
        @click="jumpToNote(activeVariant as DisclosureVariant)"
        @command="jumpToNote">
        ↩ 跳转回附注（{{ activeVariant === 'soe' ? '八、39' : '五、39' }}）
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="listed">上市版（五、39）</el-dropdown-item>
            <el-dropdown-item command="soe">国企版（八、39）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:D7-1" :context-project-id="projectId" /></span>
    </div>

    <!-- 上市公司版 -->
    <template v-if="activeVariant === 'listed'">
      <div v-for="section in listedSections" :key="section.sectionKey" class="disclosure-card">
        <h4 class="card-title">{{ section.label }}</h4>

        <el-table :data="getSectionDisplayData(section)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <span :class="{ 'label-bold': row.rowId.startsWith('__') }">
                {{ row.label }}
                <el-tooltip v-if="!section.isDynamic && !row.rowId.startsWith('__')" content="跨sheet取数（来源：D7-1审定表）" placement="top">
                  <el-icon style="margin-left:4px;color:#409eff"><InfoFilled /></el-icon>
                </el-tooltip>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.prior" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'prior', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.prior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.current" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'current', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.current) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="section.isDynamic && !isReadonly" label="操作" width="60" align="center">
            <template #default="{ row }">
              <el-button v-if="!row.rowId.startsWith('__')" type="danger" text size="small" @click="removeDynamicRow(section.sectionKey, row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="section.isDynamic && !isReadonly" style="margin-top:8px">
          <el-button size="small" @click="addDynamicRow(section.sectionKey)">添加行</el-button>
        </div>

        <!-- 说明textarea -->
        <div class="note-block">
          <div class="note-label">说明：</div>
          <el-input
            :model-value="noteTexts[getNoteKey(section.sectionKey)]"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="补充披露说明..."
            @change="(v: string) => updateNoteText(getNoteKey(section.sectionKey), v)"
          />
        </div>

        <!-- 编制提示 -->
        <details class="guidance-hint">
          <summary>📋 编制提示</summary>
          <div class="hint-content">
            <template v-if="section.sectionKey === 'listed-1'">从 D7-1 审定表自动取数，确认性质分类合计与审定数一致。<GtIndexChip value="wp:D7-1" :context-project-id="projectId" /></template>
            <template v-else-if="section.sectionKey === 'listed-2'">列示账龄超过1年的重要合同负债，说明未转收原因。</template>
            <template v-else>列示本期账面价值发生重大变动的合同负债事项。</template>
          </div>
        </details>
      </div>
    </template>

    <!-- 国企版 -->
    <template v-if="activeVariant === 'soe'">
      <div v-for="section in soeSections" :key="section.sectionKey" class="disclosure-card">
        <h4 class="card-title">{{ section.label }}</h4>

        <el-table :data="getSectionDisplayData(section)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <span :class="{ 'label-bold': row.rowId.startsWith('__') }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.prior" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'prior', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.prior) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="section.isDynamic && !row.rowId.startsWith('__') && !isReadonly" :model-value="row.current" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDynamicRow(section.sectionKey, row.rowId, 'current', v ?? 0)" />
              <span v-else :class="{ 'cross-sheet-cell': !section.isDynamic && !row.rowId.startsWith('__') }">{{ fmtAmt(row.current) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="section.isDynamic && !isReadonly" label="操作" width="60" align="center">
            <template #default="{ row }">
              <el-button v-if="!row.rowId.startsWith('__')" type="danger" text size="small" @click="removeDynamicRow(section.sectionKey, row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="section.isDynamic && !isReadonly" style="margin-top:8px">
          <el-button size="small" @click="addDynamicRow(section.sectionKey)">添加行</el-button>
        </div>

        <div class="note-block">
          <div class="note-label">说明：</div>
          <el-input
            :model-value="noteTexts[getNoteKey(section.sectionKey)]"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="补充披露说明..."
            @change="(v: string) => updateNoteText(getNoteKey(section.sectionKey), v)"
          />
        </div>

        <!-- 编制提示 -->
        <details class="guidance-hint">
          <summary>📋 编制提示</summary>
          <div class="hint-content">
            国企版按《国有企业财务决算报告附注》要求披露合同负债的分类构成及期初期末余额变动情况。
          </div>
        </details>
      </div>
    </template>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabDisclosure.vue — 附注披露 (~350行)
 * el-segmented: 上市公司版(3子节) / 国企版(2子节)
 * Task: 23.1
 * Requirements: 13.1-13.8, 14.1-14.6, 15.1-15.6, 19.5, 20.1
 */
import { computed, ref, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { useD7Disclosure, type DisclosureSection, type DisclosureRow } from '../composables/useD7Disclosure'
import { buildD7SyncPayload, D7_NOTE_SECTION, type D7DisclosureSnapshot } from '../composables/d7NoteSectionMap'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import type { ChecklistResponse } from '../composables/useD7FormData'
import type useD7CrossSheet from '../composables/useD7CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { checkNoteConsistencyGeneric } from '../composables/noteConsistencyCheck'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import GtWpDisclosureSyncBar from '../GtWpDisclosureSyncBar.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD7CrossSheet>
  variant?: 'listed' | 'soe'
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const { year: auditYear } = useAuditContext()

const variantOptions = [
  { label: '上市公司版', value: 'listed' },
  { label: '国企版', value: 'soe' },
]

const {
  listedSections, soeSections,
  activeVariant, addDynamicRow, removeDynamicRow, noteTexts,
} = useD7Disclosure({
  allResponses: allResponsesRef,
  crossSheet: props.crossSheet,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: async () => {},
  debouncedSave: props.debouncedSave,
})

// Initialize variant from prop if provided
if (props.variant) {
  activeVariant.value = props.variant
}

// ─── 保存后自动同步到附注（防抖/非阻塞/失败静默）──────────────────────────────
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())
let _d7Mounted = false
watch(
  [listedSections, soeSections, noteTexts],
  () => {
    if (!_d7Mounted) { _d7Mounted = true; return }
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)

function getSectionDisplayData(section: DisclosureSection): DisclosureRow[] {
  if (section.totalRow) {
    return [...section.rows, section.totalRow]
  }
  return section.rows
}

function updateDynamicRow(sectionKey: string, rowId: string, field: string, value: number) {
  // Find the section and update inline
  const sections = activeVariant.value === 'listed' ? listedSections.value : soeSections.value
  const section = sections.find(s => s.sectionKey === sectionKey)
  if (!section) return
  const row = section.rows.find(r => r.rowId === rowId)
  if (row) {
    ;(row as any)[field] = value
    // Trigger persist by re-adding (composable handles persistence)
  }
}

function getNoteKey(sectionKey: string): string {
  const map: Record<string, string> = {
    'listed-1': 'D7-note-listed-text-1',
    'listed-2': 'D7-note-listed-text-2',
    'listed-3': 'D7-note-listed-text-3',
    'soe-1': 'D7-note-soe-text-1',
    'soe-2': 'D7-note-soe-text-2',
  }
  return map[sectionKey] || ''
}

function updateNoteText(key: string, value: string) {
  if (!key) return
  noteTexts.value = { ...noteTexts.value, [key]: value }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 同步到附注 / 跳转回附注 ─────────────────────────────────────────────────
const router = useRouter()
const isSyncing = ref(false)

function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'D7', target)
  if (route) router.push(route)
}

function findSection(sections: DisclosureSection[], key: string): DisclosureSection | undefined {
  return (sections || []).find((s) => s.sectionKey === key)
}

function toSnapRow(r: DisclosureRow) {
  return { label: r.label, current: r.current, prior: r.prior, reason: (r as any).reason }
}

const EMPTY_TOTAL = { label: '合计', current: 0, prior: 0 }

/** 底稿披露表 → 附注单向推送（当前 activeVariant 对应上市/国企）。 */
async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  const variant = activeVariant.value as DisclosureVariant
  try {
    let snapshot: D7DisclosureSnapshot
    if (variant === 'soe') {
      const main = findSection(soeSections.value, 'soe-1')
      const change = findSection(soeSections.value, 'soe-2')
      snapshot = {
        mainRows: (main?.rows ?? []).map(toSnapRow),
        mainTotal: main?.totalRow ? toSnapRow(main.totalRow) : { ...EMPTY_TOTAL },
        changeRows: (change?.rows ?? []).map(toSnapRow),
        notes: { ...noteTexts.value },
      }
    } else {
      const main = findSection(listedSections.value, 'listed-1')
      const longTerm = findSection(listedSections.value, 'listed-2')
      const change = findSection(listedSections.value, 'listed-3')
      snapshot = {
        mainRows: (main?.rows ?? []).map(toSnapRow),
        mainTotal: main?.totalRow ? toSnapRow(main.totalRow) : { ...EMPTY_TOTAL },
        longTermRows: (longTerm?.rows ?? []).map(toSnapRow),
        longTermTotal: longTerm?.totalRow ? toSnapRow(longTerm.totalRow) : { ...EMPTY_TOTAL },
        changeRows: (change?.rows ?? []).map(toSnapRow),
        notes: { ...noteTexts.value },
      }
    }
    const payload = buildD7SyncPayload(variant, props.wpId || '', null, snapshot)
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'D7',
        accountCode: '2205',
        projectId: props.projectId,
        section: variant,
        sectionIds: [D7_NOTE_SECTION[variant]],
      },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D7_NOTE_SECTION[variant]} 合同负债」`)
    // 静默校对附注合计一致性
    const pageTotal = snapshot.mainTotal?.current ?? 0
    checkNoteConsistencyGeneric(props.projectId, auditYear.value, D7_NOTE_SECTION[variant], pageTotal, true)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}


</script>

<style scoped>
.d7-disclosure { padding: 12px; }
.d7-disclosure :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d7-disclosure :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

.variant-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.chip-wrap { display: inline-flex; align-items: center; }

.disclosure-card {
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}
.card-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; color: #303133; }
.label-bold { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; cursor: help; }

.note-block { margin-top: 12px; }
.note-label { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 6px; }

.guidance-hint {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}
.guidance-hint summary { padding: 8px 12px; cursor: pointer; font-size: 12px; color: #409eff; }
.guidance-hint .hint-content { padding: 8px 12px 12px; font-size: 12px; color: #606266; line-height: 1.6; }
</style>
