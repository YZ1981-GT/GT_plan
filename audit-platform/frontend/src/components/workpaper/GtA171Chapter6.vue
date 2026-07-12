<!--
  GtA171Chapter6.vue — A17-1 第6章「对重大错报风险的应对措施执行情况」结构化组件
  3个子节 + 适用性开关 + 编制提示
  item_id 前缀 a171-ch6-*
-->
<template>
  <div class="gt-ch6">
    <!-- (一) 财务报表层次重大错报风险的总体应对措施 -->
    <el-card shadow="never" class="gt-ch6__card">
      <template #header>
        <div class="gt-ch6__card-hd">
          <span class="gt-ch6__card-title">（一）财务报表层次重大错报风险的总体应对措施</span>
          <div class="gt-ch6__card-actions">
            <GtIndexChip value="B50" :context-project-id="props.projectId" />
            <el-button size="small" :loading="aiLoading === 1" @click="aiGenerate(1)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <el-table :data="s1Rows" border size="small" class="gt-ch6__table">
        <el-table-column label="财务报表层次重大错报风险描述" min-width="220">
          <template #default="{ row }">
            <el-input v-model="row.risk" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
          </template>
        </el-table-column>
        <el-table-column label="总体应对措施的执行情况" min-width="220">
          <template #default="{ row }">
            <el-input v-model="row.response" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
          </template>
        </el-table-column>
        <el-table-column width="45" align="center">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="removeS1Row($index)">×</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button size="small" type="primary" plain @click="addS1Row" style="margin-top:6px">+ 添加行</el-button>
    </el-card>

    <!-- (二) 认定层次的重大错报风险及应对措施 -->
    <el-card shadow="never" class="gt-ch6__card">
      <template #header>
        <div class="gt-ch6__card-hd">
          <span class="gt-ch6__card-title">（二）认定层次的重大错报风险及应对措施</span>
          <el-button size="small" :loading="aiLoading === 2" @click="aiGenerate(2)">🤖 AI</el-button>
        </div>
      </template>
      <details class="gt-ch6__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch6__guidance-body">列举事项供参考，需项目组对照总体审计策略中识别的重大错报风险及应对措施，说明执行的情况及结果。不适用的子项可关闭。</div>
      </details>
      <!-- 5个子项，各有适用性开关 -->
      <div class="gt-ch6__sub-items">
        <div v-for="(item, idx) in S2_ITEMS" :key="idx" class="gt-ch6__sub-item">
          <div class="gt-ch6__sub-header">
            <span class="gt-ch6__sub-label">{{ idx + 1 }}、{{ item.title }}</span>
            <el-switch v-model="s2Applicable[idx]" size="small" active-text="适用" inactive-text="不适用" @change="save" />
          </div>
          <template v-if="s2Applicable[idx]">
            <details class="gt-ch6__guidance gt-ch6__guidance--compact">
              <summary>📋 提示</summary>
              <div class="gt-ch6__guidance-body">{{ item.guidance }}</div>
            </details>
            <el-input v-model="s2Contents[idx]" type="textarea" :autosize="{minRows:2,maxRows:6}" :placeholder="item.placeholder" @change="save" />
          </template>
        </div>
      </div>
    </el-card>

    <!-- (三) "延伸检查"程序 -->
    <el-card shadow="never" class="gt-ch6__card">
      <template #header>
        <div class="gt-ch6__card-hd">
          <span class="gt-ch6__card-title">（三）"延伸检查"程序</span>
          <div class="gt-ch6__card-actions">
            <el-switch v-model="s3Applicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
            <el-button size="small" :loading="aiLoading === 3" @click="aiGenerate(3)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch6__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch6__guidance-body">被审计单位的财务报告用于资本运作或融资目的、首次承接的公众利益实体的审计业务、被审计单位处于高风险行业的、审计过程中已发现舞弊或疑似舞弊迹象的审计业务，还需说明执行延伸检查程序的情况。"延伸检查"程序适用情形和具体内容详见事务所《审计提示第61号—财务报表审计中执行延伸检查程序的相关要求》</div>
      </details>
      <template v-if="s3Applicable">
        <el-table :data="s3Rows" border size="small" class="gt-ch6__table">
          <el-table-column label="相关领域或业务流程" min-width="130">
            <template #default="{ row }">
              <el-input v-model="row.area" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="性质" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.nature" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="范围" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.scope" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="时间" width="100">
            <template #default="{ row }">
              <el-input v-model="row.time" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column label="结果" min-width="140">
            <template #default="{ row }">
              <el-input v-model="row.result" type="textarea" :autosize="{minRows:1,maxRows:3}" size="small" @change="save" />
            </template>
          </el-table-column>
          <el-table-column width="45" align="center">
            <template #default="{ $index }">
              <el-button type="danger" link size="small" @click="removeS3Row($index)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" type="primary" plain @click="addS3Row" style="margin-top:6px">+ 添加行</el-button>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="不适用（本项目不属于需执行延伸检查程序的情形）。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

interface S1Row { risk: string; response: string }
interface S3Row { area: string; nature: string; scope: string; time: string; result: string }

const props = defineProps<{ wpId: string; projectId: string }>()

// ─── Constants ───
const S2_ITEMS = [
  {
    title: '长期股权投资及减值准备',
    guidance: '(1)简要介绍财务报表截止日合并及母公司长期股权投资结构（与附注一致），各被投资单位经营情况、投资回报情况，以及本次审计考虑的减值准备计提情况。\n(2)说明报告期被审计单位收购和处置情况，按被审计单位进行描述（审计证据、判断、结论），包括同一/非同一控制下企业合并判断、公允价值获取、合并范围。\n(3)对非同一控制下企业合并的商誉及商誉减值测试情况（折现率选择、结论等）。\n(4)可供出售金融资产、交易性金融资产的会计处理，以及审计程序、判断、结论。',
    placeholder: '描述长期股权投资结构、减值准备、收购处置、商誉减值测试情况',
  },
  {
    title: '收入舞弊',
    guidance: '(1)审计期间被审计单位收入、成本构成及变动原因分析；\n(2)被审计单位收入确认具体原则；\n(3)实施的主要审计程序执行情况；\n(4)审计结论。',
    placeholder: '描述收入确认原则、审计程序执行情况及结论',
  },
  {
    title: '减值准备',
    guidance: '(1)被审计单位本期减值准备变动情况，详细说明变动原因及计提依据；\n(2)相关会计政策及变更情况；\n(3)实施的审计程序，准则相关规定及审计执行情况；\n(4)判断计提充足性；\n(5)审计结论以及会计政策变更对报表的影响。',
    placeholder: '描述减值准备变动、会计政策、审计程序及结论',
  },
  {
    title: '对外担保、诉讼等或有事项',
    guidance: '(1)被审计单位对外担保、诉讼具体情况，对财务报表的影响及潜在风险；\n(2)实施的审计程序；\n(3)判断或有事项对财务报表影响是否充分考虑；\n(4)审计结论及信息披露情况。',
    placeholder: '描述或有事项情况、审计程序及结论',
  },
  {
    title: '购买资产',
    guidance: '(1)报告期被审计单位资产购买的具体描述，包括背景、审批手续、合同条款、付款金额及时间、收购资产情况、对财务报表的影响等；\n(2)实施的审计程序；\n(3)判断财务处理的正确；\n(4)审计结论及信息披露情况。',
    placeholder: '描述资产购买情况、审计程序及结论',
  },
]

// ─── State ───
const s1Rows = ref<S1Row[]>([{ risk: '', response: '' }])
const s2Applicable = reactive([true, true, true, true, true])
const s2Contents = reactive(['', '', '', '', ''])
const s3Applicable = ref(false)
const s3Rows = ref<S3Row[]>([
  { area: '', nature: '核查关联方资金流水', scope: '', time: '', result: '' },
  { area: '', nature: '实地走访主要客户', scope: '', time: '', result: '' },
  { area: '', nature: '利用企业信息查询工具检索未披露的关联关系', scope: '', time: '', result: '' },
  { area: '', nature: '检查经销商的最终销售实现情况', scope: '', time: '', result: '' },
])
const aiLoading = ref<number | null>(null)

// ─── Table CRUD ───
function addS1Row() { s1Rows.value.push({ risk: '', response: '' }); save() }
function removeS1Row(i: number) { s1Rows.value.splice(i, 1); save() }
function addS3Row() { s3Rows.value.push({ area: '', nature: '', scope: '', time: '', result: '' }); save() }
function removeS3Row(i: number) { s3Rows.value.splice(i, 1); save() }

// ─── Persistence ───
let _saveTimer: ReturnType<typeof setTimeout> | null = null
function save() {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId) return
  const items: { item_id: string; conclusion: string | null; remark: string | null }[] = [
    { item_id: 'a171-ch6-s1-rows', conclusion: null, remark: JSON.stringify(s1Rows.value) },
    { item_id: 'a171-ch6-s2-applicable', conclusion: null, remark: JSON.stringify(Array.from(s2Applicable)) },
    { item_id: 'a171-ch6-s2-contents', conclusion: null, remark: JSON.stringify(Array.from(s2Contents)) },
    { item_id: 'a171-ch6-s3-applicable', conclusion: s3Applicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch6-s3-rows', conclusion: null, remark: JSON.stringify(s3Rows.value) },
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
    for (const r of items) { if (r.item_id?.startsWith('a171-ch6-')) map.set(r.item_id, r) }

    const s1Json = map.get('a171-ch6-s1-rows')?.remark
    if (s1Json) { try { s1Rows.value = JSON.parse(s1Json) } catch {} }

    const s2aJson = map.get('a171-ch6-s2-applicable')?.remark
    if (s2aJson) { try { const arr = JSON.parse(s2aJson); arr.forEach((v: boolean, i: number) => { if (i < 5) s2Applicable[i] = v }) } catch {} }

    const s2cJson = map.get('a171-ch6-s2-contents')?.remark
    if (s2cJson) { try { const arr = JSON.parse(s2cJson); arr.forEach((v: string, i: number) => { if (i < 5) s2Contents[i] = v }) } catch {} }

    s3Applicable.value = map.get('a171-ch6-s3-applicable')?.conclusion === 'Y'
    const s3Json = map.get('a171-ch6-s3-rows')?.remark
    if (s3Json) { try { s3Rows.value = JSON.parse(s3Json) } catch {} }
  } catch { /* silent */ }
}

// ─── AI ───
async function aiGenerate(section: number) {
  const titles: Record<number, string> = {
    1: '财务报表层次重大错报风险的总体应对措施',
    2: '认定层次的重大错报风险及应对措施',
    3: '"延伸检查"程序执行情况',
  }
  const guidances: Record<number, string> = {
    1: '根据B50风险评估矩阵中识别的财务报表层次重大错报风险，生成表格数据。请按JSON数组格式返回，每行包含risk(风险描述)和response(总体应对措施的执行情况)两个字段。示例：[{"risk":"管理层凌驾控制的风险","response":"执行了日记账分录测试和会计估计复核"}]',
    2: '对照总体审计策略中识别的认定层次重大错报风险（长投减值/收入舞弊/减值准备/或有事项/资产购买），说明各项执行情况及结果。',
    3: '说明延伸检查程序执行情况。请按JSON数组格式返回，每行包含area(领域或业务流程)、nature(性质)、scope(范围)、time(时间)、result(结果)。示例：[{"area":"收入确认","nature":"核查关联方资金流水","scope":"全部关联交易","time":"2025.12","result":"未发现异常"}]',
  }
  aiLoading.value = section
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 6, chapter_title: titles[section] || '', guidance: guidances[section] || '',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }

    if (section === 1) {
      // 尝试解析 JSON 数组
      const parsed = _tryParseJsonArray(content)
      if (parsed && parsed.length > 0) {
        s1Rows.value = parsed.map((r: any) => ({ risk: r.risk || '', response: r.response || '' }))
      } else {
        // 降级：把内容分行填入
        const lines = content.split('\n').filter((l: string) => l.trim())
        s1Rows.value = lines.map((l: string) => ({ risk: l, response: '' }))
      }
    } else if (section === 2) {
      s2Contents[0] = content
    } else if (section === 3) {
      s3Applicable.value = true
      const parsed = _tryParseJsonArray(content)
      if (parsed && parsed.length > 0) {
        s3Rows.value = parsed.map((r: any) => ({
          area: r.area || '', nature: r.nature || '', scope: r.scope || '', time: r.time || '', result: r.result || '',
        }))
      } else {
        s3Rows.value = [{ area: content, nature: '', scope: '', time: '', result: '' }]
      }
    }
    save()
    ElMessage.success('AI 已生成')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

import { tryParseJsonArray as _tryParseJsonArray } from '@/utils/aiJsonParse'

onMounted(loadData)
</script>

<style scoped>
.gt-ch6 { font-size: var(--wp-font-size, 13px); display: flex; flex-direction: column; gap: 12px; }
.gt-ch6__card { margin-top: 4px; }
.gt-ch6__card-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-ch6__card-actions { display: flex; align-items: center; gap: 8px; }
.gt-ch6__card-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #6b21a8; }
.gt-ch6__table { font-size: 12px; }
.gt-ch6__table :deep(.el-table__cell) { vertical-align: top; }
.gt-ch6__sub-items { display: flex; flex-direction: column; gap: 14px; }
.gt-ch6__sub-item { border-left: 3px solid #e4e7ed; padding-left: 12px; }
.gt-ch6__sub-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.gt-ch6__sub-label { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #303133; }

.gt-ch6__guidance { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-ch6__guidance--compact { margin-bottom: 6px; }
.gt-ch6__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-ch6__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; white-space: pre-wrap; }
</style>
