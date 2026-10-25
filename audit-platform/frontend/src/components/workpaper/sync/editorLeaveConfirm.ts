/**
 * 离开在线编辑前，让 OnlyOffice 自己检查「正在输入、还没按回车」的单元格（R1.6）。
 *
 * spec: oo-return-to-form-dead-end-and-save-speed · R1.6（实测结论见 design §9）
 *
 * ═══ OnlyOffice 9.4 实测（2026-10-25，【测试】在线编辑回表单验收 D2-2）═══
 *
 * * 单元格输入中（未按回车）`onDocumentStateChange` 一次都不触发 ⇒ 桥认为没改动、走 clean close，
 *   输入的内容静默丢失 —— 这正是要补的洞。
 * * 没有未保存内容时 `requestClose()` 约 1 ms 内回 `onRequestClose`。
 * * 有输入中的单元格时编辑器弹自己的「警告：此电子表格中所有未保存的更改都将丢失」（确定 / 取消），
 *   弹窗期间不发任何事件；选「取消」也不发任何事件；选「确定」先撤销全部改动（随之
 *   `onDocumentStateChange` true → false），再发 `onRequestClose`。
 *
 * ═══ 因此 ═══
 *
 * 1. 探测：发 `requestClose()`，`probeMs` 内收到答复 ⇒ 放行；收不到 ⇒ 编辑器正在提示用户，本次留下
 *    （给一句指引），并记住「提示中」。
 * 2. 提示中用户选了「确定」（晚到的答复）⇒ 交给宿主重走一遍回表单（`onLateClose`）。撤销会把桥的
 *    dirty 置真，所以宿主走的是「保存并回到表单模式」同一条路（强制保存，返回码 4 即放行）。
 * 3. 提示中又点离开 ⇒ 再探测一次；仍无答复就弹平台自己的确认（`askDiscard`）—— 编辑器无响应时也
 *    一定有出口（「任何结论都不得重新挡住离开」）。平台确认期间编辑器先答复了 ⇒ 关掉平台的确认，
 *    按第 2 条处理。
 * 4. 编辑器不在 / 不支持 `requestClose` ⇒ 当场放行（同步，不给离开路径多加一跳）。
 */
import type { WorkpaperSyncLeaveVerdict } from './bridgeLeave'

/** 等编辑器答复的上限。实测无未保存内容时约 1 ms；这里只决定「判定为编辑器在提示」要多久。 */
export const LEAVE_CONFIRM_PROBE_MS = 800

/** 编辑器弹出未保存提示时给用户的指引（OnlyOffice 自己的文案说的是它自带的「保存」按钮）。 */
export const LEAVE_EDITOR_PROMPT_NOTICE =
  '编辑器里还有正在输入的单元格：在编辑器的提示里选「确定」会放弃这些输入并回到表单；'
  + '选「取消」后按回车确认输入，再点「保存并回到表单模式」。'

export interface EditorLeaveConfirmOptions {
  /** 当前编辑器实例（没有 / 不支持 `requestClose` ⇒ 当场放行）。 */
  editor(): { requestClose?: () => void } | null
  /** 平台自己的「放弃输入并回到表单？」确认。true = 放弃并回表单。 */
  askDiscard(): Promise<boolean>
  /** 关掉仍在显示的平台确认（编辑器先答复了）。 */
  dismissAsk(): void
  /** 编辑器正在提示用户（探测无答复）。 */
  onEditorPrompt(): void
  /** 提示中用户在编辑器里选了「确定」：重走一遍回表单。 */
  onLateClose(): void
  probeMs?: number
}

export interface EditorLeaveConfirm {
  /** 交给桥 `setLeaveConfirmer` 的确认函数。 */
  confirm(): WorkpaperSyncLeaveVerdict | Promise<WorkpaperSyncLeaveVerdict>
  /** 编辑器的 `onRequestClose`。 */
  handleRequestClose(): void
  /** 会话结束 / 编辑器销毁：清掉提示中状态，等待中的确认按「留下」结算。 */
  reset(): void
  /** 编辑器是否正在提示（只读）。 */
  readonly prompting: boolean
}

export function createEditorLeaveConfirm(options: EditorLeaveConfirmOptions): EditorLeaveConfirm {
  const probeMs = options.probeMs ?? LEAVE_CONFIRM_PROBE_MS
  let prompting = false
  let pending: Promise<WorkpaperSyncLeaveVerdict> | null = null
  /** 正在等编辑器答复的那一方（探测，或平台确认期间）：收到 `onRequestClose` ⇒ answered，会话结束 ⇒ aborted。 */
  let answer: ((outcome: 'answered' | 'aborted') => void) | null = null

  /** 发一次 requestClose，等到答复或超时。发送抛错 ⇒ 视为已答复（不挡离开）。 */
  function probe(requestClose: () => void): Promise<'answered' | 'timeout' | 'aborted'> {
    return new Promise((resolve) => {
      const finish = (outcome: 'answered' | 'timeout' | 'aborted'): void => {
        if (answer !== finish) return
        answer = null
        clearTimeout(timer)
        resolve(outcome)
      }
      answer = finish
      const timer = setTimeout(() => finish('timeout'), Math.max(0, probeMs))
      try {
        requestClose()
      } catch {
        finish('answered')
      }
    })
  }

  /**
   * 平台确认与编辑器答复谁先到听谁的。编辑器先答复（用户在它的提示里选了「确定」，撤销会把 dirty
   * 置真）⇒ 关掉平台确认、本次留下，随后按晚到答复重走一遍回表单（拿最新的 dirty 判走哪条路）。
   */
  function askOrEditorAnswer(): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      let settled = false
      const settle = (discard: boolean): void => {
        if (settled) return
        settled = true
        if (answer === onEditor) answer = null
        resolve(discard)
      }
      const onEditor = (outcome: 'answered' | 'aborted'): void => {
        if (settled) return
        settle(false)
        options.dismissAsk()
        if (outcome === 'answered') setTimeout(() => options.onLateClose(), 0)
      }
      answer = onEditor
      options.askDiscard().then(settle, () => settle(false))
    })
  }

  async function run(requestClose: () => void): Promise<WorkpaperSyncLeaveVerdict> {
    try {
      const outcome = await probe(requestClose)
      if (outcome === 'answered') {
        prompting = false
        return 'close'
      }
      if (outcome === 'aborted') return 'stay'
      if (!prompting) {
        prompting = true
        options.onEditorPrompt()
        return 'stay'
      }
      // 编辑器仍在提示（或已无响应）：由平台自己的确认兜底。
      const discard = await askOrEditorAnswer()
      if (discard) prompting = false
      return discard ? 'close' : 'stay'
    } finally {
      pending = null
    }
  }

  return {
    confirm() {
      if (pending !== null) return pending
      const editor = options.editor()
      if (editor === null || typeof editor.requestClose !== 'function') return 'close'
      pending = run(() => editor.requestClose?.())
      return pending
    },
    handleRequestClose() {
      if (answer !== null) {
        answer('answered')
        return
      }
      if (prompting) {
        prompting = false
        options.onLateClose()
      }
      // 其余（不是我们发的 requestClose）不当作离开请求。
    },
    reset() {
      prompting = false
      if (answer !== null) answer('aborted')
    },
    get prompting() {
      return prompting
    },
  }
}
