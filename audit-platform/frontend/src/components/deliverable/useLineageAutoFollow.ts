/**
 * useLineageAutoFollow — 交付 docx 真·光标跟随溯源（OnlyOffice 连接器）
 *
 * Spec: deliverable-lineage-content-control Task 4
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 5.1, 5.3, 6.2, 7.2, 7.3
 *
 * 关键：连接器方法（executeMethod/attachEvent）属于 `editorInstance.createConnector()`
 * 返回的对象，**不是** DocEditor 实例本身的方法（历史 bug 根因）。
 * 全程 fail-open：连接器不可用/回调异常 → 不阻断编辑器，回退手动章节溯源。
 * 默认关闭（AUTO_FOLLOW_ENABLED 默认 false），P0 连接器 live 验证通过后方可开启。
 */

/**
 * 自动跟随启用标志。默认 false（未经 P0 live 验证不启用自动逻辑，需求 6.2/7.2/7.3）。
 * 可经环境变量 VITE_DELIVERABLE_LINEAGE_AUTOFOLLOW='true' 显式开启（验证通过后）。
 */
export const AUTO_FOLLOW_ENABLED: boolean =
  import.meta.env.VITE_DELIVERABLE_LINEAGE_AUTOFOLLOW === 'true'

/**
 * 从 onChangeContentControl / GetCurrentContentControl 回调载荷中提取 Tag。
 * OnlyOffice 不同版本载荷形状不一，做防御式多形态提取；无 Tag → null。
 */
export function extractControlTag(cc: any): string | null {
  if (!cc) return null
  const raw =
    cc.Tag ??
    cc.tag ??
    cc?.pr?.Tag ??
    cc?.pr?.tag ??
    (Array.isArray(cc) && cc.length ? cc[0]?.Tag ?? cc[0]?.tag : null) ??
    null
  return typeof raw === 'string' && raw ? raw : null
}

/** 是否为章节内容控件 Tag（sec_ 前缀）。 */
export function isSectionTag(tag: string | null): boolean {
  return !!tag && tag.startsWith('sec_')
}

export interface LineageAutoFollow {
  /** 主动查询当前光标所在内容控件并回调（打开面板时用，需求 4.1） */
  queryCurrent: () => void
  /** 解绑连接器事件（组件卸载调用，需求 3.5） */
  dispose: () => void
}

/**
 * 建立连接器并监听内容控件变化。fail-open：createConnector 抛错/不可用 → 返回空操作句柄。
 *
 * @param editorInstance OnlyOffice DocEditor 实例（须有 createConnector）
 * @param onSectionTag   命中 sec_ Tag 时的回调（触发溯源）
 */
export function createLineageAutoFollow(
  editorInstance: any,
  onSectionTag: (tag: string) => void,
): LineageAutoFollow {
  const noop: LineageAutoFollow = { queryCurrent: () => {}, dispose: () => {} }

  if (!editorInstance || typeof editorInstance.createConnector !== 'function') {
    return noop
  }

  let connector: any = null
  try {
    connector = editorInstance.createConnector()
  } catch {
    return noop
  }
  if (!connector) return noop

  const handleChange = (cc: any) => {
    try {
      const tag = extractControlTag(cc)
      if (isSectionTag(tag)) onSectionTag(tag as string)
      // 非 sec_ / 无 Tag → 忽略（需求 3.4）
    } catch {
      /* fail-open：回调异常不阻断 */
    }
  }

  try {
    connector.attachEvent?.('onChangeContentControl', handleChange)
  } catch {
    return noop
  }

  return {
    queryCurrent() {
      try {
        connector.executeMethod?.('GetCurrentContentControl', [], (res: any) => {
          handleChange(res)
        })
      } catch {
        /* fail-open：主动查询不支持则忽略，手动溯源仍可用 */
      }
    },
    dispose() {
      try {
        connector.detachEvent?.('onChangeContentControl')
      } catch {
        /* ignore */
      }
      connector = null
    },
  }
}
