# D2-7 凭证检查表导入导出端点 — 需求

## 背景（2026-11-04 现读）

D2-7 凭证检查表（`components/workpaper/d2/D2TabVoucherCheck.vue`）的「导入导出▾」三项经
`composables/useD2VcImportExport.ts` 调用三个端点：

| 前端调用 | 请求 | 期望回执 |
| --- | --- | --- |
| `exportTemplate` | `POST /api/workpapers/{wp_id}/d2/vc-export-template`（无请求体） | xlsx 文件 |
| `exportData` | `POST /api/workpapers/{wp_id}/d2/vc-export-data`，`{ currentRows, postRows }`（各为含表头行的二维数组） | xlsx 文件 |
| `importData` | `POST /api/workpapers/{wp_id}/d2/vc-import-data`，multipart `file` | `{ sheets: { 工作表名: 二维数组 } }` |

三个端点后端都不存在：spec `voucher-workflow-linkage-lineage-closure` 浏览器走查 s11 两次导入均 404，界面还多弹一条英文
「Request failed with status code 404」。原 spec `_archive/05-business-features/d2-7-voucher-check-enhancement` 的需求 12
标为完成，只交付了前端组合式函数与纯函数测试（假绿）。前序 spec 改过的 `mergeVoucherRows` 只被这条导入路径调用，目前不可达。

两区的持久化键是 `D2-vc-current-rows` / `D2-vc-post-rows`（`useD2VoucherCheckEnhanced.saveToResponses`，remark 存 JSON）；
导入后的合并（`mergeVoucherRows`，按凭证身份合并或追加）与保存（宿主严格 CAS PUT）都在前端完成。

## 需求

### R1 导出模板

1. 返回 xlsx，含两个工作表「本期增减变动检查」「期后收款调整检查」，每表第一行是 17 列表头，顺序与前端 `COLUMN_HEADERS` 一致。
2. 需对该底稿有读权限（与 `GET /checklist-responses` 同一读门）；无权 403，底稿不存在 404。

### R2 导出数据

1. 按请求体的两组二维数组原样写入两个工作表（导出的是表格当前内容，含尚未保存的编辑）。
2. 请求体形状不对（不是二维数组、列数超过 17、单区超过行数上限）返回 422，写明哪一区、哪一项不对。
3. 以 `=` `+` `-` `@` 开头的文本按文本写入，不得变成公式（防止导出文件里注入公式）。
4. 读门同 R1。

### R3 导入数据

1. 只收 `.xlsx`；文件超过大小上限返回 413；解析失败返回 400 并写明原因（中文）。
2. 只解析、不写库：回执 `{ sheets: { 工作表名: 二维数组 }, warnings: [...] }`，二维数组第一行为表头行，单元格按值读取
   （公式格取缓存值），日期单元格转成 `YYYY-MM-DD` 文本，数字保持数字，空单元格为 `null`。
3. 单表超过行数上限时截断并在 `warnings` 写明；整本都没有可识别的工作表时照常返回（前端按「未找到某工作表，已跳过」提示）。
4. 需对该底稿有写权限（与保存 checklist 同一写门，导入结果随后会被保存）；无权 403，底稿不存在 404。

### R4 前端提示

1. 三个请求不再触发全局错误提示，失败时只显示一条中文提示，内容取后端写明的原因；网络断开等无回执的情况显示通用中文文案。
2. 导入成功后的合并、保存行为不变（按凭证身份合并或追加，随后经宿主保存）。

### R5 往返

1. 导出数据得到的文件原样导入后，两区 17 列逐值与导出前相同（按凭证编号对齐）。

## 非目标

- 旧的 `?sheet=D2-7`（`_d2_import_export.py`，存 `D2-voucher-samples` 的单表口径）去留另议，本 spec 不改。
- 不改 `mergeVoucherRows` 的合并规则与两区分区规则。
- 不做服务端写库式导入（与 D2 其他页签的「导入即写库」不同，这里保持前端合并后保存，避免绕过严格 CAS）。
