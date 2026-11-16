# D2-7 凭证检查表导入导出端点 — 设计

## 1. 决策

- **01 新模块**：`backend/app/routers/wp_render_strategies/_d2_vc_import_export.py`，在 `router_registry/workpaper.py`
  与 `_d2_import_export` 并列登记（后者已超 1700 行，不再往里加）。新增路由后按 memory 铁律重启 start-dev 才生效。
- **02 契约以前端组合式函数为准**：路径、请求体、回执形状照 `useD2VcImportExport.ts` 现有写法，不改前端调用方式，
  只给三个请求加 `_silent: true` 与中文错误文案（R4）。
- **03 导入只解析不写库**：合并与保存留在前端（`mergeVoucherRows` + `saveToResponses` → 宿主严格 CAS PUT）。服务端写库
  会绕过 `if_match`，且要在后端再实现一遍按凭证身份合并，两份实现必然漂移。
- **04 导出数据按请求体写**：导出的是当前表格（含未保存编辑）。不从库里读，避免「导出的不是我看到的」。
- **05 鉴权**：导出模板 / 导出数据走读门，导入走写门，都用 `enforce_wp_gate`（读：`workpaper.checklist_read` /
  `read_checklist`；写：`workpaper.checklist_save` / `save_checklist`，与 `checklist_responses` 同一矩阵动作）。
  路径 `wp_id` 用 `uuid.UUID` 类型（非 UUID 直接 422，不让 gate 拿到非法 id）。

## 2. 常量与对拍

- 后端 `SHEET_CURRENT = "本期增减变动检查"`、`SHEET_POST = "期后收款调整检查"`、`COLUMN_HEADERS`（17 列，顺序同前端）。
- 守卫：后端测试读前端 `useD2VcImportExport.ts` 源码里的 `SHEET_NAME_CURRENT` / `SHEET_NAME_POST` / `COLUMN_HEADERS`
  字面量，与后端常量逐值比对（写法参照凭证结论取值表的前后端契约测试）；任一侧改名即红。

## 3. 端点

| 端点 | 依赖 | 处理 | 回执 |
| --- | --- | --- | --- |
| `vc-export-template` | 读门 | openpyxl 建两表，写表头，加粗、冻结首行、列宽 | `StreamingResponse` xlsx，`Content-Disposition` 用 RFC 5987 中文文件名 |
| `vc-export-data` | 读门 | pydantic 校验 `currentRows` / `postRows`：`list[list[str \| int \| float \| None]]`，单区 ≤ 2000 行、每行 ≤ 17 列；按行写入 | 同上 |
| `vc-import-data` | 写门 | 校验扩展名与大小（≤ 10 MB，超出 413）；`load_workbook(read_only=True, data_only=True)`；逐表 `iter_rows(values_only=True)` | `{ sheets, warnings }` |

- **写单元格**：字符串一律写成文本单元格（`cell.data_type = "s"`，或对 `=` `+` `-` `@` 开头的值显式按文本写），
  不能依赖 openpyxl 默认（`=` 开头的字符串会被当成公式）。
- **读单元格**：`datetime` / `date` → `YYYY-MM-DD`；`float` 且为整数值的保持数值（前端 `Number()` 处理）；其余 `str(value)`；
  每行去掉行尾全空单元格；全空行保留为空数组还是跳过 —— 前端 `deserializeSheetDataToRows` 会跳过全空行，后端按原样返回。
- **上限**：每表最多读 5000 行（含表头），超出截断并写 `warnings`：「工作表“…”超过 5000 行，只读取前 5000 行」。
- **错误**：非 `.xlsx` 400「仅支持 .xlsx 文件」；openpyxl 打不开 400「文件无法解析：…」；过大 413；无权 403；底稿不存在 404。
  错误文案中文，经平台信封返回；前端从 `detail` / `message` 取（实施时按 `ResponseWrapperMiddleware` 的错误形状现读）。

## 4. 前端（`useD2VcImportExport.ts`）

- 三个 `http.post` 第三参数加 `_silent: true`（全局拦截器不再弹英文提示）。
- 错误文案：后端原因优先；无回执（网络错误）用「导入失败，请检查网络后重试」一类中文；不再把 axios 英文 `err.message` 直接显示。
- 其余不改。

## 5. 测试

| 范围 | 用例 |
| --- | --- |
| 端点（TestClient 真发请求） | 读门：只读成员可导出、非成员 403、底稿不存在 404；写门：只读成员导入 403；非 UUID 422 |
| 导出 | 两表名与 17 列表头逐值；数据逐行写入；`=1+1` 等写成文本（读回 `data_type == "s"`）；超行数 / 超列数 422 |
| 导入 | 日期转文本、整数保持数值、空单元格 `null`；缺表照常返回；超 5000 行截断 + warning；非 xlsx 400；坏文件 400；超大 413 |
| 往返 | 导出数据 → 导入 → 二维数组与导出前逐格相等 |
| 对拍 | 前后端工作表名、表头常量逐值一致 |
| 前端 | 三个请求带 `_silent`；失败只显示一条中文提示 |
| 变异 | 去掉写门 / 读门、去掉文本写法、去掉日期转换、去掉截断，各至少一条用例打红 |
| 浏览器 | D2-7「导入导出▾」：导出模板 → 填两区 → 导入 → 合并显示 → 保存 → 刷新回读；导出数据后打开文件核对 |

## 6. 风险

- openpyxl `read_only=True` 下合并单元格只在左上角有值，其余为 `None`；本表无合并单元格，按原样返回即可。
- 行数上限是保护性的拍定值（2000 / 5000），若真实底稿超过，再按实测调整。
