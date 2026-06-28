<!--
  GtA171Chapter15.vue — A17-1 第15章「其他特殊考虑事项」结构化组件
  源模板结构：(一)内控审计意见 (二)发债业务 (三)新三板核查
  + 原A/B/C舞弊/违法/组成部分(改为D/E/F)
  每大节可不适用，item_id 前缀 a171-ch15-*
-->
<template>
  <div class="gt-ch15">
    <el-alert type="info" :closable="false" class="gt-ch15__tip">
      <template #title>此部分内容如不适用请关闭对应开关。</template>
    </el-alert>

    <!-- (一) 出具内部控制审计意见的考虑 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">（一）出具内部控制审计意见的考虑</span>
          <el-switch v-model="icApplicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
        </div>
      </template>
      <template v-if="icApplicable">
        <details class="gt-ch15__guidance">
          <summary>📋 编制提示</summary>
          <div class="gt-ch15__guidance-body">
            1、识别出的内部控制缺陷汇总：(1)财务报告内控缺陷汇总(组成部分/相关业务流程/缺陷描述及影响/缺陷类型/所影响的账户交易披露及认定/补偿性控制/发生错报的可能性及严重程序分析/缺陷认定结论) (2)非财务报告内控重大缺陷(6列) (3)内控缺陷在期后的整改情况<br/>
            2、拟发表的内部控制审计意见类型：已评价控制测试结果、财务报表审计中发现的错报及所有控制缺陷。查阅了涉及内部控制的内部审计报告或类似报告。<br/>
            已取得书面声明(A16)、已考虑期后事项(A11)、已评价内控评价报告完整性(B11-2)。<br/>
            关于意见类型确定，可参考"审计指引第31(4)号—内部控制审计报告"。如出具非标准无保留意见，应说明具体情况并按事务所质量控制制度提交专业技术委员会审核。
          </div>
        </details>
        <div class="gt-ch15__sub-label">1、识别出的内部控制缺陷汇总</div>
        <div class="gt-ch15__textarea-wrap">
          <el-input v-model="icDeficiencySummary" type="textarea" :autosize="{minRows:3}" placeholder="(1)财务报告内控缺陷汇总 (2)非财务报告内控重大缺陷 (3)期后整改情况（可索引B22B）" @change="save" />
          <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'ic1'" @click="aiGenerate('ic1')">🤖 AI</el-button>
        </div>
        <div class="gt-ch15__sub-label" style="margin-top:12px">2、拟发表的内部控制审计意见类型</div>
        <div class="gt-ch15__textarea-wrap">
          <el-input v-model="icOpinionType" type="textarea" :autosize="{minRows:2}" placeholder="标准无保留意见 / 非标准意见（说明原因）" @change="save" />
          <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'ic2'" @click="aiGenerate('ic2')">🤖 AI</el-button>
        </div>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="不适用（本项目不需要出具内部控制审计报告）。" />
    </el-card>

    <!-- (二) 发债业务的特殊考虑 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">（二）发债业务的特殊考虑</span>
          <el-switch v-model="bondApplicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
        </div>
      </template>
      <template v-if="bondApplicable">
        <details class="gt-ch15__guidance">
          <summary>📋 编制提示</summary>
          <div class="gt-ch15__guidance-body">
            1、非经营性资产：描述被审计单位控制或受托管理的非经营性资产情况（政府办公场所、公园、医院、学校、事业单位资产及不产生收益的市政道路、桥梁、博物馆等纯公益性资产）。说明对非经营性资产列报和披露是否符合企业会计准则的规定，以及项目组所执行的主要审计程序。<br/>
            2、偿债能力分析：根据审定财务报表数据，分析被审计单位自身偿债能力及偿债保障措施。发行人累计债券余额(含本期)应小于最近一年全口径所有者权益(包含少数股东权益)的40%。发行人最近3年平均净利润应能覆盖本期债券1年的利息。对于资产负债率超过65%的项目，需要对其负债率进行专项分析。资产负债率在80%至90%之间必须要求提供担保。资产负债率超过90%，不予核准发行债券。<br/>
            3、担保情况：描述被审计单位债券担保的有效性，抵押担保是否存在一物多押，抵质押资产是否是易变现有效资产，第三方担保的是否存在互保或连环保。说明对担保事项列报、披露完整性执行的审计程序。
          </div>
        </details>
        <div class="gt-ch15__sub-items">
          <div class="gt-ch15__sub-item">
            <div class="gt-ch15__sub-label">1、非经营性资产</div>
            <div class="gt-ch15__textarea-wrap">
              <el-input v-model="bondNonOperating" type="textarea" :autosize="{minRows:2}" placeholder="描述非经营性资产情况及审计程序" @change="save" />
              <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'bond1'" @click="aiGenerate('bond1')">🤖 AI</el-button>
            </div>
          </div>
          <div class="gt-ch15__sub-item">
            <div class="gt-ch15__sub-label">2、偿债能力分析</div>
            <div class="gt-ch15__textarea-wrap">
              <el-input v-model="bondSolvency" type="textarea" :autosize="{minRows:2}" placeholder="偿债能力分析（资产负债率/净利润覆盖/债券余额比例）" @change="save" />
              <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'bond2'" @click="aiGenerate('bond2')">🤖 AI</el-button>
            </div>
          </div>
          <div class="gt-ch15__sub-item">
            <div class="gt-ch15__sub-label">3、担保情况</div>
            <div class="gt-ch15__textarea-wrap">
              <el-input v-model="bondGuarantee" type="textarea" :autosize="{minRows:2}" placeholder="担保有效性、抵押质押情况、互保连环保分析" @change="save" />
              <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'bond3'" @click="aiGenerate('bond3')">🤖 AI</el-button>
            </div>
          </div>
        </div>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="不适用（本项目不涉及发债业务）。" />
    </el-card>

    <!-- (三) 新三板审计业务特殊核查事项 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">（三）新三板审计业务特殊核查事项</span>
          <el-switch v-model="neeqApplicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
        </div>
      </template>
      <template v-if="neeqApplicable">
        <details class="gt-ch15__guidance">
          <summary>📋 编制提示</summary>
          <div class="gt-ch15__guidance-body">
            1、被审计单位是否存在会计监管6号提及的情形（企业类型：融资需求/分层调整动机/首次公开发行/对赌协议；业务类型：首次承接新三板已挂牌公司/首次申请挂牌/创新层审计；风险情形：成立时间短/特殊业务模式/复杂会计政策/重大前期差错/持续经营不确定性/其他高风险）。<br/>
            2、会计监管提示6号及9号九方面问题核查（9大类：审计项目质量控制/了解被审计单位/持续经营/收入确认/关联方认定及交易/货币资金/费用确认和计量/内部控制有效性/财务报表披露）。<br/>
            3、新三板挂牌审计一般问题核查（5大类：合法合规/财务与业务匹配性/财务规范性/财务指标与会计政策/关联交易）。
          </div>
        </details>
        <div class="gt-ch15__textarea-wrap">
          <el-input v-model="neeqContent" type="textarea" :autosize="{minRows:4}" placeholder="核查情况说明（可分别描述上述三方面的核查结论）" @change="save" />
          <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'neeq'" @click="aiGenerate('neeq')">🤖 AI</el-button>
        </div>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="不适用（本项目不涉及新三板审计业务）。" />
    </el-card>

    <!-- (四) 舞弊相关 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">（四）舞弊相关</span>
          <el-radio-group v-model="fraudAnswer" size="small" @change="save">
            <el-radio-button value="none">未发现</el-radio-button>
            <el-radio-button value="found">有发现</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <details class="gt-ch15__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch15__guidance-body">如识别出舞弊或获取的信息表明可能存在舞弊，应当及时向项目合伙人报告。需考虑：管理层凌驾控制迹象；收入确认舞弊风险；日记账分录异常；关联方交易舞弊迹象。如发现舞弊，说明性质、金额、应对措施及对审计意见的影响。</div>
      </details>
      <template v-if="fraudAnswer === 'found'">
        <div class="gt-ch15__textarea-wrap">
          <el-input v-model="fraudContent" type="textarea" :autosize="{minRows:3}" placeholder="描述发现的舞弊或舞弊迹象及处理措施" @change="save" />
          <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'fraud'" @click="aiGenerate('fraud')">🤖 AI</el-button>
        </div>
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期审计未发现舞弊或舞弊迹象。" />
    </el-card>

    <!-- (五) 违反法律法规情况 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">（五）违反法律法规情况</span>
          <el-radio-group v-model="legalAnswer" size="small" @change="save">
            <el-radio-button value="none">未发现</el-radio-button>
            <el-radio-button value="found">有发现</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <template v-if="legalAnswer === 'found'">
        <div class="gt-ch15__textarea-wrap">
          <el-input v-model="legalContent" type="textarea" :autosize="{minRows:3}" placeholder="描述违法违规行为及影响评估" @change="save" />
          <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'legal'" @click="aiGenerate('legal')">🤖 AI</el-button>
        </div>
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="未发现被审计单位存在重大违反法律法规的行为。" />
    </el-card>

    <!-- (六) 组成部分审计师的利用 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">（六）组成部分审计师的利用</span>
          <el-radio-group v-model="componentAnswer" size="small" @change="save">
            <el-radio-button value="na">不适用</el-radio-button>
            <el-radio-button value="used">已利用</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <template v-if="componentAnswer === 'used'">
        <div class="gt-ch15__textarea-wrap">
          <el-input v-model="componentContent" type="textarea" :autosize="{minRows:3}" placeholder="名称、负责范围、沟通安排、复核程序及结论（参见B30）" @change="save" />
          <el-button size="small" class="gt-ch15__ai-btn" :loading="aiLoading === 'component'" @click="aiGenerate('component')">🤖 AI</el-button>
        </div>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="不适用（本次审计未利用组成部分审计师的工作）。" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{ wpId: string; projectId: string }>()

// ─── State ───
// (一) 内控审计
const icApplicable = ref(false)
const icDeficiencySummary = ref('')
const icOpinionType = ref('')
// (二) 发债
const bondApplicable = ref(false)
const bondNonOperating = ref('')
const bondSolvency = ref('')
const bondGuarantee = ref('')
// (三) 新三板
const neeqApplicable = ref(false)
const neeqContent = ref('')
// (四) 舞弊
const fraudAnswer = ref<'none' | 'found'>('none')
const fraudContent = ref('')
// (五) 违法
const legalAnswer = ref<'none' | 'found'>('none')
const legalContent = ref('')
// (六) 组成部分
const componentAnswer = ref<'na' | 'used'>('na')
const componentContent = ref('')
const aiLoading = ref<string | null>(null)

// ─── Persistence ───
let _saveTimer: ReturnType<typeof setTimeout> | null = null
function save() {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId) return
  const items: { item_id: string; conclusion: string | null; remark: string | null }[] = [
    { item_id: 'a171-ch15-ic-applicable', conclusion: icApplicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch15-ic-deficiency', conclusion: null, remark: icDeficiencySummary.value || null },
    { item_id: 'a171-ch15-ic-opinion', conclusion: null, remark: icOpinionType.value || null },
    { item_id: 'a171-ch15-bond-applicable', conclusion: bondApplicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch15-bond-nonop', conclusion: null, remark: bondNonOperating.value || null },
    { item_id: 'a171-ch15-bond-solvency', conclusion: null, remark: bondSolvency.value || null },
    { item_id: 'a171-ch15-bond-guarantee', conclusion: null, remark: bondGuarantee.value || null },
    { item_id: 'a171-ch15-neeq-applicable', conclusion: neeqApplicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch15-neeq-content', conclusion: null, remark: neeqContent.value || null },
    { item_id: 'a171-ch15-fraud-answer', conclusion: fraudAnswer.value, remark: null },
    { item_id: 'a171-ch15-fraud-content', conclusion: null, remark: fraudContent.value || null },
    { item_id: 'a171-ch15-legal-answer', conclusion: legalAnswer.value, remark: null },
    { item_id: 'a171-ch15-legal-content', conclusion: null, remark: legalContent.value || null },
    { item_id: 'a171-ch15-component-answer', conclusion: componentAnswer.value, remark: null },
    { item_id: 'a171-ch15-component-content', conclusion: null, remark: componentContent.value || null },
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
    for (const r of items) { if (r.item_id?.startsWith('a171-ch15-')) map.set(r.item_id, r) }

    icApplicable.value = map.get('a171-ch15-ic-applicable')?.conclusion === 'Y'
    icDeficiencySummary.value = map.get('a171-ch15-ic-deficiency')?.remark || ''
    icOpinionType.value = map.get('a171-ch15-ic-opinion')?.remark || ''

    bondApplicable.value = map.get('a171-ch15-bond-applicable')?.conclusion === 'Y'
    bondNonOperating.value = map.get('a171-ch15-bond-nonop')?.remark || ''
    bondSolvency.value = map.get('a171-ch15-bond-solvency')?.remark || ''
    bondGuarantee.value = map.get('a171-ch15-bond-guarantee')?.remark || ''

    neeqApplicable.value = map.get('a171-ch15-neeq-applicable')?.conclusion === 'Y'
    neeqContent.value = map.get('a171-ch15-neeq-content')?.remark || ''

    const fa = map.get('a171-ch15-fraud-answer')?.conclusion
    if (fa === 'found' || fa === 'none') fraudAnswer.value = fa
    fraudContent.value = map.get('a171-ch15-fraud-content')?.remark || ''

    const la = map.get('a171-ch15-legal-answer')?.conclusion
    if (la === 'found' || la === 'none') legalAnswer.value = la
    legalContent.value = map.get('a171-ch15-legal-content')?.remark || ''

    const ca = map.get('a171-ch15-component-answer')?.conclusion
    if (ca === 'used' || ca === 'na') componentAnswer.value = ca
    componentContent.value = map.get('a171-ch15-component-content')?.remark || ''
  } catch { /* silent */ }
}

// ─── AI Generate ───
async function aiGenerate(key: string) {
  const titles: Record<string, string> = {
    ic1: '内部控制缺陷汇总',
    ic2: '内部控制审计意见类型',
    bond1: '非经营性资产情况',
    bond2: '偿债能力分析',
    bond3: '担保情况分析',
    neeq: '新三板审计特殊核查事项',
    fraud: '舞弊相关情况',
    legal: '违反法律法规情况',
    component: '组成部分审计师利用情况',
  }
  aiLoading.value = key
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 15, chapter_title: titles[key] || '', guidance: '',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    switch (key) {
      case 'ic1': icDeficiencySummary.value = content; break
      case 'ic2': icOpinionType.value = content; break
      case 'bond1': bondNonOperating.value = content; break
      case 'bond2': bondSolvency.value = content; break
      case 'bond3': bondGuarantee.value = content; break
      case 'neeq': neeqContent.value = content; break
      case 'fraud': fraudContent.value = content; break
      case 'legal': legalContent.value = content; break
      case 'component': componentContent.value = content; break
    }
    save()
    ElMessage.success('AI 已生成')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

onMounted(loadData)
</script>

<style scoped>
.gt-ch15 { font-size: 13px; display: flex; flex-direction: column; gap: 12px; }
.gt-ch15__tip { margin-bottom: 4px; }
.gt-ch15__card { margin-top: 4px; }
.gt-ch15__card-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-ch15__card-title { font-size: 13px; font-weight: 600; color: #6b21a8; }
.gt-ch15__sub-items { display: flex; flex-direction: column; gap: 12px; }
.gt-ch15__sub-item { display: flex; flex-direction: column; gap: 4px; }
.gt-ch15__sub-label { font-size: 13px; font-weight: 500; color: #303133; }

.gt-ch15__guidance { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-ch15__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-ch15__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; }

.gt-ch15__textarea-wrap { position: relative; }
.gt-ch15__ai-btn { position: absolute; top: 4px; right: 4px; z-index: 5; opacity: 0.7; }
.gt-ch15__ai-btn:hover { opacity: 1; }
</style>
