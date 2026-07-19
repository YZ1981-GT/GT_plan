<template>
  <div class="g5-factoring-check">
    <div class="method-context">
      <p><strong>编制思路（CAS 23）</strong>：先核实保理/ABS 合同实质 → 按九步决策树判断是否终止确认 → 归入「终止确认」或「继续涉入」明细 → 不满足的作质押借款继续确认。</p>
      <p>合同条款重点：追索权、回购条件、优先/劣后、可变利益、逾期罚息、自留份额增信（参见应用指南第38号）。有追索仍终止确认将橙色警示。</p>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>一、审计目标</template>
      核查长期应收款保理/资产证券化业务是否满足金融资产终止确认条件；识别有追索权或实质保留风险报酬仍作终止确认的不当处理。
    </el-alert>

    <div class="proc-block">
      <div class="proc-title">二、审计过程</div>
      <ol>
        <li>了解保理/ABS 业务性质与内容，获取合同、凭证，摘要主要条款。</li>
        <li>按 CAS 23 九步逐笔判断（可弹窗编辑），确认企业会计处理是否恰当，并归类填列下表。</li>
      </ol>
    </div>

    <div class="toolbar tab-toolbar">
      <GtIndexChip value="wp:G5-7" />
      <el-tag size="small" type="info">共 {{ fc.rows.value.length }} 笔</el-tag>
      <el-tag v-if="fc.warningRows.value.length" size="small" type="warning">警示 {{ fc.warningRows.value.length }}</el-tag>
      <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-7" :disabled="!!props.readonly" @imported="onImported" />
      <el-button size="small" type="primary" @click="openCreate" :disabled="props.readonly">+ 新增并判断</el-button>
    </div>

    <!-- （一）终止确认 -->
    <div class="section-card">
      <div class="section-head">
        <span class="section-title">三、（一）终止确认的长期应收款</span>
        <el-tag size="small" type="success" effect="plain">{{ fc.derecognizedRows.value.length }} 笔</el-tag>
      </div>
      <el-table
        :data="fc.derecognizedRows.value"
        border
        stripe
        size="small"
        style="width:100%"
        max-height="280"
        empty-text="本期无终止确认；有保理终止确认的请新增并完成九步判断"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column label="项目/债务人" min-width="110" prop="debtor" show-overflow-tooltip />
        <el-table-column label="转移方式" width="90" prop="transferMethod" show-overflow-tooltip />
        <el-table-column label="账面金额" width="110" align="right">
          <template #default="{ row }">{{ fmt(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="终止确认金额" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.derecognizedAmount || row.amount) }}</template>
        </el-table-column>
        <el-table-column label="终止确认损益" width="110" align="right">
          <template #default="{ row }">{{ fmt(row.gainLoss) }}</template>
        </el-table-column>
        <el-table-column label="主要合同条款" min-width="140" prop="contractTerms" show-overflow-tooltip />
        <el-table-column label="分析结论" min-width="120" prop="analysisConclusion" show-overflow-tooltip />
        <el-table-column label="索引" width="70" prop="indexRef" />
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">判断</el-button>
            <el-button v-if="!props.readonly" size="small" link type="danger" @click="fc.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- （二）继续涉入 -->
    <div class="section-card">
      <div class="section-head">
        <span class="section-title">三、（二）转移且继续涉入形成的资产、负债</span>
        <el-tag size="small" type="warning" effect="plain">{{ fc.continuingRows.value.length }} 笔</el-tag>
      </div>
      <el-table
        :data="fc.continuingRows.value"
        border
        stripe
        size="small"
        style="width:100%"
        max-height="240"
        empty-text="本期无继续涉入；若九步判断为继续涉入请在弹窗填写资产/负债金额"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column label="项目/债务人" min-width="110" prop="debtor" show-overflow-tooltip />
        <el-table-column label="转移方式" width="90" prop="transferMethod" show-overflow-tooltip />
        <el-table-column label="账面金额" width="110" align="right">
          <template #default="{ row }">{{ fmt(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="继续涉入资产" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.continuingAsset) }}</template>
        </el-table-column>
        <el-table-column label="继续涉入负债" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.continuingLiability) }}</template>
        </el-table-column>
        <el-table-column label="主要合同条款" min-width="140" prop="contractTerms" show-overflow-tooltip />
        <el-table-column label="分析结论" min-width="120" prop="analysisConclusion" show-overflow-tooltip />
        <el-table-column label="索引" width="70" prop="indexRef" />
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">判断</el-button>
            <el-button v-if="!props.readonly" size="small" link type="danger" @click="fc.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 未终止确认 / 待判断 -->
    <div v-if="fc.pledgedRows.value.length || fc.pendingRows.value.length" class="section-card">
      <div class="section-head">
        <span class="section-title">三、（附）未终止确认 / 待判断（作质押借款或待完成九步）</span>
        <el-tag size="small" type="info" effect="plain">{{ fc.pledgedRows.value.length + fc.pendingRows.value.length }} 笔</el-tag>
      </div>
      <el-table
        :data="[...fc.pledgedRows.value, ...fc.pendingRows.value]"
        border
        stripe
        size="small"
        style="width:100%"
        max-height="220"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column label="债务人" min-width="100" prop="debtor" />
        <el-table-column label="保理商" min-width="100" prop="factor" />
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">{{ fmt(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="追索" width="80" prop="method" />
        <el-table-column label="判断结论" min-width="180">
          <template #default="{ row }">
            <el-tag v-if="row.judgmentConclusion" :type="conclType(row.judgmentConclusion)" size="small">
              {{ row.judgmentConclusion }}
            </el-tag>
            <el-tag v-else type="info" size="small" effect="plain">待判断</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="九步进度" width="90" align="center">
          <template #default="{ row }">{{ stepProgress(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit(row)">
              {{ stepAnswered(row) ? '继续判断' : '开始判断' }}
            </el-button>
            <el-button v-if="!props.readonly" size="small" link type="danger" @click="fc.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="tip-red">编制说明：对未丧失控制权的金融资产转移，应确认为质押借款（继续确认长期应收款并确认借款）。</p>
    </div>

    <div class="totals-bar">
      账面合计 {{ fmt(fc.totals.value.amount) }}
      · 终止确认 {{ fmt(fc.totals.value.derecognized) }}
      · 继续涉入资产 {{ fmt(fc.totals.value.continuingAsset) }} / 负债 {{ fmt(fc.totals.value.continuingLiability) }}
      · 未终止 {{ fmt(fc.totals.value.notDerecognized) }}
      <span v-if="fc.warningRows.value.length" class="warn-text"> · ⚠ {{ fc.warningRows.value.length }} 条有追索+终止确认异常</span>
    </div>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="fc.conclusion.value"
      conclusion-title="四、审计结论"
      conclusion-ai-section="factoring-conclusion"
      note-placeholder="三、审计说明：概述保理/ABS 业务性质、九步判断结果、有追索权异常识别及与国企附注终止确认/继续涉入的勾稽。"
      conclusion-placeholder="填写审计结论：评价终止确认判断适当性，按 A/B/C 口径表述。"
      @update:note="saveAuditNote"
      @update:conclusion="(v: string) => { fc.conclusion.value = v }"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>流程：新增 → 弹窗填合同信息 → 九步判断 → 自动建议结论 → 归入（一）终止确认或（二）继续涉入</li>
        <li>九步与应收款项融资（D2）同一 CAS 23 决策树；关键分水岭为步骤6/7（风险报酬）与步骤8（控制）</li>
        <li>有追索权且结论为终止确认将橙色告警，须在审计说明中专项回应</li>
        <li>国企附注（2）（3）应与本表终止确认金额、继续涉入金额勾稽</li>
      </ul>
    </details>

    <G5FactoringJudgmentDialog
      v-model="dialogVisible"
      :row="editingRow"
      :readonly="!!props.readonly"
      @save="onDialogSave"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted } from 'vue'
import {
  useG5FactoringCheck,
  emptyRow,
  type FactoringCheckRow,
} from '../../composables/useG5FactoringCheck'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G5FactoringJudgmentDialog from './G5FactoringJudgmentDialog.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const emit = defineEmits<{ imported: [] }>()
const fc = useG5FactoringCheck()

const dialogVisible = ref(false)
const editingRow = ref<FactoringCheckRow | null>(null)

function openCreate(): void {
  editingRow.value = emptyRow()
  dialogVisible.value = true
}
function openEdit(row: FactoringCheckRow): void {
  editingRow.value = { ...row, judgmentSteps: row.judgmentSteps.map(s => ({ ...s })) }
  dialogVisible.value = true
}
function onDialogSave(row: FactoringCheckRow): void {
  fc.upsertRow(row)
}

function stepAnswered(row: FactoringCheckRow): number {
  return (row.judgmentSteps || []).filter(s => s.judgment).length
}
function stepProgress(row: FactoringCheckRow): string {
  return `${stepAnswered(row)}/9`
}
function conclType(c: string): 'success' | 'danger' | 'warning' | 'info' {
  if (c === '终止确认') return 'success'
  if (c.startsWith('不终止')) return 'danger'
  if (c.startsWith('按继续涉入')) return 'warning'
  return 'info'
}
function rowClassName({ row }: { row: FactoringCheckRow }): string {
  return fc.warningRows.value.some(w => w.id === row.id) ? 'row-warning' : ''
}

// ─── 审计说明 / 综合结论（持久化；fc.conclusion ↔ G5-7-audit-conclusion）───
const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const G5_NOTE_KEY = 'G5-7-audit-note'
const G5_CONCLUSION_KEY = 'G5-7-audit-conclusion'
function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
watch(() => fc.conclusion.value, (val) => {
  if (props.readonly) return
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val ?? '' })
})
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) fc.conclusion.value = c.remark
  const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_7_ROWS))
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed)) fc.loadRows(parsed)
      else if (Array.isArray(parsed?.rows)) fc.loadRows(parsed.rows)
    } catch { /* ignore */ }
  }
})
watch(
  () => fc.rows.value,
  () => {
    if (props.readonly) return
    const json = JSON.stringify(fc.rows.value)
    g5Notes.debouncedSave(G5_ITEM_IDS.G5_7_ROWS, { remark: json, conclusion: json })
  },
  { deep: true },
)

async function onImported() {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const raw = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_7_ROWS))
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) fc.loadRows(parsed)
    } catch { /* ignore */ }
  }
  emit('imported')
}
function fmt(v: number) {
  const n = Number(v) || 0
  if (Math.abs(n) < 0.005) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g5-factoring-check { font-size: var(--wp-font-size, 13px); }
.method-context { margin-bottom: 12px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; font-size: 12px; color: #865c0a; line-height: 1.7; }
.audit-objective { margin-bottom: 12px; }
.proc-block { margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; color: #606266; }
.proc-title { font-weight: 600; color: #303133; margin-bottom: 4px; }
.proc-block ol { margin: 0; padding-left: 18px; line-height: 1.8; }
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.section-card { margin-bottom: 14px; }
.section-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.section-title { font-size: 13px; font-weight: 600; color: #303133; }
.tip-red { margin: 6px 0 0; font-size: 12px; color: #f56c6c; }
.totals-bar { margin: 8px 0 12px; padding: 8px 12px; background: #f5f7fa; font-size: 12px; }
.warn-text { color: #e6a23c; font-weight: 600; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
:deep(.row-warning) { background-color: #fdf6ec !important; }
</style>
