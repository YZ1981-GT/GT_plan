<!--
  GtA174DisagreementRecord.vue — A17-4 重大专业分歧事项记录

  专属组件：人员表(el-table 动态增删) + 6 章 textarea 卡片 + 签字区
  - Personnel_Table: 序号(auto)/姓名/职位/项目角色 + 添加/删除
  - 6 Section_Cards: textarea autosize
  - Signature_Area: 编制人(auto-fill) / 复核人 / 日期
  - 双模式: 结构化视图 / 在线编辑(GtOnlyOfficeSheet)
-->
<template>
  <div class="gt-a174">
    <!-- Mode Switch -->
    <div class="gt-a174__toolbar">
      <el-segmented
        v-model="mode"
        :options="modeOptions"
        size="small"
      />
      <span class="gt-a174__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved' && lastSavedAt">
          ✓ 已保存
        </template>
        <template v-else-if="saveStatus === 'unsaved'">
          ○ 未保存
        </template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a174__content">
      <!-- Loading -->
      <el-skeleton v-if="loading" :rows="10" animated />

      <template v-else>
        <!-- Personnel Table -->
        <el-card class="gt-a174__card" shadow="never">
          <template #header>
            <div class="gt-a174__card-header">
              <span class="gt-a174__card-title">存在专业意见分歧的人员</span>
              <el-button
                type="primary"
                size="small"
                :icon="Plus"
                :disabled="props.readonly"
                @click="addPersonnel"
              >
                添加人员
              </el-button>
            </div>
          </template>

          <el-table :data="personnel" border style="width: 100%" empty-text="暂无人员，请点击添加人员按钮">
            <el-table-column type="index" label="序号" width="60" align="center" />
            <el-table-column label="姓名" min-width="120">
              <template #default="{ row, $index }">
                <el-input
                  :model-value="row.name"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="请输入姓名"
                  @change="(v: string) => updatePersonnel($index, 'name', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="职位" min-width="140">
              <template #default="{ row, $index }">
                <el-input
                  :model-value="row.position"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="请输入职位"
                  @change="(v: string) => updatePersonnel($index, 'position', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="项目角色" min-width="140">
              <template #default="{ row, $index }">
                <el-input
                  :model-value="row.role"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="请输入项目角色"
                  @change="(v: string) => updatePersonnel($index, 'role', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ $index }">
                <el-button
                  type="danger"
                  size="small"
                  :icon="Delete"
                  circle
                  :disabled="props.readonly"
                  @click="removePersonnel($index)"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- Section Cards -->
        <el-card
          v-for="sec in sectionConfigs"
          :key="sec.num"
          class="gt-a174__card"
          shadow="never"
        >
          <template #header>
            <div class="gt-a174__card-header">
              <span class="gt-a174__card-title">{{ sec.title }}</span>
              <el-button size="small" :loading="aiLoading === sec.num" @click="aiGenerate(sec.num)">🤖 AI</el-button>
            </div>
          </template>
          <details v-if="sec.guidance" class="gt-a174__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a174__guidance-body">{{ sec.guidance }}</div>
          </details>
          <el-input
            :model-value="getSectionValue(sec.num)"
            type="textarea"
            :autosize="{ minRows: sec.minRows, maxRows: 20 }"
            :disabled="props.readonly"
            :placeholder="sec.placeholder"
            @change="(v: string) => updateSection(sec.num, v)"
          />
        </el-card>

        <!-- Signature Area -->
        <el-card class="gt-a174__card" shadow="never">
          <template #header>
            <span class="gt-a174__card-title">签字</span>
          </template>
          <div class="gt-a174__signature-grid">
            <div class="gt-a174__signature-item">
              <label>编制人</label>
              <el-input
                :model-value="signatureData.preparer"
                size="small"
                :disabled="props.readonly"
                placeholder="编制人（自动填充）"
                @change="(v: string) => updateSignature('preparer', v)"
              />
            </div>
            <div class="gt-a174__signature-item">
              <label>复核人</label>
              <el-input
                :model-value="signatureData.reviewer"
                size="small"
                :disabled="props.readonly"
                placeholder="请输入复核人"
                @change="(v: string) => updateSignature('reviewer', v)"
              />
            </div>
            <div class="gt-a174__signature-item">
              <label>日期</label>
              <el-date-picker
                :model-value="signatureData.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="选择日期"
                @change="(v: string) => updateSignature('date', v || '')"
              />
            </div>
          </div>
        </el-card>
      </template>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet
      v-else
      :wp-id="props.wpId"
      sheet-name="A17-4"
      :project-id="props.projectId"
      class="gt-a174__oo"
      @fallback="handleOOFallback"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent, computed } from 'vue'
import { Loading, Plus, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useA174DisagreementRecord } from './composables/useA174DisagreementRecord'

const GtOnlyOfficeSheet = defineAsyncComponent(
  () => import('./GtOnlyOfficeSheet.vue'),
)

defineOptions({ name: 'GtA174DisagreementRecord' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  readonly?: boolean
}>(), { projectId: '', readonly: false })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const wpIdRef = ref(props.wpId)
const {
  loading,
  personnel,
  sections,
  signatureData,
  saveStatus,
  lastSavedAt,
  loadData,
  addPersonnel,
  removePersonnel,
  updatePersonnel,
  updateSection,
  updateSignature,
  flushPendingSaves,
} = useA174DisagreementRecord(wpIdRef)

// ─── Section configs ───
const sectionConfigs = [
  { num: 1, title: '二、专业意见分歧事由', minRows: 4, placeholder: '描述存在专业意见分歧的业务背景、事由、各方主要观点和分析意见', guidance: '需要说明存在专业意见分歧的业务背景，审计过程中遇到的事项以及各方主要观点、事由、影响和主要的分析意见。' },
  { num: 2, title: '三、已执行的审计程序', minRows: 4, placeholder: '描述对专业分歧事项已采取的审计程序和获取的审计证据', guidance: '描述对专业分歧事项已采取的审计程序和获取的审计证据。' },
  { num: 3, title: '四、被审计单位和监管机构的意见', minRows: 4, placeholder: '记录管理层、治理层、监管方、董事会、审计委员会等的意见', guidance: '记录管理层、治理层（如审计委员会）、监管方、董事会等对该事项的意见和反馈。' },
  { num: 4, title: '五、解决方式和结论', minRows: 4, placeholder: '描述解决方式和最终审计结论', guidance: '描述解决方式（进一步咨询/修改方案/提升至合伙人会议等）、解决条件，并参照会计问题的处理准则或标准体现审计结论。标明需要配套执行的后续事项。' },
  { num: 5, title: '六、废弃事项落实情况', minRows: 3, placeholder: '如有废弃记录，清理相关备案并详载记录', guidance: '存入该废弃记录、清理和备案记录需审计报告形成的通知准则体系，标明需要配套执行任务等，详载清楚相关的必须记录。' },
]

/** Helper to get section value by number */
function getSectionValue(secNum: number): string {
  const fieldMap: Record<number, string> = { 1: 'parties', 2: 'cause', 3: 'procedures', 4: 'opinions', 5: 'considerations', 6: 'conclusion' }
  const sec = sections.value[secNum as keyof typeof sections.value]
  return sec ? (sec as any)[fieldMap[secNum]] || '' : ''
}

// ─── AI Generate ───
const aiLoading = ref<number | null>(null)
async function aiGenerate(section: number) {
  const titles: Record<number, string> = {
    1: '存在专业意见分歧的人员及其职位',
    2: '专业意见分歧事由',
    3: '已执行的审计程序',
    4: '被审计单位和监管机构的意见',
    5: '解决方式和结论',
    6: '废弃事项落实情况',
  }
  const guidances: Record<number, string> = {
    2: '需要说明存在专业意见分歧的业务背景、审计过程中遇到的事项，以及各方主要观点、事由、影响和分析意见。',
    3: '描述对专业分歧事项已采取的审计程序和获取的审计证据。',
    4: '记录管理层、治理层（如审计委员会）、监管方、董事会等对该事项的意见。',
    5: '描述解决方式（如进一步咨询/修改方案/提升至合伙人会议）和最终审计结论。标明需要配套执行的后续事项。',
    6: '如有废弃记录，清理相关备案并详载记录。',
  }
  aiLoading.value = section
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: section, chapter_title: titles[section] || '', guidance: guidances[section] || '',
      existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    updateSection(section, 'content', content)
    ElMessage.success('AI 已生成')
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiLoading.value = null }
}

// ─── OO Health Check + Fallback ───
async function checkOOHealth() {
  try {
    const { default: http } = await import('@/utils/http')
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    const healthy = res?.data?.data?.healthy ?? res?.data?.healthy
    if (!healthy) modeOptions.value = ['结构化视图']
  } catch {
    modeOptions.value = ['结构化视图']
  }
}
function handleOOFallback() {
  ElMessage.warning('OnlyOffice 编辑器加载失败，请尝试 docker restart audit-onlyoffice')
}

// ─── Lifecycle ───
onMounted(() => { checkOOHealth(); loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })

defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a174 {
  padding: 16px;
  max-width: 960px;
}

.gt-a174__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.gt-a174__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-a174__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a174__card {
  border-radius: 8px;
}

.gt-a174__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gt-a174__card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.gt-a174__signature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.gt-a174__signature-grid label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.gt-a174__signature-item {
  display: flex;
  flex-direction: column;
}

.gt-a174__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}

/* 编制提示 */
.gt-a174__guidance { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 0; }
.gt-a174__guidance summary { cursor: pointer; padding: 6px 10px; font-size: 12px; color: #409eff; font-weight: 500; user-select: none; }
.gt-a174__guidance-body { padding: 4px 10px 8px; font-size: 12px; color: #606266; line-height: 1.7; white-space: pre-wrap; }
</style>
