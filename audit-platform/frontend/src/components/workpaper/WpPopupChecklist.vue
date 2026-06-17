<script setup lang="ts">
/**
 * WpPopupChecklist — A1-12 重大事项决定程序的履行情况核查表
 *
 * 14 条需提交专业技术委员会讨论的情形（是否适用+索引号）
 * + 第二部分自由文本区（重大业务咨询/分歧事项）
 * 数据保存到 checklist_responses（item_id: A1-12-001~014 + A1-12-section2）
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

const ITEMS = [
  { id: 'A1-12-001', seq: 1, content: '首次承接后的境内上市公司、H股上市公司、境外上市公司的首份业务报告（A1）；' },
  { id: 'A1-12-002', seq: 2, content: '首次承接的新三板已挂牌公司、非上市公众公司的首份业务报告（A2）；' },
  { id: 'A1-12-003', seq: 3, content: '首次申请新三板挂牌的业务报告，股转公司终止审核后重新申请新三板挂牌的业务报告（A2）；' },
  { id: 'A1-12-004', seq: 4, content: '需经中国证监会核准或交易场所审核的重大资产重组、非本所上市公司客户涉及重大资产重组业绩承诺完成情况或承诺期届满减值测试的审核报告（A3）；' },
  { id: 'A1-12-005', seq: 5, content: '首次承接的未上市银行和未上市保险公司的首份业务报告（A5）；' },
  { id: 'A1-12-006', seq: 6, content: 'IPO公司的首次申报业务报告，证监会、交易所终止审核后重新申报的业务报告（A6）；' },
  { id: 'A1-12-007', seq: 7, content: '首次承接发行企业债券、公司债券及非金融企业债务融资工具的相关业务报告（A7，包括以前年度分类为C类业务）；' },
  { id: 'A1-12-008', seq: 8, content: '首次承接的证券交易所、期货交易所、证券公司的首份业务报告（A8）；' },
  { id: 'A1-12-009', seq: 9, content: '拟出具或消除以前出具的非无保留意见（包括保留意见、否定意见或无法表示意见）的A类、B类业务报告；' },
  { id: 'A1-12-010', seq: 10, content: '拟出具或消除以前出具的带有解释性说明段落（包括与持续经营的重大不确定性段、强调事项段和其他事项段）的A类、B类业务报告；' },
  { id: 'A1-12-011', seq: 11, content: '拟出具的包括其他信息段且其他信息存在未更正重大错报的A类、B类业务报告；' },
  { id: 'A1-12-012', seq: 12, content: '存在专业分歧的业务报告，包括：项目合伙人与专业咨询意见之间、项目合伙人与质量控制复核人之间、项目合伙人与项目质量复核合伙人之间；' },
  { id: 'A1-12-013', seq: 13, content: '评价为高风险的保持业务并经业务质量控制委员会或质量管理主管合伙人、项目质量复核合伙人认定审核的业务报告；' },
  { id: 'A1-12-014', seq: 14, content: '项目合伙人、质量管理主管合伙人认为必要的C类业务报告。' },
]

interface ItemState { applicable: string | null; wpRef: string }
const itemStates = ref<Record<string, ItemState>>({})
const section2Text = ref('')
const loading = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)

const allMarked = computed(() => ITEMS.every(i => itemStates.value[i.id]?.applicable))

function initStates() {
  for (const item of ITEMS) {
    if (!itemStates.value[item.id]) {
      itemStates.value[item.id] = { applicable: null, wpRef: '' }
    }
  }
}

async function loadData() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = Array.isArray(res) ? res : (res?.data ?? [])
    for (const r of list) {
      if (r.item_id?.startsWith('A1-12-') && r.item_id !== 'A1-12-section2') {
        itemStates.value[r.item_id] = { applicable: r.conclusion, wpRef: r.wp_ref || '' }
      }
      if (r.item_id === 'A1-12-section2') {
        section2Text.value = r.remark || ''
      }
    }
  } catch { /* ignore */ }
  finally { loading.value = false }
}

function scheduleSave() {
  if (saveTimer.value) clearTimeout(saveTimer.value)
  saveTimer.value = setTimeout(doSave, 2000)
}

async function doSave() {
  if (!props.wpId || !props.projectId) return
  const items = ITEMS.map(item => ({
    item_id: item.id,
    conclusion: itemStates.value[item.id]?.applicable || null,
    remark: null,
    wp_ref: itemStates.value[item.id]?.wpRef || null,
  }))
  items.push({ item_id: 'A1-12-section2', conclusion: null, remark: section2Text.value || null, wp_ref: null })
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, { project_id: props.projectId, items })
    emit('save')
    if (allMarked.value) emit('completed')
  } catch (err: any) {
    if (err?.message !== 'canceled' && err?.code !== 'ERR_CANCELED') ElMessage.error('保存失败')
  }
}

function updateApplicable(id: string, val: string) { itemStates.value[id].applicable = val || null; scheduleSave() }
function updateWpRef(id: string, val: string) { itemStates.value[id].wpRef = val; scheduleSave() }
function updateSection2(val: string) { section2Text.value = val; scheduleSave() }

onMounted(() => { initStates(); loadData() })
onBeforeUnmount(() => { if (saveTimer.value) { clearTimeout(saveTimer.value); doSave() } })
</script>

<template>
  <div class="wp-popup-checklist" v-loading="loading">
    <!-- 标题区 -->
    <div class="checklist-header">
      <div class="checklist-header__title">一、需提交专业技术委员会会议讨论、决策后出具报告的情形</div>
    </div>

    <!-- 14条列表 -->
    <div class="checklist-items">
      <div class="checklist-items__header">
        <span class="col-seq">序号</span>
        <span class="col-desc">情形描述</span>
        <span class="col-applicable">是否适用</span>
        <span class="col-wpref">如适用，索引号</span>
      </div>
      <div
        v-for="item in ITEMS"
        :key="item.id"
        class="checklist-item"
        :class="{ 'is-marked': itemStates[item.id]?.applicable }"
      >
        <span class="col-seq">{{ item.seq }}</span>
        <span class="col-desc">{{ item.content }}</span>
        <span class="col-applicable">
          <el-select
            :model-value="itemStates[item.id]?.applicable || ''"
            size="small"
            placeholder="—"
            style="width: 80px"
            @change="(val: string) => updateApplicable(item.id, val)"
          >
            <el-option label="是" value="Y" />
            <el-option label="否" value="N" />
          </el-select>
        </span>
        <span class="col-wpref">
          <el-input
            :model-value="itemStates[item.id]?.wpRef || ''"
            size="small"
            placeholder="索引号"
            style="width: 100px"
            @input="(val: string) => updateWpRef(item.id, val)"
          />
        </span>
      </div>
    </div>

    <!-- 第二部分 -->
    <div class="checklist-section2">
      <div class="checklist-section2__title">二、提交专业技术委员会讨论、决策的重大业务咨询或业务分歧事项</div>
      <el-input
        type="textarea"
        :rows="4"
        :model-value="section2Text"
        placeholder="填写重大业务咨询或业务分歧事项..."
        @input="updateSection2"
      />
    </div>

    <!-- 底部注释 -->
    <div class="checklist-notes">
      <p>注1: 本表仅适用于审计业务。</p>
      <p>注2: 本表适用于A、B类业务；执行A、B类复核流程的C类业务或存在专业分歧需经专业技术委员会审核的C类业务。</p>
    </div>
  </div>
</template>

<style scoped>
.wp-popup-checklist { padding: 8px 0; }

.checklist-header__title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.checklist-items__header {
  display: flex;
  align-items: center;
  padding: 6px 0;
  border-bottom: 2px solid #4b2d77;
  font-weight: 500;
  font-size: 12px;
  color: #4b2d77;
}

.checklist-item {
  display: flex;
  align-items: flex-start;
  padding: 8px 0;
  border-bottom: 1px solid #ebeef5;
  transition: background 0.2s;
}

.checklist-item.is-marked { background: #f4f0fa; }

.col-seq { width: 40px; min-width: 40px; text-align: center; font-weight: 600; color: #4b2d77; padding-top: 4px; }
.col-desc { flex: 1; font-size: 13px; line-height: 1.6; color: #303133; padding: 0 8px; }
.col-applicable { width: 90px; min-width: 90px; }
.col-wpref { width: 110px; min-width: 110px; }

.checklist-section2 { margin-top: 20px; }
.checklist-section2__title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.checklist-notes {
  margin-top: 16px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #909399;
  font-style: italic;
}
.checklist-notes p { margin: 4px 0; }
</style>
