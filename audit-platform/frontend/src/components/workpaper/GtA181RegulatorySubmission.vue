<!--
  GtA181RegulatorySubmission.vue — A18-1 向监管部门报送审计小结

  极简专属组件：3 区块（收件人 + 正文 + 签发）
  - 收件人: 固定前缀"致：" + bureau input + 固定后缀
  - 正文: 只读段落 + 自动填充 client/year + 联系人/电话
  - 签发: firm(只读) + partner input + date-picker
-->
<template>
  <div class="gt-a181">
    <div class="gt-a181__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a181__save-status">
        <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
        <template v-else-if="saveStatus === 'saved' && lastSavedAt">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <div v-if="mode === '结构化视图'" class="gt-a181__content">
      <el-skeleton v-if="loading" :rows="6" animated />
      <template v-else>
        <!-- 区块1: 收件人 -->
        <el-card class="gt-a181__card" shadow="never">
          <template #header><span class="gt-a181__card-title">收件人</span></template>
          <div class="gt-a181__recipient">
            <span class="gt-a181__prefix">致：</span>
            <el-input
              :model-value="recipient.bureau"
              size="small"
              :disabled="props.readonly"
              placeholder="请输入监管部门所在地"
              style="width: 160px"
              @change="(v: string) => updateField('recipient', 'bureau', v)"
            />
            <span class="gt-a181__suffix">财政局（证券监管局）</span>
          </div>
        </el-card>

        <!-- 区块2: 正文 -->
        <el-card class="gt-a181__card" shadow="never">
          <template #header><span class="gt-a181__card-title">正文</span></template>
          <div class="gt-a181__body">
            <p class="gt-a181__readonly-text">
              我们接受委托，审计了{{ projectContext.client_name || 'XX公司' }}{{ projectContext.audit_year || '202X' }}年度财务报表。
              按照有关规定，现将审计工作有关情况报送如下：
            </p>
            <p class="gt-a181__readonly-text gt-a181__readonly-text--muted">
              （正文内容按模板固定格式呈现，此处仅填写联系人信息）
            </p>
            <div class="gt-a181__body-fields">
              <div class="gt-a181__field">
                <label>项目联系人</label>
                <el-input
                  :model-value="body.contact_person"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="合伙人姓名"
                  @change="(v: string) => updateField('body', 'contact_person', v)"
                />
              </div>
              <div class="gt-a181__field">
                <label>联系电话</label>
                <el-input
                  :model-value="body.contact_phone"
                  size="small"
                  :disabled="props.readonly"
                  placeholder="联系电话"
                  @change="(v: string) => updateField('body', 'contact_phone', v)"
                />
              </div>
            </div>
          </div>
        </el-card>

        <!-- 区块3: 签发 -->
        <el-card class="gt-a181__card" shadow="never">
          <template #header><span class="gt-a181__card-title">签发</span></template>
          <div class="gt-a181__issuance">
            <div class="gt-a181__field">
              <label>事务所</label>
              <el-input :model-value="projectContext.firm_name" size="small" disabled />
            </div>
            <div class="gt-a181__field">
              <label>签字合伙人</label>
              <el-input
                :model-value="issuance.partner"
                size="small"
                :disabled="props.readonly"
                placeholder="签字合伙人"
                @change="(v: string) => updateField('issuance', 'partner', v)"
              />
            </div>
            <div class="gt-a181__field">
              <label>日期</label>
              <el-date-picker
                :model-value="issuance.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="签发日期"
                @change="(v: string) => updateField('issuance', 'date', v || '')"
              />
            </div>
          </div>
        </el-card>
      </template>
    </div>

    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A18-1" class="gt-a181__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useA181RegulatorySubmission } from './composables/useA181RegulatorySubmission'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

defineOptions({ name: 'GtA181RegulatorySubmission' })

const props = withDefaults(defineProps<{ wpId: string; readonly?: boolean }>(), { readonly: false })

const mode = ref('结构化视图')
const modeOptions = ['结构化视图', '在线编辑']

const wpIdRef = ref(props.wpId)
const {
  loading, recipient, body, issuance, projectContext,
  saveStatus, lastSavedAt, loadData, updateField, flushPendingSaves,
} = useA181RegulatorySubmission(wpIdRef)

onMounted(() => { loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a181 { padding: 16px; max-width: 800px; }
.gt-a181__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a181__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }
.gt-a181__content { display: flex; flex-direction: column; gap: 16px; }
.gt-a181__card { border-radius: 8px; }
.gt-a181__card-title { font-size: 15px; font-weight: 600; color: #303133; }
.gt-a181__recipient { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-a181__prefix { font-size: 14px; font-weight: 500; color: #303133; }
.gt-a181__suffix { font-size: 14px; color: #606266; }
.gt-a181__readonly-text { font-size: 14px; color: #303133; line-height: 1.8; margin: 0 0 12px; }
.gt-a181__readonly-text--muted { color: #909399; font-size: var(--wp-font-size, 13px); font-style: italic; }
.gt-a181__body-fields { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a181__issuance { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a181__field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; }
.gt-a181__field label { font-size: 12px; color: #909399; }
.gt-a181__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
