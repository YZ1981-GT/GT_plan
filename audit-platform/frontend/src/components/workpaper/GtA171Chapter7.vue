<!--
  GtA171Chapter7.vue — A17-1 第7章「利用专家的工作」结构化组件
  2个子项(利用专家/税务专家)各有适用性 + 征求意见内容说明
  item_id 前缀 a171-ch7-*
-->
<template>
  <div class="gt-ch7">
    <!-- 利用专家工作 -->
    <el-card shadow="never" class="gt-ch7__card">
      <template #header>
        <div class="gt-ch7__card-hd">
          <span class="gt-ch7__card-title">利用专家工作</span>
          <div class="gt-ch7__card-actions">
            <el-switch v-model="expertApplicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
          </div>
        </div>
      </template>
      <template v-if="expertApplicable">
        <div class="gt-ch7__textarea-wrap">
          <el-input v-model="expertContent" type="textarea" :autosize="{minRows:2}" placeholder="说明利用了哪位专家、工作内容、对审计的贡献、注册会计师对专家工作的评估结论。详见S12。" @change="save" />
          <el-button size="small" class="gt-ch7__ai-btn" :loading="aiLoading === 'expert'" @click="aiGenerate('expert')">🤖 AI</el-button>
        </div>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="不适用（本期审计未利用专家工作）。详见S12。" />
    </el-card>

    <!-- 税务专家复核 -->
    <el-card shadow="never" class="gt-ch7__card">
      <template #header>
        <div class="gt-ch7__card-hd">
          <span class="gt-ch7__card-title">税务专家复核</span>
          <div class="gt-ch7__card-actions">
            <el-switch v-model="taxApplicable" size="small" active-text="适用" inactive-text="不适用" @change="save" />
          </div>
        </div>
      </template>
      <template v-if="taxApplicable">
        <div class="gt-ch7__textarea-wrap">
          <el-input v-model="taxContent" type="textarea" :autosize="{minRows:2}" placeholder="说明税务专家复核情况。详见A28。" @change="save" />
          <el-button size="small" class="gt-ch7__ai-btn" :loading="aiLoading === 'tax'" @click="aiGenerate('tax')">🤖 AI</el-button>
        </div>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="不适用。详见A28。" />
    </el-card>

    <!-- 编制提示 -->
    <details class="gt-ch7__guidance">
      <summary>📋 编制提示</summary>
      <div class="gt-ch7__guidance-body">
        根据总体审计策略和具体审计过程中遇到的重大事项，需征求事务所内部（质量控制部、专业技术委员会）和外部专家的专业意见的，应详细说明在对外部专家进行了解的前提下，与之签约情况、咨询事项、咨询结果以及项目组的判评价，并索引至具体记录中。征求专家意见的内容包括但不限于：<br/><br/>
        (1) 对复杂的金融工具、土地及建筑特、厂和机器设备、珠宝、艺术品、古董、无形资产、企业合并中收购的资产和承担的负债，以及可能发生减值的资产；<br/>
        (2) 对保险合同或员工福利计划相关的负债进行精算；<br/>
        (3) 对石油和天然气储量进行估算；<br/>
        (4) 对环境负债和场地清理费用进行估价；<br/>
        (5) 对合同、法律和法规进行解释；<br/>
        (6) 对复杂或异常的纳税问题进行分析；<br/>
        (7) 信息系统内部控制的设计和执行有效性。
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{ wpId: string; projectId: string }>()

const expertApplicable = ref(false)
const expertContent = ref('')
const taxApplicable = ref(false)
const taxContent = ref('')
const aiLoading = ref<string | null>(null)

let _saveTimer: ReturnType<typeof setTimeout> | null = null
function save() {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId) return
  const items: { item_id: string; conclusion: string | null; remark: string | null }[] = [
    { item_id: 'a171-ch7-expert-applicable', conclusion: expertApplicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch7-expert-content', conclusion: null, remark: expertContent.value || null },
    { item_id: 'a171-ch7-tax-applicable', conclusion: taxApplicable.value ? 'Y' : 'N', remark: null },
    { item_id: 'a171-ch7-tax-content', conclusion: null, remark: taxContent.value || null },
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
    for (const r of items) { if (r.item_id?.startsWith('a171-ch7-')) map.set(r.item_id, r) }

    expertApplicable.value = map.get('a171-ch7-expert-applicable')?.conclusion === 'Y'
    expertContent.value = map.get('a171-ch7-expert-content')?.remark || ''
    taxApplicable.value = map.get('a171-ch7-tax-applicable')?.conclusion === 'Y'
    taxContent.value = map.get('a171-ch7-tax-content')?.remark || ''
  } catch { /* silent */ }
}

// ─── AI Generate ───
async function aiGenerate(key: string) {
  const titles: Record<string, string> = { expert: '利用专家工作情况', tax: '税务专家复核情况' }
  const guidances: Record<string, string> = {
    expert: '说明利用了哪位专家、该专家的工作内容、对审计的贡献、注册会计师对专家工作的评估结论。',
    tax: '说明税务专家复核的范围、发现的问题及结论。',
  }
  aiLoading.value = key
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 7, chapter_title: titles[key] || '', guidance: guidances[key] || '',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    if (key === 'expert') { expertContent.value = content; expertApplicable.value = true }
    else if (key === 'tax') { taxContent.value = content; taxApplicable.value = true }
    save()
    ElMessage.success('AI 已生成')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

onMounted(loadData)
</script>

<style scoped>
.gt-ch7 { font-size: var(--wp-font-size, 13px); display: flex; flex-direction: column; gap: 12px; }
.gt-ch7__card { margin-top: 4px; }
.gt-ch7__card-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-ch7__card-actions { display: flex; align-items: center; gap: 8px; }
.gt-ch7__card-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #6b21a8; }
.gt-ch7__textarea-wrap { position: relative; }
.gt-ch7__ai-btn { position: absolute; top: 4px; right: 4px; z-index: 5; opacity: 0.7; }
.gt-ch7__ai-btn:hover { opacity: 1; }
.gt-ch7__guidance { margin-top: 4px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-ch7__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-ch7__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; }
</style>
