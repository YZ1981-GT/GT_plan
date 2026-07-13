<template>
  <div class="f2-unit-price">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表分析主要原材料采购单价的历年趋势及与行业均价的偏离度，验证采购价格公允、采购成本真实（CAS 1231 / CAS 1323）。</p>
        <p>2. 灰色底纹列为自动计算列（采购额/同比变动率/环比变动率/偏离度%），由单价与采购量自动测算，不可手工编辑。</p>
        <p>3. 偏离度异常的材料行以红色高亮提示，请填写行业均价并撰写分析结论，警惕向关联方高买或转移定价。</p>
        <p>4. 可通过工具栏"AI 生成"辅助撰写价格分析结论，"💬"发起复核对话，"导入导出"批量维护单价数据。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价主要原材料采购单价的公允性与变动合理性，识别采购价格异常及关联方转移定价风险。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="up.addRow()">+ 新增材料</el-button>
        <el-input v-model="up.searchQuery.value" size="small" placeholder="搜索材料名称/规格" clearable class="search" />
      </div>
      <div class="toolbar-right">
        <el-tag v-if="up.abnormalCount.value > 0" type="danger" size="small">
          {{ up.abnormalCount.value }} 行偏离度异常
        </el-tag>
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-62"
          :disabled="isReadonly"
          ai-section="price-analysis"
          :existing-content="up.auditNote.value"
          review-section="F2-62-price"
          @ai-filled="(t: string) => { up.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-62" /></span>
        <el-tag size="small" type="info">共 {{ up.filteredRows.value.length }} 行</el-tag>
      </div>
    </div>

    <div class="table-scroll-wrap">
      <el-table
        :data="up.filteredRows.value"
        border
        size="small"
        max-height="480"
        :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''"
      >
        <el-table-column prop="materialName" label="材料名称" width="120" fixed />
        <el-table-column label="规格" width="90" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.spec" size="small"
              @change="(v: string) => up.updateRow(row.id, { spec: v })" />
            <span v-else>{{ row.spec }}</span>
          </template>
        </el-table-column>
        <el-table-column label="单位" width="70" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
              @change="(v: string) => up.updateRow(row.id, { unit: v })" />
            <span v-else>{{ row.unit }}</span>
          </template>
        </el-table-column>

        <el-table-column label="T期" align="center">
          <el-table-column label="单价" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.priceT" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { priceT: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.qtyT" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { qtyT: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购额" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula" title="单价×采购量">{{ row.amountT.toLocaleString() }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-1期" align="center">
          <el-table-column label="单价" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.priceT1" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { priceT1: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.qtyT1" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { qtyT1: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购额" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula" title="单价×采购量">{{ row.amountT1.toLocaleString() }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-2期" align="center">
          <el-table-column label="单价" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.priceT2" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { priceT2: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.qtyT2" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { qtyT2: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购额" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula" title="单价×采购量">{{ row.amountT2.toLocaleString() }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="同比变动率" width="95" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula" title="(T期单价-T-1期单价)/T-1期单价×100">{{ up.fmtRate(row.yoyChangeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="环比变动率" width="95" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula" title="(T-1期单价-T-2期单价)/T-2期单价×100">{{ up.fmtRate(row.momChangeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="行业均价" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.industryAvgPrice" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => up.updateRow(row.id, { industryAvgPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="偏离度%" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula" :class="{ 'dev-warn': row.isHighDeviation }" title="(T期单价-行业均价)/行业均价×100">{{ row.deviationPct.toFixed(1) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分析结论" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.analysisConclusion" size="small"
              @change="(v: string) => up.updateRow(row.id, { analysisConclusion: v })" />
            <span v-else>{{ row.analysisConclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @change="(v: string) => up.updateRow(row.id, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="55" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="up.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">分析结论</span>
        </div>
      </template>
      <el-input v-model="up.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="汇总原材料单价趋势、偏离度分析及审计结论…" />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="audit-card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNoteText"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述所执行的原材料单价趋势与偏离度核查程序、测试范围与结果，以及发现的异常事项及其处理。"
        @change="saveAuditNote"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2UnitPrice } from '../../composables/useF2UnitPrice'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const up = useF2UnitPrice({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计说明（逐 sheet 打磨补齐，持久化走 f2-spe:save-items）──────────────────
const NOTE_KEY = 'F2-62-audit-note'
const auditNoteText = ref('')
function persistSpeAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  persistSpeAudit(NOTE_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
})
</script>

<style scoped>
.f2-unit-price { padding: 12px 16px; font-size: var(--wp-font-size, 13px); }
.f2-unit-price :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-unit-price :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.search { width: 180px; }

/* 表格 */
.table-scroll-wrap { overflow-x: auto; }
.formula { border-bottom: 1px dashed #909399; cursor: help; }
.dev-warn { color: #f56c6c; font-weight: 600; background: #fef0f0; padding: 0 4px; border-radius: 2px; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fef0f0; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; border-radius: 8px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.audit-card-header { font-weight: 600; font-size: 14px; color: #303133; }
</style>
