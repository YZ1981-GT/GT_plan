<template>
<div class="d7-related-party">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示关联方合同负债（科目2205），依据 CAS14 收入准则及关联方披露准则关注关联交易的真实性与商业实质。</p>
        <p>2. "期末余额"由期初 + 贷方发生 − 借方发生自动计算（灰色底纹），不可手工录入。</p>
        <p>3. 关联方长期挂账的合同负债应核查经济业务实质，警惕通过关联方虚增或调节收入。</p>
        <p>4. 数据可从 D7-2 明细表按关联关系一键导入；需关注至审计日的结转情况及处理计划。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        <span class="ao-title">一、审计目标</span>
      </template>
      <template #default>
        <ol class="ao-list">
          <li>资产负债表中记录的合同负债是存在的，且已经记录在恰当的账户中；</li>
          <li>记录的合同负债由被审计单位拥有或控制；</li>
          <li>记录的合同负债是被审计单位应当履行的短期义务；</li>
          <li>负债以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
        </ol>
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加关联方</el-button>
        <el-button size="small" :disabled="isReadonly" @click="importFromD72">从D7-2导入</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" :disabled="isReadonly">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D7-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
      </el-alert>
      <el-button size="small" @click="toggleBrowseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>
    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="browseRows"
      :width="tableWidth"
      :height="tableHeight"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
    />

    <!-- 11列表格 -->
    <el-table v-if="!useVirtualScroll || !browseMode" :data="rows" size="small" border max-height="500">
      <el-table-column label="关联方名称" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.partyName" size="small" @change="(v: string) => updateCell(row.rowId, 'partyName', v)" />
          <span v-else>
            {{ row.partyName }}
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" style="margin-left:4px" />
          </span>
        </template>
      </el-table-column>
      <el-table-column label="关联关系" width="140">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.relationship" size="small" @change="(v: string) => updateCell(row.rowId, 'relationship', v)">
            <el-option v-for="r in RELATIONSHIP_OPTIONS" :key="r" :label="r" :value="r" />
          </el-select>
          <span v-else>{{ row.relationship }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'openingBalance', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.openingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方发生" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方发生" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="发生时间及账龄" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.agingTime" size="small" @change="(v: string) => updateCell(row.rowId, 'agingTime', v)" />
          <span v-else>{{ row.agingTime }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未结转原因" width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => updateCell(row.rowId, 'reason', v)" />
          <span v-else>{{ row.reason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="至审计日结转金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.auditDateTransfer" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'auditDateTransfer', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.auditDateTransfer) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="处理计划" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.plan" size="small" @change="(v: string) => updateCell(row.rowId, 'plan', v)" />
          <span v-else>{{ row.plan }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否公允" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.isFairValue || ''"
            size="small"
            placeholder="选择"
            @change="(v: string) => updateCell(row.rowId, 'isFairValue', v)"
          >
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="待定" value="待定" />
          </el-select>
          <span v-else>{{ row.isFairValue || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="判断依据" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.fairValueBasis || ''"
            size="small"
            placeholder="公允价值判断依据..."
            @change="(v: string) => updateCell(row.rowId, 'fairValueBasis', v)"
          />
          <span v-else>{{ row.fairValueBasis || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-section">
      <span>期初合计：<strong>{{ fmtAmt(totalRow.openingBalance) }}</strong></span>
      <span>借方合计：<strong>{{ fmtAmt(totalRow.debitAmount) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmt(totalRow.creditAmount) }}</strong></span>
      <span>期末合计：<strong>{{ fmtAmt(totalRow.endBalance) }}</strong></span>
      <span>结转合计：<strong>{{ fmtAmt(totalRow.auditDateTransfer) }}</strong></span>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genRelatedPartyNote">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReview('D7-6-note-explanation')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="对关联方合同负债的分析说明..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReview('D7-6-note-conclusion')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="关联方交易结论..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">3. 关联方交易公允性总结</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genFairValueSummary">🤖 AI辅助</el-button>
            </el-tooltip>
          </div>
        </div>
        <el-input
          v-model="fairValueSummary"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 7 }"
          :disabled="isReadonly"
          placeholder="总结关联方交易公允性判断结果..."
        />
      </div>
    </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabRelatedParty.vue — 关联方 D7-6 (~300行)
 * Task: 21.1
 * Requirements: 11.1-11.9, 19.3, 20.1, 21.1-21.3
 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import { useD7RelatedParty, RELATIONSHIP_OPTIONS } from '../composables/useD7RelatedParty'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useD7AiGenerate } from '../composables/useD7AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string) { openReviewDialog(sectionId) }

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD7ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D7-6',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const {
  rows, totalRow, addRow, removeRow, updateCell, importFromD72, auditNotes,
} = useD7RelatedParty({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD7AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genRelatedPartyNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('related-party-note', auditNotes.value.explanation, {
    task: '关联方合同负债分析说明',
    rowCount: rows.value.length,
    endBalanceTotal: totalRow.value.endBalance,
    auditDateTransferTotal: totalRow.value.auditDateTransfer,
  }, 'AI · 关联方审计说明')
  if (text) auditNotes.value.explanation = text
}

// --- 关联方交易公允性总结 ---
const fairValueSummary = ref('')

watch(
  () => allResponsesRef.value.get('D7-6-fair-value-summary')?.remark,
  (val) => { fairValueSummary.value = val || '' },
  { immediate: true },
)

watch(fairValueSummary, (val) => {
  props.debouncedSave('D7-6-fair-value-summary', { remark: val })
})

async function genFairValueSummary() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('related-party-fairvalue', fairValueSummary.value, {
    task: '关联方交易公允性总结',
    rowCount: rows.value.length,
  }, 'AI · 公允性总结')
  if (text) fairValueSummary.value = text
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => rows.value)
const browseRowCount = computed(() => rows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('partyName', '关联方名称', 160),
  virtualTextCol('relationship', '关联关系', 120),
  virtualNumCol('endBalance', '期末余额', 110, fmtAmt),
  virtualNumCol('auditDateTransfer', '至审计日结转', 120, fmtAmt),
])

const {
  browseMode,
  useVirtualScroll,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 920,
})
</script>

<style scoped>
.d7-related-party { padding: 12px; }
.d7-related-party :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d7-related-party :deep(.el-table .cell) {
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

/* 审计目标 */
.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }

.total-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  font-size: var(--wp-font-size, 13px);
}

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
</style>
