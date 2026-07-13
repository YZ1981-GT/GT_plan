<template>
  <div class="g5-ecl-policy">
    <div class="section-head tab-toolbar">
      <h3 class="sheet-title">G5-8 会计政策检查</h3>
      <GtIndexChip value="wp:G5-8" />
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：检查长期应收款预期信用损失（ECL）会计政策及关键参数是否符合准则要求，评价政策一致性与合规性。
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header><div class="section-header"><span>（一）基本政策</span><el-button size="small" type="primary" text>AI</el-button></div></template>
      <el-table :data="policy.section1.value" border size="small" style="font-size:13px">
        <el-table-column prop="checkItem" label="检查项" min-width="140" />
        <el-table-column prop="requirement" label="要求" min-width="120" />
        <el-table-column label="企业政策" min-width="120">
          <template #default="{ row }"><el-input v-model="row.companyPolicy" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="合规性" width="100">
          <template #default="{ row }">
            <el-select v-model="row.compliance" size="small" :disabled="props.readonly">
              <el-option label="合规" value="合规" /><el-option label="不合规" value="不合规" /><el-option label="待核实" value="待核实" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="120">
          <template #default="{ row }"><el-input v-model="row.explanation" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span>（二）ECL 参数</span>
          <div><el-button size="small" type="primary" text>AI</el-button>
          <el-button size="small" plain @click="policy.addSection2Row()" :disabled="props.readonly">+ 新增</el-button></div>
        </div>
      </template>
      <el-table :data="policy.section2.value" border size="small" style="font-size:13px">
        <el-table-column label="检查项" min-width="140">
          <template #default="{ row }"><el-input v-model="row.checkItem" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="要求" min-width="120">
          <template #default="{ row }"><el-input v-model="row.requirement" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="企业政策" min-width="120">
          <template #default="{ row }"><el-input v-model="row.companyPolicy" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="合规性" width="100">
          <template #default="{ row }">
            <el-select v-model="row.compliance" size="small" :disabled="props.readonly">
              <el-option label="合规" value="合规" /><el-option label="不合规" value="不合规" /><el-option label="待核实" value="待核实" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="120">
          <template #default="{ row }"><el-input v-model="row.explanation" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><div class="section-header"><span>综合结论</span><el-button size="small" type="primary" text>AI</el-button></div></template>
      <el-input v-model="policy.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="props.readonly" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="props.readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述 ECL 会计政策核对情况、关键参数（PD/LGD/EAD）及前瞻性信息合理性评价。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="props.readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、会计政策合规、参数合理。B、除下述事项外未见异常。C、存在重大不合规或参数不当事项。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>核对企业是否采用三阶段 ECL 模型，判断标准与准则一致（CAS 22）</li>
        <li>关注 ECL 关键参数：违约概率 PD、违约损失率 LGD、违约风险敞口 EAD 的确定依据</li>
        <li>关注前瞻性信息与宏观经济情景权重的合理性</li>
        <li>合规性逐项判断（合规 / 不合规 / 待核实），不合规项须在说明中记录并跟进</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG5EclPolicy } from '../../composables/useG5EclPolicy'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'
import GtIndexChip from '../../GtIndexChip.vue'
const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const policy = useG5EclPolicy()

// ─── 审计说明 / 审计结论（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-8-audit-note'
const G5_CONCLUSION_KEY = 'G5-8-audit-conclusion'
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
</script>

<style scoped>
.g5-ecl-policy { font-size: var(--wp-font-size, 13px); padding: 4px; }
.section-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.section-card { margin-bottom: 12px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
