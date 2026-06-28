<!--
  GtA171Chapter4.vue — A17-1 第4章「审计过程中合伙人已关注的事项」结构化组件
  6个子节独立适用性+内容，item_id 前缀 a171-ch4-*
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
      <template v-if="s1HasRisk">
        <p class="gt-ch4__hint">说明识别的特别风险及应对情况（参见B50风险评估矩阵）</p>
        <el-input v-model="s1Content" type="textarea" :autosize="{minRows:3}" placeholder="描述识别的特别风险及对应的审计应对措施" @change="save" />
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
        <!-- 1.已更正错报 -->
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">1、已更正错报汇总及评价</div>
          <el-input v-model="s2Corrected" type="textarea" :autosize="{minRows:2}" placeholder="详见A2-2、A2-3（可补充说明）" @change="save" />
        </div>
        <!-- 2.未更正错报 -->
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">2、未更正错报汇总及评价</div>
          <el-input v-model="s2Uncorrected" type="textarea" :autosize="{minRows:2}" placeholder="详见A13-1（可补充说明）" @change="save" />
        </div>
        <!-- 3.披露不足 -->
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">3、披露不足事项汇总</div>
          <el-input v-model="s2Disclosure" type="textarea" :autosize="{minRows:2}" placeholder="无披露不足事项 / 列明具体事项" @change="save" />
        </div>
        <!-- 4.沟通 -->
        <div class="gt-ch4__sub-item">
          <div class="gt-ch4__sub-label">4、与管理层和治理层的沟通</div>
          <el-input v-model="s2Communication" type="textarea" :autosize="{minRows:2}" placeholder="详见A10-1; A10-2（可补充说明）" @change="save" />
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
      <template v-if="s3HasDeficiency">
        <p class="gt-ch4__hint">详见B22B内控缺陷评价表、A9-1/A9-2缺陷沟通函</p>
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
      <template v-if="s4HasJudgment">
        <el-input v-model="s4Content" type="textarea" :autosize="{minRows:3}" placeholder="描述涉及的重大职业判断事项及结论" @change="save" />
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期审计未涉及需特别说明的重大职业判断事项。" />
    </el-card>

    <!-- (五) 导致注册会计师难以实施必要审计程序的情形 -->
    <el-card shadow="never" class="gt-ch4__card">
      <template #header>
        <div class="gt-ch4__card-hd">
          <span class="gt-ch4__card-title">（五）难以实施必要审计程序的情形</span>
          <div class="gt-ch4__card-actions">
            <el-switch v-model="s5HasDifficulty" size="small" active-text="有" inactive-text="无" @change="save" />
            <el-button size="small" :loading="aiLoading === 5" @click="aiGenerate(5)">🤖 AI</el-button>
          </div>
        </div>
      </template>
      <template v-if="s5HasDifficulty">
        <el-input v-model="s5Content" type="textarea" :autosize="{minRows:3}" placeholder="描述导致难以实施必要审计程序的具体情形及替代程序" @change="save" />
      </template>
      <el-alert v-else type="success" :closable="false" show-icon title="本期审计未遇到导致难以实施必要审计程序的情形。" />
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

const props = defineProps<{ wpId: string; projectId: string }>()

// ─── State ───
const s1HasRisk = ref(false)
const s1Content = ref('')
const s2Corrected = ref('详见A2-2、A2-3')
const s2Uncorrected = ref('详见A13-1')
const s2Disclosure = ref('')
const s2Communication = ref('详见A10-1; A10-2')
const s3HasDeficiency = ref(false)
const s3Content = ref('')
const s4HasJudgment = ref(false)
const s4Content = ref('')
const s5HasDifficulty = ref(false)
const s5Content = ref('')
const s6HasModification = ref(false)
const s6Content = ref('')
const aiLoading = ref<number | null>(null)

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
    { item_id: 'a171-ch4-s1-content', conclusion: null, remark: s1Content.value || null },
    { item_id: 'a171-ch4-s2-corrected', conclusion: null, remark: s2Corrected.value || null },
    { item_id: 'a171-ch4-s2-uncorrected', conclusion: null, remark: s2Uncorrected.value || null },
    { item_id: 'a171-ch4-s2-disclosure', conclusion: null, remark: s2Disclosure.value || null },
    { item_id: 'a171-ch4-s2-communication', conclusion: null, remark: s2Communication.value || null },
    { item_id: 'a171-ch4-s3-hasdeficiency', conclusion: s3HasDeficiency.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s3-content', conclusion: null, remark: s3Content.value || null },
    { item_id: 'a171-ch4-s4-hasjudgment', conclusion: s4HasJudgment.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s4-content', conclusion: null, remark: s4Content.value || null },
    { item_id: 'a171-ch4-s5-hasdifficulty', conclusion: s5HasDifficulty.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch4-s5-content', conclusion: null, remark: s5Content.value || null },
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
    s1Content.value = map.get('a171-ch4-s1-content')?.remark || ''
    s2Corrected.value = map.get('a171-ch4-s2-corrected')?.remark || '详见A2-2、A2-3'
    s2Uncorrected.value = map.get('a171-ch4-s2-uncorrected')?.remark || '详见A13-1'
    s2Disclosure.value = map.get('a171-ch4-s2-disclosure')?.remark || ''
    s2Communication.value = map.get('a171-ch4-s2-communication')?.remark || '详见A10-1; A10-2'
    s3HasDeficiency.value = map.get('a171-ch4-s3-hasdeficiency')?.conclusion === 'Y'
    s3Content.value = map.get('a171-ch4-s3-content')?.remark || ''
    s4HasJudgment.value = map.get('a171-ch4-s4-hasjudgment')?.conclusion === 'Y'
    s4Content.value = map.get('a171-ch4-s4-content')?.remark || ''
    s5HasDifficulty.value = map.get('a171-ch4-s5-hasdifficulty')?.conclusion === 'Y'
    s5Content.value = map.get('a171-ch4-s5-content')?.remark || ''
    s6HasModification.value = map.get('a171-ch4-s6-hasmodification')?.conclusion === 'Y'
    s6Content.value = map.get('a171-ch4-s6-content')?.remark || ''
  } catch { /* silent */ }
}

// ─── AI ───
async function aiGenerate(section: number) {
  const titles: Record<number, string> = {
    1: '特别风险及应对情况',
    2: '已更正或未更正错报的评价',
    3: '值得关注的内控缺陷',
    4: '重大职业判断事项',
    5: '难以实施必要审计程序的情形',
    6: '可能导致出具非无保留意见审计报告的事项',
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
      case 1: s1Content.value = content; s1HasRisk.value = true; break
      case 2: s2Corrected.value = content; break
      case 3: s3Content.value = content; s3HasDeficiency.value = true; break
      case 4: s4Content.value = content; s4HasJudgment.value = true; break
      case 5: s5Content.value = content; s5HasDifficulty.value = true; break
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
.gt-ch4__hint { font-size: 12px; color: #909399; margin: 0 0 8px; }
.gt-ch4__sub-items { display: flex; flex-direction: column; gap: 12px; }
.gt-ch4__sub-item { display: flex; flex-direction: column; gap: 4px; }
.gt-ch4__sub-label { font-size: 13px; font-weight: 500; color: #606266; }
</style>
