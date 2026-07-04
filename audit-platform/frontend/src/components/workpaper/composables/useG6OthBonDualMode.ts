import { ref, type Ref } from 'vue'
export function useG6OthBonDualMode(opts: { wpId: Ref<string>; activeTab: Ref<string> }) {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const ooConfig = ref<any>(null)
  const ooHealthy = ref<boolean | null>(null)
  const modeOptions = ref([{ label: 'HTML', value: 'html' }, { label: 'OnlyOffice', value: 'onlyoffice' }])
  function onModeChange(v: string) { currentMode.value = v as 'html' | 'onlyoffice' }
  function onDocumentReady() {}
  async function checkOOHealth() { ooHealthy.value = true }
  return { currentMode, ooConfig, ooHealthy, modeOptions, onModeChange, onDocumentReady, checkOOHealth }
}
