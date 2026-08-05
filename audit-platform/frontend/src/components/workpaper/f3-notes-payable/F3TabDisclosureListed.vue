<script setup lang="ts">
/** F3TabDisclosureListed — 附注披露（上市）| 与附注模块（五、36 应付票据）联动 */
import { ref, toRef, watch, inject, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useF3DisclosureListed } from '../composables/useF3DisclosureListed'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import { buildF3SyncPayload, F3_NOTE_SECTION } from '../composables/f3NoteSectionMap'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import GtIndexChip from '../GtIndexChip.vue'
import WpAmountInput from '../shared/WpAmountInput.vue'
import { useDisplayPrefsStore, DisplayPrefs_Key } from '@/stores/displayPrefs'
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards: string[]
}>()

const {
  isApplicable, section1Rows, section1Subtotal, section2Rows, section2Subtotal,
  noteText, addRow, removeRow, updateCell,
} = useF3DisclosureListed({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

async function generateListedNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'listed-note',
    noteText.value,
    {
      sheet: 'F3-note-listed',
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

// ─── 同步到附注模块（disclosure_notes 五、36 应付票据，单向 push 保证披露一致） ───
const noteSectionId = F3_NOTE_SECTION.listed
const isSyncing = ref(false)

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId) return
  const payload = buildF3SyncPayload(
    'listed',
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
watch([section1Rows, section2Rows, noteText], () => {
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}, { deep: true })
</script>

<template>
  <div class="f3-disclosure-listed">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />

    <template v-else>
      <!-- 编制提示 -->
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. 应付票据（科目2201）按种类披露：银行承兑汇票、商业承兑汇票，分别列示期末/期初余额。</p>
          <p>2. 期末已到期未兑付的应付票据金额及原因、开具票据的保证金存款受限情况应单独披露。</p>
          <p>3. 大额或异常应付票据、关联方开具/承兑票据应结合 CAS 36 关联方披露一并说明。</p>
          <p>4. 分类合计应与 F3-1 审定表、资产负债表"应付票据"项目核对一致（浅蓝为跨sheet取数）。</p>
          <p>5. 编制完成后点击「同步到附注模块」，将分类余额与附注说明推送到附注章节「{{ noteSectionId }} 应付票据」，保证两边披露信息一致。</p>
        </div>
      </details>

      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        title="审计目标：应付票据按种类披露完整准确，到期未兑付、保证金受限及关联方票据充分披露，分类合计与审定表核对一致。"
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
          (1) 应付票据按种类分类
          <el-tooltip content="数据来源：F3-1审定表银行/商业承兑分类" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
          <GtIndexChip value="wp:F3-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...section1Rows, section1Subtotal]" size="small" border stripe class="disclosure-table">
          <el-table-column prop="label" label="种类" width="200">
            <template #default="{ row }">
              <span :class="{ 'subtotal-label': row.rowId === '__subtotal__' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">
              <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">{{ displayPrefs.fmtAmount(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="上年年末余额" width="130" align="right">
            <template #default="{ row }">
              <span :class="{ 'cross-sheet-cell': row.rowId?.startsWith('cs-') }">{{ displayPrefs.fmtAmount(row.priorAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">
          (2) 其他应披露事项
          <el-button size="small" :disabled="isReadonly" @click="addRow">+ 添加</el-button>
        </h4>
        <el-table :data="[...section2Rows, section2Subtotal]" size="small" border stripe class="disclosure-table">
          <el-table-column prop="label" label="项目" width="200">
            <template #default="{ row }">
              <span v-if="row.rowId === '__subtotal__'" class="subtotal-label">合计</span>
              <el-input v-else :model-value="row.label" size="small" :disabled="isReadonly"
                @change="(v: string) => updateCell(row.rowId, 'label', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="130" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__subtotal__'">{{ displayPrefs.fmtAmount(row.endAmount) }}</span>
              <WpAmountInput v-else :model-value="row.endAmount"
                :disabled="isReadonly"
                @update:model-value="(v: number) => updateCell(row.rowId, 'endAmount', v)" />
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <span v-if="row.rowId === '__subtotal__'">{{ displayPrefs.fmtAmount(row.priorAmount) }}</span>
              <WpAmountInput v-else :model-value="row.priorAmount"
                :disabled="isReadonly"
                @update:model-value="(v: number) => updateCell(row.rowId, 'priorAmount', v)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__subtotal__'" link type="danger" size="small"
                :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
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
            @click="generateListedNote"
          >AI 填写说明</el-button>
        </div>
        <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
          placeholder="说明：本期末已到期未支付的应付票据总额为XXX元。（另可补充保证金受限、关联方票据等披露事项）" />
      </div>

      <!-- 源模板红字编制指引：供应链票据认定 -->
      <div class="template-guide">
        【如果法律上认定供应链票据属于《商业汇票承兑、贴现与再贴现管理办法》（中国人民银行
        中国银行保险监督管理委员会令〔2022〕第4号）的范围、具备《票据法》规定的要件，则出票人应当
        自法律认定生效日（2023年1月1日）起将其作为"应付票据"进行会计处理，且无需对前期比较期间数据
        进行追溯调整。】
      </div>
    </template>
  </div>
</template>

<style scoped>
.f3-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.f3-disclosure-listed :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-disclosure-listed :deep(.el-table .cell) {
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
.subtotal-label {
  font-weight: 600;
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
  border: 1px dashed #c45656;
  border-radius: 6px;
  background: #fef0f0;
  color: #c45656;
  line-height: 1.7;
  font-size: 12px;
}
</style>
