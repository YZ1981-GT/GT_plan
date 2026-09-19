<script setup lang="ts">
/** F3TabDisclosureSOE — 附注披露（国企）| 与附注模块（八、36 应付票据）联动 */
import { ref, toRef, watch, inject, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useF3DisclosureSoe } from '../composables/useF3DisclosureSoe'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import { buildF3SyncPayload, F3_NOTE_SECTION } from '../composables/f3NoteSectionMap'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import GtIndexChip from '../GtIndexChip.vue'
import WpAmountInput from '../shared/WpAmountInput.vue'
// 🔴 `DisplayPrefs_Key` 的真源是 `composables/displayPrefsKey.ts`，不是 store 模块。
// 从 `@/stores/displayPrefs` 连带 import 它会在**运行时**抛
// 「does not provide an export named 'DisplayPrefs_Key'」并让整页崩成「页面渲染出错」，
// 而 get_diagnostics / vitest / Vite transform 四层全绿（2026-08-07 浏览器实测）。
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards: string[]
}>()

const {
  isApplicable, section1Rows, section1Subtotal, dynamicRows,
  noteText, addRow, removeRow, updateCell,
} = useF3DisclosureSoe({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

async function generateSoeNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'soe-note',
    noteText.value,
    {
      sheet: 'F3-note-soe',
      section1: section1Rows.value.map((r) => ({
        label: r.label,
        endAmount: r.endAmount,
        priorAmount: r.priorAmount,
      })),
      subtotal: section1Subtotal.value,
    },
    'AI · 附注说明',
  )
  if (text) noteText.value = text
}

// 保存后自动同步到附注（防抖/非阻塞/失败静默/只读 gate）
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── 同步到附注模块（disclosure_notes 八、36 应付票据，单向 push 保证披露一致） ───
const noteSectionId = F3_NOTE_SECTION.soe
const isSyncing = ref(false)

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId) return
  const payload = buildF3SyncPayload(
    'soe',
    props.wpId,
    props.applicableStandards,
    section1Rows.value.map((r) => ({ label: r.label, endAmount: r.endAmount, priorAmount: r.priorAmount })),
    {
      label: '合计',
      endAmount: section1Subtotal.value.endAmount,
      priorAmount: section1Subtotal.value.priorAmount,
    },
    noteText.value,
  )
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注模块「${noteSectionId} 应付票据」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// 数据变更后自动同步到附注（debounce 由 autoSync 内部 800ms 控制，只读/失败静默）
watch([section1Rows, dynamicRows, noteText], () => {
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}, { deep: true })
</script>

<template>
  <div class="f3-disclosure-soe">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />

    <template v-else>
      <!-- 编制提示 -->
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 应付票据（科目2201）按银行承兑汇票、商业承兑汇票分类披露期末/期初余额。</p>
          <p>2. 期末已到期未兑付的应付票据金额及原因、开具票据的保证金存款受限情况应单独披露。</p>
          <p>3. 国企需关注关联方（同一控制下企业）票据及集团资金池票据的披露完整性。</p>
          <p>4. 分类合计应与 F3-1 审定表、资产负债表"应付票据"项目核对一致（浅蓝为跨sheet取数）。</p>
          <p>5. 编制完成后点击「同步到附注模块」，将分类余额与附注说明推送到附注章节「{{ noteSectionId }} 应付票据」，保证两边披露信息一致。</p>
        </div>
      </details>

      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        title="审计目标：应付票据按种类披露完整准确，到期未兑付、保证金受限及关联方（同一控制下企业）票据充分披露，与审定表核对一致。"
        class="objective-alert"
      />

      <!-- 附注联动工具条 -->
      <div class="sync-toolbar">
        <div class="sync-left">
          <el-tag size="small" type="warning">关联附注章节：{{ noteSectionId }} 应付票据</el-tag>
          <GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" />
        </div>
        <el-button
          size="small"
          type="primary"
          :disabled="isReadonly"
          :loading="isSyncing"
          @click="syncToDisclosureNotes"
        >同步到附注模块</el-button>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">
          (1) 应付票据分类
          <el-tag size="small" type="info">跨sheet取数</el-tag>
          <GtIndexChip value="wp:F3-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe class="disclosure-table">
          <el-table-column prop="label" label="类别" width="200" />
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ displayPrefs.fmtAmount(row.endAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ displayPrefs.fmtAmount(row.priorAmount) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">
          (2) 补充披露
          <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加</el-button>
        </h4>
        <el-table :data="dynamicRows" size="small" border stripe class="disclosure-table">
          <el-table-column prop="label" label="项目" width="200">
            <template #default="{ row }">
              <el-input :model-value="row.label" size="small" :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'label', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.endAmount"
                :disabled="isReadonly"
                @update:model-value="(v: number) => updateCell(row.rowId, 'endAmount', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.priorAmount"
                :disabled="isReadonly"
                @update:model-value="(v: number) => updateCell(row.rowId, 'priorAmount', v)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="note-area">
        <div class="note-head">
          <span class="note-prefix">附注说明（随附注一并披露）：</span>
          <el-button
            v-if="!isReadonly && aiAvailable"
            size="small"
            type="primary"
            plain
            :loading="aiLoading"
            @click="generateSoeNote"
          >AI 填写说明</el-button>
        </div>
        <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
          placeholder="注：企业应说明本期已到期未支付的应付票据总金额。（另可补充保证金受限、关联方票据等披露事项）" />
      </div>

      <!-- 源模板蓝字编制指引 -->
      <div class="template-guide">
        注：企业应说明本期已到期未支付的应付票据总金额。
      </div>
    </template>
  </div>
</template>

<style scoped>
.f3-disclosure-soe {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.f3-disclosure-soe :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-disclosure-soe :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
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
.guidance-content p {
  margin: 2px 0;
}
.disclosure-card {
  margin-bottom: 16px;
}
.card-title {
  margin: 0 0 8px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.cross-sheet-cell {
  background-color: #e6f7ff;
  padding: 2px 6px;
  border-radius: 2px;
  color: #409eff;
}
.note-area {
  margin-top: 12px;
}
.note-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.note-prefix {
  font-weight: 600;
}
.objective-alert {
  margin-bottom: 12px;
}
.sync-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fdf6ec;
  border: 1px solid #f5dab1;
  border-radius: 6px;
}
.sync-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.template-guide {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px dashed #409eff;
  border-radius: 6px;
  background: #ecf5ff;
  color: #2b6cb0;
  line-height: 1.7;
  font-size: 12px;
}
</style>
