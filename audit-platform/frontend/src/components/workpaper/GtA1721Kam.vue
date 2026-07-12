<!--
  GtA1721Kam.vue — A17-2-1 关键审计事项(KAM)

  el-segmented 双模式 + Section 四 适用性开关(顶部) +
  Section 一 候选清单 el-table(4列+动态行+communicate高亮) +
  Section 二 KAM 详情卡片(el-card × N, 6 textarea + GtIndexChip + 删除确认) +
  Section 三 附注披露(per KAM textarea) + GtOnlyOfficeSheet
-->
<template>
  <div class="gt-a1721">
    <!-- Toolbar -->
    <div class="gt-a1721__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a1721__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a1721__content">

      <!-- Section 四: 适用性 (at TOP) -->
      <el-card shadow="never" class="gt-a1721__section gt-a1721__applicability">
        <template #header>
          <span class="gt-a1721__section-title">四、适用性</span>
        </template>
        <div class="gt-a1721__switch-row">
          <el-switch
            :model-value="applicability.noKam"
            active-text="不存在/不沟通关键审计事项"
            @change="(v: boolean) => toggleApplicability(v)"
          />
        </div>
        <div v-if="applicability.noKam" class="gt-a1721__reason-wrap">
          <el-input
            :model-value="applicability.reason || ''"
            type="textarea"
            :autosize="{ minRows: 3 }"
            placeholder="请说明不存在/不沟通关键审计事项的原因"
            @change="(v: string) => setApplicabilityReason(v)"
          />
        </div>
      </el-card>

      <!-- Sections 一/二/三: hidden when noKam = true -->
      <template v-if="!applicability.noKam">

        <!-- Section 一: KAM 候选清单 -->
        <el-card shadow="never" class="gt-a1721__section gt-a1721__candidates">
          <template #header>
            <div class="gt-a1721__section-header">
              <span class="gt-a1721__section-title">一、识别关键审计事项</span>
              <div class="gt-a1721__section-actions">
                <el-button size="small" :loading="aiLoading === 'candidates'" @click="aiGenerateCandidates">🤖 AI</el-button>
                <el-button type="primary" size="small" plain @click="addCandidate">+ 添加候选</el-button>
              </div>
            </div>
          </template>
          <details class="gt-a1721__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a1721__guidance-body">
              对于"重大事项概要汇总"（A17-1）底稿的四（一）至（五）中记录的需合伙人关注事项，如果未识别为需沟通的关键审计事项，需在本底稿中记录判断理由。<br/><br/>
              候选事项按4类分组填列：<br/>
              <b>(一) 评估的重大错报风险较高的领域或识别出的特别风险</b><br/>
              <span style="color:#909399">示例：收入确认的准确性（计算收入时，参数的选取及系统处理的准确性、及时性将对收入金额产生重要影响）；固定资产减值准备的计提（采用收益法测算，结果具有高度不确定性）</span><br/><br/>
              <b>(二) 涉及重大管理层判断（包括具有高度估计不确定性的会计估计）的领域</b><br/>
              <span style="color:#909399">示例：第三层次公允价值计量的金融资产的估值（金额重大且涉及复杂的估值模型）；开发支出资本化（确定是否满足所有资本化条件需要管理层进行重大会计判断和估计）</span><br/><br/>
              <b>(三) 本期重大交易或事项对审计的影响</b><br/>
              <span style="color:#909399">示例：对外投资的结构化主体纳入合并范围的判断（重大投资活动会对合并范围产生重大影响）；非同一控制下收购子公司（收购日公允价值确定、商誉计算、控制权分析）；在一段时间内确认的工程收入（完工百分比法时，履约进度及预计总成本主要依赖管理层的重大估计和判断）</span><br/><br/>
              <b>(四) 其他</b><br/>
              <span style="color:#909399">示例：合同负债列报的重大错报（重大错报已经更正，且该账户并非财务报表使用者重点关注的领域）；对境外子公司审计程序受限（审计范围受限情形影响审计意见类型）</span>
            </div>
          </details>
          <el-table
            :data="candidates"
            border
            size="small"
            class="gt-a1721__candidate-table"
            :row-class-name="candidateRowClassName"
          >
            <el-table-column label="序号" width="60" align="center">
              <template #default="{ $index }">{{ $index + 1 }}</template>
            </el-table-column>
            <el-table-column label="事项描述" min-width="200">
              <template #default="{ row, $index }">
                <el-input
                  :model-value="row.description"
                  size="small"
                  placeholder="如：收入确认的准确性 / 商誉减值测试"
                  @change="(v: string) => updateCandidate($index, 'description', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="风险等级" width="100">
              <template #default="{ row, $index }">
                <el-select
                  :model-value="row.risk_level"
                  size="small"
                  placeholder="选择"
                  @change="(v: string) => updateCandidate($index, 'risk_level', v)"
                >
                  <el-option label="高" value="高" />
                  <el-option label="中" value="中" />
                  <el-option label="低" value="低" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="沟通记录索引" width="110">
              <template #default="{ row, $index }">
                <el-input
                  :model-value="row.ref_index || ''"
                  size="small"
                  placeholder="如A10-1"
                  @change="(v: string) => updateCandidate($index, 'ref_index', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="是否重点关注" width="100" align="center">
              <template #default="{ row, $index }">
                <el-select
                  :model-value="row.is_focus || ''"
                  size="small"
                  @change="(v: string) => updateCandidate($index, 'is_focus', v)"
                >
                  <el-option label="是" value="Y" />
                  <el-option label="否" value="N" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="是否确定为KAM" width="90" align="center">
              <template #default="{ row, $index }">
                <el-select
                  :model-value="row.communicate"
                  size="small"
                  @change="(v: string) => updateCandidate($index, 'communicate', v)"
                >
                  <el-option label="是" value="Y" />
                  <el-option label="否" value="N" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="判断的原因和理据" min-width="160">
              <template #default="{ row, $index }">
                <el-input
                  :model-value="row.reason"
                  size="small"
                  placeholder="判断的原因和理据"
                  @change="(v: string) => updateCandidate($index, 'reason', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60" align="center">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeCandidate($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- Section 二: KAM 详情卡片 -->
        <div class="gt-a1721__section gt-a1721__kam-cards">
          <div class="gt-a1721__section-header">
            <span class="gt-a1721__section-title">二、在审计报告中沟通的关键审计事项</span>
            <div class="gt-a1721__section-actions">
              <el-button size="small" :loading="aiLoading === 'kam'" @click="aiGenerateKam">🤖 AI</el-button>
              <el-button type="primary" size="small" plain @click="addKam">+ 添加关键审计事项</el-button>
            </div>
          </div>
          <details class="gt-a1721__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a1721__guidance-body">
              注1：建议分别描述①基本情况②相关会计政策③认定的原因；<br/>
              注2：建议依次描述①了解、评估并测试关键内部控制②了解和评估相关会计政策、实质性程序等③实施审计程序的结果（需要避免使预期使用者认为这种描述是针对单一关键审计事项发表单独的意见，也需要避免使预期使用者对财务报表整体的审计意见产生疑问）；<br/>
              注3：底稿索引，含内部控制、实质性程序及与治理层沟通等。<br/><br/>
              在审计报告中描述一项关键审计事项在审计中如何应对时，描述的详细程度属于职业判断。根据CSA 1504第十三条第（二）项的要求，注册会计师<b>可以</b>描述下列要素：(1)审计应对措施或审计方案中，与该事项最为相关或对评估的重大错报风险最有针对性的方面；(2)对已实施审计程序的简要概述；(3)实施审计程序的结果；(4)对该事项的主要看法。<br/><br/>
              注册会计师可能需要注意用于描述关键审计事项的语言，使之：(1)不暗示注册会计师在对财务报表形成审计意见时尚未恰当解决该事项；(2)将该事项直接联系到被审计单位的具体情况，避免使用一般化或标准化的语言；(3)能够体现出对该事项在相关财务报表披露（如有）中如何应对的考虑；(4)不对财务报表单一要素单独发表意见，也不暗示是对财务报表单一要素单独发表意见。
            </div>
          </details>

          <el-card
            v-for="(kam, idx) in kams"
            :key="idx"
            shadow="hover"
            class="gt-a1721__kam-card"
          >
            <template #header>
              <div class="gt-a1721__kam-card-header">
                <span class="gt-a1721__kam-card-title">关键审计事项 {{ idx + 1 }}</span>
                <el-popconfirm
                  title="确定删除该关键审计事项？"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="removeKam(idx)"
                >
                  <template #reference>
                    <el-button type="danger" size="small" link>删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>

            <div class="gt-a1721__kam-fields">
              <div class="gt-a1721__kam-field">
                <label class="gt-a1721__kam-label">基本情况</label>
                <el-input
                  :model-value="kam.basic"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="描述关键审计事项的基本情况"
                  @change="(v: string) => updateKamField(idx, 'basic', v)"
                />
              </div>
              <div class="gt-a1721__kam-field">
                <label class="gt-a1721__kam-label">会计政策及重大会计估计</label>
                <el-input
                  :model-value="kam.policy"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="相关会计政策及重大会计估计"
                  @change="(v: string) => updateKamField(idx, 'policy', v)"
                />
              </div>
              <div class="gt-a1721__kam-field">
                <label class="gt-a1721__kam-label">认定为关键审计事项的原因</label>
                <el-input
                  :model-value="kam.reason"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="认定为关键审计事项的原因"
                  @change="(v: string) => updateKamField(idx, 'reason', v)"
                />
              </div>
              <div class="gt-a1721__kam-field">
                <label class="gt-a1721__kam-label">审计应对措施</label>
                <el-input
                  :model-value="kam.response"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="针对该关键审计事项的审计应对措施"
                  @change="(v: string) => updateKamField(idx, 'response', v)"
                />
              </div>
              <div class="gt-a1721__kam-field">
                <label class="gt-a1721__kam-label">审计结果</label>
                <el-input
                  :model-value="kam.result"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="审计结果及结论"
                  @change="(v: string) => updateKamField(idx, 'result', v)"
                />
              </div>
              <div class="gt-a1721__kam-field">
                <label class="gt-a1721__kam-label">底稿索引号</label>
                <GtIndexChip
                  v-if="kam.ref_index"
                  :value="kam.ref_index"
                />
                <el-input
                  :model-value="kam.ref_index"
                  size="small"
                  placeholder="输入底稿索引号（如 D2-1）"
                  @change="(v: string) => updateKamField(idx, 'ref_index', v)"
                />
              </div>
              <div class="gt-a1721__kam-field">
                <label class="gt-a1721__kam-label">财务报表附注索引号</label>
                <el-input
                  :model-value="kam.note_index || ''"
                  size="small"
                  placeholder="如：财务报表附注 五、20"
                  @change="(v: string) => updateKamField(idx, 'note_index', v)"
                />
              </div>
            </div>
          </el-card>

          <el-empty v-if="kams.length === 0" description="暂无关键审计事项，点击上方按钮添加" />
        </div>

        <!-- Section 三: 附注披露 -->
        <el-card shadow="never" class="gt-a1721__section gt-a1721__notes">
          <template #header>
            <span class="gt-a1721__section-title">三、被审计单位财务报表附注的相关披露</span>
          </template>
          <details class="gt-a1721__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a1721__guidance-body">
              针对每个关键审计事项，分别描述：<br/>
              1、会计政策及会计估计<br/>
              2、报表附注披露（如项目注释、关联方及关联交易、其他重要事项等）
            </div>
          </details>
          <div v-if="notes.length === 0" class="gt-a1721__notes-empty">
            请先在第二节添加关键审计事项
          </div>
          <div
            v-for="(note, idx) in notes"
            :key="idx"
            class="gt-a1721__note-item"
          >
            <label class="gt-a1721__note-label">KAM {{ idx + 1 }} 附注披露</label>
            <el-input
              :model-value="note.content"
              type="textarea"
              :autosize="{ minRows: 2 }"
              placeholder="输入该关键审计事项对应的附注披露内容"
              @change="(v: string) => updateNote(idx, v)"
            />
          </div>
        </el-card>

      </template>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A17-2-1" :project-id="props.projectId" class="gt-a1721__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useA1721Kam } from './composables/useA1721Kam'
import type { A1721RenderData } from './composables/useA1721Kam'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

defineOptions({ name: 'GtA1721Kam' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: A1721RenderData | null
}>(), { projectId: '', htmlData: null })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const {
  candidates,
  kams,
  notes,
  applicability,
  saveStatus,
  addCandidate,
  removeCandidate,
  addKam,
  removeKam,
  updateKamField,
  updateCandidate,
  updateNote,
  toggleApplicability,
  setApplicabilityReason,
  flushPendingSaves,
} = useA1721Kam({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

// ─── Candidate row highlight ───
function candidateRowClassName({ row }: { row: any }): string {
  return row.communicate === 'Y' ? 'gt-a1721__row-communicate' : ''
}

// ─── OO health check ───
async function checkOOHealth() {
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get<any>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    // ResponseWrapperMiddleware信封：{code,message,data:{healthy:true}} 或直接 {healthy:true}
    const healthy = res?.data?.healthy ?? res?.healthy
    if (!healthy) {
      modeOptions.value = ['结构化视图']
    }
  } catch {
    modeOptions.value = ['结构化视图']
  }
}

// Flush before switching to OO
watch(mode, async (newMode, oldMode) => {
  if (oldMode === '结构化视图' && newMode === '在线编辑') {
    await flushPendingSaves()
  }
})

// ─── Self-load when htmlData not provided (bundle embed scenario) ───
async function selfLoad() {
  if (props.htmlData) return // Already hydrated via prop
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get<any>(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=a17-2-1-kam`,
      { _silent: true } as any,
    )
    const data = res?.sheets?.[0]?.html_data
    if (data) {
      // Manually trigger hydration by updating the internal ref
      // The composable watches htmlData prop but we need to trigger it for self-load
      Object.assign(candidates.value, data.candidates ? data.candidates.map((c: any) => ({
        description: c.description ?? '', risk_level: c.risk_level ?? '',
        communicate: c.communicate === 'Y' ? 'Y' : 'N', reason: c.reason ?? '',
      })) : [])
      if (Array.isArray(data.kams)) {
        kams.value = data.kams.map((k: any, i: number) => ({
          index: k.index ?? i, basic: k.basic ?? '', policy: k.policy ?? '',
          reason: k.reason ?? '', response: k.response ?? '', result: k.result ?? '', ref_index: k.ref_index ?? '',
        }))
      }
      if (Array.isArray(data.notes)) {
        notes.value = data.notes.map((n: any) => ({ kam_index: n.kam_index ?? 0, content: n.content ?? '' }))
      }
      if (data.applicability) {
        applicability.value = { noKam: !!data.applicability.no_kam, reason: data.applicability.reason ?? null }
      }
    }
  } catch { /* silent — component renders empty state gracefully */ }
}

// ─── AI Generate ───
const aiLoading = ref<string | null>(null)

async function aiGenerateCandidates() {
  aiLoading.value = 'candidates'
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 12, chapter_title: '关键审计事项候选清单',
      guidance: '根据B50风险评估矩阵中识别的重大错报风险，生成关键审计事项候选清单。按JSON数组返回，每行含description(事项描述)/risk_level(高/中/低)/communicate(Y/N)/reason(原因)。示例：[{"description":"商誉减值测试","risk_level":"高","communicate":"Y","reason":"涉及重大会计估计和管理层判断"}]',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    const parsed = _tryParseJsonArray(content)
    if (parsed?.length) {
      for (const r of parsed) {
        addCandidate()
        const idx = candidates.value.length - 1
        if (r.description) updateCandidate(idx, 'description', r.description)
        if (r.risk_level) updateCandidate(idx, 'risk_level', r.risk_level)
        if (r.communicate) updateCandidate(idx, 'communicate', r.communicate)
        if (r.reason) updateCandidate(idx, 'reason', r.reason)
      }
    }
    ElMessage.success('AI 已生成候选清单')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

async function aiGenerateKam() {
  aiLoading.value = 'kam'
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: 12, chapter_title: '关键审计事项详情',
      guidance: '根据候选清单中标记为"沟通"的事项，生成关键审计事项详情。按JSON数组返回，每行含basic(基本情况)/policy(会计政策及重大估计)/reason(认定为KAM的原因)/response(审计应对措施)/result(审计结果)/note_disclosure(附注披露建议)。',
      existing_content: candidates.value.filter(c => c.communicate === 'Y').map(c => c.description).join('; '),
      knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    const parsed = _tryParseJsonArray(content)
    if (parsed?.length) {
      for (const r of parsed) {
        addKam()
        const idx = kams.value.length - 1
        if (r.basic) updateKamField(idx, 'basic', r.basic)
        if (r.policy) updateKamField(idx, 'policy', r.policy)
        if (r.reason) updateKamField(idx, 'reason', r.reason)
        if (r.response) updateKamField(idx, 'response', r.response)
        if (r.result) updateKamField(idx, 'result', r.result)
      }
    }
    ElMessage.success('AI 已生成 KAM 详情')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

import { tryParseJsonArray as _tryParseJsonArray } from '@/utils/aiJsonParse'

onMounted(() => { checkOOHealth(); selfLoad() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => flushPendingSaves() })
</script>

<style scoped>
.gt-a1721 { padding: 16px; }
.gt-a1721__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.gt-a1721__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* Content layout */
.gt-a1721__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-left: 8px;
}

/* Sections */
.gt-a1721__section { border-radius: 8px; }
.gt-a1721__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.gt-a1721__section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.gt-a1721__section-actions { display: flex; align-items: center; gap: 8px; }

/* 编制提示 */
.gt-a1721__guidance { margin: 8px 0; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-a1721__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-a1721__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; }

/* Applicability */
.gt-a1721__applicability { border-left: 3px solid #e6a23c; }
.gt-a1721__switch-row { margin-bottom: 12px; }
.gt-a1721__reason-wrap { margin-top: 8px; }

/* Candidate Table */
.gt-a1721__candidate-table { width: 100%; }
:deep(.gt-a1721__row-communicate) {
  background-color: #ecf5ff !important;
}

/* KAM Cards */
.gt-a1721__kam-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-a1721__kam-card { border-radius: 8px; }
.gt-a1721__kam-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.gt-a1721__kam-card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.gt-a1721__kam-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.gt-a1721__kam-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-a1721__kam-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
}

/* Notes */
.gt-a1721__notes-empty {
  color: #909399;
  font-size: var(--wp-font-size, 13px);
  padding: 8px 0;
}
.gt-a1721__note-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.gt-a1721__note-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
}

/* OO */
.gt-a1721__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}
</style>
