<!--
  GtA81OtherInfoRepresentation.vue — A8-1 管理层对审计报告日后公布其他信息的书面声明

  专属组件：6 条声明卡片 + 签字区
  - Statement 1/4/5: 文件清单 (el-tag 增删)
  - Statement 2: 日期选择器
  - Statement 3: Y/N radio + 条件 textarea
  - Statement 6: textarea
  - 签字区: 公司名(自动填充) + 法定代表人 + 日期
-->
<template>
  <div class="gt-a81">
    <div class="gt-a81__toolbar">
      <el-segmented v-model="mode" :options="modeOptions" size="small" />
      <span class="gt-a81__save-status">
        <template v-if="saveStatus === 'saving'"><el-icon class="is-loading"><Loading /></el-icon> 保存中...</template>
        <template v-else-if="saveStatus === 'saved' && lastSavedAt">✓ 已保存</template>
        <template v-else-if="saveStatus === 'unsaved'">○ 未保存</template>
      </span>
    </div>

    <div v-if="mode === '结构化视图'" class="gt-a81__content">
      <el-skeleton v-if="loading" :rows="8" animated />
      <template v-else>
        <!-- 编制指导 -->
        <el-collapse class="gt-a81__guidance">
          <el-collapse-item title="编制指导" name="guidance">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>A8-1 管理层对其他信息的书面声明</template>
              <p>本声明书用于管理层就审计报告日后公布的其他信息向注册会计师作出的书面声明。</p>
              <p>依据：CAS 1521《注册会计师对其他信息的责任》</p>
              <p>管理层需确认其他信息与财务报表的一致性，并对其他信息的完整性和准确性承担责任。</p>
            </el-alert>
          </el-collapse-item>
        </el-collapse>

        <!-- 抬头 -->
        <div class="gt-a81__header">
          <h3>{{ projectContext.clientName || 'XX公司' }}</h3>
          <p class="gt-a81__addressee">
            致：致同会计师事务所（特殊普通合伙）
            <template v-if="projectContext.cpaNames.length">
              <br />{{ projectContext.cpaNames.join('、') }} 中国注册会计师
            </template>
          </p>
        </div>

        <!-- 引言段 -->
        <div class="gt-a81__intro">
          <p>
            本声明书依据贵所对本公司{{ projectContext.clientName ? '（' + projectContext.clientName + '）' : '' }}财务报表实施审计的需要而出具，
            旨在就审计报告日后公布的其他信息作出声明。
          </p>
        </div>

        <!-- 声明第1条：年度报告文件清单 -->
        <el-card class="gt-a81__card" shadow="never">
          <template #header>
            <div class="gt-a81__card-header">
              <span class="gt-a81__card-num">1</span>
              <span class="gt-a81__card-title">本公司年度报告包含以下文件：</span>
              <el-button size="small" type="primary" plain disabled class="gt-a81__ai-btn">
                <el-icon><MagicStick /></el-icon> AI
              </el-button>
            </div>
          </template>
          <div class="gt-a81__file-list">
            <el-tag
              v-for="(file, idx) in statements[1].files"
              :key="idx"
              :closable="!props.readonly"
              type="info"
              class="gt-a81__file-tag"
              @close="removeFile(1, idx)"
            >{{ file }}</el-tag>
            <div v-if="!props.readonly" class="gt-a81__file-add">
              <el-input
                v-model="newFileInputs[1]"
                size="small"
                placeholder="输入文件名称"
                style="width: 200px"
                @keyup.enter="handleAddFile(1)"
              />
              <el-button size="small" type="primary" plain @click="handleAddFile(1)">添加</el-button>
            </div>
          </div>
        </el-card>

        <!-- 声明第2条：计划公布日期 -->
        <el-card class="gt-a81__card" shadow="never">
          <template #header>
            <div class="gt-a81__card-header">
              <span class="gt-a81__card-num">2</span>
              <span class="gt-a81__card-title">本公司计划于以下日期公布上述年度报告：</span>
            </div>
          </template>
          <el-date-picker
            :model-value="statements[2].date"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="props.readonly"
            placeholder="选择计划公布日期"
            @change="(v: string) => updateStatement(2, 'date', v || '')"
          />
        </el-card>

        <!-- 声明第3条：一致性确认 -->
        <el-card class="gt-a81__card" shadow="never">
          <template #header>
            <div class="gt-a81__card-header">
              <span class="gt-a81__card-num">3</span>
              <span class="gt-a81__card-title">本公司确认上述其他信息与已审计财务报表中的信息是否一致：</span>
            </div>
          </template>
          <div class="gt-a81__consistency">
            <el-radio-group
              :model-value="statements[3].consistency"
              :disabled="props.readonly"
              @change="(v: string) => updateStatement(3, 'consistency', v)"
            >
              <el-radio value="Y">一致</el-radio>
              <el-radio value="N">不一致</el-radio>
            </el-radio-group>
            <el-input
              v-if="statements[3].consistency === 'N'"
              :model-value="statements[3].explanation"
              type="textarea"
              :rows="3"
              :disabled="props.readonly"
              placeholder="请说明不一致事项"
              class="gt-a81__explanation"
              @change="(v: string) => updateStatement(3, 'explanation', v)"
            />
          </div>
        </el-card>

        <!-- 声明第4条：审计报告日前提交文件 -->
        <el-card class="gt-a81__card" shadow="never">
          <template #header>
            <div class="gt-a81__card-header">
              <span class="gt-a81__card-num">4</span>
              <span class="gt-a81__card-title">审计报告日前已提交给注册会计师审阅的文件：</span>
            </div>
          </template>
          <div class="gt-a81__file-list">
            <el-tag
              v-for="(file, idx) in statements[4].files"
              :key="idx"
              :closable="!props.readonly"
              type="info"
              class="gt-a81__file-tag"
              @close="removeFile(4, idx)"
            >{{ file }}</el-tag>
            <div v-if="!props.readonly" class="gt-a81__file-add">
              <el-input
                v-model="newFileInputs[4]"
                size="small"
                placeholder="输入文件名称"
                style="width: 200px"
                @keyup.enter="handleAddFile(4)"
              />
              <el-button size="small" type="primary" plain @click="handleAddFile(4)">添加</el-button>
            </div>
          </div>
        </el-card>

        <!-- 声明第5条：审计报告日后提供文件 -->
        <el-card class="gt-a81__card" shadow="never">
          <template #header>
            <div class="gt-a81__card-header">
              <span class="gt-a81__card-num">5</span>
              <span class="gt-a81__card-title">审计报告日后将提供给注册会计师的文件：</span>
            </div>
          </template>
          <div class="gt-a81__file-list">
            <el-tag
              v-for="(file, idx) in statements[5].files"
              :key="idx"
              :closable="!props.readonly"
              type="info"
              class="gt-a81__file-tag"
              @close="removeFile(5, idx)"
            >{{ file }}</el-tag>
            <div v-if="!props.readonly" class="gt-a81__file-add">
              <el-input
                v-model="newFileInputs[5]"
                size="small"
                placeholder="输入文件名称"
                style="width: 200px"
                @keyup.enter="handleAddFile(5)"
              />
              <el-button size="small" type="primary" plain @click="handleAddFile(5)">添加</el-button>
            </div>
          </div>
        </el-card>

        <!-- 声明第6条：其他事项 -->
        <el-card class="gt-a81__card" shadow="never">
          <template #header>
            <div class="gt-a81__card-header">
              <span class="gt-a81__card-num">6</span>
              <span class="gt-a81__card-title">其他事项</span>
            </div>
          </template>
          <el-input
            :model-value="statements[6].other"
            type="textarea"
            :rows="3"
            :disabled="props.readonly"
            placeholder="如无其他事项，可留空"
            @change="(v: string) => updateStatement(6, 'other', v)"
          />
        </el-card>

        <!-- 签字区 -->
        <el-card class="gt-a81__card gt-a81__signature" shadow="never">
          <template #header><span class="gt-a81__card-title">签字</span></template>
          <div class="gt-a81__signature-content">
            <div class="gt-a81__field">
              <label>公司名称</label>
              <el-input :model-value="projectContext.clientName || 'XX公司'" size="small" disabled />
            </div>
            <div class="gt-a81__field">
              <label>法定代表人签字</label>
              <el-input
                :model-value="signatureData.representative || ''"
                size="small"
                :disabled="props.readonly"
                placeholder="法定代表人签字"
                @change="(v: string) => updateSignature('representative', v)"
              />
            </div>
            <div class="gt-a81__field">
              <label>日期</label>
              <el-date-picker
                :model-value="signatureData.signatureDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="props.readonly"
                placeholder="签字日期"
                @change="(v: string) => updateSignature('date', v || '')"
              />
            </div>
          </div>
        </el-card>
      </template>
    </div>

    <GtOnlyOfficeSheet v-else :wp-id="props.wpId" sheet-name="A8-1" class="gt-a81__oo" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading, MagicStick } from '@element-plus/icons-vue'
import { useA81OtherInfoRepresentation } from './composables/useA81OtherInfoRepresentation'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

defineOptions({ name: 'GtA81OtherInfoRepresentation' })

const props = withDefaults(defineProps<{ wpId: string; readonly?: boolean }>(), { readonly: false })

const mode = ref('结构化视图')
const modeOptions = ['结构化视图', '在线编辑']

const newFileInputs = reactive<Record<number, string>>({ 1: '', 4: '', 5: '' })

const wpIdRef = ref(props.wpId)
const {
  loading, statements, signatureData, projectContext,
  saveStatus, lastSavedAt,
  loadData, addFile, removeFile, updateStatement, updateSignature, flushPendingSaves,
} = useA81OtherInfoRepresentation(wpIdRef)

function handleAddFile(statementNum: 1 | 4 | 5) {
  const value = newFileInputs[statementNum]
  if (value?.trim()) {
    addFile(statementNum, value)
    newFileInputs[statementNum] = ''
  }
}

onMounted(() => { loadData(props.wpId) })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a81 { padding: 16px; max-width: 860px; }
.gt-a81__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.gt-a81__save-status { font-size: 12px; color: #909399; display: inline-flex; align-items: center; gap: 4px; }
.gt-a81__content { display: flex; flex-direction: column; gap: 16px; }
.gt-a81__guidance { margin-bottom: 8px; }
.gt-a81__header { text-align: center; margin-bottom: 16px; }
.gt-a81__header h3 { margin: 0 0 8px; font-size: 18px; color: #303133; }
.gt-a81__addressee { font-size: 14px; color: #606266; margin: 0; }
.gt-a81__intro { margin-bottom: 16px; }
.gt-a81__intro p { font-size: 14px; color: #909399; font-style: italic; line-height: 1.8; margin: 0; }
.gt-a81__card { border-radius: 8px; }
.gt-a81__card-header { display: flex; align-items: center; gap: 8px; }
.gt-a81__card-num { width: 24px; height: 24px; background: #409EFF; color: #fff; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: var(--wp-font-size, 13px); font-weight: 600; flex-shrink: 0; }
.gt-a81__card-title { font-size: 14px; font-weight: 500; color: #303133; flex: 1; }
.gt-a81__ai-btn { margin-left: auto; }
.gt-a81__file-list { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.gt-a81__file-tag { margin: 0; }
.gt-a81__file-add { display: flex; gap: 8px; align-items: center; margin-top: 8px; width: 100%; }
.gt-a81__consistency { display: flex; flex-direction: column; gap: 12px; }
.gt-a81__explanation { margin-top: 8px; }
.gt-a81__signature-content { display: flex; gap: 16px; flex-wrap: wrap; }
.gt-a81__field { display: flex; flex-direction: column; gap: 4px; min-width: 180px; }
.gt-a81__field label { font-size: 12px; color: #909399; }
.gt-a81__oo { height: calc(100vh - 200px); min-height: 500px; }
</style>
