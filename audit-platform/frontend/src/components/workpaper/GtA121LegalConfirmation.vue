<!--
  GtA121LegalConfirmation.vue — A12-1 法律事务确认函及律师回复函

  el-segmented 双模式 + Part 1 发函(白色卡片) + Part 2 回函(浅蓝卡片)
  诉讼动态列表 + 条件展开 + GtIndexChip(A5-3)
-->
<template>
  <div class="gt-a121">
    <!-- Toolbar -->
    <div class="gt-a121__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a121__save-status">
        <template v-if="saveStatus === 'saving'">
          <el-icon class="is-loading"><Loading /></el-icon> 保存中...
        </template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a121__content">

      <!-- ═══════════ Part 1: 发函 ═══════════ -->
      <el-card class="gt-a121__card gt-a121__card--send" shadow="never">
        <template #header>
          <span class="gt-a121__card-title">第一部分：法律事务确认函（发函）</span>
        </template>

        <!-- 收件人 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">收件人</h4>
          <div class="gt-a121__row">
            <div class="gt-a121__field">
              <label>律师事务所</label>
              <el-input
                :model-value="sendSection.recipient.firm_name || ''"
                size="small"
                placeholder="律师事务所名称"
                @change="(v: string) => updateField('send', 'recipient-firm', v)"
              />
            </div>
            <div class="gt-a121__field">
              <label>律师姓名</label>
              <el-input
                :model-value="sendSection.recipient.lawyer_name || ''"
                size="small"
                placeholder="律师姓名"
                @change="(v: string) => updateField('send', 'recipient-lawyer', v)"
              />
            </div>
          </div>
        </div>

        <!-- 说明段 -->
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="gt-a121__explanation"
        >
          <template #title>说明</template>
          {{ sendSection.explanation_text }}
        </el-alert>

        <!-- 问询一：未决诉讼 -->
        <div class="gt-a121__section">
          <div class="gt-a121__section-header">
            <h4 class="gt-a121__section-title">一、未决诉讼、仲裁及行政处罚</h4>
            <GtIndexChip v-if="crossReferences.a5_3_wp_id" :wp-id="crossReferences.a5_3_wp_id" label="A5-3" />
          </div>

          <!-- 诉讼列表 -->
          <div v-if="sendSection.inquiry_1.litigation_list.length === 0" class="gt-a121__empty">
            <span class="gt-a121__empty-text">无未决诉讼</span>
          </div>
          <div
            v-for="(item, idx) in sendSection.inquiry_1.litigation_list"
            :key="idx"
            class="gt-a121__litigation-card"
          >
            <div class="gt-a121__litigation-header">
              <span>诉讼记录 {{ idx + 1 }}</span>
              <el-button size="small" type="danger" text @click="removeLitigation(idx)">
                删除
              </el-button>
            </div>
            <div class="gt-a121__litigation-fields">
              <div class="gt-a121__field gt-a121__field--full">
                <label>案件事实描述</label>
                <el-input
                  :model-value="item.description || ''"
                  type="textarea"
                  :autosize="{ minRows: 2 }"
                  placeholder="请描述案件事实"
                  @change="(v: string) => updateLitigation(idx, 'description', v)"
                />
              </div>
              <div class="gt-a121__field gt-a121__field--full">
                <label>律师看法</label>
                <el-input
                  :model-value="item.opinion || ''"
                  type="textarea"
                  :autosize="{ minRows: 2 }"
                  placeholder="律师对案件的看法"
                  @change="(v: string) => updateLitigation(idx, 'opinion', v)"
                />
              </div>
              <div class="gt-a121__field">
                <label>可能损失金额估计（元）</label>
                <el-input-number
                  :model-value="item.estimated_loss"
                  size="small"
                  :min="0"
                  :precision="2"
                  :controls="false"
                  placeholder="金额"
                  @change="(v: number | undefined) => updateLitigation(idx, 'estimated_loss', v)"
                />
              </div>
            </div>
          </div>
          <el-button size="small" type="primary" plain @click="addLitigation" class="gt-a121__add-btn">
            + 添加诉讼
          </el-button>
        </div>

        <!-- 问询二：其他法律责任 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">二、其他法律责任事件</h4>
          <el-input
            :model-value="sendSection.inquiry_2.content || ''"
            type="textarea"
            :autosize="{ minRows: 3 }"
            placeholder="请描述其他法律责任事件"
            @change="(v: string) => updateField('send', 'inquiry2-content', v)"
          />
        </div>

        <!-- 问询三：律师费 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">三、律师服务费结算</h4>
          <el-input
            :model-value="sendSection.inquiry_3.content || ''"
            type="textarea"
            :autosize="{ minRows: 3 }"
            placeholder="请描述律师费结算情况"
            @change="(v: string) => updateField('send', 'inquiry3-content', v)"
          />
        </div>

        <!-- 简化说明 -->
        <p class="gt-a121__simplified-note">{{ sendSection.simplified_note }}</p>

        <!-- 签章区 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">签章</h4>
          <div class="gt-a121__row">
            <div class="gt-a121__field">
              <label>公司名称</label>
              <el-input
                :model-value="sendSection.sign_info.company_name || ''"
                size="small"
                placeholder="公司名称（自动填充）"
                @change="(v: string) => updateField('send', 'sign-company', v)"
              />
            </div>
            <div class="gt-a121__field">
              <label>日期</label>
              <el-date-picker
                :model-value="sendSection.sign_info.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                @change="(v: string) => updateField('send', 'sign-date', v || '')"
              />
            </div>
          </div>
        </div>

        <!-- 回函信息表 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">回函信息</h4>
          <div class="gt-a121__row gt-a121__row--3col">
            <div class="gt-a121__field">
              <label>回函地址</label>
              <el-input
                :model-value="sendSection.reply_info_table.address || ''"
                size="small"
                placeholder="回函地址"
                @change="(v: string) => updateField('send', 'reply-address', v)"
              />
            </div>
            <div class="gt-a121__field">
              <label>电话</label>
              <el-input
                :model-value="sendSection.reply_info_table.phone || ''"
                size="small"
                placeholder="电话"
                @change="(v: string) => updateField('send', 'reply-phone', v)"
              />
            </div>
            <div class="gt-a121__field">
              <label>联系人</label>
              <el-input
                :model-value="sendSection.reply_info_table.contact || ''"
                size="small"
                placeholder="联系人"
                @change="(v: string) => updateField('send', 'reply-contact', v)"
              />
            </div>
          </div>
        </div>
      </el-card>

      <!-- ═══════════ Part 2: 回函 ═══════════ -->
      <el-card class="gt-a121__card gt-a121__card--reply" shadow="never">
        <template #header>
          <span class="gt-a121__card-title">第二部分：律师回复函（回函）</span>
        </template>

        <!-- 诉讼确认 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">诉讼确认</h4>
          <el-radio-group
            :model-value="replySection.litigation_status"
            @change="(v: string) => updateField('reply', 'status', v)"
          >
            <el-radio value="no_litigation">确认无诉讼</el-radio>
            <el-radio value="has_litigation">确认有诉讼</el-radio>
          </el-radio-group>
          <el-input
            v-if="showLitigationDetails"
            :model-value="replySection.litigation_details || ''"
            type="textarea"
            :autosize="{ minRows: 3 }"
            placeholder="请描述诉讼详情"
            class="gt-a121__conditional-textarea"
            @change="(v: string) => updateField('reply', 'details', v)"
          />
        </div>

        <!-- 律师费结算 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">律师费结算</h4>
          <el-radio-group
            :model-value="replySection.fee_status"
            @change="(v: string) => updateField('reply', 'fee-status', v)"
          >
            <el-radio value="no_outstanding">未积欠</el-radio>
            <el-radio value="has_outstanding">尚有未付</el-radio>
          </el-radio-group>
          <div v-if="showOutstandingAmount" class="gt-a121__conditional-input">
            <label>未付金额（元）</label>
            <el-input-number
              :model-value="replySection.outstanding_amount"
              size="small"
              :min="0"
              :precision="2"
              :controls="false"
              placeholder="未付金额"
              @change="(v: number | undefined) => updateField('reply', 'fee-amount', v)"
            />
          </div>
        </div>

        <!-- 律师签字 -->
        <div class="gt-a121__section">
          <h4 class="gt-a121__section-title">律师签字</h4>
          <div class="gt-a121__row gt-a121__row--3col">
            <div class="gt-a121__field">
              <label>律师事务所</label>
              <el-input
                :model-value="replySection.sign.firm_name || ''"
                size="small"
                placeholder="律师事务所名称"
                @change="(v: string) => updateField('reply', 'sign-firm', v)"
              />
            </div>
            <div class="gt-a121__field">
              <label>律师签字</label>
              <el-input
                :model-value="replySection.sign.lawyer_name || ''"
                size="small"
                placeholder="律师姓名"
                @change="(v: string) => updateField('reply', 'sign-lawyer', v)"
              />
            </div>
            <div class="gt-a121__field">
              <label>日期</label>
              <el-date-picker
                :model-value="replySection.sign.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                @change="(v: string) => updateField('reply', 'sign-date', v || '')"
              />
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- Online Edit Mode -->
    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A12-1" class="gt-a121__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA121LegalConfirmation } from './composables/useA121LegalConfirmation'
import type { A121RenderData } from './composables/useA121LegalConfirmation'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

defineOptions({ name: 'GtA121LegalConfirmation' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  htmlData?: A121RenderData | null
}>(), { projectId: '', htmlData: null })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const {
  sendSection,
  replySection,
  crossReferences,
  saveStatus,
  showLitigationDetails,
  showOutstandingAmount,
  addLitigation,
  removeLitigation,
  updateLitigation,
  updateField,
  flushPendingSaves,
} = useA121LegalConfirmation({
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
.gt-a121 { padding: 16px; }
.gt-a121__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a121__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }

.gt-a121__content { display: flex; flex-direction: column; gap: 16px; max-width: 900px; }
.gt-a121__card { border-radius: 8px; }
.gt-a121__card--reply { background-color: #f0f9ff; }
.gt-a121__card-title { font-size: 16px; font-weight: 600; color: #303133; }

.gt-a121__section { margin-bottom: 20px; }
.gt-a121__section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.gt-a121__section-title { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 8px; }

.gt-a121__row { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a121__row--3col { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.gt-a121__field { display: flex; flex-direction: column; gap: 4px; min-width: 160px; flex: 1; }
.gt-a121__field--full { width: 100%; flex: unset; }
.gt-a121__field label { font-size: 12px; color: #909399; }

.gt-a121__explanation { border-radius: 6px; margin-bottom: 16px; }

.gt-a121__empty { padding: 16px; text-align: center; border: 1px dashed #dcdfe6; border-radius: 6px; margin-bottom: 12px; }
.gt-a121__empty-text { color: #909399; font-size: 13px; }

.gt-a121__litigation-card { border: 1px solid #e4e7ed; border-radius: 6px; padding: 12px; margin-bottom: 12px; }
.gt-a121__litigation-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 13px; font-weight: 500; color: #606266; }
.gt-a121__litigation-fields { display: flex; flex-direction: column; gap: 8px; }

.gt-a121__add-btn { margin-top: 8px; }

.gt-a121__simplified-note { font-size: 13px; color: #909399; font-style: italic; margin: 12px 0; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }

.gt-a121__conditional-textarea { margin-top: 12px; }
.gt-a121__conditional-input { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
.gt-a121__conditional-input label { font-size: 13px; color: #606266; white-space: nowrap; }

.gt-a121__oo { height: calc(100vh - 200px); min-height: 500px; }

@media (max-width: 768px) {
  .gt-a121__row--3col { grid-template-columns: 1fr; }
}
</style>
