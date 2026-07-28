<template>
<div class="d3-disclosure-listed">
  <template v-if="!isApplicable">
    <el-alert type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />
  </template>
  <template v-else>
    <!-- 工具栏：同步到附注 + 跳转回附注 -->
    <div class="d3-disclosure-toolbar">
      <el-button type="primary" plain size="small" :loading="isSyncing" :disabled="isReadonly"
        title="将披露表的表格与文本框内容同步到附注模块（五、38 预收款项）"
        @click="syncToDisclosureNotes">同步到附注</el-button>
      <el-dropdown split-button type="default" size="small" :disabled="!projectId"
        @click="jumpToNote('listed')"
        @command="jumpToNote">
        ↩ 跳转回附注（五、38）
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="listed">上市版（五、38）</el-dropdown-item>
            <el-dropdown-item command="soe">国企版（八、38）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 子节一：按性质分类 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (1) 预收账款按性质分类
        <span class="cross-sheet-badge">
          <el-tooltip content="数据来源：D3-1审定表按性质分类区块" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
        </span>
        <GtIndexChip target="D3-1" label="→D3-1" />
      </h4>
      <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe>
        <el-table-column prop="label" label="项目" width="200">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">
              {{ fmtAmount(row.endAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">
              {{ fmtAmount(row.priorAmount) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input v-model="note1" type="textarea" :rows="2" :disabled="isReadonly"
          placeholder="按性质分类的附注披露说明..." />
      </div>
    </div>

    <!-- 子节二：超1年重要预收 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (2) 账龄超过1年的重要预收账款
        <el-button size="small" :disabled="isReadonly" @click="addRow(2)">+ 添加</el-button>
      </h4>
      <el-table :data="[...section2Rows, section2Subtotal]" size="small" border stripe>
        <el-table-column prop="label" label="对方单位" width="160">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else-if="row.rowId?.startsWith('cs-')">
              <span class="cross-sheet-cell">{{ row.label }}</span>
            </template>
            <template v-else>
              <el-input v-model="row.label" size="small" :disabled="isReadonly"
                @change="(val: string) => updateCell(2, row.rowId, 'label', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__' || row.rowId?.startsWith('cs-')">
              <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">{{ fmtAmount(row.endAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.endAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(2, row.rowId, 'endAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__' || row.rowId?.startsWith('cs-')">
              <span>{{ fmtAmount(row.priorAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.priorAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(2, row.rowId, 'priorAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="140">
          <template #default="{ row }">
            <template v-if="!row.rowId?.startsWith('cs-') && row.rowId !== '__subtotal__'">
              <el-input v-model="row.reason" size="small" :disabled="isReadonly"
                @change="(val: string) => updateCell(2, row.rowId, 'reason', val)" />
            </template>
            <span v-else>{{ row.reason || '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-popconfirm v-if="!row.rowId?.startsWith('cs-') && row.rowId !== '__subtotal__'" title="删除？" @confirm="removeRow(2, row.rowId)">
              <template #reference><el-button size="small" type="danger" link>删</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input v-model="note2" type="textarea" :rows="2" :disabled="isReadonly"
          placeholder="超1年预收的附注披露说明..." />
      </div>
    </div>

    <!-- 子节三：重大变动 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (3) 重大变动说明
        <el-button size="small" :disabled="isReadonly" @click="addRow(3)">+ 添加</el-button>
      </h4>
      <el-table :data="[...section3Rows, section3Subtotal]" size="small" border stripe>
        <el-table-column prop="label" label="项目" width="180">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else>
              <el-input v-model="row.label" size="small" :disabled="isReadonly"
                @change="(val: string) => updateCell(3, row.rowId, 'label', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-val">{{ fmtAmount(row.endAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.endAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(3, row.rowId, 'endAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期初金额" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__subtotal__'">
              <span class="subtotal-val">{{ fmtAmount(row.priorAmount) }}</span>
            </template>
            <template v-else>
              <el-input v-model.number="row.priorAmount" size="small" :disabled="isReadonly"
                @change="(val: any) => updateCell(3, row.rowId, 'priorAmount', val)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="变动原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__subtotal__'" v-model="row.reason" size="small" :disabled="isReadonly"
              @change="(val: string) => updateCell(3, row.rowId, 'reason', val)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-popconfirm v-if="row.rowId !== '__subtotal__'" title="删除？" @confirm="removeRow(3, row.rowId)">
              <template #reference><el-button size="small" type="danger" link>删</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">说明：</span>
        <el-input v-model="note3" type="textarea" :rows="2" :disabled="isReadonly"
          placeholder="重大变动的附注披露说明..." />
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <div class="hint-content">
        1. 上市公司应按CAS30财务报表列报要求，分别披露预收账款按性质分类和按账龄分类情况。<br/>
        2. 账龄超过1年的重要预收账款应逐户披露，说明未结转原因。<br/>
        3. 重大变动应说明变动原因，包括新签大额合同、大额结转等情形。<br/>
        4. 跨sheet取数单元格（浅蓝色背景）自动从D3-1审定表同步，无需手动维护。
      </div>
    </details>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D3TabDisclosureListed.vue — 附注披露（上市公司）
 * 3子节卡片 + 跨sheet取数 + 动态行 + 合计 + 说明 + 编制提示
 */
import { computed, ref, toRef, watch, onUnmounted, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useD3DisclosureListed } from '../composables/useD3DisclosureListed'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import {
  buildD3SyncPayload,
  D3_NOTE_SECTION,
  type D3DisclosureSnapshot,
} from '../composables/d3NoteSectionMap'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import type { useD3CrossSheet } from '../composables/useD3CrossSheet'
import type { ChecklistResponse } from '../composables/useD3FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useD3CrossSheet>
  applicableStandards?: string[] | string
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// 父级经模板传入的是解包后的普通值（非 ref），此处重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>
const applicableStandardsRef = computed<string[]>(() => {
  const v = props.applicableStandards
  return Array.isArray(v) ? v : (typeof v === 'string' && v ? [v] : [])
}) as unknown as Ref<string[]>

const {
  isApplicable,
  section1Rows,
  section1Subtotal,
  note1,
  section2Rows,
  section2Subtotal,
  note2,
  section3Rows,
  section3Subtotal,
  note3,
  addRow,
  removeRow,
  updateCell,
} = useD3DisclosureListed({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  applicableStandards: applicableStandardsRef,
})

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

// ─── 同步到附注 / 跳转回附注 ─────────────────────────────────────────────────
const router = useRouter()
const isSyncing = ref(false)

function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'D3', target)
  if (route) router.push(route)
}

/** 底稿披露表 → 附注单向推送（结构化表格 + 文本框内容同步到附注 五、38 预收款项）。 */
async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  try {
    const snapshot: D3DisclosureSnapshot = {
      mainRows: section1Rows.value.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
      mainTotal: { label: '合计', endAmount: section1Subtotal.value.endAmount, priorAmount: section1Subtotal.value.priorAmount },
      longTermRows: section2Rows.value.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount, reason: r.reason })),
      longTermTotal: { label: '合计', endAmount: section2Subtotal.value.endAmount, priorAmount: section2Subtotal.value.priorAmount },
      changeRows: section3Rows.value.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount, reason: r.reason })),
      notes: { nature: note1.value, longTerm: note2.value, change: note3.value },
    }
    const payload = buildD3SyncPayload('listed', props.wpId || '', applicableStandardsRef.value, snapshot)
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'D3',
        accountCode: '2203',
        projectId: props.projectId,
        section: 'listed',
        sectionIds: [D3_NOTE_SECTION.listed],
      },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D3_NOTE_SECTION.listed} 预收款项」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// 保存后自动同步（防抖/非阻塞/失败静默/只读 gate；与手动按钮同源）
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onUnmounted(() => autoSync.cancelPending())
let autoSyncArmed = false
watch(
  [note1, note2, note3, section2Rows, section3Rows],
  () => {
    if (!autoSyncArmed) { autoSyncArmed = true; return } // 跳过挂载首帧
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)
</script>

<style scoped>
.d3-disclosure-listed { padding: 16px; }
.d3-disclosure-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.disclosure-card { margin-bottom: 20px; padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
.cross-sheet-badge { font-weight: normal; }
.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.note-area { margin-top: 12px; display: flex; align-items: flex-start; gap: 8px; }
.note-prefix { font-size: var(--wp-font-size, 13px); color: #606266; white-space: nowrap; padding-top: 6px; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; }
.compile-hint summary { padding: 8px 12px; cursor: pointer; font-size: var(--wp-font-size, 13px); color: #409eff; }
.compile-hint .hint-content { padding: 8px 12px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
</style>
