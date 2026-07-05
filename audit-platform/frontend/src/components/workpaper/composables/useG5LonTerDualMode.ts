import { ref, type Ref } from 'vue'
export function useG5LonTerDualMode(opts: { wpId: Ref<string>; activeTab: Ref<string> }) {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const ooConfig = ref<any>(null)
  const ooHealthy = ref<boolean | null>(null)
  const modeOptions = ref([{ label: '结构化视图', value: 'html' }, { label: '在线编辑', value: 'onlyoffice' }])
  function onModeChange(v: string) { currentMode.value = v as 'html' | 'onlyoffice' }
  function onDocumentReady() {}
  async function checkOOHealth() { ooHealthy.value = true }
  return { currentMode, ooConfig, ooHealthy, modeOptions, onModeChange, onDocumentReady, checkOOHealth }
}
