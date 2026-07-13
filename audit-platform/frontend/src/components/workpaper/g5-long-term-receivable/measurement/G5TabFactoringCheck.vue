<template>
  <div class="g5-factoring-check">
    <div class="method-context">
      <p><strong>保理终止确认五项条件</strong>：风险报酬转移、控制权转移、无继续涉入、无回购义务、公允反映</p>
      <p>有追索权保理通常<strong>不应</strong>终止确认 — 若企业终止确认=是，系统橙色警告</p>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：核查应收款保理业务是否满足金融资产终止确认条件，识别有追索权保理仍作终止确认的错误处理。
    </el-alert>

    <div class="toolbar tab-toolbar">
      <GtIndexChip value="wp:G5-7" />
      <el-tag size="small" type="info">共 {{ fc.rows.value.length }} 行</el-tag>
      <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-7" @imported="onImported" />
      <el-button size="small" type="primary" plain @click="fc.addRow()" :disabled="props.readonly">+ 新增</el-button>
    </div>

    <el-table :data="fc.rows.value" border stripe style="width:100%;font-size:13px" max-height="480"
      :row-class-name="({ row }) => fc.warningRows.value.some(w => w.id === row.id) ? 'row-warning' : ''">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column label="债务人" min-width="100">
        <template #default="{ row }"><el-input v-model="row.debtor" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="保理商" min-width="100">
        <template #default="{ row }"><el-input v-model="row.factor" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.amount" size="small" :controls="false" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="方式" width="100">
        <template #default="{ row }">
          <el-select v-model="row.method" size="small" :disabled="props.readonly">
            <el-option label="有追索" value="有追索" /><el-option label="无追索" value="无追索" /><el-option label="其他" value="其他" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="终止确认" width="90">
        <template #default="{ row }">
          <el-select v-model="row.derecognition" size="small" :disabled="props.readonly">
            <el-option label="是" value="是" /><el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="判断依据" min-width="120">
        <template #default="{ row }"><el-input v-model="row.basis" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="结论" min-width="100">
        <template #default="{ row }"><el-input v-model="row.conclusion" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="props.readonly" /></template>
      </el-table-column>
      <el-table-column width="50" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!props.readonly" size="small" type="danger" link @click="fc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-bar">
      总额 {{ fmt(fc.totals.value.amount) }} · 已终止 {{ fmt(fc.totals.value.derecognized) }} · 未终止 {{ fmt(fc.totals.value.notDerecognized) }}
      <span v-if="fc.warningRows.value.length" class="warn-text"> · ⚠ {{ fc.warningRows.value.length }} 条有追索+终止确认异常</span>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><div class="section-header"><span>综合结论</span><el-button size="small" type="primary" text>AI 辅助</el-button></div></template>
      <el-input v-model="fc.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :disabled="props.readonly" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="props.readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述保理业务终止确认条件核查、有追索权异常识别及合同风险报酬转移实质判断。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="props.readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、终止确认处理恰当。B、除下述事项外未见异常。C、存在有追索权保理错误终止确认等重大事项。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>终止确认五项条件：风险报酬转移、控制权转移、无继续涉入、无回购义务、公允反映</li>
        <li>有追索权保理通常保留信用风险，一般<strong>不应</strong>终止确认；若企业已终止确认将橙色告警</li>
        <li>逐笔录入债务人/保理商/金额/方式/终止确认判断及依据</li>
        <li>结论应结合合同条款与风险报酬转移实质，异常笔数须专项说明（CAS 23）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG5FactoringCheck } from '../../composables/useG5FactoringCheck'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const fc = useG5FactoringCheck()

// ─── 审计说明 / 审计结论（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-7-audit-note'
const G5_CONCLUSION_KEY = 'G5-7-audit-conclusion'
function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function onImported(rows: unknown[]) { fc.loadRows(rows as any) }
function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g5-factoring-check { font-size: var(--wp-font-size, 13px); }
.method-context { margin-bottom: 12px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; font-size: 12px; color: #865c0a; }
.audit-objective { margin-bottom: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.totals-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; font-size: 12px; }
.warn-text { color: #e6a23c; font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.section-header { display: flex; justify-content: space-between; }
:deep(.row-warning) { background-color: #fdf6ec !important; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
