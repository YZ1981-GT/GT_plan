<template>
  <div class="f2-reversal">
    <h3 class="title">跌价转回 F2-49</h3>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 以前减记存货价值的影响因素已消失的，减记金额应予恢复，并在原已计提跌价准备金额内转回（CAS 1 号存货，转回不得超过原计提数）。</p>
        <p>2. 灰色底纹列为自动计算列（当前 NRV、现需计提、转回金额），据售价/完工成本/销售费用自动测算，不可手工编辑。</p>
        <p>3. 存在转回金额但缺"转回依据"的行自动标橙，须落实价值恢复的客观证据（价格回升、订单恢复等），防止无依据转回操纵利润。</p>
        <p>4. 切换分段可分别查看期初已计提与当前 NRV/转回测算；转回后账面价值不得超过成本。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证存货跌价准备转回的条件是否满足（减值因素消失且有客观证据），确认转回金额未超过原计提数，防止通过不当转回高估存货与利润。"
      class="objective-alert"
    />

    <div class="summary">
      <el-tag size="small" type="success">可转回笔数: {{ rev.summary.value.reverseCount }}</el-tag>
      <el-tag size="small" type="info">转回合计: {{ rev.summary.value.reverseTotal.toLocaleString() }}</el-tag>
      <el-tag v-if="rev.summary.value.missingRationale > 0" size="small" type="warning">
        {{ rev.summary.value.missingRationale }} 笔缺转回依据
      </el-tag>
    </div>
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="rev.addRow()">+ 新增行</el-button>
        <el-segmented v-model="rev.activeSegment.value" :options="segments" size="small" />
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-49"
          :disabled="isReadonly"
          ai-section="reversal-evaluation"
          :existing-content="rev.auditNote.value"
          :related-context="{ reverseCount: rev.summary.value.reverseCount }"
          ai-title="AI 生成 · 跌价转回评价"
          review-section="F2-49-conclusion"
          @ai-filled="(t: string) => { rev.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ rev.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>
    <el-table :data="rev.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.needsRationale ? 'warn-row' : ''">
      <el-table-column label="品名" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => rev.updateRow(row.rowId, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>

      <template v-if="rev.activeSegment.value === 'prior'">
        <el-table-column label="账面成本" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookCost" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { bookCost: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="已计提跌价" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorProvision" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { priorProvision: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="售价" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.sellingPrice" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { sellingPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="完工成本" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.completionCost" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { completionCost: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="销售费用" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.sellingExpense" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { sellingExpense: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="当前NRV" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula" title="售价 − 完工成本 − 销售费用">{{ row.currentNrv.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="现需计提" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula" title="账面成本 − 当前NRV（不小于0）">{{ row.currentRequired.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="转回金额" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.shouldReverse" class="formula reverse" title="已计提跌价 − 现需计提（限原计提数内）">{{ row.reversalAmount.toLocaleString() }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="转回依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.rationale" size="small"
              @change="(v: string) => rev.updateRow(row.rowId, { rationale: v })" />
            <span v-else>{{ row.rationale }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="rev.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input v-model="rev.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="跌价准备转回评价审计说明..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2ImpairmentReversal } from '../../composables/useF2ImpairmentReversal'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const segments = [
  { label: '期初跌价', value: 'prior' },
  { label: '当前NRV/转回', value: 'current' },
]

const rev = useF2ImpairmentReversal({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-reversal { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-reversal :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-reversal :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.title { margin: 0 0 8px; }
.summary { margin-bottom: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
.reverse { color: #67c23a; }
:deep(.warn-row) { background: #fdf6ec; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; font-size: var(--wp-font-size, 13px); }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
