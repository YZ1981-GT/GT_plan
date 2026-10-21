<!--
  公式参数选择器：点击 TB/WP/NOTE/ROW 快捷按钮后弹出选择 popover。

  spec: formula-management-ux-improvements · A 批 · Task A4

  四种模式：
  - tb：科目选择（ACNR tbAddresses）
  - wp：底稿/sheet 选择（ACNR listSheets）
  - note：附注章节选择（noteTree）
  - row：行次选择（当前报表行列表）
-->
<template>
  <el-popover
    :visible="visible"
    placement="bottom-start"
    :width="360"
    trigger="click"
    @update:visible="v => visible = v"
  >
    <template #reference>
      <el-button
        size="small"
        link
        :style="{ fontSize: '10px', padding: '0 2px' }"
        :title="buttonTitle"
        @click.stop="onOpen"
      >{{ mode.toUpperCase() }}</el-button>
    </template>

    <div class="gt-fpp">
      <div class="gt-fpp-title">{{ panelTitle }}</div>
      <el-input
        v-model="searchQuery"
        size="small"
        clearable
        :placeholder="searchPlaceholder"
        class="gt-fpp-search"
      />

      <div class="gt-fpp-list">
        <div
          v-for="item in filteredItems"
          :key="item.key"
          class="gt-fpp-item"
          @click="onSelect(item)"
        >
          <span class="gt-fpp-item-code">{{ item.code }}</span>
          <span class="gt-fpp-item-label">{{ item.label }}</span>
        </div>
        <div v-if="!filteredItems.length" class="gt-fpp-empty">
          {{ loading ? '加载中...' : '无匹配项' }}
        </div>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

defineOptions({ name: 'FormulaParamPicker' })

interface PickerItem {
  key: string
  code: string
  label: string
  /** 生成的公式文本（选中后直接插入） */
  formulaText: string
}

const props = defineProps<{
  mode: 'tb' | 'wp' | 'note' | 'row'
  /** TB 模式：科目列表 [{code, name}] */
  tbItems?: Array<{ code: string; name: string }>
  /** WP 模式：底稿列表 [{wpCode, sheetCode, label}] */
  wpItems?: Array<{ wpCode: string; sheetCode?: string; label: string }>
  /** NOTE 模式：章节列表 [{section, title}] */
  noteItems?: Array<{ section: string; title: string }>
  /** ROW 模式：行次列表 [{rowCode, rowName}] */
  rowItems?: Array<{ rowCode: string; rowName: string }>
  loading?: boolean
}>()

const emit = defineEmits<{
  select: [formulaText: string]
}>()

const visible = ref(false)
const searchQuery = ref('')

const TITLES: Record<string, string> = {
  tb: '选择试算表科目',
  wp: '选择底稿/Sheet',
  note: '选择附注章节',
  row: '选择行次',
}

const BUTTON_TITLES: Record<string, string> = {
  tb: '试算表取数（点击选择科目）',
  wp: '底稿取数（点击选择底稿）',
  note: '附注取数（点击选择章节）',
  row: '行次引用（点击选择行次）',
}

const SEARCH_PLACEHOLDERS: Record<string, string> = {
  tb: '搜索科目代码或名称...',
  wp: '搜索底稿编码...',
  note: '搜索章节编号或标题...',
  row: '搜索行次或项目名...',
}

const panelTitle = computed(() => TITLES[props.mode] || '选择')
const buttonTitle = computed(() => BUTTON_TITLES[props.mode] || '')
const searchPlaceholder = computed(() => SEARCH_PLACEHOLDERS[props.mode] || '搜索...')

const allItems = computed<PickerItem[]>(() => {
  switch (props.mode) {
    case 'tb':
      return (props.tbItems || []).map(it => ({
        key: it.code,
        code: it.code,
        label: it.name,
        formulaText: `TB('${it.code}','期末余额')`,
      }))
    case 'wp':
      return (props.wpItems || []).map(it => ({
        key: `${it.wpCode}/${it.sheetCode || ''}`,
        code: it.wpCode,
        label: it.label,
        formulaText: it.sheetCode
          ? `WP('${it.wpCode}','${it.sheetCode}','审定数')`
          : `WP('${it.wpCode}','审定数')`,
      }))
    case 'note':
      return (props.noteItems || []).map(it => ({
        key: it.section,
        code: it.section,
        label: it.title,
        formulaText: `NOTE('${it.section}','合计')`,
      }))
    case 'row':
      return (props.rowItems || []).map(it => ({
        key: it.rowCode,
        code: it.rowCode,
        label: it.rowName,
        formulaText: `ROW('${it.rowCode}')`,
      }))
    default:
      return []
  }
})

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return allItems.value
  return allItems.value.filter(it =>
    it.code.toLowerCase().includes(q) || it.label.toLowerCase().includes(q),
  )
})

function onOpen() {
  visible.value = true
  searchQuery.value = ''
}

function onSelect(item: PickerItem) {
  emit('select', item.formulaText)
  visible.value = false
}

// 关闭时清理搜索
watch(visible, v => { if (!v) searchQuery.value = '' })
</script>

<style scoped>
.gt-fpp { max-height: 320px; display: flex; flex-direction: column; }
.gt-fpp-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--gt-color-text-primary); }
.gt-fpp-search { margin-bottom: 6px; }
.gt-fpp-list { overflow-y: auto; flex: 1; max-height: 240px; }
.gt-fpp-item {
  display: flex; gap: 8px; padding: 4px 6px; cursor: pointer; border-radius: 3px;
  font-size: 12px; line-height: 1.6;
}
.gt-fpp-item:hover { background: var(--gt-bg-info, #ecf5ff); }
.gt-fpp-item-code { font-weight: 600; color: var(--gt-color-primary); min-width: 60px; white-space: nowrap; }
.gt-fpp-item-label { color: var(--gt-color-text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-fpp-empty { padding: 12px; text-align: center; font-size: 12px; color: var(--gt-color-text-placeholder); }
</style>
