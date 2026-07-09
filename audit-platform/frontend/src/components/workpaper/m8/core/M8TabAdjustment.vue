<template>
  <div class="m8-tab-adjustment">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M8-3 一般风险准备调整分录汇总</h3>
        <el-tag type="warning" effect="dark" size="small">借贷平衡</el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <el-button size="small" @click="handleAI('adjustment')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>一般风险准备调整分录（M8-3）：</strong>
        金融企业一般风险准备调整典型场景：①补提一般风险准备（借:利润分配-提取一般风险准备 贷:一般风险准备）
        ②冲回多计提（借:一般风险准备 贷:利润分配-提取一般风险准备）③监管要求补提（借:利润分配 贷:一般风险准备）。
        每笔分录必须<strong>借贷平衡</strong>（∑借方 === ∑贷方，阈值0.01元）。保存后自动同步M8-1审定表AJE/RJE列。
      </div>
    </div>

    <!-- ═══ AJE / RJE 切换 ═══ -->
    <div class="type-switch">
      <el-segmented
        v-model="adjustment.activeType.value"
        :options="typeOptions"
        size="small"
        @change="(val: any) => adjustment.switchType(val)"
      />
      <el-button type="primary" size="small" plain @click="handleAddEntry">
        + 新增分录
      </el-button>
    </div>

    <!-- ═══ 调整分录表格 ═══ -->
    <el-table
      :data="adjustment.filteredEntries.value"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
    >
      <!-- A列: 调整事项说明 -->
      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项..."
            @change="(val: string) => handleUpdateEntry($index, 'description', val)"
          />
          <span v-else>{{ row.description || '—' }}</span>
        </template>
      </el-table-column>

      <!-- B列: 类别 -->
      <el-table-column label="类别" width="130">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="选择类别"
            style="width: 100%"
            @change="(val: string) => handleUpdateEntry($index, 'category', val)"
          >
            <el-option label="报表调整" value="报表调整" />
            <el-option label="账项调整" value="账项调整" />
            <el-option label="重分类调整" value="重分类" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.category || '—' }}</span>
        </template>
      </el-table-column>

      <!-- C列: 报表项目 -->
      <el-table-column label="报表项目" min-width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            placeholder="报表项目"
            @change="(val: string) => handleUpdateEntry($index, 'reportItem', val)"
          />
          <span v-else>{{ row.reportItem || '—' }}</span>
        </template>
      </el-table-column>

      <!-- D列: 科目名称 -->
      <el-table-column label="科目名称" min-width="140">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="科目名称"
            @change="(val: string) => handleUpdateEntry($index, 'accountName', val)"
          />
          <span v-else>{{ row.accountName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- E列: 附注项目 -->
      <el-table-column label="附注项目" min-width="100">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            placeholder="附注"
            @change="(val: string) => handleUpdateEntry($index, 'noteItem', val)"
          />
          <span v-else>{{ row.noteItem || '—' }}</span>
        </template>
      </el-table-column>

      <!-- G列: 借方调整金额 -->
      <el-table-column label="借方调整金额" width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            :controls="false"
            :precision="2"
            :min="0"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdateEntry($index, 'debitAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- H列: 贷方调整金额 -->
      <el-table-column label="贷方调整金额" width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            :controls="false"
            :precision="2"
            :min="0"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdateEntry($index, 'creditAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- I列: 索引 -->
      <el-table-column label="索引" width="90">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.refIndex"
            size="small"
            placeholder="索引"
            @change="(val: string) => handleUpdateEntry($index, 'refIndex', val)"
          />
          <span v-else>{{ row.refIndex || '—' }}</span>
        </template>
      </el-table-column>

      <!-- J列: 备注 -->
      <el-table-column label="备注" min-width="100">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => handleUpdateEntry($index, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="handleRemoveEntry($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ Footer: 借贷合计 + 平衡状态 ═══ -->
    <div :class="['adjustment-footer', { 'unbalanced': !adjustment.currentBalance.value.isBalanced }]">
      <el-tag type="primary" size="small" effect="dark">
        ∑借方: {{ fmtAmount(adjustment.currentBalance.value.totalDebit) }}
      </el-tag>
      <el-tag type="success" size="small" effect="dark">
        ∑贷方: {{ fmtAmount(adjustment.currentBalance.value.totalCredit) }}
      </el-tag>
      <el-tag
        :type="adjustment.currentBalance.value.isBalanced ? 'success' : 'danger'"
        size="small"
        effect="dark"
      >
        差额: {{ fmtAmount(adjustment.currentBalance.value.diff) }}
      </el-tag>
      <el-tag
        :type="adjustment.currentBalance.value.isBalanced ? 'success' : 'danger'"
        size="small"
        :effect="adjustment.currentBalance.value.isBalanced ? 'plain' : 'dark'"
      >
        {{ adjustment.currentBalance.value.isBalanced ? '✓ 借贷平衡' : '✗ 借贷不平衡' }}
      </el-tag>
      <el-button
        type="primary"
        size="small"
        :disabled="!adjustment.currentBalance.value.isBalanced"
        :loading="isSaving"
        @click="handleSaveAndPublish"
      >
        保存并同步M8-1
      </el-button>
    </div>

    <!-- ═══ 4104净影响 ═══ -->
    <div class="net-impact" v-if="adjustment.ajeNet4104.value !== 0 || adjustment.rjeNet4104.value !== 0">
      <el-tag type="warning" size="small" effect="plain">
        AJE对4104净影响: {{ fmtAmount(adjustment.ajeNet4104.value) }}（{{ adjustment.ajeNet4104.value >= 0 ? '调增' : '调减' }}）
      </el-tag>
      <el-tag type="warning" size="small" effect="plain" v-if="adjustment.rjeNet4104.value !== 0">
        RJE对4104净影响: {{ fmtAmount(adjustment.rjeNet4104.value) }}（{{ adjustment.rjeNet4104.value >= 0 ? '重分类入' : '重分类出' }}）
      </el-tag>
    </div>

    <!-- ═══ 审计说明区（el-card） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">调整分录说明</span>
          <el-button size="small" @click="handleAI('adjustment-note')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="adjustmentNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请说明调整分录原因及审计判断依据..."
        @change="saveAdjustmentNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>一般风险准备（4104）为<strong>权益类贷方科目</strong>：调增=贷方增加，调减=借方减少</li>
        <li>每笔分录必须<strong>借贷平衡</strong>（∑借方 = ∑贷方，阈值0.01元）</li>
        <li>类别选项：报表调整 / 账项调整 / 重分类调整 / 其他</li>
        <li>AJE（审计调整分录）：改变账面数的调整</li>
        <li>RJE（重分类调整）：仅影响报表列示的调整</li>
        <li>保存后自动发布 EventBus 'adjustment:created' → M8-1审定表刷新AJE/RJE列</li>
        <li>补提：借:利润分配-提取一般风险准备 贷:一般风险准备</li>
        <li>冲回：借:一般风险准备 贷:利润分配-提取一般风险准备</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M8TabAdjustment — M8-3 一般风险准备调整分录汇总
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 4.5
 * Requirements: 4.1-4.4
 *
 * xlsx结构：24×10 (A:J)
 * Columns: 调整事项说明(A) | 类别(B) | 报表项目(C) | 科目名称(D) | 附注项目(E) |
 *          …(F) | 借方调整金额(G) | 贷方调整金额(H) | 索引(I) | 备注(J)
 *
 * Features:
 * - Dynamic row add (ElMessageBox.prompt for entry name) + delete
 * - 类别 column: el-select [报表调整, 账项调整, 重分类调整, 其他]
 * - Footer: ∑借方 / ∑贷方 / 差额 / 平衡状态
 * - 红色高亮 if !balanced
 * - 方法论上下文 amber block
 * - AI辅助 + 复核按钮
 * - EventBus publish 'adjustment:created' when saved
 * - Sync AJE/RJE amounts back to M8-1
 *
 * Composables: useM8FormData + useM8Adjustment + useM8DualMode + useVersionTrail
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM8FormData } from '../../composables/useM8FormData'
import { useM8DualMode } from '../../composables/useM8DualMode'
import { useM8Adjustment } from '../../composables/useM8Adjustment'
import { useVersionTrail } from '../../composables/useVersionTrail'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const dualMode = useM8DualMode({ wpId: computed(() => props.wpId) })
const adjustment = useM8Adjustment(formData)
const versionTrail = useVersionTrail({
  projectId: computed(() => props.projectId),
  workpaperId: computed(() => props.wpId),
})

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const adjustmentNote = ref('')

const typeOptions = [
  { label: 'AJE 审计调整', value: 'AJE' },
  { label: 'RJE 重分类', value: 'RJE' },
]

// ─── Handlers ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 新增分录（ElMessageBox.prompt输入名称） */
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入调整事项说明',
      '新增调整分录',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：补提一般风险准备...',
        inputValidator: (val: string) => {
          if (!val || !val.trim()) return '请输入调整事项说明'
          return true
        },
      },
    )
    adjustment.addEntry()
    // 设置描述到最后一条
    const entries = adjustment.entries.value
    if (entries.length > 0) {
      adjustment.updateEntry(entries.length - 1, 'description', value.trim())
    }
  } catch {
    // 用户取消
  }
}

function handleUpdateEntry(filteredIndex: number, field: string, value: string | number): void {
  // filteredEntries 中的 index 映射回 entries 的真实 index
  const filteredEntry = adjustment.filteredEntries.value[filteredIndex]
  if (!filteredEntry) return
  const realIndex = adjustment.entries.value.findIndex(e => e === filteredEntry)
  if (realIndex >= 0) {
    adjustment.updateEntry(realIndex, field as any, value)
  }
}

function handleRemoveEntry(filteredIndex: number): void {
  const filteredEntry = adjustment.filteredEntries.value[filteredIndex]
  if (!filteredEntry) return
  const realIndex = adjustment.entries.value.findIndex(e => e === filteredEntry)
  if (realIndex >= 0) {
    adjustment.removeEntry(realIndex)
  }
}

async function handleSaveAndPublish(): Promise<void> {
  isSaving.value = true
  try {
    await adjustment.saveAndPublish()
    await versionTrail.createSnapshot('M8-3 调整分录保存')
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAdjustmentNote(): void {
  formData.debouncedSave('M8-3-adjustmentNote', { remark: adjustmentNote.value || null })
}

function handleAI(_section: string): void { /* AI辅助钩子 */ }
function handleReview(): void { openReviewDialog?.('M8-3-adjustment', '调整分录汇总') }

function getRowClassName(): string { return '' }

// ─── EventBus + Lifecycle ────────────────────────────────────────────────────
let unsubAdjudicated: (() => void) | null = null

function onAdjudicatedRefresh(): void { formData.loadData() }

onMounted(async () => {
  await formData.loadData()

  // 恢复分录数据
  _restoreEntries()

  // 恢复说明文本
  const noteResp = formData.allResponses.value.get('M8-3-adjustmentNote')
  if (noteResp?.remark) adjustmentNote.value = noteResp.remark

  // EventBus订阅
  unsubAdjudicated = adjustment.subscribeAdjudicated(onAdjudicatedRefresh)
})

onUnmounted(() => {
  if (unsubAdjudicated) { unsubAdjudicated(); unsubAdjudicated = null }
})

/** 从 checklist_responses 恢复分录行 */
function _restoreEntries(): void {
  const restored: any[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M8-3-entry-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          index: d.index || restored.length + 1,
          description: d.description || '',
          category: d.category || '',
          reportItem: d.reportItem || '',
          accountName: d.accountName || '',
          noteItem: d.noteItem || '',
          type: d.type || 'AJE',
          debitAmount: Number(d.debitAmount) || 0,
          creditAmount: Number(d.creditAmount) || 0,
          refIndex: d.refIndex || '',
          remark: d.remark || '',
        })
      } catch { /* skip corrupt data */ }
    }
  }
  if (restored.length > 0) {
    // 按index排序
    restored.sort((a, b) => a.index - b.index)
    adjustment.entries.value = restored
  }
}
</script>

<style scoped>
.m8-tab-adjustment { padding: 12px; font-size: 13px; }

/* ─── Header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }

/* ─── Type switch ─── */
.type-switch { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }

/* ─── Table ─── */
:deep(.el-table) { font-size: 13px; }

/* ─── Footer ─── */
.adjustment-footer {
  margin-top: 12px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  transition: background 0.3s;
}
.adjustment-footer.unbalanced {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

/* ─── Net impact ─── */
.net-impact {
  margin-bottom: 16px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* ─── 审计说明卡片 ─── */
.audit-note-card { margin-top: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* ─── 编制提示 ─── */
.m8-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}
.m8-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m8-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m8-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
