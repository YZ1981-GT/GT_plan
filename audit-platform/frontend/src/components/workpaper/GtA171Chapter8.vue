<!--
  GtA171Chapter8.vue — A17-1 第8章「已审财务报表分析」结构化组件
  自动从分析性复核(A1-13/A1-14)取数展示显著变动项+手动补充
  3个子节：(一)已审财务报表分析 (二)同行业对比 (三)财务与非财务印证
  item_id 前缀 a171-ch8-*
-->
<template>
  <div class="gt-ch8">
    <!-- 自动取数摘要 -->
    <el-card shadow="never" class="gt-ch8__card gt-ch8__card--auto">
      <template #header>
        <div class="gt-ch8__card-hd">
          <span class="gt-ch8__card-title">📊 报表变动自动分析（取自 A1-13/A1-14）</span>
          <el-button size="small" :loading="autoLoading" @click="loadAutoData">刷新取数</el-button>
        </div>
      </template>
      <div v-if="autoLoading" class="gt-ch8__loading">加载中...</div>
      <div v-else-if="significantItems.length > 0" class="gt-ch8__auto-results">
        <div class="gt-ch8__stat-row">
          <el-tag type="danger" size="small">显著变动 {{ significantCount }} 项</el-tag>
          <el-tag type="warning" size="small">关注 {{ attentionCount }} 项</el-tag>
          <el-tag size="small">重要性水平 {{ materialityDisplay }}</el-tag>
        </div>
        <el-table :data="significantItems" border size="small" class="gt-ch8__table" max-height="300">
          <el-table-column label="报表" width="70" prop="sheet" />
          <el-table-column label="项目" min-width="120" prop="name" />
          <el-table-column label="上年审定数" width="110" prop="prior" align="right" />
          <el-table-column label="本年审定数" width="110" prop="current" align="right" />
          <el-table-column label="变动%" width="80" align="right">
            <template #default="{ row }">
              <span :class="{'gt-ch8__red': Math.abs(row.pct) >= 30}">{{ row.pct !== null ? row.pct.toFixed(1) + '%' : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="70">
            <template #default="{ row }">
              <el-tag :type="row.status === 'significant' ? 'danger' : 'warning'" size="small">{{ row.status === 'significant' ? '显著' : '关注' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <el-alert v-else type="info" :closable="false" show-icon title="暂无自动分析数据（项目内A1-13/A1-14底稿尚未生成或无数据）" />
    </el-card>

    <!-- (一) 已审财务报表分析 -->
    <el-card shadow="never" class="gt-ch8__card">
      <template #header>
        <div class="gt-ch8__card-hd">
          <span class="gt-ch8__card-title">（一）已审财务报表分析</span>
          <el-button size="small" :loading="aiLoading === 1" @click="aiGenerate(1)">🤖 AI</el-button>
        </div>
      </template>
      <details class="gt-ch8__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch8__guidance-body">
          1、财务报表数据：对于金额异常或年度间变动异常的报表项目（如两个期间的数据变动幅度达30%以上或超过执行重要性水平，或占公司报表日资产总额5%或报告期利润总额10%以上的），非会计准则指定的报表项目、名称反映不出其性质或内容的报表项目，应当说明该项目的具体情况及变动原因。<br/><br/>
          对于上述报表项目的变动情况，应结合风险评估和计划阶段评估出的重大错报风险、拟实施的审计程序，逐项说明已经实施的审计程序和审计结论。（注：和本小结第八项重复的，可以索引）<br/><br/>
          2、财务指标：对财务指标进行分析，如：上市公司基本指标（每股收益、每股净资产、每股经营活动产生的现金流量净额）；盈利能力指标（净资产收益率、总资产净利润、销售净利率、销售毛利率、期间费用净利率）；营运能力指标（资产负债率、存货周转率、应收账款周转率）；偿债能力指标（流动比率、速动比率等）。
        </div>
      </details>
      <el-input v-model="s1Content" type="textarea" :autosize="{minRows:4}" placeholder="结合自动取数结果，分析报表重大变动项目的原因及审计结论" @change="save" />
    </el-card>

    <!-- (二) 同行业公司对比分析 -->
    <el-card shadow="never" class="gt-ch8__card">
      <template #header>
        <div class="gt-ch8__card-hd">
          <span class="gt-ch8__card-title">（二）同行业公司对比分析</span>
          <el-button size="small" :loading="aiLoading === 2" @click="aiGenerate(2)">🤖 AI</el-button>
        </div>
      </template>
      <details class="gt-ch8__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch8__guidance-body">
          列表并描述重要财务指标（如净资产收益率、毛利率、存货周转率、应收账款周转率、销售费用率、管理费用率等）与3-5家同行业可比公司的对比分析。若存在数据、趋势的不一致，分析原因及其合理性。
        </div>
      </details>
      <el-input v-model="s2Content" type="textarea" :autosize="{minRows:3}" placeholder="与同行业可比公司的财务指标对比分析" @change="save" />
    </el-card>

    <!-- (三) 财务与非财务信息印证 -->
    <el-card shadow="never" class="gt-ch8__card">
      <template #header>
        <div class="gt-ch8__card-hd">
          <span class="gt-ch8__card-title">（三）财务与非财务信息印证</span>
          <el-button size="small" :loading="aiLoading === 3" @click="aiGenerate(3)">🤖 AI</el-button>
        </div>
      </template>
      <details class="gt-ch8__guidance">
        <summary>📋 编制提示</summary>
        <div class="gt-ch8__guidance-body">
          1、整体经营情况与财务数据的一致性：结合一，分析公司整体经营情况与营业收入、营业成本、管理费用、销售费用等财务数据的一致性。<br/>
          2、财务与非财务信息的印证：分析已审报表与公司招股说明书、法律意见书中相关信息的一致性；其他非财务信息与财务信息的一致性，如公司的水、电、煤消耗量变动情况及一线生产员工人数的变动情况与产量的变动情况是否匹配。<br/>
          3、关注财务异常信息：分析公司会计政策、会计估计的一致性、与同行业的可比性；财务数据异常变动原因及合理性分析；财务指标与同行业其他公司对比分析；公司人工成本、固定资产和在建工程余额、变动的合理性分析。
        </div>
      </details>
      <el-input v-model="s3Content" type="textarea" :autosize="{minRows:3}" placeholder="财务与非财务信息印证分析" @change="save" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface SignificantItem { sheet: string; name: string; prior: string; current: string; pct: number | null; status: string }

const props = defineProps<{ wpId: string; projectId: string }>()

// ─── Auto data from A1-13/A1-14 ───
const autoLoading = ref(false)
const significantItems = ref<SignificantItem[]>([])
const significantCount = ref(0)
const attentionCount = ref(0)
const materialityDisplay = ref('—')

// ─── Manual content ───
const s1Content = ref('')
const s2Content = ref('')
const s3Content = ref('')
const aiLoading = ref<number | null>(null)

// ─── Load auto analytical data ───
async function loadAutoData() {
  if (!props.projectId) return
  autoLoading.value = true
  try {
    // 从 projectId 推断年份(后端auto-data端点要求year参数)
    const yearParam = new Date().getFullYear()
    const res = await api.get<any>(
      `/api/projects/${props.projectId}/auto-data/a17_ch08_analytical_review`,
      { params: { year: yearParam }, _silent: true } as any,
    )
    const data = res?.data ?? res
    if (data?.items && Array.isArray(data.items)) {
      significantItems.value = data.items
      significantCount.value = data.significant_count ?? 0
      attentionCount.value = data.attention_count ?? 0
      materialityDisplay.value = data.materiality ? `${Number(data.materiality).toLocaleString()} 元` : '—'
    } else if (data?.summary) {
      // Fallback: parse from summary text
      significantItems.value = []
      significantCount.value = 0
      attentionCount.value = 0
    }
  } catch { /* silent */ }
  finally { autoLoading.value = false }
}

// ─── Persistence ───
let _saveTimer: ReturnType<typeof setTimeout> | null = null
function save() {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId) return
  const items: { item_id: string; conclusion: string | null; remark: string | null }[] = [
    { item_id: 'a171-ch8-s1-content', conclusion: null, remark: s1Content.value || null },
    { item_id: 'a171-ch8-s2-content', conclusion: null, remark: s2Content.value || null },
    { item_id: 'a171-ch8-s3-content', conclusion: null, remark: s3Content.value || null },
  ]
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, { project_id: props.projectId || undefined, items })
  } catch { /* silent */ }
}

// ─── Load saved data ───
async function loadData() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items = Array.isArray(res) ? res : (res as any)?.data || []
    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const r of items) { if (r.item_id?.startsWith('a171-ch8-')) map.set(r.item_id, r) }
    s1Content.value = map.get('a171-ch8-s1-content')?.remark || ''
    s2Content.value = map.get('a171-ch8-s2-content')?.remark || ''
    s3Content.value = map.get('a171-ch8-s3-content')?.remark || ''
  } catch { /* silent */ }
}

// ─── AI ───
async function aiGenerate(section: number) {
  const titles: Record<number, string> = {
    1: '已审财务报表分析（结合变动数据）',
    2: '同行业公司对比分析',
    3: '财务与非财务信息印证',
  }
  const guidances: Record<number, string> = {
    1: '根据A1-13/A1-14分析性复核数据，对变动幅度超30%或超重要性水平的报表项目逐项分析原因，说明已执行的审计程序和结论。同时分析关键财务指标（流动比率、资产负债率、净资产收益率、毛利率、周转率等）。',
    2: '列示被审计单位关键财务指标与同行业3-5家可比公司的对比，分析差异原因及合理性。',
    3: '分析公司整体经营情况与财务数据的一致性；财务与非财务信息（水电煤耗量、产量、员工人数）的匹配性；关注会计政策/估计一致性、异常变动、人工成本/固定资产/在建工程合理性。',
  }
  aiLoading.value = section
  try {
    // Build context: pass auto data as existing_content for section 1
    let existingContent = ''
    if (section === 1 && significantItems.value.length > 0) {
      const lines = significantItems.value.slice(0, 20).map(
        r => `${r.sheet} ${r.name}: 上年${r.prior}→本年${r.current} 变动${r.pct !== null ? r.pct.toFixed(1) + '%' : '—'} [${r.status}]`
      )
      existingContent = `自动取数结果（显著${significantCount.value}项/关注${attentionCount.value}项）：\n${lines.join('\n')}`
    }
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 8, chapter_title: titles[section] || '', guidance: guidances[section] || '',
      existing_content: existingContent, knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    switch (section) {
      case 1: s1Content.value = content; break
      case 2: s2Content.value = content; break
      case 3: s3Content.value = content; break
    }
    save()
    ElMessage.success('AI 已生成')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

onMounted(() => { loadData(); loadAutoData() })
</script>

<style scoped>
.gt-ch8 { font-size: var(--wp-font-size, 13px); display: flex; flex-direction: column; gap: 12px; }
.gt-ch8__card { margin-top: 4px; }
.gt-ch8__card--auto { border-color: #e6f0ff; }
.gt-ch8__card-hd { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-ch8__card-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #6b21a8; }
.gt-ch8__loading { text-align: center; padding: 20px; color: #909399; }
.gt-ch8__stat-row { display: flex; gap: 8px; margin-bottom: 8px; }
.gt-ch8__table { font-size: 12px; }
.gt-ch8__red { color: #f56c6c; font-weight: 500; }

/* 编制提示 */
.gt-ch8__guidance { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-ch8__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-ch8__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; white-space: pre-wrap; }
</style>
