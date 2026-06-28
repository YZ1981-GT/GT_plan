<!--
  GtA171Chapter15.vue — A17-1 第15章「其他特殊考虑事项」结构化组件
  3个子节(A舞弊/B违法/C组成部分)独立Y/N/NA适用性，item_id 前缀 a171-ch15-*
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
      <template v-if="sCAnswer === 'used'">
        <p class="gt-ch15__hint">说明利用组成部分审计师工作的情况（参见B30集团审计范围）</p>
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

// ─── State ───
const sAAnswer = ref<'none' | 'found'>('none')
const sAContent = ref('')
const sBAnswer = ref<'none' | 'found'>('none')
const sBContent = ref('')
const sCAnswer = ref<'na' | 'used'>('na')
const sCContent = ref('')
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

// ─── Load ───
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

// ─── AI ───
async function aiGenerate(section: string) {
  const titles: Record<string, string> = {
    A: '舞弊相关特殊考虑事项',
    B: '违反法律法规情况',
    C: '组成部分审计师的利用情况',
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
.gt-ch15__hint { font-size: 12px; color: #909399; margin: 0 0 8px; }
</style>
