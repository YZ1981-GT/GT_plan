<!--
  ProcedurePanel — 审计程序清单展示 + 勾选完成 + 裁剪操作
  Sprint 2 Task 2.3
-->
<template>
  <div class="gt-procedure-panel">
    <!-- 顶部统计 -->
    <div class="gt-procedure-header">
      <span class="gt-procedure-rate">
        完成率：<strong>{{ completionRate }}%</strong>
      </span>
      <el-button size="small" text type="primary" @click="showAddDialog = true">
        + 自定义
      </el-button>
    </div>

    <!-- 按类别分组展示 -->
    <div v-if="loading" v-loading="true" style="min-height: 100px" />
    <template v-else>
      <div v-for="(procs, category) in groupedByCategory" :key="category" class="gt-procedure-group">
        <div class="gt-procedure-group-title">{{ categoryLabel(category) }}</div>
        <div
          v-for="proc in procs"
          :key="proc.id"
          class="gt-procedure-item"
          :class="{
            'gt-procedure-completed': proc.status === 'completed',
            'gt-procedure-mandatory': proc.is_mandatory,
          }"
        >
          <el-checkbox
            :model-value="proc.status === 'completed'"
            :disabled="proc.is_mandatory && proc.status === 'completed'"
            @change="(val: any) => onToggleComplete(proc, !!val)"
          />
          <div class="gt-procedure-content">
            <span class="gt-procedure-id">{{ proc.procedure_id }}</span>
            <span class="gt-procedure-desc">{{ proc.description }}</span>
            <el-tag v-if="proc.is_mandatory" size="small" type="info" class="gt-procedure-tag">
              必做
            </el-tag>
          </div>
          <el-button
            v-if="!proc.is_mandatory && proc.status !== 'not_applicable'"
            size="small"
            text
            type="danger"
            @click="onTrim(proc)"
          >
            裁剪
          </el-button>
        </div>
      </div>
      <div v-if="procedures.length === 0" class="gt-procedure-empty">
        暂无程序清单
      </div>
    </template>

    <!-- 新增自定义程序对话框 -->
    <el-dialog v-model="showAddDialog" title="新增自定义程序" width="400px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="描述">
          <el-input v-model="newDesc" type="textarea" :rows="3" placeholder="请输入程序描述" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select v-model="newCategory" style="width: 100%">
            <el-option label="常规" value="routine" />
            <el-option label="自定义" value="custom" />
            <el-option label="专项" value="special" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!newDesc.trim()" @click="onAddCustom">确定</el-button>
      </template>
    </el-dialog>

    <!-- 裁剪原因对话框 -->
    <el-dialog v-model="showTrimDialog" title="裁剪程序" width="400px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="裁剪原因">
          <el-input v-model="trimReason" type="textarea" :rows="3" placeholder="请输入裁剪原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTrimDialog = false">取消</el-button>
        <el-button type="danger" :disabled="!trimReason.trim()" @click="onConfirmTrim">确认裁剪</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useProcedures, type Procedure } from '@/composables/useProcedures'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  projectId: string
  wpId: string
  userId?: string
}>()

const emit = defineEmits<{
  (e: 'completion-change', rate: number): void
}>()

const {
  procedures,
  loading,
  completionRate,
  groupedByCategory,
  fetchProcedures,
  markComplete,
  trimProcedure,
  createCustom,
} = useProcedures(props.projectId, props.wpId)

// 新增对话框
const showAddDialog = ref(false)
const newDesc = ref('')
const newCategory = ref('custom')

// 裁剪对话框
const showTrimDialog = ref(false)
const trimReason = ref('')
const trimTarget = ref<Procedure | null>(null)

const CATEGORY_LABELS: Record<string, string> = {
  routine: '常规程序',
  custom: '自定义程序',
  special: '专项程序',
  'special-ipo': '专项-IPO',
  'special-listed': '专项-上市',
  other: '其他',
}

function categoryLabel(cat: string) {
  return CATEGORY_LABELS[cat] || cat
}

async function onToggleComplete(proc: Procedure, checked: boolean) {
  if (checked) {
    const uid = props.userId || '00000000-0000-0000-0000-000000000000'
    await markComplete(proc.id, uid)
    emit('completion-change', completionRate.value)
  }
}

function onTrim(proc: Procedure) {
  trimTarget.value = proc
  trimReason.value = ''
  showTrimDialog.value = true
}

async function onConfirmTrim() {
  if (!trimTarget.value) return
  await trimProcedure(trimTarget.value.id, trimReason.value)
  showTrimDialog.value = false
  trimTarget.value = null
  emit('completion-change', completionRate.value)
  ElMessage.success('程序已裁剪')
}

async function onAddCustom() {
  await createCustom(newDesc.value, newCategory.value)
  showAddDialog.value = false
  newDesc.value = ''
  ElMessage.success('自定义程序已添加')
}

// 初始加载
onMounted(() => fetchProcedures(true))

// wpId 变化时重新加载
watch(() => props.wpId, () => fetchProcedures(true))
</script>

<style scoped>
.gt-procedure-panel {
  padding: 8px;
}
.gt-procedure-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gt-color-border-light, #eee);
}
.gt-procedure-rate {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #666);
}
.gt-procedure-rate strong {
  color: var(--gt-color-primary, #4b2d77);
  font-size: 16px;
}
.gt-procedure-group {
  margin-bottom: 12px;
}
.gt-procedure-group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-secondary, #999);
  margin-bottom: 6px;
  text-transform: uppercase;
}
.gt-procedure-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: 4px;
  transition: background 0.15s;
}
.gt-procedure-item:hover {
  background: var(--gt-color-bg-elevated, #f9f7fb);
}
.gt-procedure-completed {
  opacity: 0.7;
}
.gt-procedure-completed .gt-procedure-desc {
  text-decoration: line-through;
}
.gt-procedure-content {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.gt-procedure-id {
  font-family: monospace;
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #aaa);
  min-width: 60px;
}
.gt-procedure-desc {
  font-size: 13px;
  color: var(--gt-color-text, #333);
  line-height: 1.4;
}
.gt-procedure-tag {
  margin-left: 4px;
}
.gt-procedure-empty {
  text-align: center;
  padding: 24px;
  color: var(--gt-color-text-tertiary, #ccc);
  font-size: 13px;
}
</style>
