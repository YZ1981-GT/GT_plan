<template>
  <div class="g6-directory">
    <h3 class="sheet-title">底稿目录</h3>

    <el-alert
      v-if="classificationSummary"
      :type="classificationAlertType"
      :closable="false"
      show-icon
      class="classification-banner"
      :title="classificationBannerTitle"
    >
      <template #default>
        <span>{{ classificationSummary.message || '已从 G6-7/G6-8 回写分类摘要。' }}</span>
        <ul
          v-if="classificationSummary.instruments?.length"
          class="instrument-matrix"
        >
          <li
            v-for="row in classificationSummary.instruments"
            :key="row.instrumentId || row.instrumentName"
          >
            {{ row.instrumentName || row.instrumentId }}：
            SPPI {{ row.sppiOverall === 'pass' ? '通过' : row.sppiOverall === 'fail' ? '未通过' : '未完成' }}
            → {{ row.expectedClassification || '未定' }}
            <template v-if="row.accountConflict">（科目冲突）</template>
          </li>
        </ul>
      </template>
    </el-alert>

    <el-alert
      v-if="eclStatusError"
      type="warning"
      :closable="false"
      show-icon
      class="classification-banner"
      :title="eclStatusError"
    />

    <div class="directory-layout">
      <div class="entity-info">
        <el-descriptions :column="1" border size="small" class="info-desc">
          <el-descriptions-item label="被审计单位">{{ entityName || '——' }}</el-descriptions-item>
          <el-descriptions-item label="截止日">{{ balanceSheetDate || '——' }}</el-descriptions-item>
          <el-descriptions-item label="编制人">{{ preparer || '——' }}</el-descriptions-item>
          <el-descriptions-item label="复核人">{{ reviewer || '——' }}</el-descriptions-item>
        </el-descriptions>

        <div class="methodology-context">
          <div class="methodology-bar" />
          <div class="methodology-content">
            <strong>关于工作底稿与审计程序索引号对应的说明</strong>
            <p>本底稿目录涵盖G6其他债权投资全部底稿。索引号G6A为程序表，G6-1至G6-4为实质性程序底稿(审定表/明细表/坏账准备/调整分录)，附注分上市公司/国企两版，G0-1至G0-8为投资循环函证底稿。各底稿通过索引号实现交叉引用与跳转。</p>
          </div>
        </div>
      </div>

      <div class="directory-table">
        <el-table :data="directoryRows" border stripe style="width: 100%; font-size: 13px">
          <el-table-column prop="seq" label="序号" width="55" align="center" />
          <el-table-column prop="content" label="底稿名称" min-width="220" />
          <el-table-column label="底稿编码" width="120">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexCode" :value="row.indexCode" @click="emit('jump', row.indexCode)" />
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="preparer" label="编制人" width="80" />
          <el-table-column prop="prepareDate" label="编制日期" width="100" />
          <el-table-column prop="reviewer" label="复核人" width="80" />
          <el-table-column prop="reviewDate" label="复核日期" width="100" />
          <el-table-column label="页码" width="55" align="center">
            <template #default="{ row }">{{ row.pages || '-' }}</template>
          </el-table-column>
          <el-table-column label="备注" min-width="140">
            <template #default="{ row }">
              <span v-if="row.remarkHint" class="remark-hint">{{ row.remarkHint }}</span>
              <span v-else-if="row.status === 'done'" class="status-done">✓ 已完成</span>
              <span v-else-if="row.status === 'pending'" class="status-pending">○ 待完成</span>
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDirectory.vue — 底稿目录（29行×8列 只读）
 * 读取 G6-1-classification-summary，在 G6-7/G6-8/G6-1 行备注与顶部 banner 展示分类提示。
 */
import { computed, onMounted, ref } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG6MainFormData } from '../../composables/useG6MainFormData'
import {
  G6_CLASSIFICATION_SUMMARY_KEY,
  fetchG6ChecklistMap,
  parseG6ClassificationSummary,
  resolveG6EclWorkpaperDetailed,
  type G6ClassificationSummary,
} from '../../composables/g6CrossHelpers'
import {
  evaluateG6EclSuiteStatus,
  formatG6EclStatusRemark,
  type G6SheetStatus,
} from '../../composables/g6SuiteStatus'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ jump: [code: string] }>()

const entityName = ref(props.htmlData?.entityName || '')
const balanceSheetDate = ref(props.htmlData?.balanceSheetDate || '')
const preparer = ref(props.htmlData?.preparer || '')
const reviewer = ref(props.htmlData?.reviewer || '')

const formData = useG6MainFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const classificationSummary = ref<G6ClassificationSummary | null>(null)
const eclStatusByCode = ref<Record<string, G6SheetStatus>>({})
const eclStatusError = ref<string | null>(null)

const classificationAlertType = computed(() => {
  if (classificationSummary.value?.accountConflict || classificationSummary.value?.level === 'warning') {
    return 'warning'
  }
  if (classificationSummary.value?.level === 'ok') return 'success'
  return 'info'
})

const classificationBannerTitle = computed(() => {
  const s = classificationSummary.value
  if (!s) return ''
  const cls = s.expectedClassification || '未定'
  const conflict = s.accountConflict ? ' · 与「其他债权投资」科目定位可能冲突' : ''
  return `G6-7×G6-8 分类摘要：${cls}${conflict}`
})

interface DirectoryRow {
  seq: number
  content: string
  indexCode: string
  pages: string
  preparer: string
  prepareDate: string
  reviewer: string
  reviewDate: string
  remark: string
  status?: 'done' | 'pending' | ''
  remarkHint?: string
}

const baseRows: DirectoryRow[] = [
  { seq: 1, content: '其他债权投资实质性程序表', indexCode: 'G6A', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 2, content: '其他债权投资审定表', indexCode: 'G6-1', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 3, content: '其他债权投资明细表', indexCode: 'G6-2', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 4, content: '坏账准备测算表', indexCode: 'G6-3', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 5, content: '调整分录汇总', indexCode: 'G6-4', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 6, content: '附注披露信息（上市公司）', indexCode: 'G6-附注(上市)', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 7, content: '附注披露信息（国企）', indexCode: 'G6-附注(国企)', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 8, content: '底稿目录', indexCode: 'G6-目录', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 9, content: '公允价值测试表', indexCode: 'G6-5', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 10, content: '实际利率法利息测算', indexCode: 'G6-6', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 11, content: '业务模式分析', indexCode: 'G6-7', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 12, content: 'SPPI合同现金流测试', indexCode: 'G6-8', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 13, content: '有价证券盘点表', indexCode: 'G6-9', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 14, content: '盘点倒轧表', indexCode: 'G6-10', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 15, content: '三阶段划分检查', indexCode: 'G6-11', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 16, content: '减值准备测算表', indexCode: 'G6-12', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 17, content: '预期信用损失计量', indexCode: 'G6-13', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 18, content: '转回核销检查', indexCode: 'G6-14', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 19, content: '凭证检查表', indexCode: 'G6-15', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 20, content: '函证控制表', indexCode: 'G0-1', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 21, content: '函证发出清单', indexCode: 'G0-2', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 22, content: '函证回收统计', indexCode: 'G0-3', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 23, content: '差异核对表', indexCode: 'G0-4', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 24, content: '替代程序底稿', indexCode: 'G0-5', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 25, content: '函证样本表', indexCode: 'G0-6', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 26, content: '函证模板-证券', indexCode: 'G0-7', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 27, content: '函证模板-债券', indexCode: 'G0-8', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 28, content: '审计说明', indexCode: '', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
  { seq: 29, content: '审计结论', indexCode: '', pages: '', preparer: '', prepareDate: '', reviewer: '', reviewDate: '', remark: '', status: '' },
]

const directoryRows = computed(() => {
  const s = classificationSummary.value
  const ecl = eclStatusByCode.value
  return baseRows.map((row) => {
    const eclStatus = ecl[row.indexCode]
    if (eclStatus) {
      return {
        ...row,
        status: eclStatus.hasData && eclStatus.tone === 'ok' ? 'done' : eclStatus.hasData ? 'pending' : '',
        remarkHint: formatG6EclStatusRemark(eclStatus),
      }
    }
    if (!s) return { ...row }
    if (row.indexCode === 'G6-7') {
      return {
        ...row,
        remarkHint: s.businessModelLabel
          ? `业务模式：${s.businessModelLabel}`
          : (s.businessModel || ''),
      }
    }
    if (row.indexCode === 'G6-8') {
      return {
        ...row,
        remarkHint: s.sppiOverall
          ? `SPPI：${s.sppiOverall === 'pass' ? '通过' : s.sppiOverall === 'fail' ? '未通过' : s.sppiOverall}`
          : '',
      }
    }
    if (row.indexCode === 'G6-1' && s.expectedClassification) {
      return {
        ...row,
        remarkHint: s.accountConflict
          ? `预期 ${s.expectedClassification}（科目冲突）`
          : `预期分类：${s.expectedClassification}`,
      }
    }
    return { ...row }
  })
})

onMounted(async () => {
  await formData.loadAll()
  classificationSummary.value = parseG6ClassificationSummary(
    formData.allResponses.value.get(G6_CLASSIFICATION_SUMMARY_KEY),
  )
  eclStatusError.value = null
  try {
    // 目录在 Main 实例：不得把 Main wp 回退成 ECL 目标
    const resolved = await resolveG6EclWorkpaperDetailed(
      props.projectId,
      undefined,
      { allowFallback: false },
    )
    if (!resolved.wpId) {
      eclStatusError.value = resolved.error || '未解析到 ECL 底稿实例，G6-11~15 状态暂不可用'
      return
    }
    const map = await fetchG6ChecklistMap(resolved.wpId)
    const statuses = evaluateG6EclSuiteStatus(map)
    eclStatusByCode.value = Object.fromEntries(statuses.map((item) => [item.code, item]))
  } catch {
    eclStatusError.value = '读取 ECL 编制状态失败'
  }
})
</script>

<style scoped>
.g6-directory { padding: 12px; font-size: var(--wp-font-size, 13px); }
.sheet-title { margin: 0 0 16px; font-size: 15px; font-weight: 600; }
.classification-banner { margin-bottom: 12px; }
.instrument-matrix {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.6;
}

.directory-layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
@media (max-width: 900px) { .directory-layout { grid-template-columns: 1fr; } }

.entity-info { display: flex; flex-direction: column; gap: 12px; }
.info-desc { width: 100%; }

.methodology-context { position: relative; padding: 12px 12px 12px 16px; background: #fffbe6; border-radius: 4px; }
.methodology-bar { position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: #d48806; border-radius: 4px 0 0 4px; }
.methodology-content { font-size: 12px; color: #614700; }
.methodology-content strong { display: block; margin-bottom: 4px; font-size: var(--wp-font-size, 13px); }
.methodology-content p { margin: 0; line-height: 1.6; }

.directory-table { overflow: auto; }
.status-done { color: #52c41a; font-size: 12px; }
.status-pending { color: #909399; font-size: 12px; }
.remark-hint { color: #b45309; font-size: 12px; line-height: 1.4; }
</style>
