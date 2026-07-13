<template>
  <div class="f2-supplier-structure">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表分析重要供应商的采购集中度及其历年变动，评价采购结构合理性与供应链稳定性（CAS 1231 风险评估）。</p>
        <p>2. 灰色底纹列为自动计算列（占比%/排名/变动率），由各期采购金额自动测算，不可手工编辑。</p>
        <p>3. 关注前 5 大/前 10 大集中度过高、报告期新进入前 5 大、或采购额大幅波动的供应商，警惕关联方隐藏与利益输送。</p>
        <p>4. 可通过工具栏"AI 生成"辅助撰写结构分析结论，"💬"发起复核对话，"导入导出"批量维护供应商结构数据。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价重要供应商采购集中度及其变动趋势的合理性，识别供应链集中风险与未披露关联方交易。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ss.addRow()">+ 新增供应商</el-button>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="warning">
          前5大占比 {{ ss.concentrationSummary.value.top5Ratio.toFixed(1) }}%
          | 前10大 {{ ss.concentrationSummary.value.top10Ratio.toFixed(1) }}%
        </el-tag>
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-68"
          :disabled="isReadonly"
          ai-section="supplier-analysis"
          :existing-content="ss.auditNote.value"
          review-section="F2-68-structure"
          @ai-filled="(t: string) => { ss.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-68" /></span>
        <el-tag size="small" type="info">共 {{ ss.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <div class="table-scroll-wrap">
      <el-table
        :data="ss.enrichedRows.value"
        border
        size="small"
        max-height="480"
        :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''"
      >
        <!-- 固定列区 -->
        <el-table-column type="index" label="序号" width="55" fixed />
        <el-table-column label="供应商名称" width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supplierName" size="small"
              @change="(v: string) => ss.updateRow(row.id, { supplierName: v })" />
            <span v-else>{{ row.supplierName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="采购品类" width="100" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.category" size="small"
              @change="(v: string) => ss.updateRow(row.id, { category: v })" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合作年份" width="90" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.coopYear" size="small"
              @change="(v: string) => ss.updateRow(row.id, { coopYear: v })" />
            <span v-else>{{ row.coopYear }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方" width="80" fixed>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isRelated" size="small"
              @change="(v: '是'|'否') => ss.updateRow(row.id, { isRelated: v })">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isRelated }}</span>
          </template>
        </el-table-column>

        <!-- 滚动列区：各期金额/占比/排名 -->
        <el-table-column label="T期" align="center">
          <el-table-column label="金额" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.amountT" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ss.updateRow(row.id, { amountT: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="占比%" width="75" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula" :class="{ 'ratio-warn': row.isHighConcentration }" title="该供应商采购额/T期采购总额×100">{{ row.ratioT.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="排名" width="60" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula" title="按T期采购金额降序排名">{{ row.rankT || '—' }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-1期" align="center">
          <el-table-column label="金额" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.amountT1" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ss.updateRow(row.id, { amountT1: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="占比%" width="75" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula" title="该供应商采购额/T-1期采购总额×100">{{ row.ratioT1.toFixed(1) }}</span></template>
          </el-table-column>
          <el-table-column label="排名" width="60" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula" title="按T-1期采购金额降序排名">{{ row.rankT1 || '—' }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-2期" align="center">
          <el-table-column label="金额" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.amountT2" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ss.updateRow(row.id, { amountT2: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="占比%" width="75" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula" title="该供应商采购额/T-2期采购总额×100">{{ row.ratioT2.toFixed(1) }}</span></template>
          </el-table-column>
          <el-table-column label="排名" width="60" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula" title="按T-2期采购金额降序排名">{{ row.rankT2 || '—' }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T vs T-1" align="center">
          <el-table-column label="变动率" width="80" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span v-if="typeof row.changeTvsT1 === 'number'" class="formula" title="(T期金额-T-1期金额)/T-1期金额×100">{{ (row.changeTvsT1 * 100).toFixed(1) }}%</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="新增/退出" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.entryFlag" :type="row.isNewTop5 ? 'danger' : 'warning'" size="small">
              {{ row.entryFlag }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="集中度评价" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.concentrationEval" size="small"
              @change="(v: string) => ss.updateRow(row.id, { concentrationEval: v })" />
            <span v-else>{{ row.concentrationEval }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @change="(v: string) => ss.updateRow(row.id, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="55" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="ss.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="summary-bar">
      T期采购总额：{{ ss.concentrationSummary.value.totalT.toLocaleString() }}
      | 前5大集中度：{{ ss.concentrationSummary.value.top5Ratio.toFixed(1) }}%
      | 前10大：{{ ss.concentrationSummary.value.top10Ratio.toFixed(1) }}%
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">分析结论</span>
        </div>
      </template>
      <el-input v-model="ss.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="汇总供应商集中度分析、变动趋势及审计结论…" />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="audit-card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNoteText"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述所执行的供应商集中度分析程序、测试范围与结果，以及发现的异常事项及其处理。"
        @change="saveAuditNote"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2SupplierStructure } from '../../composables/useF2SupplierStructure'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ss = useF2SupplierStructure({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计说明（逐 sheet 打磨补齐，持久化走 f2-spe:save-items）──────────────────
const NOTE_KEY = 'F2-68-audit-note'
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
.f2-supplier-structure { padding: 12px 16px; font-size: var(--wp-font-size, 13px); }
.f2-supplier-structure :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-supplier-structure :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 表格 */
.table-scroll-wrap { overflow-x: auto; }
.formula { border-bottom: 1px dashed #909399; cursor: help; }
.ratio-warn { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fdf6ec; }
.summary-bar { margin-top: 12px; font-size: 12px; color: #606266; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; border-radius: 8px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.audit-card-header { font-weight: 600; font-size: 14px; color: #303133; }
</style>
