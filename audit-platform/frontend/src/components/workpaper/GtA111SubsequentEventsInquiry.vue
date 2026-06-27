<!--
  GtA111SubsequentEventsInquiry.vue — A11-1 期后事项问询函

  10 个 CAS 1332 问询事项卡片式 Q&A：
  - el-segmented 双模式（结构化视图 / 在线编辑）
  - 左侧 mini 导航（12 项：元信息 + Q1~Q10 + 证据）
  - 元信息卡片（询问日期 + 受访对象 + 地点 + 签字）
  - 10 Q&A 卡片（编号标题 + 只读问题 + 条件指导 el-alert + 答复 textarea + AI disabled 按钮）
  - 证据区卡片
  - 顶部编制时间提示 el-alert
  - 问询目的折叠区
  - GtOnlyOfficeSheet 在线编辑模式
-->
<template>
  <div class="gt-a111">
    <!-- Toolbar -->
    <div class="gt-a111__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <div class="gt-a111__toolbar-right">
        <span class="gt-a111__save-status">
          <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
          <template v-else-if="saveStatus === 'saved' && lastSavedAt">✓ 已保存</template>
          <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
        </span>
      </div>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a111__layout">
      <!-- Left Navigation -->
      <aside class="gt-a111__nav">
        <div
          v-for="item in navItems"
          :key="item.id"
          class="gt-a111__nav-item"
          :class="{ 'gt-a111__nav-item--active': activeNavItem === item.id }"
          @click="scrollToItem(item.id)"
        >
          {{ item.label }}
        </div>
      </aside>

      <!-- Main Content -->
      <main class="gt-a111__content">
        <el-skeleton v-if="loading" :rows="10" animated />
        <template v-else>
          <!-- Timing guidance alert -->
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            class="gt-a111__timing-alert"
          >
            <template #title>问询时间要求</template>
            问询应在尽量接近审计报告日进行，以涵盖资产负债表日后至审计报告日之间的所有期后事项。
          </el-alert>

          <!-- 问询目的 (collapsible, read-only) -->
          <el-collapse v-model="purposeCollapse" class="gt-a111__purpose">
            <el-collapse-item title="问询目的" name="purpose">
              <p class="gt-a111__muted-text">
                根据《中国注册会计师审计准则第1332号——期后事项》的规定，注册会计师应当实施审计程序，
                以确定在财务报表日至审计报告日之间发生的、需要在财务报表中调整或披露的事项是否已得到适当处理。
                本问询旨在获取管理层对期后事项的陈述，作为期后事项审计程序的一部分。
              </p>
            </el-collapse-item>
          </el-collapse>

          <!-- Meta Card -->
          <el-card id="nav-meta" class="gt-a111__card" shadow="never">
            <template #header><span class="gt-a111__card-title">问询元信息</span></template>
            <div class="gt-a111__meta-grid">
              <div class="gt-a111__field">
                <label>询问日期</label>
                <el-date-picker
                  :model-value="metaData.inquiryDate"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="选择日期"
                  @change="(v: string) => updateMeta('inquiryDate', v || '')"
                />
              </div>
              <div class="gt-a111__field">
                <label>受访对象</label>
                <el-input
                  :model-value="metaData.interviewee"
                  size="small"
                  placeholder="如：张三（财务总监）"
                  @change="(v: string) => updateMeta('interviewee', v)"
                />
              </div>
              <div class="gt-a111__field">
                <label>询问地点</label>
                <el-input
                  :model-value="metaData.location"
                  size="small"
                  placeholder="如：公司会议室"
                  @change="(v: string) => updateMeta('location', v)"
                />
              </div>
              <div class="gt-a111__field">
                <label>项目组签字</label>
                <el-input
                  :model-value="metaData.teamSignature"
                  size="small"
                  placeholder="执行人签字"
                  @change="(v: string) => updateMeta('teamSignature', v)"
                />
              </div>
            </div>
          </el-card>

          <!-- 10 Q&A Cards -->
          <el-card
            v-for="qa in qaList"
            :id="`nav-q${qa.number}`"
            :key="qa.number"
            class="gt-a111__card"
            shadow="never"
          >
            <template #header>
              <span class="gt-a111__card-title">{{ qa.number }}. {{ qa.title }}</span>
            </template>
            <div class="gt-a111__qa">
              <p class="gt-a111__question-text">{{ qa.text }}</p>
              <el-alert
                v-if="qa.hasGuidance && qa.guidanceText"
                type="info"
                :closable="false"
                show-icon
                class="gt-a111__guidance"
              >
                <template #title>编制指导</template>
                {{ qa.guidanceText }}
              </el-alert>
              <div class="gt-a111__answer-row">
                <el-input
                  :model-value="qa.answer"
                  type="textarea"
                  :autosize="{ minRows: 3 }"
                  placeholder="受访对象答复"
                  @change="(v: string) => updateAnswer(qa.number, v)"
                />
                <el-tooltip content="AI 生成建议答复即将上线" placement="top">
                  <el-button size="small" disabled class="gt-a111__ai-btn">
                    <el-icon><MagicStick /></el-icon> AI
                  </el-button>
                </el-tooltip>
              </div>
            </div>
          </el-card>

          <!-- Evidence Card -->
          <el-card id="nav-evidence" class="gt-a111__card" shadow="never">
            <template #header><span class="gt-a111__card-title">贵公司已提供的相关证据</span></template>
            <el-input
              :model-value="evidence"
              type="textarea"
              :autosize="{ minRows: 4 }"
              placeholder="请描述已获取的支持性证据（如：银行对账单、法律确认函等）"
              @change="(v: string) => updateEvidence(v)"
            />
          </el-card>
        </template>
      </main>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A11-1" class="gt-a111__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, defineAsyncComponent } from 'vue'
import { Loading, MagicStick } from '@element-plus/icons-vue'
import { useA111SubsequentEvents, NAV_ITEMS } from './composables/useA111SubsequentEvents'
import { api } from '@/services/apiProxy'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

defineOptions({ name: 'GtA111SubsequentEventsInquiry' })

const props = withDefaults(defineProps<{ wpId: string; projectId?: string }>(), { projectId: '' })

// ─── Mode switch ─────────────────────────────────────────────────────────────

const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])
const purposeCollapse = ref<string[]>([])
const navItems = NAV_ITEMS

// ─── OO health check ─────────────────────────────────────────────────────────

async function checkOOHealth() {
  try {
    const res = await api.get<any>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    if (!res?.healthy) {
      modeOptions.value = ['结构化视图']
    }
  } catch {
    modeOptions.value = ['结构化视图']
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

const wpIdRef = ref(props.wpId)
const {
  loading, metaData, qaList, evidence, projectContext,
  saveStatus, lastSavedAt, activeNavItem,
  loadData, updateMeta, updateAnswer, updateEvidence, flushPendingSaves, scrollToItem,
} = useA111SubsequentEvents(wpIdRef)

// Flush pending saves before switching to OO
watch(mode, async (newMode, oldMode) => {
  if (oldMode === '结构化视图' && newMode === '在线编辑') {
    await flushPendingSaves()
  }
})

onMounted(() => {
  loadData(props.wpId)
  checkOOHealth()
})

onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a111 { padding: 16px; }
.gt-a111__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a111__toolbar-right { display: flex; align-items: center; gap: 12px; }
.gt-a111__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }

.gt-a111__layout { display: flex; gap: 16px; }

/* Left Navigation */
.gt-a111__nav {
  position: sticky;
  top: 80px;
  align-self: flex-start;
  width: 72px;
  min-width: 72px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: #f5f7fa;
  border-radius: 8px;
  padding: 8px 4px;
}
.gt-a111__nav-item {
  padding: 6px 8px;
  font-size: 12px;
  color: #606266;
  border-radius: 4px;
  cursor: pointer;
  text-align: center;
  transition: all 0.2s;
  white-space: nowrap;
}
.gt-a111__nav-item:hover { background: #e8eaed; color: #303133; }
.gt-a111__nav-item--active { background: #409eff; color: #fff; font-weight: 500; }

/* Main Content */
.gt-a111__content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 16px; max-width: 860px; }

.gt-a111__timing-alert { border-radius: 8px; }
.gt-a111__purpose { margin-bottom: 0; }
.gt-a111__muted-text { font-size: 13px; color: #909399; line-height: 1.8; margin: 0; }

.gt-a111__card { border-radius: 8px; }
.gt-a111__card-title { font-size: 15px; font-weight: 600; color: #303133; }

/* Meta Grid */
.gt-a111__meta-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.gt-a111__field { display: flex; flex-direction: column; gap: 4px; }
.gt-a111__field label { font-size: 12px; color: #909399; }

/* Q&A */
.gt-a111__qa { display: flex; flex-direction: column; gap: 12px; }
.gt-a111__question-text { font-size: 14px; color: #606266; line-height: 1.7; margin: 0; }
.gt-a111__guidance { border-radius: 6px; }
.gt-a111__answer-row { display: flex; gap: 8px; align-items: flex-start; }
.gt-a111__answer-row .el-textarea { flex: 1; }
.gt-a111__ai-btn { margin-top: 4px; }

/* OO */
.gt-a111__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
