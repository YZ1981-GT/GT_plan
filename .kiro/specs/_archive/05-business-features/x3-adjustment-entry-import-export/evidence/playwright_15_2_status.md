# 任务 15.2 Playwright 实测状态

## 结论（2026-08-16 第三轮）：核心链路全通，挖出并修复 1 个真实缺陷

项目 `2aa00f57-…`（重庆和平药房连锁有限责任公司_2025），16 张 X-3 均有真实底稿。

### 已验证（真实 UI 操作 + 落库核查 + 复原）

| sheet | 机制/键族 | 验证内容 | 结果 |
|---|---|---|---|
| **L2-3** | single_json / adjustment_savebatch(remark) | 下拉三项可见 → 上传 xlsx → 表格显示 3 行 → 落库 3 行 → 复原 | ✅ |
| **N2-3** | single_json / **父宿主重载**（props.allResponses 一次性 IIFE） | 上传 → 表格立即刷新显示 3 行 → 落库 → 复原 | ✅ |
| **N5-3** | single_json / formdata_setfield(conclusion) / **形态④ + 小写 aje/rje** | 上传 → 表格显示 3 行 → 落库 type='aje'（小写枚举正确）→ 复原 | ✅ |
| **L6-3** | per_field / **读回补齐（4.2 新增）** | 落库 → **刷新页面** → onMounted 读回补齐显示 3 行 → 复原 | ✅（修复后） |

三种视图刷新机制全覆盖：直接响应式（L2）/ 父宿主重载（N2）/ onMounted 读回补齐（L6）；
两种枚举大小写（大写 AJE/RJE 与 N5 小写 aje/rje）；single_json 与 per_field 两种键族。

### 🔴 挖出并修复的真实缺陷：L6-3 刷新即崩

- **现象**：L6-3 页刷新后整个 Tab 空白，console 报
  `TypeError: Cannot read properties of undefined (reading 'value') at L6TabAdjustment.vue`。
- **根因**：`L6TabAdjustment.vue` 的 `onMounted` 与 `handleImported` 调
  `loadFromResponses(formData.allResponses.value)`，但 `useL6FormData` 导出的是
  **`responses`** 不是 `allResponses`（M1/M2/M9 的 FormData 确实导出 `allResponses`，
  唯独 L6 不一致）⇒ `formData.allResponses` 为 undefined ⇒ 读 `.value` 抛错、Tab 挂载崩溃。
- **影响**：L6-3 用户填/导入的数据刷新后**永远看不到**（表格崩溃），且导入后
  `handleImported` 同样崩 ⇒ 4.2「读回补齐」与 11.1「导入读回」在 L6 上从未真正生效。
- **为何前面没抓到**：Vue 访问不存在的属性不报类型错，Volar/vitest/get_diagnostics/
  HEAD-swap 四层全绿；只有浏览器真挂载才暴露 —— 正是 15.2 Playwright 实测的价值。
- **修复**：`formData.allResponses.value` → `formData.responses.value`（两处）。
  修后刷新 L6-3 读回补齐正常显示 3 行。
- **防回归守卫**：`ieWiringIntegrity.spec.ts` 新增 **GS11**（16 条）——
  每张 X-3 Tab 读的 `formData.<字段>` 必须被对应 `use{X}FormData` 的 return 导出。
  反向自检 RED：把 L6 改回 `allResponses` 立即打红 `L6-3` 那条，还原后 48 passed。

### 千分符说明（非缺陷）

L2-3/L6-3 表单金额在 `el-input-number`（spinbutton）里显示原始值 `1234567.89`，
**无千分符** —— 这是 memory 记的平台既有行为（EP 2.13.6 的 input-number 无 formatter），
不是本 spec 引入。真正的千分符只在只读展示处（`fmtAmount`）生效，如 L6 的借贷合计条。

### 未逐一 UI 走查的其余张（M1/M2/M3~M10/N1/N3）

导入**落库能力**已由任务 15.1 `verify_x3_roundtrip_live.py` 证明（16/16 往返 + 还原，
16 个互不相同 wp_id、0 归属不符）。UI 层的差异化风险点 = 「导入后视图是否刷新」，
其三种机制已由上面 L2/N2/L6 + 字段一致性守卫 GS11（覆盖全 16 张）共同覆盖。
N3-3 与 N2-3 同为父宿主重载机制、同一份 useN2/N3 结构，GS11 已覆盖其字段一致性。

## 截图（evidence/）

- `playwright_L2-3_dropdown_3items.png` —— 下拉三项展开
- `playwright_L2-3_imported_3rows.png` —— L2-3 导入后 3 行 + 金额
- `playwright_N2-3_parent_reload.png` —— N2-3 父宿主重载显示导入行
- `playwright_N5-3_imported_form4.png` —— N5-3 形态④ + 小写枚举导入行
- `playwright_L6-3_readback_after_refresh_fixed.png` —— L6-3 修复后刷新读回 3 行
