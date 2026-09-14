<template>
  <div class="h5-tab-detail">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：核实油气资产原值、累计折耗及净值的明细构成，确认与审定表(H5-1)勾稽一致。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
        <!--
          🔴 H5 不能挂 `CycleImportExportDropdown`（2026-08-12 实证）

          该组件拼的是**路径形态** `/api/workpapers/{wp_id}/{prefix}/export-data`，
          而 h5 的真实端点是第三形态，由 `app/routers/h5_oil_gas_assets.py` 提供：
            POST /api/h5/export-template   body: H5ExportRequest（wp_id 在 body 里）
            POST /api/h5/export-data       body: H5ExportRequest
            POST /api/h5/import-data       Form: wp_id / sheet(默认 H5-2) / file
          运行期路由表（2113 条）里 `/api/workpapers/{wp_id}/h5/*` **完全不存在**
          ——`_h5_import_export.py` 工厂虽声明了这三条，但从未 include_router。

          ⇒ 挂 dropdown 必 404。registry 的 72 个前缀中，只有 h5 与 n4 是这种
            「registry 有登记但路径形态不可达」的情况，已由后端守卫
            `backend/tests/test_ie_prefix_reachability.py` 钉死清单。

          h5 的导入导出要接线，得走适配 body/Form 形态的 composable，
          而现存 `composables/useH5ImportExport.ts` 也拼了错的路径形态
          （`/api/workpapers/${wpId}/h5/...`），本身即坏 —— 修它属独立任务。
        -->
      </div>
    </div>

    <!-- 区段Tab切换 -->
    <el-segmented v-model="state.activeSegment.value" :options="segmentOptions" class="segment-bar" />

    <!-- Section标题 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-2 油气资产明细表</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-2')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 区段1: 基础信息 -->
      <el-table v-if="state.activeSegment.value === 'basic'" :data="displayRows" border stripe size="small" class="detail-table">
        <el-table-column prop="category" label="资产分类" min-width="100">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.category" size="small"
              @change="onUpdate(row.rowId, 'category', $event)" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="资产名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.name" size="small"
              @change="onUpdate(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="oilField" label="油田/气田" min-width="110">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.oilField" size="small"
              @change="onUpdate(row.rowId, 'oilField', $event)" />
            <span v-else>{{ row.oilField }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="block" label="区块" min-width="100">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.block" size="small"
              @change="onUpdate(row.rowId, 'block', $event)" />
            <span v-else>{{ row.block }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 区段2: 原值变动 -->
      <el-table v-if="state.activeSegment.value === 'cost'" :data="displayRows" border stripe size="small" class="detail-table">
        <el-table-column prop="name" label="资产" min-width="100" fixed />
        <el-table-column prop="originalCostBegin" label="期初原值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.originalCostBegin" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'originalCostBegin', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCostIncrease" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.originalCostIncrease" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'originalCostIncrease', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCostDecrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.originalCostDecrease" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'originalCostDecrease', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末原值" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtAmt(row.originalCostEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseReason" label="增加原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.increaseReason" size="small"
              @change="onUpdate(row.rowId, 'increaseReason', $event)" />
            <span v-else>{{ row.increaseReason }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 区段3: 折耗 -->
      <el-table v-if="state.activeSegment.value === 'depletion'" :data="displayRows" border stripe size="small" class="detail-table">
        <el-table-column prop="name" label="资产" min-width="100" fixed />
        <el-table-column prop="accDepletionBegin" label="期初折耗" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.accDepletionBegin" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'accDepletionBegin', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepletionBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepletionProvision" label="本期计提" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.accDepletionProvision" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'accDepletionProvision', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepletionProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepletionReversal" label="本期转回" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.accDepletionReversal" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'accDepletionReversal', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepletionReversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末折耗" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+计提-转回">{{ fmtAmt(row.accDepletionEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净值" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=原值期末-折耗期末">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 交叉验证提示 -->
    <el-alert v-if="state.crossValidation.value.hasCostWarning || state.crossValidation.value.hasDepWarning"
      type="warning" :closable="false" show-icon class="cross-alert">
      <template #title>
        交叉验证（H5-1审定表）：
        <span v-if="state.crossValidation.value.hasCostWarning">原值差异 {{ fmtAmt(state.crossValidation.value.costDiff) }}</span>
        <span v-if="state.crossValidation.value.hasDepWarning"> 折耗差异 {{ fmtAmt(state.crossValidation.value.deplDiff) }}</span>
      </template>
    </el-alert>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增资产行</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计说明..." :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
        placeholder="填写审计结论..." :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>明细表分3区段Tab(基础信息/原值变动/折耗)，行保持同步</li>
        <li>原值期末=期初+增加-减少（资产类方向）</li>
        <li>折耗期末=期初+计提-转回（备抵类方向）</li>
        <li>净值=原值期末-折耗期末</li>
        <li>合计行与H5-1审定表自动交叉验证</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Detail, SEGMENT_CONFIGS } from '../../composables/useH5Detail'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const state = useH5Detail({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onSave: (itemId, value) => formData.setResponse(itemId, value),
})

const segmentOptions = SEGMENT_CONFIGS.map((s) => ({ label: s.label, value: s.key }))

const displayRows = computed(() => {
  const rows = [...state.rows.value]
  rows.push(state.subtotalRow.value as any)
  return rows
})

function onUpdate(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field as any, value ?? 0)
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增资产行', {
    confirmButtonText: '确定', cancelButtonText: '取消',
  })
  if (value) state.addRow(value)
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h5-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.segment-bar { margin-bottom: 16px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.cross-alert { margin-bottom: 12px; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
