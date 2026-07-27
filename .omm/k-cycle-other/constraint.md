# 约束（K 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 K 循环附加约束。

1. **同码科目（K1坏账/K2=1231、K5/L5=2701、K9/I6=6602）不得各自独立全额回写同一 TB 行**；
   审定合计关系须显式核对。
2. **减值归口**：非金融资产减值 → K11（6701）；金融资产 ECL → G14（6702），不混。
3. **主入口 `handleChildSave` 四要点**：解包 `{remark,conclusion}` 直存（不双层包裹）+ http 带 `/api` 前缀 +
   selfLoad 用 `_mergeResponses` 合并 `responses_snapshot` + TB 取数带 `year`。
4. **双模式**：`useK{n}DualMode` 用 `http.get`（带鉴权）+ 切 OO 前 GET `onlyoffice-config`（**带 project_id**）拉成功才切；
   el-segmented 用 `:model-value` + `@change`（禁 v-model）；目录 sheet 从 OO 分支排除。
5. **AI context 全转 str**，走 `POST /ai/generate-text`，禁 `JSON.stringify(context)`；每个文本区都要 AI 辅助。
6. **附注 `applyAutoFill` 读 `K{n}-1-rows` 按 name 匹配**（不读永不写入的 `-row-i-audited` 死键）。
7. **循环 IE**：`http.post('.../{prefix}/export-template', null, {params:{sheet}})`；
   后端 `_SPECS` 的 item_id / storage_field 必须与前端持久化键/字段一致。
8. **检查表对照源模板判类型**：凭证级 → 复用 `useK1VoucherCheck`（含核对①~⑤ + 检查比例 + 抽凭），
   核对标签经 `checkLabels` 按科目定制；合规清单才用 radio。
9. **抽凭 `phase` 仅 `preliminary|final`**（不用 current/substantive）；`year` 从 props 不硬编码。
10. **截止测试**：`POST /sampling/cutoff-test` + 显式 `cutoff_date`；跨期判定 K8/K9 用自然月、I2/I6 用截止日 XOR
    （两种语义都 spec'd，各自保留）；双侧证据缺失结论"证据不完整"。
11. **「从集中登记带入」用共享 `useAdjudicationBringIn`**（损益单科目/多分类/双科目/双维度/roll-forward 各按范式），
    弹窗逐笔选目标分类行（科目↔分类歧义不自动分配）。
12. **目录页按 E1 标准**（目录卡 + 结论看板 + 4 阶段泳道 + 本循环 grid，grid 用 `loadCycleWorkpaperCards` 源模板 canonical 清单）；
    目录 sheet 隐藏 header 工具栏。
