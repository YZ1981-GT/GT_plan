<template>
  <el-dialog
    v-model="visible"
    title="生成审计报告正文"
    width="640px"
    append-to-body
    destroy-on-close
    class="gt-opt-dialog"
    @close="onClose"
  >
    <!-- 待补充字段警告条（非阻断，仅在有缺失字段时展示） -->
    <el-alert
      v-if="missingFields.length"
      type="warning"
      :closable="false"
      show-icon
      class="gt-opt-missing"
    >
      <template #title>
        待补充字段：{{ missingFieldsText }}（不阻断生成）
      </template>
    </el-alert>

    <!-- 模板元信息 -->
    <div v-if="templateVersion || companySubtypeResolved" class="gt-opt-meta">
      <el-tag v-if="companySubtypeResolved" size="small" type="info" effect="plain">
        企业子类型：{{ subtypeLabel(companySubtypeResolved) }}
      </el-tag>
      <el-tag v-if="templateVersion" size="small" type="info" effect="plain">
        模板版本：{{ templateVersion }}
      </el-tag>
    </div>

    <!-- 分组可选段落清单 -->
    <div v-if="groups.length" class="gt-opt-groups">
      <div v-for="grp in groups" :key="grp.name" class="gt-opt-group">
        <div class="gt-opt-group-title">{{ grp.name }}</div>
        <div
          v-for="item in grp.items"
          :key="item.section_id"
          class="gt-opt-item"
        >
          <div class="gt-opt-item-row">
            <el-checkbox v-model="selections[item.section_id]">
              <span class="gt-opt-desc">{{ item.description }}</span>
              <span class="gt-opt-sid">（{{ item.section_id }}）</span>
            </el-checkbox>
            <el-button
              v-if="item.preview"
              link
              size="small"
              class="gt-opt-preview-toggle"
              @click="togglePreview(item.section_id)"
            >
              {{ expanded[item.section_id] ? '收起预览' : '展开预览' }}
            </el-button>
          </div>
          <div v-if="expanded[item.section_id]" class="gt-opt-preview-text">
            {{ item.preview }}
          </div>
        </div>
      </div>
    </div>
    <el-empty v-else description="该模板无可选段落" :image-size="60" />

    <template #footer>
      <el-button @click="onCancel">取消</el-button>
      <el-button type="primary" :loading="confirmLoading" @click="onConfirm">
        确认生成
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import type { OptionalSection } from '@/services/deliverableApi'

const props = withDefaults(
  defineProps<{
    /** preview 返回的可选段落清单 */
    optionalSections: OptionalSection[]
    /** 待补充字段（非阻断警告条） */
    missingFields?: string[]
    /** 模板版本号（展示用） */
    templateVersion?: string
    /** 后端解析出的企业子类型（展示用） */
    companySubtypeResolved?: string
    /** 重新生成时预填上次勾选（section_id → 保留） */
    initialSelections?: Record<string, boolean> | null
    /** 确认按钮 loading（由父级 confirm 调用控制） */
    confirmLoading?: boolean
  }>(),
  {
    missingFields: () => [],
    templateVersion: '',
    companySubtypeResolved: '',
    initialSelections: null,
    confirmLoading: false,
  },
)

const emit = defineEmits<{
  /** 确认生成，回传 section_id → 是否保留 */
  (e: 'confirm', selections: Record<string, boolean>): void
  /** 取消/关闭（不触发生成） */
  (e: 'cancel'): void
}>()

const visible = defineModel<boolean>('visible', { default: false })

/** 勾选状态：section_id → 是否保留 */
const selections = reactive<Record<string, boolean>>({})
/** 展开预览状态 */
const expanded = reactive<Record<string, boolean>>({})

const missingFields = computed(() => props.missingFields ?? [])
const missingFieldsText = computed(() => missingFields.value.join('、'))
const templateVersion = computed(() => props.templateVersion)
const companySubtypeResolved = computed(() => props.companySubtypeResolved)

const SUBTYPE_LABELS: Record<string, string> = {
  type_a: 'A 类（上市/三板创新层/公开发债）',
  type_b: 'B 类（三板基础层/银行/保险/证券）',
  type_c: 'C 类（其他公众利益实体）',
  type_d: 'D 类（非公众利益实体）',
}
function subtypeLabel(v: string): string {
  return SUBTYPE_LABELS[v] || v
}

/** 按 group 分组（保持后端返回顺序） */
const groups = computed(() => {
  const order: string[] = []
  const map: Record<string, OptionalSection[]> = {}
  for (const s of props.optionalSections) {
    const g = s.group || '其他段落'
    if (!map[g]) {
      map[g] = []
      order.push(g)
    }
    map[g].push(s)
  }
  return order.map((name) => ({ name, items: map[name] }))
})

/** 初始化勾选：优先 initialSelections（上次选择），否则用 default_keep */
function initSelections() {
  // 清空旧键
  for (const k of Object.keys(selections)) delete selections[k]
  for (const k of Object.keys(expanded)) delete expanded[k]
  for (const s of props.optionalSections) {
    const prev = props.initialSelections?.[s.section_id]
    selections[s.section_id] = prev !== undefined ? prev : s.default_keep
    expanded[s.section_id] = false
  }
}

// 段落清单变化或弹窗打开时重新初始化勾选
watch(
  () => props.optionalSections,
  () => initSelections(),
  { immediate: true, deep: false },
)
watch(visible, (v) => {
  if (v) initSelections()
})

function togglePreview(sectionId: string) {
  expanded[sectionId] = !expanded[sectionId]
}

function onConfirm() {
  // 浅拷贝纯对象回传，避免父级持有 reactive 引用
  emit('confirm', { ...selections })
}

function onCancel() {
  visible.value = false
  emit('cancel')
}

function onClose() {
  // el-dialog 关闭（点遮罩/X）不触发生成
  emit('cancel')
}
</script>

<style scoped>
.gt-opt-missing {
  margin-bottom: 12px;
}
.gt-opt-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.gt-opt-groups {
  max-height: 420px;
  overflow-y: auto;
}
.gt-opt-group {
  margin-bottom: 16px;
}
.gt-opt-group-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
  padding: 6px 0;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
}
.gt-opt-item {
  padding: 6px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}
.gt-opt-item:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}
.gt-opt-item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.gt-opt-desc {
  color: var(--gt-color-text-primary);
}
.gt-opt-sid {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
.gt-opt-preview-toggle {
  color: var(--gt-color-primary, #4b2d77);
  flex-shrink: 0;
}
.gt-opt-preview-text {
  margin: 6px 0 2px 24px;
  padding: 8px 10px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.7;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-left: 2px solid var(--gt-color-border-purple, #b890dd);
  border-radius: var(--gt-radius-sm);
  white-space: pre-wrap;
}
</style>
