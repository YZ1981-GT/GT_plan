<!--
  GtA171Chapter15.vue — A17-1 第15章「其他特殊考虑事项」结构化组件
  3个子节(A舞弊/B违法/C组成部分)独立Y/N/NA适用性+编制提示
  item_id 前缀 a171-ch15-*
-->
<template>
  <div class="gt-ch15">
    <!-- A. 舞弊相关 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">A. 舞弊相关</span>
          <div class="gt-ch15__card-actions">
            <el-radio-group v-model="sAAnswer" size="small" @change="save">
              <el-radio-button value="none">未发现</el-radio-button>
              <el-radio-button value="found">有发现</el-radio-button>
            </el-radio-group>
            <el-button size="small" :loading="aiLoading === 'A'" @click="aiGenerate('A')">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch15__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch15__guidance-body">
          如识别出舞弊或获取的信息表明可能存在舞弊，应当及时向项目合伙人报告。<br/>
          需考虑：是否存在管理层凌驾控制的迹象；收入确认是否存在舞弊风险；<br/>
          日记账分录测试是否发现异常；关联方交易是否存在舞弊迹象。<br/>
          如发现舞弊，说明舞弊的性质、涉及金额、已采取的应对措施及对审计意见的影响。
        </div>
      </details>
      <template v-if="sAAnswer === 'found'">
        <el-input v-model="sAContent" type="textarea" :autosize="{minRows:3}" placeholder="描述发现的舞弊或舞弊迹象及处理措施" @change="save" />
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期审计未发现舞弊或舞弊迹象。" />
    </el-card>

    <!-- B. 违反法律法规情况 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">B. 违反法律法规情况</span>
          <div class="gt-ch15__card-actions">
            <el-radio-group v-model="sBAnswer" size="small" @change="save">
              <el-radio-button value="none">未发现</el-radio-button>
              <el-radio-button value="found">有发现</el-radio-button>
            </el-radio-group>
            <el-button size="small" :loading="aiLoading === 'B'" @click="aiGenerate('B')">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch15__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch15__guidance-body">
          需关注被审计单位是否存在违反《公司法》《证券法》《税法》等法律法规的行为。<br/>
          特别关注：重大税务处罚、环保违规、行政处罚、诉讼纠纷等对财务报表可能产生重大影响的事项。<br/>
          如发现违法违规行为，评估其对财务报表的影响，以及是否需要在审计报告中反映。
        </div>
      </details>
      <template v-if="sBAnswer === 'found'">
        <el-input v-model="sBContent" type="textarea" :autosize="{minRows:3}" placeholder="描述发现的违反法律法规行为及影响评估" @change="save" />
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="未发现被审计单位存在重大违反法律法规的行为。" />
    </el-card>

    <!-- C. 组成部分审计师的利用 -->
    <el-card shadow="never" class="gt-ch15__card">
      <template #header>
        <div class="gt-ch15__card-hd">
          <span class="gt-ch15__card-title">C. 组成部分审计师的利用</span>
          <div class="gt-ch15__card-actions">
            <el-radio-group v-model="sCAnswer" size="small" @change="save">
              <el-radio-button value="na">不适用</el-radio-button>
              <el-radio-button value="used">已利用</el-radio-button>
            </el-radio-group>
            <el-button size="small" :loading="aiLoading === 'C'" @click="aiGenerate('C')">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <details class="gt-ch15__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch15__guidance-body">
          如利用组成部分审计师的工作，需说明：<br/>
          (1) 组成部分审计师的名称及负责的审计范围；<br/>
          (2) 对组成部分审计师的独立性和专业胜任能力的评价；<br/>
          (3) 与组成部分审计师的沟通安排（包括审计计划、时间要求、重要性水平）；<br/>
          (4) 对组成部分审计师工作的复核程序及结论；<br/>
          (5) 是否存在需要集团项目组额外执行程序的情况（参见B30集团审计范围）。
        </div>
      </details>
      <template v-if="sCAnswer === 'used'">
        <el-input v-model="sCContent" type="textarea" :autosize="{minRows:3}" placeholder="描述组成部分审计师名称、负责范围、沟通及复核安排" @change="save" />
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

const sAAnswer = ref<'none' | 'found'>('none')
const sAContent = ref('')
const sBAnswer = ref<'none' | 'found'>('none')
const sBContent = ref('')
const sCAnswer = ref<'na' | 'used'>('na')
const sCContent = ref('')
const aiLoading = ref<string | null>(null)

let _saveTimer: ReturnType<typeof setTimeout> | null = null
function save() {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId) return
  const items: { item_id: string; conclusion: string | null; remark: string | null }[] = [
    { item_id: 'a171-ch15-a-answer', conclusion: sAAnswer.value, remark: null },
    { item_id: 'a171-ch15-a-content', conclusion: null, remark: sAContent.value || null },
    { item_id: 'a171-ch15-b-answer', conclusion: sBAnswer.value, remark: null },
    { item_id: 'a171-ch15-b-content', conclusion: null, remark: sBContent.value || null },
    { item_id: 'a171-ch15-c-answer', conclusion: sCAnswer.value, remark: null },
    { item_id: 'a171-ch15-c-content', conclusion: null, remark: sCContent.value || null },
  ]
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, { project_id: props.projectId || undefined, items })
  } catch { /* silent */ }
}

async function loadData() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items = Array.isArray(res) ? res : (res as any)?.data || []
    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const r of items) { if (r.item_id?.startsWith('a171-ch15-')) map.set(r.item_id, r) }

    const aAns = map.get('a171-ch15-a-answer')?.conclusion
    if (aAns === 'found' || aAns === 'none') sAAnswer.value = aAns
    sAContent.value = map.get('a171-ch15-a-content')?.remark || ''

    const bAns = map.get('a171-ch15-b-answer')?.conclusion
    if (bAns === 'found' || bAns === 'none') sBAnswer.value = bAns
    sBContent.value = map.get('a171-ch15-b-content')?.remark || ''

    const cAns = map.get('a171-ch15-c-answer')?.conclusion
    if (cAns === 'used' || cAns === 'na') sCAnswer.value = cAns
    sCContent.value = map.get('a171-ch15-c-content')?.remark || ''
  } catch { /* silent */ }
}

async function aiGenerate(section: string) {
  const titles: Record<string, string> = {
    A: '舞弊相关特殊考虑事项', B: '违反法律法规情况', C: '组成部分审计师的利用情况',
  }
  aiLoading.value = section
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 15, chapter_title: titles[section] || '', guidance: '',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    switch (section) {
      case 'A': sAContent.value = content; sAAnswer.value = 'found'; break
      case 'B': sBContent.value = content; sBAnswer.value = 'found'; break
      case 'C': sCContent.value = content; sCAnswer.value = 'used'; break
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
.gt-ch15__card { margin-top: 4px; }
.gt-ch15__card-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-ch15__card-actions { display: flex; align-items: center; gap: 8px; }
.gt-ch15__card-title { font-size: 13px; font-weight: 600; color: #6b21a8; }

/* 编制提示折叠区 */
.gt-ch15__guidance { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-ch15__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-ch15__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; white-space: pre-wrap; }
</style>
