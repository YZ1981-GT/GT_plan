<!--
  GtA182RegulatoryCommunication.vue — A18-2 与监管层沟通函

  5 区块卡片（收件人 + 引言折叠 + 4事项适用性 + 双签签发 + 提示折叠）
  - 收件人: el-select (3 options) + 条件 el-input (custom)
  - 引言: el-collapse 2 段只读文字 + auto-fill client/year
  - 4 事项: v-for cards, el-radio-group (Y/N/NA) + conditional textarea
  - 签发: firm(read-only) + CPA1 + CPA2 + date-picker
  - 提示: el-collapse 2 tables (read-only)
-->
<template>
  <div class="gt-a182">
    <div class="gt-a182__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <div class="gt-a182__toolbar-right">
        <el-tooltip content="AI辅助（即将上线）" placement="top">
          <el-button size="small" disabled>
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </el-tooltip>
        <span class="gt-a182__save-status">
          <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
          <template v-else-if="saveStatus === 'saved' && lastSavedAt">✓ 已保存</template>
          <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
        </span>
      </div>
    </div>

    <div v-if="mode === '结构化视图'" class="gt-a182__content">
      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-else>
        <!-- 区块1: 收件人 -->
        <el-card class="gt-a182__card" shadow="never">
          <template #header><span class="gt-a182__card-title">收件人</span></template>
          <div class="gt-a182__recipient">
            <span class="gt-a182__prefix">致：</span>
            <el-select
              :model-value="recipient.authority"
              size="small"
              :disabled="props.readonly"
              placeholder="选择监管机构"
              style="width: 240px"
              @change="(v: string) => updateRecipient('authority', v)"
            >
              <el-option label="中国证券监督管理委员会" value="中国证券监督管理委员会" />
              <el-option label="中国银行保险监督管理委员会" value="中国银行保险监督管理委员会" />
              <el-option label="其他" value="其他" />
            </el-select>
            <el-input
              v-if="recipient.authority === '其他'"
              :model-value="recipient.custom"
              size="small"
              :disabled="props.readonly"
              placeholder="请输入监管机构名称"
              style="width: 200px"
              @change="(v: string) => updateRecipient('custom', v)"
            />
          </div>
        </el-card>

        <!-- 区块2: 引言 -->
        <el-card class="gt-a182__card" shadow="never">
          <template #header><span class="gt-a182__card-title">引言</span></template>
          <el-collapse v-model="introCollapse">
            <el-collapse-item title="沟通目的与依据" name="intro">
              <p class="gt-a182__readonly-text">
                根据《中国注册会计师审计准则第1151号——与治理层的沟通》和《中国注册会计师审计准则第1152号——向治理层和管理层通报内部控制缺陷》的规定，我们将在审计{{ projectContext.client_name || 'XX公司' }}{{ projectContext.audit_year || '202X' }}年度财务报表过程中识别的以下事项向贵方沟通。
              </p>
              <p class="gt-a182__readonly-text gt-a182__readonly-text--muted">
                本沟通函仅用于上述目的，不得用于其他目的。本沟通函仅供贵方使用，未经我们书面许可，不得将其内容向第三方披露。
              </p>
            </el-collapse-item>
          </el-collapse>
        </el-card>

        <!-- 区块3: 4 事项卡片 -->
        <el-card
          v-for="matter in matters"
          :key="matter.id"
          class="gt-a182__card"
          shadow="never"
        >
          <template #header>
            <span class="gt-a182__card-title">{{ matter.id }}. {{ matter.title }}</span>
          </template>
          <div class="gt-a182__matter">
            <div class="gt-a182__matter-applicability">
              <span class="gt-a182__label">适用性：</span>
              <el-radio-group
                :model-value="matter.applicability"
                :disabled="props.readonly"
                size="small"
                @change="(v: string) => updateMatter(matter.id, 'applicability', v)"
              >
                <el-radio value="Y">适用</el-radio>
                <el-radio value="N">不适用</el-radio>
                <el-radio value="NA">不涉及</el-radio>
              </el-radio-group>
            </div>
            <el-input
              v-show="matter.applicability === 'Y'"
              :model-value="matter.content"
              type="textarea"
              :autosize="{ minRows: 4 }"
              :disabled="props.readonly"
              placeholder="请描述沟通事项内容"
              @change="(v: string) => updateMatter(matter.id, 'content', v)"
            />
          </div>
        </el-card>

        <!-- 区块4: 签发 -->
        <el-card class="gt-a182__card" shadow="never">
          <template #header><span class="gt-a182__card-title">签发</span></template>
          <div class="gt-a182__issuance">
            <div class="gt-a182__field">
              <label>事务所</label>
              <el-input :model-value="projectContext.firm_name" size="small" disabled />
            </div>
            <div class="gt-a182__field">
              <label>中国注册会计师（1）</label>
              <el-input
                :model-value="issuance.cpa1"
                size="small"
                :disabled="props.readonly"
                placeholder="签字注册会计师"
                @change="(v: string) => updateIssuance('cpa1', v)"
              />
            </div>
            <div class="gt-a182__field">
              <label>中国注册会计师（2）</label>
              <el-input
                :model-value="issuance.cpa2"
                size="small"
                :disabled="props.readonly"
                placeholder="签字注册会计师"
                @change="(v: string) => updateIssuance('cpa2', v)"
              />
            </div>
            <div class="gt-a182__field">
              <label>日期</label>
              <el-date-picker
                :model-value="issuance.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="签发日期"
                @change="(v: string) => updateIssuance('date', v || '')"
              />
            </div>
          </div>
        </el-card>

        <!-- 区块5: 提示 -->
        <el-card class="gt-a182__card" shadow="never">
          <template #header><span class="gt-a182__card-title">参考提示</span></template>
          <el-collapse v-model="guidanceCollapse">
            <el-collapse-item title="审计准则要求" name="guidance1">
              <table class="gt-a182__guidance-table">
                <thead><tr><th>条款</th><th>要求</th></tr></thead>
                <tbody>
                  <tr><td>CAS 1151.14</td><td>注册会计师应当就审计中发现的舞弊向治理层通报</td></tr>
                  <tr><td>CAS 1151.15</td><td>注册会计师应当就审计中注意到的重大违反法律法规行为向治理层通报</td></tr>
                  <tr><td>CAS 1152.09</td><td>注册会计师应当以书面形式向治理层通报审计中识别出的重大缺陷</td></tr>
                </tbody>
              </table>
            </el-collapse-item>
            <el-collapse-item title="沟通事项分类说明" name="guidance2">
              <table class="gt-a182__guidance-table">
                <thead><tr><th>类别</th><th>说明</th></tr></thead>
                <tbody>
                  <tr><td>舞弊</td><td>管理层、员工或第三方有意实施的欺骗行为</td></tr>
                  <tr><td>违法行为</td><td>违反法律法规的行为（已发生或可能发生）</td></tr>
                  <tr><td>不一致/错报</td><td>年度报告中信息与已审计财务报表之间的重大不一致</td></tr>
                  <tr><td>其他事项</td><td>审计中注意到的其他需要治理层关注的事项</td></tr>
                </tbody>
              </table>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </template>
    </div>

    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A18-2" class="gt-a182__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading, MagicStick } from '@element-plus/icons-vue'
import { useA182RegulatoryCommunication } from './composables/useA182RegulatoryCommunication'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

defineOptions({ name: 'GtA182RegulatoryCommunication' })

const props = withDefaults(defineProps<{ wpId: string; readonly?: boolean }>(), { readonly: false })

const mode = ref('结构化视图')
const modeOptions = ['结构化视图', '在线编辑']
const introCollapse = ref<string[]>([])
const guidanceCollapse = ref<string[]>([])

const wpIdRef = ref(props.wpId)
const {
  loading, recipient, matters, issuance, projectContext,
  saveStatus, lastSavedAt, loadData, updateRecipient, updateMatter, updateIssuance, flushPendingSaves,
} = useA182RegulatoryCommunication(wpIdRef)

onMounted(() => { loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a182 { padding: 16px; max-width: 860px; }
.gt-a182__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a182__toolbar-right { display: flex; align-items: center; gap: 12px; }
.gt-a182__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }
.gt-a182__content { display: flex; flex-direction: column; gap: 16px; }
.gt-a182__card { border-radius: 8px; }
.gt-a182__card-title { font-size: 15px; font-weight: 600; color: #303133; }
.gt-a182__recipient { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-a182__prefix { font-size: 14px; font-weight: 500; color: #303133; }
.gt-a182__readonly-text { font-size: 14px; color: #303133; line-height: 1.8; margin: 0 0 12px; }
.gt-a182__readonly-text--muted { color: #909399; font-size: var(--wp-font-size, 13px); font-style: italic; }
.gt-a182__matter { display: flex; flex-direction: column; gap: 12px; }
.gt-a182__matter-applicability { display: flex; align-items: center; gap: 8px; }
.gt-a182__label { font-size: var(--wp-font-size, 13px); color: #606266; white-space: nowrap; }
.gt-a182__issuance { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a182__field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; }
.gt-a182__field label { font-size: 12px; color: #909399; }
.gt-a182__guidance-table { width: 100%; border-collapse: collapse; font-size: var(--wp-font-size, 13px); }
.gt-a182__guidance-table th,
.gt-a182__guidance-table td { border: 1px solid #ebeef5; padding: 8px 12px; text-align: left; }
.gt-a182__guidance-table th { background: #f5f7fa; font-weight: 500; color: #606266; }
.gt-a182__guidance-table td { color: #303133; }
.gt-a182__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
