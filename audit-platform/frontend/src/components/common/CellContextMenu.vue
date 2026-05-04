<template>
  <Teleport to="body">
    <Transition name="gt-ucell-ctx-fade">
      <div v-if="visible" class="gt-ucell-context-menu"
        :style="{ left: x + 'px', top: y + 'px' }" @contextmenu.prevent>
        <div class="gt-ucell-ctx-header">
          <span>{{ itemName }}</span>
          <span v-if="value != null" style="color:#4b2d77;font-weight:600">{{ formattedValue }}</span>
        </div>
        <div class="gt-ucell-ctx-divider" />
        <!-- 通用项 -->
        <div class="gt-ucell-ctx-item" @click="$emit('copy')"><span class="gt-ucell-ctx-icon">📋</span> 复制值</div>
        <div class="gt-ucell-ctx-item" @click="$emit('formula')"><span class="gt-ucell-ctx-icon">ƒx</span> 查看公式</div>
        <!-- 自定义插槽：模块特有的菜单项 -->
        <slot />
        <!-- 多选项 -->
        <template v-if="multiCount > 1">
          <div class="gt-ucell-ctx-divider" />
          <div class="gt-ucell-ctx-item" @click="$emit('sum')">
            <span class="gt-ucell-ctx-icon">Σ</span> 求和 <b style="color:#4b2d77;margin-left:4px">{{ multiCount }} 格</b>
          </div>
          <div class="gt-ucell-ctx-item" @click="$emit('compare')">
            <span class="gt-ucell-ctx-icon">⇄</span> 对比差异
          </div>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  visible: boolean
  x: number
  y: number
  itemName: string
  value?: any
  multiCount: number
}>()

defineEmits<{
  (e: 'copy'): void
  (e: 'formula'): void
  (e: 'sum'): void
  (e: 'compare'): void
}>()

const formattedValue = computed(() => {
  const v = props.value
  if (v == null) return ''
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
})
</script>

<style>
/* ══ 通用单元格选中高亮（GT品牌紫色系） ══ */
.gt-ucell--selected {
  position: relative;
  background: var(--gt-color-primary-bg, #f4f0fa) !important;
  outline: 1.5px solid var(--gt-color-primary, #4b2d77);
  outline-offset: -1.5px;
  z-index: 1;
  animation: gt-ucell-glow 2s ease-in-out infinite alternate;
}
/* 左侧强调条 */
.gt-ucell--selected::before {
  content: '';
  position: absolute;
  left: 0; top: 2px; bottom: 2px;
  width: 2.5px;
  background: var(--gt-gradient-primary, linear-gradient(180deg, #4b2d77, #A06DFF));
  border-radius: 0 2px 2px 0;
  opacity: 0.85;
}
/* 右下角小三角标记 */
.gt-ucell--selected::after {
  content: '';
  position: absolute;
  right: 0; bottom: 0;
  width: 0; height: 0;
  border-style: solid;
  border-width: 0 0 6px 6px;
  border-color: transparent transparent var(--gt-color-primary-light, #A06DFF) transparent;
  opacity: 0.6;
}
@keyframes gt-ucell-glow {
  0% { outline-color: var(--gt-color-primary, #4b2d77); background: var(--gt-color-primary-bg, #f4f0fa) !important; }
  100% { outline-color: var(--gt-color-primary-light, #A06DFF); background: rgba(160, 109, 255, 0.06) !important; }
}
/* 多选时第二个及以后的单元格用虚线区分 */
.el-table__body .gt-ucell--selected ~ .gt-ucell--selected {
  outline-style: dashed;
}

/* ══ 右键菜单（GT品牌风格） ══ */
.gt-ucell-context-menu {
  position: fixed; z-index: 10001;
  background: var(--gt-color-bg-white, #fff);
  border-radius: var(--gt-radius-md, 8px);
  box-shadow: var(--gt-shadow-lg, 0 8px 24px rgba(75,45,119,0.175));
  padding: 6px 0; min-width: 210px;
  border: 1px solid var(--gt-color-border-light, #f0f0f5);
  backdrop-filter: blur(8px);
}
.gt-ucell-ctx-header {
  padding: 8px 16px; font-size: 12px; color: var(--gt-color-text-tertiary, #999);
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
}
.gt-ucell-ctx-header span:last-child {
  color: var(--gt-color-primary, #4b2d77); font-weight: 600; font-size: 13px;
}
.gt-ucell-ctx-divider {
  height: 1px; margin: 4px 12px;
  background: linear-gradient(90deg, transparent, var(--gt-color-border, #e5e5ea), transparent);
}
.gt-ucell-ctx-item {
  padding: 9px 16px; font-size: 14px; cursor: pointer;
  color: var(--gt-color-text, #1d1d1f);
  display: flex; align-items: center; gap: 8px;
  transition: all var(--gt-transition-fast, 0.15s);
  border-radius: 0;
  margin: 0 4px;
  border-radius: var(--gt-radius-sm, 4px);
}
.gt-ucell-ctx-item:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
  color: var(--gt-color-primary, #4b2d77);
}
.gt-ucell-ctx-item:active {
  background: rgba(75, 45, 119, 0.12);
}
.gt-ucell-ctx-icon {
  width: 20px; text-align: center; font-size: 14px;
  color: var(--gt-color-text-secondary, #6e6e73);
}
.gt-ucell-ctx-item:hover .gt-ucell-ctx-icon {
  color: var(--gt-color-primary, #4b2d77);
}
/* 菜单出入动画 */
.gt-ucell-ctx-fade-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.gt-ucell-ctx-fade-leave-active { transition: opacity 0.1s ease; }
.gt-ucell-ctx-fade-enter-from { opacity: 0; transform: translateY(-4px) scale(0.97); }
.gt-ucell-ctx-fade-leave-to { opacity: 0; }

/* ══ 单元格批注标记（右上角橙色三角） ══ */
.gt-cell--has-comment {
  position: relative;
}
.gt-cell--has-comment::after {
  content: '';
  position: absolute;
  right: 0; top: 0;
  width: 0; height: 0;
  border-style: solid;
  border-width: 8px 8px 0 0;
  border-color: var(--gt-color-wheat, #FFC23D) transparent transparent transparent;
  z-index: 2;
}

/* ══ 单元格已复核标记（左下角绿色圆点） ══ */
.gt-cell--reviewed {
  position: relative;
}
.gt-cell--reviewed::before {
  content: '✓';
  position: absolute;
  right: 3px; top: 1px;
  width: 14px; height: 14px;
  font-size: 10px; line-height: 14px; text-align: center;
  color: #fff;
  background: var(--gt-color-success, #28A745);
  border-radius: 50%;
  z-index: 2;
}
</style>
