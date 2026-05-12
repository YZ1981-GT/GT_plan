/**
 * ShortcutManager — 快捷键管理
 * Phase 8 Task 9.3
 */
import { eventBus } from '@/utils/eventBus'

export interface ShortcutEntry {
  key: string
  handler: () => void
  description: string
  scope?: string
}

/**
 * 检查当前焦点是否在输入框/文本域/可编辑元素内
 * 用于在输入框中忽略全局快捷键（Escape 除外）
 */
export function isInputFocused(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.contentEditable === 'true'
  )
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
    // 在输入框/文本域/可编辑元素里忽略快捷键（Escape 除外）
    if (isInputFocused(event) && event.key !== 'Escape') return
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
export function registerDefaultShortcuts(_router: any) {
  shortcutManager.register('Ctrl+S', () => {
    eventBus.emit('shortcut:save')
  }, '保存当前编辑内容', '底稿编辑/附注编辑/报告编辑')

  // [R9 F9 Task 31] Ctrl+Z/Y 不再由 shortcutManager 注册
  // Univer 编辑器内置 undo/redo 命令系统，原生处理 Ctrl+Z/Ctrl+Shift+Z
  // 如果 shortcutManager 拦截这些快捷键，会阻止 Univer 的撤销/重做功能

  // 注意：不注册 Ctrl+F，避免阻止浏览器原生搜索。
  // 各模块（TrialBalance/DisclosureEditor）自行监听 keydown 实现表内搜索。

  shortcutManager.register('Ctrl+G', () => {
    eventBus.emit('shortcut:goto')
  }, '跳转到指定科目', '试算表/穿透查询')

  shortcutManager.register('Ctrl+E', () => {
    eventBus.emit('shortcut:export')
  }, '导出当前页面', '报表/附注/底稿')

  shortcutManager.register('Ctrl+ENTER', () => {
    eventBus.emit('shortcut:submit')
  }, '提交/确认', '表单/弹窗')

  shortcutManager.register('ESCAPE', () => {
    eventBus.emit('shortcut:escape')
  }, '关闭弹窗/退出全屏', '全局')

  shortcutManager.register('F5', () => {
    eventBus.emit('shortcut:refresh')
  }, '刷新当前数据', '全局')

  shortcutManager.register('Ctrl+/', () => {
    eventBus.emit('shortcut:help')
  }, '显示快捷键帮助面板', '全局')

  shortcutManager.register('F1', () => {
    eventBus.emit('shortcut:help')
  }, '显示快捷键帮助面板', '全局')

  shortcutManager.register('Ctrl+TAB', () => {
    eventBus.emit('shortcut:tab-focus')
  }, '切换栏目焦点', '三栏/四栏布局')

  shortcutManager.register('Ctrl+ARROWUP', () => {
    eventBus.emit('shortcut:list-up')
  }, '列表项上移', '列表页')

  shortcutManager.register('Ctrl+ARROWDOWN', () => {
    eventBus.emit('shortcut:list-down')
  }, '列表项下移', '列表页')

  shortcutManager.install()
}
