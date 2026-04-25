<template>
  <el-dropdown trigger="click" @command="switchLanguage">
    <span class="gt-lang-trigger">
      🌐
      {{ currentLabel }}
      <el-icon class="el-icon--right"><ArrowDown /></el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="lang in languages"
          :key="lang.value"
          :command="lang.value"
          :class="{ 'is-active': currentLang === lang.value }"
        >
          {{ lang.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useI18n } from '@/i18n'
import http from '@/utils/http'

const props = withDefaults(defineProps<{
  userId?: string
}>(), {})

const { locale, setLocale } = useI18n()

const languages = [
  { label: '简体中文', value: 'zh-CN' },
  { label: 'English', value: 'en-US' },
]

const currentLang = computed(() => locale.value)

const currentLabel = computed(() => {
  return languages.find(l => l.value === currentLang.value)?.label || '简体中文'
})

async function switchLanguage(lang: string) {
  if (lang === currentLang.value) return
  setLocale(lang)

  if (props.userId) {
    try {
      await http.put(`/api/users/${props.userId}/language`, { language: lang })
    } catch {
      // 静默失败，本地已保存
    }
  }

  ElMessage.success(lang === 'zh-CN' ? '已切换为中文' : 'Switched to English')
}
</script>

<style scoped>
.gt-lang-trigger {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: all var(--gt-transition-fast);
}
.gt-lang-trigger:hover {
  color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg);
}
</style>
