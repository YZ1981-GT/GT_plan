<!--
  GtA171Chapter4.vue — A17-1 第4章「审计过程中合伙人已关注的事项」结构化组件
  6个子节独立适用性+内容+编制提示(源模板红色文字)
  item_id 前缀 a171-ch4-*
-->
<template>
  <div class="gt-ch4">
    <!-- (一) 特别风险 -->
    <el-card shadow="never" class="gt-ch4__card">
      <template #header>
        <div class="gt-ch4__card-hd">
          <span class="gt-ch4__card-title">（一）特别风险</span>
          <div class="gt-ch4__card-actions">
            <el-switch v-model="s1HasRisk" size="small" active-text="有" inactive-text="无" @change="save" />
            <el-button size="small" :loading="aiLoading === 1" @click="aiGenerate(1)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch4__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch4__guidance-body">
          与审计应对措施的差异是指：由于对被审计单位和及其环境了解的加深，对特别风险的应对可能需要变更程序的性质、时间安排或范围。审计应对措施也包括确定是否需要修改重要性水平。
        </div>
      </details>
      <template v-if="s1HasRisk">
        <el-table :data="s1Rows" border size="small" class="gt-ch4__table">
          <el-table-column label="特别风险描述" min-width="160">
            <template #default="{ row }">
              <el-input v-model="row.risk" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="影响报告意见的错报" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.impact" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="所采取的措施及结论" min-width="160">
            <template #default="{ row }">
              <el-input v-model="row.measure" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="与审计应对措施的差异说明" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.diff" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column width="45" align="center">
            <template #default="{ $index }">
              <el-button type="danger" link size="small" @click="removeS1Row($index)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" type="primary" plain @click="addS1Row" style="margin-top:6px">+ 添加行</el-button>
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期未识别特别风险。" />
    </el-card>

    <!-- (二) 已更正或未更正的错报 -->
    <el-card shadow="never" class="gt-ch4__card">
      <template #header>
        <div class="gt-ch4__card-hd">
          <span class="gt-ch4__card-title">（二）已更正或未更正的错报</span>
          <el-button size="small" :loading="aiLoading === 2" @click="aiGenerate(2)">🤖 AI</el-button>
        </div>
      </template>
      <div class="gt-ch4__sub-items">
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">1、已更正错报汇总及评价</div>
          <details class="gt-ch4__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-ch4__guidance-body">按公司排列，调整金额进行统计，说明在审阶段本年调整金额占全部调整金额的比例、占重要性水平的比例。如公司数量很多，则可只列示调整金额较大的实体。</div>
          </details>
          <el-input v-model="s2Corrected" type="textarea" :autosize="{minRows:2}" placeholder="详见A2-2、A2-3" @change="save" />
        </div>
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">2、未更正错报汇总及评价</div>
          <details class="gt-ch4__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-ch4__guidance-body">
              (1) 按公司排列，未调整金额进行统计，说明在本期及以前期间累计的未更正错报占重要性水平的比例。如公司数量很多，可只列示未调整金额较大的实体。<br/>
              与审计计划阶段的重要性标准不考虑对收益趋势造成影响的、诸如"审计小结"、"审计总结备忘录"等合理且不会引起误解的其他标题。<br/>
              (2) 未更正错报应与管理层沟通中所列一致，指出在审计报告上二中所列的未更正错报是/不是金额较小对财务报表的整体影响不重大。对错误金额较大的未调整事项说明与客户沟通结果及形成审计差异的原因。
            </div>
          </details>
          <el-input v-model="s2Uncorrected" type="textarea" :autosize="{minRows:2}" placeholder="详见A13-1" @change="save" />
        </div>
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">3、披露不足事项汇总</div>
          <el-input v-model="s2Disclosure" type="textarea" :autosize="{minRows:2}" placeholder="无披露不足事项 / 列明具体事项" @change="save" />
        </div>
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">4、与管理层和治理层的沟通</div>
          <el-input v-model="s2Communication" type="textarea" :autosize="{minRows:2}" placeholder="详见A10-1; A10-2" @change="save" />
        </div>
      </div>
    </el-card>

    <!-- (三) 值得关注的缺陷和其他控制缺陷 -->
    <el-card shadow="never" class="gt-ch4__card">
      <template #header>
        <div class="gt-ch4__card-hd">
          <span class="gt-ch4__card-title">（三）值得关注的缺陷和其他控制缺陷</span>
          <div class="gt-ch4__card-actions">
            <el-switch v-model="s3HasDeficiency" size="small" active-text="有" inactive-text="无" @change="save" />
            <el-button size="small" :loading="aiLoading === 3" @click="aiGenerate(3)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch4__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch4__guidance-body">
          应在审计过程中发现并向治理层沟通的内控缺陷汇总，特别关注与治理层自身的审计相关内部控制方面值得关注的重大缺陷。详见B22B内控缺陷评价表。
        </div>
      </details>
      <template v-if="s3HasDeficiency">
        <el-input v-model="s3Content" type="textarea" :autosize="{minRows:3}" placeholder="说明识别的值得关注的内控缺陷" @change="save" />
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期未识别值得关注的内控缺陷。" />
    </el-card>

    <!-- (四) 重大职业判断 -->
    <el-card shadow="never" class="gt-ch4__card">
      <template #header>
        <div class="gt-ch4__card-hd">
          <span class="gt-ch4__card-title">（四）重大职业判断</span>
          <div class="gt-ch4__card-actions">
            <el-switch v-model="s4HasJudgment" size="small" active-text="有" inactive-text="无" @change="save" />
            <el-button size="small" :loading="aiLoading === 4" @click="aiGenerate(4)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch4__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch4__guidance-body">
          重大职业判断对照表：列示审计过程中涉及的重大职业判断内容、影响财务报告的重要性、已执行的程序及结论、应对措施是否需要改变。
        </div>
      </details>
      <template v-if="s4HasJudgment">
        <el-table :data="s4Rows" border size="small" class="gt-ch4__table">
          <el-table-column label="重大职业判断的内容" min-width="180">
            <template #default="{ row }">
              <el-input v-model="row.content" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="影响财务报告的重要性" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.importance" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="已执行的程序及结论" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.procedure" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="应对措施是否需改变" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.change_needed" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column width="45" align="center">
            <template #default="{ $index }">
              <el-button type="danger" link size="small" @click="removeS4Row($index)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" type="primary" plain @click="addS4Row" style="margin-top:6px">+ 添加行</el-button>
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期审计未涉及需特别说明的重大职业判断事项。" />
    </el-card>

    <!-- (五) 导致注册会计师难以实施必要审计程序的情形 -->
    <el-card shadow="never" class="gt-ch4__card">
      <template #header>
        <div class="gt-ch4__card-hd">
          <span class="gt-ch4__card-title">（五）导致注册会计师建议实施或变更审计程序的情形</span>
          <div class="gt-ch4__card-actions">
            <el-switch v-model="s5HasDifficulty" size="small" active-text="有" inactive-text="无" @change="save" />
            <el-button size="small" :loading="aiLoading === 5" @click="aiGenerate(5)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch4__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch4__guidance-body">
          项目组在十二个月成员组成发生变更的原因，该变更是否对审计产生不利影响。如需增减审计人员或审计工时，应说明原因并获得合伙人批准。<br/>
          在审计过程中遇到的意外情况，包括取证困难、客户配合不力等，以及被审计单位施加的审计范围限制情况。
        </div>
      </details>
      <template v-if="s5HasDifficulty">
        <el-table :data="s5Rows" border size="small" class="gt-ch4__table">
          <el-table-column label="可能导致变更审计程序的事项" min-width="200">
            <template #default="{ row }">
              <el-input v-model="row.event" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="对审计报告意见的影响" min-width="160">
            <template #default="{ row }">
              <el-input v-model="row.impact" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="已执行的程序及取得的审计证据" min-width="180">
            <template #default="{ row }">
              <el-input v-model="row.procedure" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="应对措施是否需要改变" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.change_needed" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column width="45" align="center">
            <template #default="{ $index }">
              <el-button type="danger" link size="small" @click="removeS5Row($index)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" type="primary" plain @click="addS5Row" style="margin-top:6px">+ 添加行</el-button>
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期审计未遇到导致变更审计程序的情形。" />
    </el-card>

    <!-- (六) 可能导致出具非无保留意见审计报告的事项 -->
    <el-card shadow="never" class="gt-ch4__card">
      <template #header>
        <div class="gt-ch4__card-hd">
          <span class="gt-ch4__card-title">（六）可能导致出具非无保留意见审计报告的事项</span>
          <div class="gt-ch4__card-actions">
            <el-switch v-model="s6HasModification" size="small" active-text="有" inactive-text="无" @change="save" />
            <el-button size="small" :loading="aiLoading === 6" @click="aiGenerate(6)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch4__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch4__guidance-body">
          (1) 被审计单位拒绝更正的错报是否与出具非无保留意见审计报告相关；<br/>
          (2) 是否审计单位已无法补救的事项及其影响。
        </div>
      </details>
      <template v-if="s6HasModification">
        <el-input v-model="s6Content" type="textarea" :autosize="{minRows:3}" placeholder="描述可能导致出具非标审计报告的事项" @change="save" />
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="不存在可能导致出具非无保留意见审计报告的事项。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface RiskRow { risk: string; impact: string; measure: string; diff: string }
interface JudgmentRow { content: string; importance: string; procedure: string; change_needed: string }
interface DifficultyRow { event: string; impact: string; procedure: string; change_needed: string }

const props = defineProps<{ wpId: string; projectId: string }>()

// ─── State ───
const s1HasRisk = ref(false)
const s1Rows = ref<RiskRow[]>([{ risk: '', impact: '', measure: '', diff: '' }])
const s2Corrected = ref('详见A2-2、A2-3')
const s2Uncorrected = ref('详见A13-1')
const s2Disclosure = ref('')
const s2Communication = ref('详见A10-1; A10-2')
const s3HasDeficiency = ref(false)
const s3Content = ref('')
const s4HasJudgment = ref(false)
const s4Rows = ref<JudgmentRow[]>([{ content: '', importance: '', procedure: '', change_needed: '' }])
const s5HasDifficulty = ref(false)
const s5Rows = ref<DifficultyRow[]>([{ event: '', impact: '', procedure: '', change_needed: '' }])
const s6HasModification = ref(false)
const s6Content = ref('')
const aiLoading = ref<number | null>(null)

// ─── Table CRUD ───
function addS1Row() { s1Rows.value.push({ risk: '', impact: '', measure: '', diff: '' }); save() }
function removeS1Row(i: number) { s1Rows.value.splice(i, 1); save() }
function addS4Row() { s4Rows.value.push({ content: '', importance: '', procedure: '', change_needed: '' }); save() }
function removeS4Row(i: number) { s4Rows.value.splice(i, 1); save() }
function addS5Row() { s5Rows.value.push({ event: '', impact: '', procedure: '', change_needed: '' }); save() }
function removeS5Row(i: number) { s5Rows.value.splice(i, 1); save() }

// ─── Persistence ───
let _saveTimer: ReturnType<typeof setTimeout> | null = null
function save() {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId) return
  const items: { item_id: string; conclusion: string | null; remark: string | null }[] = [
    { item_id: 'a171-ch4-s1-hasrisk', conclusion: s1HasRisk.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s1-rows', conclusion: null, remark: JSON.stringify(s1Rows.value) },
    { item_id: 'a171-ch4-s2-corrected', conclusion: null, remark: s2Corrected.value || null },
    { item_id: 'a171-ch4-s2-uncorrected', conclusion: null, remark: s2Uncorrected.value || null },
    { item_id: 'a171-ch4-s2-disclosure', conclusion: null, remark: s2Disclosure.value || null },
    { item_id: 'a171-ch4-s2-communication', conclusion: null, remark: s2Communication.value || null },
    { item_id: 'a171-ch4-s3-hasdeficiency', conclusion: s3HasDeficiency.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s3-content', conclusion: null, remark: s3Content.value || null },
    { item_id: 'a171-ch4-s4-hasjudgment', conclusion: s4HasJudgment.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s4-rows', conclusion: null, remark: JSON.stringify(s4Rows.value) },
    { item_id: 'a171-ch4-s5-hasdifficulty', conclusion: s5HasDifficulty.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s5-rows', conclusion: null, remark: JSON.stringify(s5Rows.value) },
    { item_id: 'a171-ch4-s6-hasmodification', conclusion: s6HasModification.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s6-content', conclusion: null, remark: s6Content.value || null },
  ]
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, { project_id: props.projectId || undefined, items })
  } catch { /* silent */ }
}

// ─── Load ───
async function loadData() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items = Array.isArray(res) ? res : (res as any)?.data || []
    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const r of items) { if (r.item_id?.startsWith('a171-ch4-')) map.set(r.item_id, r) }

    s1HasRisk.value = map.get('a171-ch4-s1-hasrisk')?.conclusion === 'Y'
    const s1Json = map.get('a171-ch4-s1-rows')?.remark
    if (s1Json) { try { s1Rows.value = JSON.parse(s1Json) } catch {} }

    s2Corrected.value = map.get('a171-ch4-s2-corrected')?.remark || '详见A2-2、A2-3'
    s2Uncorrected.value = map.get('a171-ch4-s2-uncorrected')?.remark || '详见A13-1'
    s2Disclosure.value = map.get('a171-ch4-s2-disclosure')?.remark || ''
    s2Communication.value = map.get('a171-ch4-s2-communication')?.remark || '详见A10-1; A10-2'

    s3HasDeficiency.value = map.get('a171-ch4-s3-hasdeficiency')?.conclusion === 'Y'
    s3Content.value = map.get('a171-ch4-s3-content')?.remark || ''

    s4HasJudgment.value = map.get('a171-ch4-s4-hasjudgment')?.conclusion === 'Y'
    const s4Json = map.get('a171-ch4-s4-rows')?.remark
    if (s4Json) { try { s4Rows.value = JSON.parse(s4Json) } catch {} }

    s5HasDifficulty.value = map.get('a171-ch4-s5-hasdifficulty')?.conclusion === 'Y'
    const s5Json = map.get('a171-ch4-s5-rows')?.remark
    if (s5Json) { try { s5Rows.value = JSON.parse(s5Json) } catch {} }

    s6HasModification.value = map.get('a171-ch4-s6-hasmodification')?.conclusion === 'Y'
    s6Content.value = map.get('a171-ch4-s6-content')?.remark || ''
  } catch { /* silent */ }
}

// ─── AI ───
async function aiGenerate(section: number) {
  const titles: Record<number, string> = {
    1: '特别风险及应对情况', 2: '已更正或未更正错报的评价',
    3: '值得关注的内控缺陷', 4: '重大职业判断事项',
    5: '导致变更审计程序的情形', 6: '可能导致出具非无保留意见审计报告的事项',
  }
  aiLoading.value = section
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 4, chapter_title: titles[section] || '', guidance: '',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    switch (section) {
      case 1: s1HasRisk.value = true; s1Rows.value = [{ risk: content, impact: '', measure: '', diff: '' }]; break
      case 2: s2Corrected.value = content; break
      case 3: s3Content.value = content; s3HasDeficiency.value = true; break
      case 4: s4HasJudgment.value = true; s4Rows.value = [{ content, importance: '', procedure: '', change_needed: '' }]; break
      case 5: s5HasDifficulty.value = true; s5Rows.value = [{ event: content, impact: '', procedure: '', change_needed: '' }]; break
      case 6: s6Content.value = content; s6HasModification.value = true; break
    }
    save()
    ElMessage.success('AI 已生成')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

onMounted(loadData)
</script>

<style scoped>
.gt-ch4 { font-size: 13px; display: flex; flex-direction: column; gap: 12px; }
.gt-ch4__card { margin-top: 4px; }
.gt-ch4__card-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-ch4__card-actions { display: flex; align-items: center; gap: 8px; }
.gt-ch4__card-actions :deep(.el-switch__label) { font-size: 13px; }
.gt-ch4__card-title { font-size: 13px; font-weight: 600; color: #6b21a8; }
.gt-ch4__sub-items { display: flex; flex-direction: column; gap: 12px; }
.gt-ch4__sub-item { display: flex; flex-direction: column; gap: 4px; }
.gt-ch4__sub-label { font-size: 13px; font-weight: 500; color: #606266; }
.gt-ch4__table { font-size: 12px; }
.gt-ch4__table :deep(.el-table__cell) { vertical-align: top; }

/* 编制提示折叠区 */
.gt-ch4__guidance { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-ch4__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-ch4__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; white-space: pre-wrap; }
</style>
