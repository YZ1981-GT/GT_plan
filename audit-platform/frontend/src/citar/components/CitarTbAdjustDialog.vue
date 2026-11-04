<template>
  <el-dialog
    :model-value="Boolean(account)"
    title="修改审定数"
    width="560px"
    append-to-body
    class="tb-adj"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => { if (!v) emit('close') }"
  >
    <!-- 关闭动画期间 account 已置空：内容用打开时的副本，弹窗不会先变空再收起 -->
    <div v-if="shown" class="tb-adj__body">
      <p class="tb-adj__note">
        试算表审定数只能经调整分录改变：这里按差额生成一张<strong>调整分录草稿</strong>，复核批准后才进入试算表。
      </p>
      <dl class="tb-adj__facts">
        <dt>科目</dt><dd>{{ shown.code }} {{ shown.name }}</dd>
        <dt>当前审定数</dt><dd>{{ current.dir }} {{ fmtMoney(current.amount, '0.00') }}</dd>
      </dl>
      <div class="tb-adj__row">
        <label for="tb-adj-dir">目标审定数</label>
        <select id="tb-adj-dir" v-model="direction" class="citar-search tb-adj__dir">
          <option value="借">借</option>
          <option value="贷">贷</option>
        </select>
        <input v-model="amountText" class="citar-search tb-adj__amount" aria-label="目标金额" placeholder="金额" />
      </div>
      <div class="tb-adj__row">
        <label for="tb-adj-counter">对方科目</label>
        <input id="tb-adj-counter" v-model.trim="counterCode" class="citar-search tb-adj__amount" :list="datalistId" placeholder="标准科目编号" />
        <span class="tb-adj__name">{{ accountNames.get(counterCode) || '' }}</span>
      </div>
      <div class="tb-adj__row">
        <label for="tb-adj-desc">摘要</label>
        <input id="tb-adj-desc" v-model="description" class="citar-search tb-adj__desc" maxlength="200" />
      </div>
      <p v-if="preview.error" class="tb-adj__error">{{ preview.error }}</p>
      <table v-else class="sheet-table tb-adj__preview">
        <thead><tr><th>科目</th><th>借方</th><th>贷方</th></tr></thead>
        <tbody>
          <tr v-for="l in preview.lines" :key="l.standard_account_code">
            <td>{{ l.standard_account_code }} {{ l.account_name || '' }}</td>
            <td class="is-numeric">{{ fmtMoney(l.debit_amount) }}</td>
            <td class="is-numeric">{{ fmtMoney(l.credit_amount) }}</td>
          </tr>
        </tbody>
      </table>
      <datalist :id="datalistId">
        <option v-for="[code, name] in accountNames" :key="code" :value="code">{{ name }}</option>
      </datalist>
      <div class="tb-adj__footer">
        <button class="citar-btn" type="button" :disabled="saving" @click="emit('close')">取消</button>
        <button class="citar-btn citar-btn--primary" type="button" :disabled="saving || Boolean(preview.error)" @click="submit">
          {{ saving ? '生成中…' : '生成调整分录草稿' }}
        </button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 试算平衡表改审定数（spec citar-table-manual-edit R2）：按差额生成借贷平衡的 AJE 草稿，不直接改试算表。
 * 本组件只发「新建调整分录」一个请求（平台既有端点 POST /adjustments）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { adjustments as P_adj } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { buildTbAdjustLines, signedOf } from '../citarTbAdjust'
import { fmtMoney, splitDirection } from '../useCitarProject'

export interface TbAdjustAccount {
  code: string
  name: string
  /** 当前审定数（借正贷负） */
  audited: number
}

const props = defineProps<{
  account: TbAdjustAccount | null
  projectId: string
  year: number
  accountNames: Map<string, string>
}>()

const emit = defineEmits<{ close: []; created: [no: string] }>()

const datalistId = 'citar-tb-adjust-accounts'
const direction = ref<'借' | '贷'>('借')
const amountText = ref('')
const counterCode = ref('')
const description = ref('')
const saving = ref(false)

const current = computed(() => splitDirection(shown.value?.audited ?? 0))

/** 打开时的科目副本：父组件关窗时把 account 置空，关闭动画期间内容照常显示 */
const shown = ref<TbAdjustAccount | null>(null)

watch(() => props.account, (a) => {
  if (!a) return
  shown.value = { ...a }
  const side = splitDirection(a.audited)
  direction.value = side.dir === '贷' ? '贷' : '借'
  amountText.value = side.amount ? String(side.amount) : ''
  counterCode.value = ''
  description.value = `调整 ${a.code} ${a.name} 审定数`
})

const target = computed(() => {
  const t = amountText.value.replace(/,/g, '').trim()
  const n = t === '' ? 0 : Number(t)
  return Number.isFinite(n) ? signedOf(direction.value, n) : NaN
})

const preview = computed(() => {
  const a = shown.value
  if (!a) return { lines: [], error: '' }
  if (Number.isNaN(target.value)) return { lines: [], error: '金额只能填数字' }
  return buildTbAdjustLines({
    code: a.code,
    name: a.name,
    current: a.audited,
    target: target.value,
    counterCode: counterCode.value,
    counterName: props.accountNames.get(counterCode.value) || '',
    description: description.value,
  })
})

async function submit() {
  if (!props.account || preview.value.error) return
  if (props.accountNames.size && !props.accountNames.has(counterCode.value)) {
    ElMessage.warning(`标准科目表里没有 ${counterCode.value}，请从下拉选项里选`)
    return
  }
  saving.value = true
  try {
    const res: any = await api.post(P_adj.create(props.projectId), {
      adjustment_type: 'aje',
      year: props.year,
      description: description.value.trim() || undefined,
      line_items: preview.value.lines,
    }, { _silent: true } as any)
    const no = res?.adjustment_no || ''
    ElMessage.success(`已生成调整分录草稿${no ? ` ${no}` : ''}，复核批准后进入试算表`)
    emit('created', no)
  } catch (e) {
    handleApiError(e, '生成调整分录')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/unaudited.css"></style>

<style scoped>
.tb-adj__note {
  margin: 0 0 12px;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-5c5c68);
}

.tb-adj__facts {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 6px 12px;
  margin: 0 0 12px;
  font-size: var(--citar-fs-13);
}

.tb-adj__facts dt {
  color: var(--citar-c-8c8c96);
}

.tb-adj__facts dd {
  margin: 0;
}

.tb-adj__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: var(--citar-fs-13);
}

.tb-adj__row > label {
  width: 90px;
  color: var(--citar-c-5c5c68);
}

.tb-adj__dir {
  width: 64px;
}

.tb-adj__amount {
  width: 180px;
}

.tb-adj__desc {
  flex: 1;
}

.tb-adj__name {
  color: var(--citar-c-8c8c96);
}

.tb-adj__error {
  margin: 4px 0 0;
  color: var(--citar-c-8a5300);
  font-size: var(--citar-fs-13);
}

.tb-adj__preview {
  margin-top: 6px;
}

.tb-adj__footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}
</style>
