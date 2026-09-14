<!--
  GtA271ItAuditMemo.vue — A27-1 IT审计总结备忘录

  el-segmented 双模式 + 备忘录抬头(4字段) + 目的段(read-only) +
  IT团队表(动态增删) + 7章节卡片(radio+条件展开+GtIndexChip)
-->
<template>
  <div class="gt-a271">
    <!-- Toolbar -->
    <div class="gt-a271__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a271__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a271__content">
      <!-- Memo Header -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header><span class="gt-a271__card-title">备忘录抬头</span></template>
        <div class="gt-a271__header-row">
          <div class="gt-a271__field">
            <label>日期</label>
            <el-date-picker
              :model-value="header.date"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              @change="(v: string) => updateHeader('date', v || '')"
            />
          </div>
          <div class="gt-a271__field">
            <label>致</label>
            <el-input
              :model-value="header.to || projectContext.partner || ''"
              size="small"
              placeholder="收件人"
              @change="(v: string) => updateHeader('to', v)"
            />
          </div>
          <div class="gt-a271__field">
            <label>发自</label>
            <el-input
              :model-value="header.from_user || projectContext.current_user || ''"
              size="small"
              placeholder="发件人"
              @change="(v: string) => updateHeader('from_user', v)"
            />
          </div>
          <div class="gt-a271__field">
            <label>主题</label>
            <el-input
              :model-value="header.subject || 'IT审计总结'"
              size="small"
              placeholder="主题"
              @change="(v: string) => updateHeader('subject', v)"
            />
          </div>
        </div>
      </el-card>

      <!-- Purpose Section -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="gt-a271__purpose"
      >
        <template #title>目的</template>
        {{ purposeText || '本备忘录旨在总结本次审计中对被审计单位信息技术环境的了解、IT一般控制和信息处理控制的测试结果，以及对识别出的IT控制缺陷的评估。' }}
      </el-alert>

      <!-- IT Team Table -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header>
          <div class="gt-a271__card-header-row">
            <span class="gt-a271__card-title">IT审计团队</span>
            <el-button size="small" type="primary" plain @click="addTeamMember">
              + 添加成员
            </el-button>
          </div>
        </template>
        <el-table :data="itTeamTable" border size="small" class="gt-a271__team-table">
          <el-table-column label="序号" width="60" align="center">
            <template #default="{ row }">{{ row.index }}</template>
          </el-table-column>
          <el-table-column label="姓名" min-width="120">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.name || ''"
                size="small"
                placeholder="姓名"
                @change="(v: string) => updateTeamMember($index, 'name', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="职级" min-width="120">
            <template #default="{ row, $index }">
              <el-input
                :model-value="row.title || ''"
                size="small"
                placeholder="职级"
                @change="(v: string) => updateTeamMember($index, 'title', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60" align="center">
            <template #default="{ $index }">
              <el-button size="small" type="danger" text @click="removeTeamMember($index)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- Chapter 1: 了解信息系统环境 -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header>
          <div class="gt-a271__card-header-row">
            <span class="gt-a271__card-title">一、了解信息系统环境</span>
            <GtIndexChip v-if="crossReferences.b22a_4_3_wp_id" :wp-id="crossReferences.b22a_4_3_wp_id" label="B22A-4-3" />
          </div>
        </template>
        <el-input
          :model-value="chapters[0].content || ''"
          type="textarea"
          :autosize="{ minRows: 4 }"
          placeholder="请描述被审计单位的信息系统环境"
          @change="(v: string) => updateChapter(1, 'content', v)"
        />
      </el-card>

      <!-- Chapter 2: IT风险和一般控制 -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header>
          <div class="gt-a271__card-header-row">
            <span class="gt-a271__card-title">二、IT风险和一般控制</span>
            <GtIndexChip v-if="crossReferences.c22_wp_id" :wp-id="crossReferences.c22_wp_id" label="C22" />
          </div>
        </template>
        <el-input
          :model-value="chapters[1].content || ''"
          type="textarea"
          :autosize="{ minRows: 4 }"
          placeholder="请描述IT风险评估和一般控制测试结果"
          @change="(v: string) => updateChapter(2, 'content', v)"
        />
      </el-card>

      <!-- Chapter 3: IT一般控制结论 -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header><span class="gt-a271__card-title">三、IT一般控制结论</span></template>
        <div class="gt-a271__radio-section">
          <span class="gt-a271__radio-label">结论：</span>
          <el-radio-group
            :model-value="chapters[2].conclusion"
            @change="(v: string) => updateChapter(3, 'conclusion', v)"
          >
            <el-radio value="部分有效">部分有效</el-radio>
            <el-radio value="没有有效">没有有效</el-radio>
            <el-radio value="已有效">已有效</el-radio>
          </el-radio-group>
        </div>
        <el-input
          v-if="showCh3Deficiency"
          :model-value="chapters[2].deficiency || ''"
          type="textarea"
          :autosize="{ minRows: 3 }"
          placeholder="请描述IT一般控制缺陷情况"
          class="gt-a271__conditional-textarea"
          @change="(v: string) => updateChapter(3, 'deficiency', v)"
        />
      </el-card>

      <!-- Chapter 4: IT一般控制缺陷 (conditional) -->
      <el-card v-show="showChapter4" class="gt-a271__card" shadow="never">
        <template #header>
          <div class="gt-a271__card-header-row">
            <span class="gt-a271__card-title">四、IT一般控制缺陷</span>
            <GtIndexChip v-if="crossReferences.c21_1_wp_id" :wp-id="crossReferences.c21_1_wp_id" label="C21-1" />
          </div>
        </template>
        <el-input
          :model-value="chapters[3].content || ''"
          type="textarea"
          :autosize="{ minRows: 4 }"
          placeholder="请详细描述IT一般控制缺陷"
          @change="(v: string) => updateChapter(4, 'content', v)"
        />
      </el-card>

      <!-- Chapter 5: 信息处理控制 -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header>
          <div class="gt-a271__card-header-row">
            <span class="gt-a271__card-title">五、信息处理控制</span>
            <GtIndexChip v-if="crossReferences.b23_15_wp_id" :wp-id="crossReferences.b23_15_wp_id" label="B23-15" />
          </div>
        </template>
        <el-input
          :model-value="chapters[4].content || ''"
          type="textarea"
          :autosize="{ minRows: 4 }"
          placeholder="请描述信息处理控制测试结果"
          @change="(v: string) => updateChapter(5, 'content', v)"
        />
      </el-card>

      <!-- Chapter 6: 信息处理控制结论 -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header><span class="gt-a271__card-title">六、信息处理控制结论</span></template>
        <div class="gt-a271__radio-section">
          <span class="gt-a271__radio-label">结论：</span>
          <el-radio-group
            :model-value="chapters[5].conclusion"
            @change="(v: string) => updateChapter(6, 'conclusion', v)"
          >
            <el-radio value="部分有效">部分有效</el-radio>
            <el-radio value="没有有效">没有有效</el-radio>
            <el-radio value="已有效">已有效</el-radio>
          </el-radio-group>
        </div>
        <el-input
          v-if="showCh6Deficiency"
          :model-value="chapters[5].deficiency || ''"
          type="textarea"
          :autosize="{ minRows: 3 }"
          placeholder="请描述信息处理控制缺陷情况"
          class="gt-a271__conditional-textarea"
          @change="(v: string) => updateChapter(6, 'deficiency', v)"
        />
      </el-card>

      <!-- Chapter 7: 缺陷评估 -->
      <el-card class="gt-a271__card" shadow="never">
        <template #header><span class="gt-a271__card-title">七、缺陷评估</span></template>
        <div class="gt-a271__ch7-fields">
          <div class="gt-a271__field gt-a271__field--full">
            <label>评估内容</label>
            <el-input
              :model-value="chapters[6].content || ''"
              type="textarea"
              :autosize="{ minRows: 4 }"
              placeholder="请描述对IT控制缺陷的整体评估"
              @change="(v: string) => updateChapter(7, 'content', v)"
            />
          </div>
          <div class="gt-a271__field gt-a271__field--full">
            <label>评估结论</label>
            <el-input
              :model-value="chapters[6].conclusion || ''"
              size="small"
              placeholder="请输入评估结论"
              @change="(v: string) => updateChapter(7, 'conclusion', v)"
            />
          </div>
        </div>
      </el-card>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A27-1" class="gt-a271__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA271ItAuditMemo } from './composables/useA271ItAuditMemo'
import type { A271RenderData } from './composables/useA271ItAuditMemo'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

defineOptions({ name: 'GtA271ItAuditMemo' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: A271RenderData | null
}>(), { projectId: '', htmlData: null })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const {
  header,
  itTeamTable,
  chapters,
  crossReferences,
  projectContext,
  purposeText,
  saveStatus,
  showChapter4,
  showCh3Deficiency,
  showCh6Deficiency,
  updateHeader,
  updateChapter,
  addTeamMember,
  removeTeamMember,
  updateTeamMember,
  flushPendingSaves,
} = useA271ItAuditMemo({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  htmlData: toRef(props, 'htmlData'),
})

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
.gt-a271 { padding: 16px; }
.gt-a271__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a271__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }

.gt-a271__content { display: flex; flex-direction: column; gap: 16px; max-width: 900px; }
.gt-a271__card { border-radius: 8px; }
.gt-a271__card-title { font-size: 15px; font-weight: 600; color: #303133; }
.gt-a271__card-header-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }

/* Header row */
.gt-a271__header-row { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a271__field { display: flex; flex-direction: column; gap: 4px; min-width: 160px; flex: 1; }
.gt-a271__field--full { width: 100%; flex: unset; }
.gt-a271__field label { font-size: 12px; color: #909399; }

/* Purpose */
.gt-a271__purpose { border-radius: 6px; }

/* Team table */
.gt-a271__team-table { width: 100%; }

/* Radio section */
.gt-a271__radio-section { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.gt-a271__radio-label { font-size: 14px; font-weight: 500; color: #303133; }
.gt-a271__conditional-textarea { margin-top: 12px; }

/* Ch7 fields */
.gt-a271__ch7-fields { display: flex; flex-direction: column; gap: 12px; }

/* OO */
.gt-a271__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
