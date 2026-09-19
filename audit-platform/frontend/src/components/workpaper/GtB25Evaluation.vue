<script setup lang="ts">
/**
 * GtB25Evaluation — B2-5 与前任注册会计师沟通后的评价（决策向导）
 *
 * 对照源模板：对沟通的评价（答复充分/有限/未答复，三选一互斥）→ 对承接业务的
 * 考虑（接受/不接受委托 + 理由）。选"未答复"时联动提示 B2-3 第二封催函。
 * 数据存 checklist_responses（item_id B2-5-evaluation, JSON）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from './GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId?: string
  readonly?: boolean
}>()

const ITEM_ID = 'B2-5-evaluation'

const QUALITY_OPTIONS = ['得到的答复充分', '得到的答复有限', '未得到答复']
const DECISION_OPTIONS = ['可以接受委托', '不接受委托']
// 源模板固定的"不接受委托"理由
const REJECT_REASONS = [
  '变更会计师事务所的原因是由于前任注册会计师在会计、审计问题上与被审计单位管理层存在分歧，管理层对前任注册会计师的审计意见不满意，经多次沟通仍难以达成一致意见。',
  '未得到答复，且没有理由认为变更会计师事务所的原因异常。后任注册会计师应设法以其他方式与前任注册会计师再次进行沟通；如果仍得不到答复，后任可以致函前任，说明如果在适当的时间内得不到答复，将假设不存在专业方面的原因使其拒绝接受委托，并表明拟接受此项业务委托。',
]

interface Evaluation {
  quality: string
  decision: string
  acceptReason: string
  rejectReasons: string[]
  rejectSupplement: string
}

const form = ref<Evaluation>({
  quality: '',
  decision: '',
  acceptReason: '',
  rejectReasons: [],
  rejectSupplement: '',
})

const loading = ref(false)

// 未答复联动提示（R5.2）
const showFollowUpHint = computed(() => form.value.quality === '未得到答复')

async function load() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const row = list.find((r) => r.item_id === ITEM_ID)
    if (row?.remark) {
      try {
        const parsed = JSON.parse(row.remark)
        if (parsed && typeof parsed === 'object') form.value = { ...form.value, ...parsed }
      } catch { /* ignore */ }
    }
  } catch { /* empty */ } finally {
    loading.value = false
  }
}

const _timer = ref<ReturnType<typeof setTimeout> | null>(null)
function save() {
  if (props.readonly || !props.wpId) return
  if (_timer.value) clearTimeout(_timer.value)
  _timer.value = setTimeout(async () => {
    try {
      await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
        project_id: props.projectId || undefined,
        items: [{ item_id: ITEM_ID, conclusion: null, remark: JSON.stringify(form.value) }],
      })
    } catch { /* silent */ }
  }, 600)
}

function onSaveClick() {
  save()
  ElMessage.success('评价已保存')
}

onMounted(load)
</script>

<template>
  <div class="gt-b25" v-loading="loading">
    <el-alert type="info" :closable="false" show-icon class="gt-b25__desc">
      <template #title>
        与前任注册会计师沟通后的评价（衔接业务承接质量控制）。根据沟通答复情况判断是否接受委托。
      </template>
    </el-alert>

    <el-card shadow="never" class="gt-b25__card">
      <template #header><span class="gt-b25__title">一、对沟通的评价</span></template>
      <el-radio-group v-model="form.quality" :disabled="readonly" @change="save" class="gt-b25__radios">
        <el-radio v-for="o in QUALITY_OPTIONS" :key="o" :value="o" :label="o">{{ o }}</el-radio>
      </el-radio-group>
      <el-alert
        v-if="showFollowUpHint"
        type="warning"
        :closable="false"
        show-icon
        class="gt-b25__followup"
      >
        <template #title>
          未得到答复：请确认是否已发出 <b>B2-3 第二封沟通函（催函）</b>（一般距第一封约两周）。
          如仍未获答复且无异常理由，可假设不存在专业方面的原因使其拒绝接受委托并拟接受委托。
        </template>
      </el-alert>
    </el-card>

    <el-card shadow="never" class="gt-b25__card">
      <template #header><span class="gt-b25__title">二、对承接业务的考虑</span></template>
      <el-alert type="info" :closable="false" class="gt-b25__link">
        <template #title>
          <span>本评价结论应纳入业务承接决策（与承接业务的质量控制衔接）：</span>
          <GtIndexChip value="B1" :validate="false" />
        </template>
      </el-alert>
      <el-radio-group v-model="form.decision" :disabled="readonly" @change="save" class="gt-b25__radios">
        <el-radio v-for="o in DECISION_OPTIONS" :key="o" :value="o" :label="o">{{ o }}</el-radio>
      </el-radio-group>

      <!-- 接受委托：理由 -->
      <div v-if="form.decision === '可以接受委托'" class="gt-b25__block">
        <div class="gt-b25__label">可以接受委托。理由如下：</div>
        <el-input
          v-model="form.acceptReason"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="readonly"
          placeholder="说明可以接受委托的理由"
          @change="save"
        />
      </div>

      <!-- 不接受委托：固定理由多选 + 补充 -->
      <div v-else-if="form.decision === '不接受委托'" class="gt-b25__block">
        <div class="gt-b25__label">不接受委托。理由如下（勾选适用项）：</div>
        <el-checkbox-group v-model="form.rejectReasons" :disabled="readonly" @change="save">
          <el-checkbox
            v-for="(r, i) in REJECT_REASONS"
            :key="i"
            :value="r"
            :label="r"
            class="gt-b25__reason"
          >
            <span class="gt-b25__reason-text">{{ r }}</span>
          </el-checkbox>
        </el-checkbox-group>
        <el-input
          v-model="form.rejectSupplement"
          type="textarea"
          :autosize="{ minRows: 2 }"
          :disabled="readonly"
          placeholder="其他理由补充（可选）"
          class="gt-b25__supp"
          @change="save"
        />
      </div>

      <div v-if="!readonly" class="gt-b25__actions">
        <el-button type="primary" @click="onSaveClick">保存评价</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.gt-b25 { padding: 6px; font-size: 13px; }
.gt-b25__desc { margin-bottom: 12px; }
.gt-b25__card { margin-bottom: 14px; max-width: 900px; }
.gt-b25__title { font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
.gt-b25__radios { display: flex; flex-direction: column; gap: 8px; }
.gt-b25__followup { margin-top: 12px; }
.gt-b25__link { margin-bottom: 12px; }
.gt-b25__block { margin-top: 14px; }
.gt-b25__label { font-weight: 600; margin-bottom: 8px; }
.gt-b25__reason { display: flex; align-items: flex-start; height: auto; margin-bottom: 10px; white-space: normal; }
.gt-b25__reason-text { white-space: normal; line-height: 1.5; font-size: 12px; }
.gt-b25__supp { margin-top: 8px; }
.gt-b25__actions { margin-top: 16px; }
</style>
