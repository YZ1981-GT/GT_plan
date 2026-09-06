/**
 * 强制保存（forcesave）回执的共享类型。
 *
 * 单独一个文件而不是写在 `GtOnlyOfficeSheet.vue` 里：`<script setup>` 不允许
 * `export interface`，而这个类型要被编辑器组件、同步 bridge 与宿主三方共用。
 */

/**
 * `GtOnlyOfficeSheet.forceSave()` 的回执。
 *
 * 🔴 刻意**没有**叫 `success` / `saved` 的字段。2026-09-06 D2-2 浏览器实测：
 * Command Service 返回 HTTP 200（命令已接受）与「文件真的落盘」相差 **12 秒**，
 * 期间去读磁盘文件拿到的是切换前的旧版本。一旦这里出现一个含糊的「成功」布尔，
 * 调用点必然拿它当落盘完成 —— 于是只暴露语义明确的两态。
 */
export interface ForceSaveResult {
  /** 命令是否被 OnlyOffice 接受。**不代表**已落盘。 */
  accepted: boolean
  /**
   * 文件是否**已耐久**：后端轮询确认磁盘文件 sha256 真的变了，
   * 或 OO 明确回报文档本无未保存改动（error=4）。
   *
   * 只有它为 `true` 才允许读磁盘文件做回写。
   */
  durable: boolean
  /** 可读原因，可直接作为用户可见文案。 */
  detail: string
  /**
   * 三态出站结果：`accepted`（还会有 callback，已等到落盘）/
   * `nothing_to_save`（无待保存内容，磁盘已最新）/ `rejected`（命令未送达或被拒）。
   */
  outcome?: string
  /**
   * canonical 文件在 forcesave 前后的指纹，**必须原样回传给 pull**。
   *
   * 服务端用它做第二道陈旧校验（前端那道门可以被绕过：直接打 API）。
   * 丢掉这个字段的后果是 pull 请求体变成 `{}`、服务端拿不到判据 ——
   * 2026-09-06 复测实录里就这么漏过一次。
   */
  artifact?: {
    before?: { mtime_ns?: number; size?: number; sha256?: string }
    after?: { mtime_ns?: number; size?: number; sha256?: string }
  }
}
