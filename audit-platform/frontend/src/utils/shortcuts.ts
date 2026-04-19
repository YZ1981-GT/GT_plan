/**
 * ShortcutManager — 快捷键管理
 * Phase 8 Task 9.3
 */

export interface ShortcutEntry {
  key: string
  handler: () => void
  description: string
  scope?: string
}

class ShortcutManager {
  private shortcuts: Map<string, ShortcutEntry> = new Map()
  private enabled = true

  register(key: string, handler: () => void, description: string, scope = '全局') {
    this.shortcuts.set(key, { key, handler, description, scope })
  }

  unregister(key: string) {
    this.shortcuts.delete(key)
  }

  handleKeydown(event: KeyboardEvent) {
    if (!this.enabled) return
    const key = this.getShortcutKey(event)
    const entry = this.shortcuts.get(key)
    if (entry) {
      entry.handler()
      event.preventDefault()
    }
  }

  getShortcutKey(event: KeyboardEvent): string {
    const modifiers: string[] = []
    if (event.ctrlKey || event.metaKey) modifiers.push('Ctrl')
    if (event.shiftKey) modifiers.push('Shift')
    if (event.altKey) modifiers.push('Alt')
    modifiers.push(event.key.toUpperCase())
    return modifiers.join('+')
  }

  getAll(): ShortcutEntry[] {
    return Array.from(this.shortcuts.values())
  }

  setEnabled(v: boolean) {
    this.enabled = v
  }

  install() {
    document.addEventListener('keydown', (e) => this.handleKeydown(e))
  }

  uninstall() {
    document.removeEventListener('keydown', (e) => this.handleKeydown(e))
  }
}

export const shortcutManager = new ShortcutManager()

// Default shortcuts from design doc
export function registerDefaultShortcuts(router: any) {
  shortcutManager.register('Ctrl+S', () => {
    document.dispatchEvent(new CustomEvent('shortcut:save'))
  }, '保存当前编辑内容', '底稿编辑/附注编辑/报告编辑')

  shortcutManager.register('Ctrl+Z', () => {
    document.dispatchEvent(new CustomEvent('shortcut:undo'))
  }, '撤销上一步操作', '全局')

  shortcutManager.register('Ctrl+Shift+Z', () => {
    document.dispatchEvent(new CustomEvent('shortcut:redo'))
  }, '重做', '全局')

  shortcutManager.register('Ctrl+F', () => {
    document.dispatchEvent(new CustomEvent('shortcut:search'))
  }, '搜索', '全局')

  shortcutManager.register('Ctrl+G', () => {
    document.dispatchEvent(new CustomEvent('shortcut:goto'))
  }, '跳转到指定科目', '试算表/穿透查询')

  shortcutManager.register('Ctrl+E', () => {
    document.dispatchEvent(new CustomEvent('shortcut:export'))
  }, '导出当前页面', '报表/附注/底稿')

  shortcutManager.register('Ctrl+ENTER', () => {
    document.dispatchEvent(new CustomEvent('shortcut:submit'))
  }, '提交/确认', '表单/弹窗')

  shortcutManager.register('ESCAPE', () => {
    document.dispatchEvent(new CustomEvent('shortcut:escape'))
  }, '关闭弹窗/退出全屏', '全局')

  shortcutManager.register('F5', () => {
    document.dispatchEvent(new CustomEvent('shortcut:refresh'))
  }, '刷新当前数据', '全局')

  shortcutManager.register('Ctrl+/', () => {
    document.dispatchEvent(new CustomEvent('shortcut:help'))
  }, '显示快捷键帮助面板', '全局')

  shortcutManager.register('Ctrl+TAB', () => {
    document.dispatchEvent(new CustomEvent('shortcut:tab-focus'))
  }, '切换栏目焦点', '三栏/四栏布局')

  shortcutManager.register('Ctrl+ARROWUP', () => {
    document.dispatchEvent(new CustomEvent('shortcut:list-up'))
  }, '列表项上移', '列表页')

  shortcutManager.register('Ctrl+ARROWDOWN', () => {
    document.dispatchEvent(new CustomEvent('shortcut:list-down'))
  }, '列表项下移', '列表页')

  shortcutManager.install()
}
