<!--
  GtA101GovernanceCommunication.vue — A10-1 与治理层沟通函

  el-segmented 双模式 + 左侧导航(scrollspy) + 16章折叠卡片 +
  服务费表格(章三) + GtIndexChip(章九→A9-2, 章十三→A13) +
  签发区 + 提示折叠框
-->
<template>
  <div class="gt-a101">
    <!-- Toolbar -->
    <div class="gt-a101__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a101__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a101__layout">
      <!-- Left Navigation Sidebar -->
      <nav class="gt-a101__nav">
        <ul class="gt-a101__nav-list">
          <li
            class="gt-a101__nav-item"
            :class="{ 'is-active': activeChapter === 0 }"
            @click="scrollToChapter(0)"
          >收件人</li>
          <li
            v-for="ch in chapters"
            :key="ch.number"
            class="gt-a101__nav-item"
            :class="{ 'is-active': activeChapter === ch.number }"
            @click="scrollToChapter(ch.number)"
          >
            <span class="gt-a101__nav-num">{{ ch.number }}</span>
            <span class="gt-a101__nav-title">{{ getAbbrevTitle(ch.title) }}</span>
          </li>
          <li
            class="gt-a101__nav-item"
            :class="{ 'is-active': activeChapter === 17 }"
            @click="scrollToChapter(17)"
          >签发</li>
          <li
            class="gt-a101__nav-item"
            :class="{ 'is-active': activeChapter === 18 }"
            @click="scrollToChapter(18)"
          >提示</li>
        </ul>
      </nav>

      <!-- Right Content Area -->
      <div class="gt-a101__content">
        <!-- Section 0: Recipient + Introduction -->
        <div id="a101-section-0" class="gt-a101__section">
          <el-card shadow="never" class="gt-a101__card">
            <template #header><span class="gt-a101__card-title">收件人</span></template>
            <el-input
              :model-value="recipient"
              size="default"
              :placeholder="projectContext.client_name ? projectContext.client_name + '董事会' : 'xx公司董事会/监事会/审计委员会'"
              @change="(v: string) => updateRecipient(v)"
            />
          </el-card>

          <!-- Introduction paragraphs -->
          <el-alert
            v-for="(text, idx) in introductionText"
            :key="idx"
            type="info"
            :closable="false"
            show-icon
            class="gt-a101__intro"
          >
            {{ text }}
          </el-alert>
        </div>

        <!-- 16 Chapter Cards -->
        <el-collapse v-model="expandedChapters" class="gt-a101__chapters">
          <el-collapse-item
            v-for="ch in chapters"
            :key="ch.number"
            :name="ch.number"
            :id="`a101-section-${ch.number}`"
            class="gt-a101__chapter-item"
          >
            <template #title>
              <div class="gt-a101__chapter-header">
                <span class="gt-a101__chapter-title">{{ toChineseNum(ch.number) }}、{{ ch.title }}</span>
                <GtIndexChip
                  v-if="ch.number === 9 && crossReferences.a9_2_wp_id"
                  :wp-id="crossReferences.a9_2_wp_id"
                  label="A9-2"
                />
                <GtIndexChip
                  v-if="ch.number === 13 && crossReferences.a13_wp_id"
                  :wp-id="crossReferences.a13_wp_id"
                  label="A13"
                />
              </div>
            </template>

            <!-- Chapter content textarea -->
            <el-input
              :model-value="ch.content || ''"
              type="textarea"
              :autosize="{ minRows: 4 }"
              :placeholder="`请输入${ch.title}相关内容`"
              @change="(v: string) => updateChapter(ch.number, v)"
            />

            <!-- Chapter 3 special: Service Fee Table -->
            <div v-if="ch.number === 3" class="gt-a101__fee-section">
              <h4 class="gt-a101__fee-title">非审计服务费用明细</h4>
              <el-table :data="serviceFees" border size="small" class="gt-a101__fee-table">
                <el-table-column label="服务项目" prop="name" min-width="180" />
                <el-table-column label="金额（元）" min-width="160">
                  <template #default="{ row, $index }">
                    <el-input-number
                      :model-value="row.amount"
                      :precision="2"
                      :min="0"
                      :controls="false"
                      size="small"
                      placeholder="请输入金额"
                      @change="(v: number | undefined) => updateFee($index, v ?? null)"
                    />
                  </template>
                </el-table-column>
              </el-table>
              <div class="gt-a101__fee-total">
                <span>合计：</span>
                <span class="gt-a101__fee-total-amount">¥ {{ totalFee.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</span>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- Section 17: Signing -->
        <div id="a101-section-17" class="gt-a101__section">
          <el-card shadow="never" class="gt-a101__card">
            <template #header><span class="gt-a101__card-title">签发</span></template>
            <div class="gt-a101__sign-fields">
              <div class="gt-a101__field">
                <label>会计师事务所</label>
                <el-input
                  :model-value="signingSection.firm_name || projectContext.firm_name || ''"
                  size="small"
                  placeholder="事务所名称"
                  @change="(v: string) => updateSigning('firm_name', v)"
                />
              </div>
              <div class="gt-a101__field">
                <label>中国注册会计师</label>
                <el-input
                  :model-value="signingSection.partner_name || ''"
                  size="small"
                  placeholder="合伙人姓名"
                  @change="(v: string) => updateSigning('partner_name', v)"
                />
              </div>
              <div class="gt-a101__field">
                <label>日期</label>
                <el-date-picker
                  :model-value="signingSection.date"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  placeholder="选择日期"
                  @change="(v: string) => updateSigning('date', v || '')"
                />
              </div>
            </div>
          </el-card>
        </div>

        <!-- Section 18: Guidance Notes -->
        <div id="a101-section-18" class="gt-a101__section">
          <el-collapse class="gt-a101__guidance">
            <el-collapse-item title="编制提示" name="guidance">
              <p class="gt-a101__guidance-text">{{ guidanceNotes }}</p>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A10-1" class="gt-a101__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA101GovernanceCommunication } from './composables/useA101GovernanceCommunication'
import { useA101Navigation } from './composables/useA101Navigation'
import type { A101RenderData } from './composables/useA101GovernanceCommunication'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

defineOptions({ name: 'GtA101GovernanceCommunication' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: A101RenderData | null
}>(), { projectId: '', htmlData: null })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const {
  recipient,
  introductionText,
  chapters,
  serviceFees,
  signingSection,
  guidanceNotes,
  crossReferences,
  projectContext,
  saveStatus,
  totalFee,
  updateRecipient,
  updateChapter,
  updateFee,
  updateSigning,
  flushPendingSaves,
} = useA101GovernanceCommunication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

// ─── Navigation ───
const { activeChapter, scrollToChapter } = useA101Navigation()

// ─── Collapse State: ch1-5 expanded, ch6-16 collapsed ───
const expandedChapters = ref<number[]>([1, 2, 3, 4, 5])

// ─── Helpers ───
const CHINESE_NUMS = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四', '十五', '十六']

function toChineseNum(n: number): string {
  return CHINESE_NUMS[n - 1] || String(n)
}

function getAbbrevTitle(title: string): string {
  return title.length > 6 ? title.slice(0, 6) + '…' : title
}

// ─── OO health check ───
async function checkOOHealth() {
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.get<any>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    if (!res?.healthy) {
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

onMounted(() => { checkOOHealth() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => flushPendingSaves() })
</script>

<style scoped>
.gt-a101 { padding: 16px; }
.gt-a101__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a101__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }

/* Layout: left nav + right content */
.gt-a101__layout { display: flex; gap: 16px; }

/* Left navigation */
.gt-a101__nav {
  position: sticky;
  top: 80px;
  width: 180px;
  min-width: 180px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  border-right: 1px solid #ebeef5;
  padding-right: 12px;
}
.gt-a101__nav-list { list-style: none; margin: 0; padding: 0; }
.gt-a101__nav-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-a101__nav-item:hover { background-color: #f5f7fa; }
.gt-a101__nav-item.is-active { background-color: #ecf5ff; color: #409eff; font-weight: 500; }
.gt-a101__nav-num { min-width: 16px; text-align: center; font-weight: 600; }
.gt-a101__nav-title { overflow: hidden; text-overflow: ellipsis; }

/* Right content */
.gt-a101__content { flex: 1; max-width: 900px; display: flex; flex-direction: column; gap: 16px; }
.gt-a101__section { display: flex; flex-direction: column; gap: 12px; }
.gt-a101__card { border-radius: 8px; }
.gt-a101__card-title { font-size: 15px; font-weight: 600; color: #303133; }

/* Introduction */
.gt-a101__intro { border-radius: 6px; }

/* Chapters */
.gt-a101__chapters { border: none; }
.gt-a101__chapter-item { margin-bottom: 8px; }
.gt-a101__chapter-header { display: flex; align-items: center; gap: 8px; width: 100%; }
.gt-a101__chapter-title { font-size: 14px; font-weight: 600; color: #303133; }

/* Fee table */
.gt-a101__fee-section { margin-top: 16px; }
.gt-a101__fee-title { font-size: 13px; font-weight: 500; color: #606266; margin-bottom: 8px; }
.gt-a101__fee-table { width: 100%; }
.gt-a101__fee-total { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 8px; font-size: 14px; font-weight: 600; }
.gt-a101__fee-total-amount { color: #e6a23c; font-size: 16px; }

/* Signing */
.gt-a101__sign-fields { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a101__field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; flex: 1; }
.gt-a101__field label { font-size: 12px; color: #909399; }

/* Guidance */
.gt-a101__guidance { border: none; }
.gt-a101__guidance-text { font-size: 13px; color: #909399; line-height: 1.8; }

/* OO */
.gt-a101__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
