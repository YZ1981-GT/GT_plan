# 底稿双向回写 umbrella spec 验收准则

> **⚠️ 因果约束：本文件是 `backend/data/workpaper_sync_migration_paradigm.json`
> 中 `adjudication_criteria.acceptance_criteria[].text` 的投影，不是独立编写的需求文档。**
>
> - **单一来源**：paradigm JSON 的 AC 文本是权威源。
> - **修改流程**：改 AC 必须先改 paradigm JSON，再重生成本文件。禁止只改本文件。
> - **守卫**：`test_migration_paradigm_contract.py::TestAcceptanceCriteriaVerbatim`
>   逐字比对本文件与 paradigm JSON，不一致即打红。
> - **重生成命令**：
>   ```
>   python -c "
>   import json; from pathlib import Path
>   p = json.loads(Path('backend/data/workpaper_sync_migration_paradigm.json').read_bytes().decode('utf-8'))
>   lines = ['# 底稿双向回写 umbrella spec 验收准则', '', '> ...（保留本段因果约束说明）', '']
>   for item in p['adjudication_criteria']['acceptance_criteria']:
>       lines.append(f\"{item['ac']}. {item['text']}\"); lines.append('')
>   Path('.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/requirements.md').write_text('\\n'.join(lines), 'utf-8')
>   "
>   ```

1.3. 能力态 SHALL 限定为 `bidirectional / single_html / single_onlyoffice / unreachable`，不得使用含糊的 `dual` 布尔值。

1.4. WHEN 入口未注册 adapter 或 adapter 未通过契约校验 THEN 前端 SHALL 禁止显示“可双向回写”，并显示可操作原因。

1.5. WHEN 入口被裁决为纯 OO 或纯 HTML THEN 系统 SHALL 只显示真实可用模式，不显示不可兑现的切换按钮。

1.7. 不可达旧桩 SHALL 删除；不得以豁免或 `DEPRECATED` 注释长期保留。

12.1. adapter 迁移 SHALL 由 manifest slice 驱动；每个独立 entry 必须记录 capability 裁决、authoritative model immutable definition、非空 immutable definition bundle id/digest 及其 template/instrumentation/contract typed slots、representation generation、自动测试、真实 OO operation 和验收态。projection-based entry 缺 approved per-entry contract/bundle 时不得进入 bidirectional 验收。

12.8. 无 HTML 对端的纯 OO entry SHALL 标为 `single_onlyoffice`；不得为满足数字伪造字段映射或修改模板制造对端。

12.9. 无 OO 业务价值或不可达入口 SHALL 删除或标 `single_html`；不得保留空白模板切换入口。
