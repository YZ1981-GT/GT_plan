<script setup lang="ts">
/**
 * D2TabBizModel — 业务模式D2-13
 * QA卡片: 4个Y/N判断 + 业务模式组合表(5列) + 推荐模式高亮
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2BizModel } from '../composables/useD2BizModel'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const {
  judgments,
  groups,
  allAnswered,
  recommendedModel,
  updateJudgment,
  updateGroup,
  addGroup,
  removeGroup,
} = useD2BizModel({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-13',
)
</script>

<template>
  <div class="d2-tab-bizmodel">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag type="info" size="small">业务模式判定 (CAS 22)</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
    </div>

    <!-- 推荐业务模式 -->
    <el-alert
      v-if="allAnswered && recommendedModel"
      type="success"
      :closable="false"
      class="recommend-alert"
    >
      <template #title>
        <span style="font-weight:600">推荐业务模式: {{ recommendedModel }}</span>
      </template>
    </el-alert>

    <!-- QA判断卡片 -->
    <div class="qa-cards">
      <el-card
        v-for="j in judgments"
        :key="j.questionId"
        shadow="hover"
        class="qa-card"
      >
        <div class="qa-question">
          {{ j.question }}
          <GtReviewTrigger :section-id="`D2-bizmodel-judgment-${j.questionId}`" />
        </div>
        <div class="qa-answer">
          <el-radio-group
            :model-value="j.answer"
            :disabled="isReadonly"
            @change="(v: string) => updateJudgment(j.questionId, 'answer', v)"
          >
            <el-radio-button value="Y">是</el-radio-button>
            <el-radio-button value="N">否</el-radio-button>
          </el-radio-group>
        </div>
        <div class="qa-explanation">
          <el-input
            :model-value="j.explanation"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="判断依据..."
            @change="(v: string) => updateJudgment(j.questionId, 'explanation', v)"
          />
        </div>
      </el-card>
    </div>

    <!-- 业务模式组合表 -->
    <div class="group-section">
      <div class="section-header">
        <span class="section-title">业务模式组合判定</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addGroup">添加组合</el-button>
      </div>
      <el-table :data="groups" border size="small" style="width: 100%">
        <el-table-column label="组合名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.groupName" size="small" @change="(v: string) => updateGroup(row.rowId, 'groupName', v)" />
            <span v-else>{{ row.groupName || '-' }}</span>
            <GtReviewDot row-prefix="D2-bizmodel-group" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="业务模式" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.bizModel" size="small" @change="(v: string) => updateGroup(row.rowId, 'bizModel', v)" />
            <span v-else>{{ row.bizModel || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="SPPI结果" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.sppiResult" size="small" @change="(v: string) => updateGroup(row.rowId, 'sppiResult', v)">
              <el-option label="通过" value="通过" />
              <el-option label="未通过" value="未通过" />
            </el-select>
            <span v-else>{{ row.sppiResult || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计量基础" width="160">
          <template #default="{ row }">{{ row.measurementBasis || '-' }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeGroup(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-bizmodel { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.recommend-alert { margin-bottom: 16px; }
.qa-cards { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.qa-card { }
.qa-question { font-size: 14px; font-weight: 500; margin-bottom: 8px; }
.qa-answer { margin-bottom: 8px; }
.qa-explanation { }
.group-section { }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; }
</style>
