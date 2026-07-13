<template>
  <div class="g10-l3" data-testid="g10-l3-reconciliation">
    <div class="methodology">
      负债方向 L3 调节：期末 = 期初 + 本期新增 − 本期终止 + 转入L3 − 转出L3 + FV变动 + 利息费用 + 其他
    </div>
    <div class="toolbar">
      <h3>G10-6 第三层次公允价值调节表</h3>
      <G10ImportExportDropdown :wp-id="wpId" sheet="G10-6" @imported="onImported" />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="l3.addRow()">+ 新增</el-button>
      <GtReviewTrigger section-id="G10-6-l3" />
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实第三层次公允价值负债期初至期末调节过程的完整与准确，验证层次转移的恰当性，确认调节结果与 G10-5 公允价值测试勾稽一致。" />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G10-6" /></span>
        <el-tag size="small" type="info">共 {{ l3.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-alert v-if="l3.varianceRows.value.length" type="warning" :closable="false" class="var-alert">
      {{ l3.varianceRows.value.length }} 行存在差异（企业期末 ≠ 计算期末）
    </el-alert>

    <el-table :data="l3.rows.value" border size="small" style="font-size:13px" max-height="480">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="负债名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input v-model="row.liabilityName" size="small" :disabled="isReadonly"
            @change="(v: string) => l3.updateCell(row.rowId, 'liabilityName', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期初" width="96" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.openingBalance" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'openingBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="本期新增" width="96" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.currentNew" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'currentNew', v)" />
        </template>
      </el-table-column>
      <el-table-column label="本期终止" width="96" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.currentTerminated" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'currentTerminated', v)" />
        </template>
      </el-table-column>
      <el-table-column label="转入L3" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.transferIntoL3" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'transferIntoL3', v)" />
        </template>
      </el-table-column>
      <el-table-column label="转出L3" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.transferOutOfL3" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'transferOutOfL3', v)" />
        </template>
      </el-table-column>
      <el-table-column label="FV变动" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.fairValueChange" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'fairValueChange', v)" />
        </template>
      </el-table-column>
      <el-table-column label="利息费用" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.interestExpense" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'interestExpense', v)" />
        </template>
      </el-table-column>
      <el-table-column label="其他" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.otherChanges" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'otherChanges', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期末(公式)" width="100" align="right">
        <template #default="{ row }"><span class="formula">{{ fmt(row.closingBalance) }}</span></template>
      </el-table-column>
      <el-table-column label="企业期末" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.reportedClosing" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'reportedClosing', v)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="88" align="right">
        <template #default="{ row }">
          <span :class="{ 'var-warn': Math.abs(row.variance) > 0.01 }">{{ fmt(row.variance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="80">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => l3.updateCell(row.rowId, 'remark', v)" />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="l3.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述第三层次调节表各行变动的核实情况、层次转入转出原因、企业期末与计算期末差异的核查结果。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>依据 CAS 37《金融工具列报》，第三层次公允价值须披露期初到期末的调节过程。</p>
        <p>计算期末 = 期初 + 本期新增 − 本期终止 + 转入L3 − 转出L3 + FV变动 + 利息费用 + 其他；「企业期末」与「计算期末」差异大于 0.01 时须核查并说明。</p>
        <p>转入/转出 Level3 应说明触发层次调整的原因；本表期末合计应与 G10-5 公允价值测试中 Level3 负债勾稽。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG10L3Reconciliation } from '../../composables/useG10L3Reconciliation'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const l3 = useG10L3Reconciliation({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计说明 / 审计结论（自由文本，conclusion:null 落库）────────────────────
const NOTE_KEY = 'G10-6-l3-audit-note'
const CONCLUSION_KEY = 'G10-6-l3-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) auditConclusion.value = c.remark
})

function onImported() {
  emit('imported')
  l3.reloadFromStore()
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g10-l3 { font-size: var(--wp-font-size, 13px); }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.formula { border-bottom: 1px dashed #909399; }
.var-warn { color: #e6a23c; font-weight: 600; }
.var-alert { margin-bottom: 8px; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 12px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
