<script setup lang="ts">
/**
 * J2TabAccrualCheck — J2-4 长期应付职工薪酬/设定受益计划净资产检查表（计提情况检查表）
 *
 * 对齐源模板「计提情况检查表J2-4」全 48 行结构：
 *  （一）判断为设定受益计划的理由：4 项固定判断（对应主要条款/判断理由/结论 是·否·N/A）
 *  （二）了解精算师资质及利用精算师的工作：利用专家的工作(→S12) / 评估专家工作(→S12A)
 *  （三）精算假设完整性测试：动态行（主要条款 / 是否在精算报告中 / 精算报告中的精算假设）
 *  （四）计量准确性测试：5 项（义务现值/计划资产/当期损益/其他综合收益/其他），各含考虑因素 + 测试过程
 *  三、审计说明 + 四、审计结论（AI 辅助）
 *
 *  各区块 JSON 持久化到 checklist_responses.remark（item_id J2-4-*），复用父 GtJ2 的 saveImmediate + allResponses。
 */
import { ref, reactive, computed, inject, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { GenerateWorkpaperAiText } from '../composables/useWorkpaperScaffold'
import GtIndexChip from '../GtIndexChip.vue'

interface RespItem { item_id: string; conclusion: string | null; remark: string | null }
const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, RespItem>
  isReadonly?: boolean
  saveImmediate?: (items: RespItem[]) => Promise<void> | void
}>()
const isReadonly = computed(() => props.isReadonly ?? false)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')

const KEY = {
  judge: 'J2-4-judge', expert: 'J2-4-expert', assumptions: 'J2-4-assumptions',
  measurement: 'J2-4-measurement', note: 'J2-4-note', conclusion: 'J2-4-conclusion',
}

// ── （一）判断为设定受益计划的理由 ────────────────────────────────────────────
interface JudgeRow { key: string; item: string; clause: string; reason: string; conclusion: string }
const judgeRows = reactive<JudgeRow[]>([
  { key: 'j1', item: '计划福利公式不仅仅与提存金金额相关，且要求企业在资产不足以满足该公式的福利时提供进一步的提存金', clause: '', reason: '', conclusion: '' },
  { key: 'j2', item: '通过计划间接地或直接地对提存金的特定回报作出担保', clause: '', reason: '', conclusion: '' },
  { key: 'j3', item: '企业给予补偿的事项是职工在职时提供的服务而不是退休本身', clause: '', reason: '', conclusion: '' },
  { key: 'j4', item: '精算风险和投资风险由企业来承担', clause: '', reason: '', conclusion: '' },
])
const JUDGE_OPTIONS = ['是', '否', 'N/A']

// ── （二）了解精算师资质及利用精算师的工作 ────────────────────────────────────
interface ExpertRow { key: string; item: string; indexCode: string; remark: string }
const expertRows = reactive<ExpertRow[]>([
  { key: 'e1', item: '利用专家的工作', indexCode: 'S12', remark: '' },
  { key: 'e2', item: '评估专家工作', indexCode: 'S12A', remark: '' },
])

// ── （三）精算假设完整性测试（动态行） ────────────────────────────────────────
interface AssumeRow { id: number; clause: string; inReport: string; reportAssumption: string }
const assumeRows = reactive<AssumeRow[]>([])
let assumeSeq = 1
const INREPORT_OPTIONS = ['是', '否']
async function addAssumeRow() {
  if (isReadonly.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入涉及精算假设的设定受益计划主要条款', '新增精算假设条款', {
      confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '如：折现率与货币、期限匹配的高质量公司债券收益率',
    })
    assumeRows.push({ id: assumeSeq++, clause: value || '', inReport: '', reportAssumption: '' })
    scheduleSave()
  } catch { /* 取消 */ }
}
function removeAssumeRow(id: number) {
  if (isReadonly.value) return
  const i = assumeRows.findIndex(r => r.id === id)
  if (i >= 0) { assumeRows.splice(i, 1); scheduleSave() }
}

// ── （四）计量准确性测试（5 项，各含考虑因素 + 测试过程） ──────────────────────
interface MeasureSection { key: string; title: string; factors: string; process: string }
const measureSections = reactive<MeasureSection[]>([
  { key: 'dbo', title: '1、设定受益计划义务现值测试', factors: '考虑因素：（1）设定受益计划义务；（2）折现率的选取', process: '' },
  { key: 'asset', title: '2、设定受益计划资产测试', factors: '考虑因素：（1）设定受益资产原值；（2）设定受益资产公允价值的变动；（3）设定受益资产上限', process: '' },
  { key: 'pl', title: '3、计入当期损益金额测试', factors: '考虑因素：（1）当期服务成本；（2）过去服务成本；（3）结算利得和损失', process: '' },
  { key: 'oci', title: '4、计入其他综合收益金额测试', factors: '考虑因素：（1）精算利得或损失；（2）计划资产回报；（3）资产上限影响的变动', process: '' },
  { key: 'other', title: '5、其他测试', factors: '考虑因素：（1）本期结算时消除的负债；（2）已支付的福利', process: '' },
])

// ── 审计说明 / 结论 ───────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
const aiLoading = ref('')

// ── 加载 ──────────────────────────────────────────────────────────────────────
function parseJson<T>(id: string, fb: T): T { const raw = props.allResponses?.get(id)?.remark; if (!raw) return fb; try { const p = JSON.parse(raw); return (p ?? fb) as T } catch { return fb } }
function assignByKey<T extends { key: string }>(target: T[], saved: unknown) {
  if (!Array.isArray(saved)) return
  for (const s of saved as Record<string, unknown>[]) { const row = target.find(r => r.key === s.key); if (row) Object.assign(row, s) }
}
function load() {
  assignByKey(judgeRows, parseJson(KEY.judge, null))
  assignByKey(expertRows, parseJson(KEY.expert, null))
  assignByKey(measureSections, parseJson(KEY.measurement, null))
  const savedAssume = parseJson<AssumeRow[] | null>(KEY.assumptions, null)
  if (Array.isArray(savedAssume)) {
    assumeRows.splice(0, assumeRows.length, ...savedAssume)
    assumeSeq = Math.max(0, ...assumeRows.map(r => r.id)) + 1
  }
  const nt = props.allResponses?.get(KEY.note)?.remark; if (nt) auditNote.value = nt
  const cc = props.allResponses?.get(KEY.conclusion)?.remark; if (cc) auditConclusion.value = cc
}

// ── 保存（防抖） ──────────────────────────────────────────────────────────────
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  props.saveImmediate([
    { item_id: KEY.judge, conclusion: null, remark: JSON.stringify(judgeRows) },
    { item_id: KEY.expert, conclusion: null, remark: JSON.stringify(expertRows) },
    { item_id: KEY.assumptions, conclusion: null, remark: JSON.stringify(assumeRows) },
    { item_id: KEY.measurement, conclusion: null, remark: JSON.stringify(measureSections) },
    { item_id: KEY.note, conclusion: null, remark: auditNote.value },
    { item_id: KEY.conclusion, conclusion: null, remark: auditConclusion.value },
  ])
}

// ── AI 辅助 ───────────────────────────────────────────────────────────────────
async function aiGen(target: 'note' | 'conclusion' | string) {
  if (isReadonly.value) return
  aiLoading.value = target
  try {
    const judged = judgeRows.filter(r => r.conclusion).map(r => `${r.item.slice(0, 20)}…=${r.conclusion}`).join('；')
    const context: Record<string, string> = {
      科目: '2221 长期应付职工薪酬 / 设定受益计划净资产检查表（J2-4）',
      设定受益计划判断: judged || '（未判断）',
      精算假设条款数: String(assumeRows.length),
    }
    let existing = ''
    let section = ''
    if (target === 'note') { existing = auditNote.value; section = 'j2-4-note' }
    else if (target === 'conclusion') { existing = auditConclusion.value; section = 'j2-4-conclusion' }
    else {
      const sec = measureSections.find(s => s.key === target)
      if (!sec) { aiLoading.value = ''; return }
      existing = sec.process; section = `j2-4-measure-${target}`
      context['测试项目'] = sec.title
      context['考虑因素'] = sec.factors
    }
    const text = await generateAiText({ section, context, existingContent: existing })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
    } else {
      if (target === 'note') auditNote.value = text
      else if (target === 'conclusion') auditConclusion.value = text
      else { const sec = measureSections.find(s => s.key === target); if (sec) sec.process = text }
      scheduleSave()
    }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j2-tab-accrual-check">
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：①长期应付职工薪酬存在且记录于恰当账户；②所有应记录的长期应付职工薪酬及相关披露均已记录/包括（完整性）；③由被审计单位拥有或控制；④以恰当金额列示，计价/分摊调整已恰当记录，相关披露已恰当计量和描述。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="doc-title">长期应付职工薪酬/设定受益计划净资产检查表</h3>
      <GtIndexChip value="wp:J2-4" :context-project-id="projectId" />
    </div>

    <div class="proc-title">二、审计过程</div>

    <!-- （一）判断为设定受益计划的理由 -->
    <h4 class="sec-title">（一）判断为设定受益计划的理由</h4>
    <el-table :data="judgeRows" border size="small" class="wp-table">
      <el-table-column label="序号" width="56" align="center"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
      <el-table-column label="判断项目" min-width="320"><template #default="{ row }">{{ row.item }}</template></el-table-column>
      <el-table-column label="对应的设定受益计划主要条款" min-width="200">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.clause" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.clause }}</span>
        </template>
      </el-table-column>
      <el-table-column label="判断理由" min-width="200">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.reason" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.reason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="判断结论" width="120" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.conclusion" placeholder="选择" size="small" @change="scheduleSave">
            <el-option v-for="o in JUDGE_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.conclusion }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- （二）了解精算师资质及利用精算师的工作 -->
    <h4 class="sec-title">（二）了解精算师资质及利用精算师的工作</h4>
    <el-table :data="expertRows" border size="small" class="wp-table" style="max-width: 760px">
      <el-table-column label="序号" width="56" align="center"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
      <el-table-column label="项目" min-width="200"><template #default="{ row }">{{ row.item }}</template></el-table-column>
      <el-table-column label="索引号" width="120" align="center">
        <template #default="{ row }"><GtIndexChip :value="`wp:${row.indexCode}`" :context-project-id="projectId" /></template>
      </el-table-column>
      <el-table-column label="评价说明" min-width="240">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- （三）精算假设完整性测试 -->
    <div class="sec-head">
      <h4 class="sec-title">（三）精算假设完整性测试</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addAssumeRow">+ 新增条款</el-button>
    </div>
    <el-table :data="assumeRows" border size="small" class="wp-table">
      <el-table-column label="序号" width="56" align="center"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
      <el-table-column label="涉及精算假设的设定受益计划主要条款" min-width="300">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.clause" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.clause }}</span>
        </template>
      </el-table-column>
      <el-table-column label="该精算假设是否在精算师的精算报告中" width="200" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.inReport" placeholder="选择" size="small" @change="scheduleSave">
            <el-option v-for="o in INREPORT_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.inReport }}</span>
        </template>
      </el-table-column>
      <el-table-column label="精算报告中的精算假设" min-width="220">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.reportAssumption" type="textarea" :autosize="{ minRows: 1 }" size="small" @change="scheduleSave" />
          <span v-else>{{ row.reportAssumption }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ row }"><el-button size="small" type="danger" link @click="removeAssumeRow(row.id)">删除</el-button></template>
      </el-table-column>
      <template #empty><span class="empty-hint">暂无数据，点击"+ 新增条款"添加涉及精算假设的主要条款</span></template>
    </el-table>

    <!-- （四）计量准确性测试 -->
    <h4 class="sec-title">（四）计量准确性测试</h4>
    <div v-for="sec in measureSections" :key="sec.key" class="measure-section">
      <div class="measure-hd">
        <span class="measure-title">{{ sec.title }}</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === sec.key" :disabled="isReadonly" @click="aiGen(sec.key)">🤖 AI辅助</el-button>
      </div>
      <div class="factors-block">{{ sec.factors }}</div>
      <el-input v-model="sec.process" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="测试过程如下：（描述执行的测试程序、获取的证据及结果）" @change="scheduleSave" />
    </div>

    <!-- 三、审计说明 -->
    <div class="note-wrap">
      <div class="note-hd"><span>三、审计说明</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'note'" :disabled="isReadonly" @click="aiGen('note')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly" placeholder="审计说明可以概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。" @change="scheduleSave" />
    </div>

    <!-- 四、审计结论 -->
    <div class="note-wrap">
      <div class="note-hd"><span>四、审计结论</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="aiGen('conclusion')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="请输入审计结论，或点击 AI 辅助生成（如：未见异常；或除上述调整事项外其余未见异常等）。" @change="scheduleSave" />
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，先判断是否构成设定受益计划（4 项条件任一满足即需按设定受益计划核算）。</p>
        <p>2. 设定受益义务须由精算师采用预期累计福利单位法计量；依据 ISA 620 评价精算师胜任能力、客观性及工作充分性（利用专家 S12 / 评估专家 S12A）。</p>
        <p>3. 精算假设完整性测试：核对精算师报告是否涵盖折现率、死亡率、离职率、薪酬增长率等关键假设。</p>
        <p>4. 计量准确性测试按义务现值/计划资产/当期损益/其他综合收益/其他五方面执行，测试过程与审定表（J2-1）、明细表（J2-2）勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.j2-tab-accrual-check { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.doc-title { font-size: 15px; font-weight: 600; margin: 0; }
.proc-title { font-size: 14px; font-weight: 600; color: #303133; margin: 8px 0; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 18px 0 8px; }
.sec-head { display: flex; align-items: center; justify-content: space-between; margin: 18px 0 8px; }
.sec-head .sec-title { margin: 0; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.empty-hint { font-size: 12px; color: #909399; }
.measure-section { margin-bottom: 14px; }
.measure-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.measure-title { font-size: 13px; font-weight: 600; color: #303133; }
.factors-block { font-size: 12px; color: #b88230; background: #fdf6ec; border-left: 3px solid #e6a23c; padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; }
.note-wrap { margin-top: 14px; }
.note-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #303133; }
.conclusion-actions { display: flex; gap: 6px; align-items: center; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
