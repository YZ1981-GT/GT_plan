<template>
<div class="d6-tab-related-party">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 本表检查关联方合同资产（科目1402）的关联关系、余额及交易情况，识别是否存在通过关联方虚增合同资产的风险。</p>
      <p>2. 灰色底纹列为自动计算列（期末余额 = 期初余额 + 借方发生 − 贷方发生；账面价值 = 期末余额 − 坏账准备），不可手工编辑。</p>
      <p>3. 可从 D6-2 明细表一键导入标记为关联方的合同资产；关注长期挂账、未结转关联方款项的商业实质。</p>
      <p>4. 需披露关联方交易，并与附注关联方章节保持一致；重大关联方余额应结合期后结转情况评价可回收性。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：识别与关联方相关的合同资产及交易，评价其真实性、商业实质与可回收性，确认关联方交易披露的完整与恰当。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加关联方</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromDetail">从D6-2导入</el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload
                :show-file-list="false"
                accept=".xlsx"
                :auto-upload="false"
                :disabled="isReadonly || importing"
                @change="(f: any) => onImportFile(f.raw || f)"
              >
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-2" :context-project-id="projectId" /></span>
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

  <!-- 14列表格 -->
  <el-table v-if="!useVirtualScroll || !browseMode" :data="rows" size="small" border stripe max-height="500" style="width:100%">
    <el-table-column label="关联方名称" min-width="150">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.partyName"
          size="small"
          @change="(v: string) => updateCell(row.rowId, 'partyName', v)"
        />
        <span v-else>{{ row.partyName }}</span>
      </template>
    </el-table-column>

    <el-table-column label="关联关系" width="140">
      <template #default="{ row }">
        <el-select
          v-if="!isReadonly"
          :model-value="row.relationship"
          size="small"
          @change="(v: string) => updateCell(row.rowId, 'relationship', v)"
        >
          <el-option v-for="r in RELATIONSHIP_OPTIONS" :key="r" :label="r" :value="r" />
        </el-select>
        <span v-else>{{ row.relationship }}</span>
      </template>
    </el-table-column>

    <el-table-column label="期初余额" width="120" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.priorBalance"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(v: number) => updateCell(row.rowId, 'priorBalance', v ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.priorBalance) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="借方发生" width="120" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.debitAmount"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="贷方发生" width="120" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.creditAmount"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="期末余额" width="120" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span class="auto-calc">{{ fmtAmount(row.endBalance) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="坏账准备" width="110" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.impairment"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(v: number) => updateCell(row.rowId, 'impairment', v ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.impairment) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="账面价值" width="120" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span class="auto-calc">{{ fmtAmount(row.bookValue) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="发生时间及账龄" width="130">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.agingAndTiming"
          size="small"
          @change="(v: string) => updateCell(row.rowId, 'agingAndTiming', v)"
        />
        <span v-else>{{ row.agingAndTiming }}</span>
      </template>
    </el-table-column>

    <el-table-column label="未结转原因" width="140">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.unsettledReason"
          size="small"
          @change="(v: string) => updateCell(row.rowId, 'unsettledReason', v)"
        />
        <span v-else>{{ row.unsettledReason }}</span>
      </template>
    </el-table-column>

    <el-table-column label="至审计日结转金额" width="140" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.postSettlement"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(v: number) => updateCell(row.rowId, 'postSettlement', v ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.postSettlement) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="处理计划" width="120">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.plan"
          size="small"
          @change="(v: string) => updateCell(row.rowId, 'plan', v)"
        />
        <span v-else>{{ row.plan }}</span>
      </template>
    </el-table-column>

    <el-table-column label="索引号" width="80">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.indexRef"
          size="small"
          @change="(v: string) => updateCell(row.rowId, 'indexRef', v)"
        />
        <span v-else>{{ row.indexRef }}</span>
      </template>
    </el-table-column>

    <el-table-column label="备注" min-width="100">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.remark"
          size="small"
          @change="(v: string) => updateCell(row.rowId, 'remark', v)"
        />
        <span v-else>{{ row.remark }}</span>
      </template>
    </el-table-column>

    <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
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
    <span>期初合计：<strong>{{ fmtAmount(totalRow.priorBalance) }}</strong></span>
    <span>借方合计：<strong>{{ fmtAmount(totalRow.debitAmount) }}</strong></span>
    <span>贷方合计：<strong>{{ fmtAmount(totalRow.creditAmount) }}</strong></span>
    <span>期末合计：<strong>{{ fmtAmount(totalRow.endBalance) }}</strong></span>
    <span>坏账准备合计：<strong>{{ fmtAmount(totalRow.impairment) }}</strong></span>
    <span>账面价值合计：<strong>{{ fmtAmount(totalRow.bookValue) }}</strong></span>
    <span>结转合计：<strong>{{ fmtAmount(totalRow.postSettlement) }}</strong></span>
  </div>

  <!-- 审计意见区（卡片式） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-2" :context-project-id="projectId" />
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
          <GtReviewTrigger section-id="D6-5-note-explanation" label="💬 复核" />
        </div>
      </div>
      <el-input
        v-model="auditNotes.explanation"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对关联方合同资产的分析说明..."
      />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">2. 审计结论</span>
        <div class="opinion-actions">
          <GtReviewTrigger section-id="D6-5-note-conclusion" label="💬 复核" />
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
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabRelatedParty.vue — 关联关系及交易检查 D6-5
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD6RelatedParty, RELATIONSHIP_OPTIONS } from '../composables/useD6RelatedParty'
import type { ChecklistResponse } from '../composables/useD6FormData'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useD6AiGenerate } from '../composables/useD6AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtReviewTrigger from '../GtReviewTrigger.vue'

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

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-5',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
}

const {
  rows,
  totalRow,
  addRow,
  removeRow,
  updateCell,
  importFromDetail,
  auditNotes,
} = useD6RelatedParty({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD6AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genRelatedPartyNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('related-party-note', auditNotes.value.explanation, {
    task: '关联方合同资产分析说明',
    rowCount: rows.value.length,
    endBalanceTotal: totalRow.value.endBalance,
    bookValueTotal: totalRow.value.bookValue,
  }, 'AI · 关联方审计说明')
  if (text) auditNotes.value.explanation = text
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const browseRows = computed(() => rows.value)
const browseRowCount = computed(() => rows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('partyName', '关联方名称', 160),
  virtualTextCol('relationship', '关联关系', 120),
  virtualNumCol('endBalance', '期末余额', 110, fmtAmount),
  virtualNumCol('bookValue', '账面价值', 110, fmtAmount),
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
  tableWidth: 960,
})
</script>

<style scoped>
.d6-tab-related-party { padding: 16px; }
.d6-tab-related-party :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.d6-tab-related-party :deep(.el-table .cell) {
  font-size: 13px !important;
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
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }

.total-section {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  font-size: 13px;
}

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
