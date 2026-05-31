"""扫描致同底稿模板目录，生成完整的 gt_template_library.json

用法：python backend/scripts/analyze/scan_wp_templates.py

扫描 `backend/wp_templates/` 目录下所有 Excel 文件，
从文件名解析底稿编码、循环、程序类型，更新 gt_template_library.json。
扫描完成后幂等 upsert wp_template_registry 表（JSON 是权威源，registry 是派生）。
"""
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = ROOT / "wp_templates"
OUTPUT_PATH = ROOT / "data" / "gt_template_library.json"

# 循环前缀 → 循环名称
CYCLE_MAP = {
    "B": "初步业务活动/风险评估",
    "C": "控制测试",
    "D": "收入循环",
    "E": "货币资金循环",
    "F": "存货循环",
    "G": "投资循环",
    "H": "固定资产循环",
    "I": "无形资产循环",
    "J": "职工薪酬循环",
    "K": "管理循环",
    "L": "债务循环",
    "M": "权益循环",
    "N": "税金循环",
    "A": "完成阶段",
    "S": "特定项目程序",
    "Q": "关联方循环",
}

# 程序类型推断
def _infer_wp_type(filename: str, parent_dir: str) -> str:
    fn = filename.lower()
    pd = parent_dir.lower()
    if "函证" in fn or "函证" in pd:
        return "confirmation"
    if "分析程序" in fn or "分析" in pd:
        return "analytical"
    if "检查" in fn or "检查" in pd:
        return "inspection"
    if "舞弊" in fn or "ipo" in fn or "上市" in fn:
        return "fraud_response"
    if "控制测试" in fn or "控制测试" in pd:
        return "control_test"
    if "穿行测试" in fn:
        return "walkthrough"
    if "审定表" in fn or "明细表" in fn or "常规程序" in pd:
        return "substantive"
    if "风险评估" in pd or "了解" in fn:
        return "risk_assessment"
    if "初步业务" in pd:
        return "preliminary"
    if "完成阶段" in pd:
        return "completion"
    return "substantive"

# 从文件名提取底稿编码
CODE_PATTERN = re.compile(r'^([A-Z]\d+(?:-\d+)?(?:至[A-Z]\d+-\d+)?(?:[A-Za-z])?)')

def _extract_code(filename: str) -> str | None:
    stem = Path(filename).stem
    # 跳过临时文件
    if stem.startswith("~$"):
        return None
    m = CODE_PATTERN.match(stem)
    return m.group(1) if m else None

def _extract_cycle_prefix(code: str) -> str:
    return code[0] if code else "?"

def scan():
    if not TEMPLATE_DIR.exists():
        print(f"模板目录不存在: {TEMPLATE_DIR}")
        sys.exit(1)

    templates = []
    seen_codes = set()

    for xlsx_path in sorted(TEMPLATE_DIR.rglob("*.xlsx")):
        if xlsx_path.name.startswith("~$"):
            continue
        code = _extract_code(xlsx_path.name)
        if not code:
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)

        cycle_prefix = _extract_cycle_prefix(code)
        cycle_name = CYCLE_MAP.get(cycle_prefix, f"{cycle_prefix}类")
        wp_type = _infer_wp_type(xlsx_path.name, xlsx_path.parent.name)
        rel_path = xlsx_path.relative_to(ROOT).as_posix()

        templates.append({
            "code": code,
            "name": xlsx_path.stem.split(" ", 1)[-1] if " " in xlsx_path.stem else xlsx_path.stem,
            "wp_type": wp_type,
            "cycle_prefix": cycle_prefix,
            "cycle_name": cycle_name,
            "file_path": rel_path,
            "description": "",
        })

    # 同时扫描 .xls 文件
    for xls_path in sorted(TEMPLATE_DIR.rglob("*.xls")):
        if xls_path.name.startswith("~$"):
            continue
        if xls_path.suffix == ".xlsx":
            continue
        code = _extract_code(xls_path.name)
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        cycle_prefix = _extract_cycle_prefix(code)
        cycle_name = CYCLE_MAP.get(cycle_prefix, f"{cycle_prefix}类")
        wp_type = _infer_wp_type(xls_path.name, xls_path.parent.name)
        rel_path = xls_path.relative_to(ROOT).as_posix()
        templates.append({
            "code": code,
            "name": xls_path.stem.split(" ", 1)[-1] if " " in xls_path.stem else xls_path.stem,
            "wp_type": wp_type,
            "cycle_prefix": cycle_prefix,
            "cycle_name": cycle_name,
            "file_path": rel_path,
            "description": "",
        })

    templates.sort(key=lambda t: t["code"])

    output = {
        "description": "致同标准底稿模板库目录 — 自动扫描生成",
        "version": "2025-R1",
        "scan_source": str(TEMPLATE_DIR.relative_to(ROOT)),
        "total_count": len(templates),
        "templates": templates,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"扫描完成：{len(templates)} 个底稿模板 → {OUTPUT_PATH}")

    # 按循环统计
    from collections import Counter
    cycle_counts = Counter(t["cycle_prefix"] for t in templates)
    for prefix in sorted(cycle_counts):
        name = CYCLE_MAP.get(prefix, prefix)
        print(f"  {prefix} ({name}): {cycle_counts[prefix]} 个")

async def sync_registry_from_json(db=None):
    """JSON 生成后幂等 upsert wp_template_registry（JSON 是权威源，registry 是派生）。

    读取 gt_template_library.json（utf-8-sig 兼容 BOM），对每条 template 执行
    INSERT ... ON CONFLICT(wp_code) DO UPDATE，确保 registry 表与 JSON 完全同步。

    Args:
        db: 可选的 AsyncSession。若不传则自行创建会话。
    """
    from sqlalchemy import text

    # ROOT = backend/ 目录 (parent×3 from scripts/analyze/scan_wp_templates.py)
    # JSON 位于 backend/data/gt_template_library.json → ROOT / "data" / ...
    library_path = ROOT / "data" / "gt_template_library.json"
    if not library_path.exists():
        print(f"gt_template_library.json 不存在: {library_path}")
        return

    # utf-8-sig 读取以兼容 BOM
    raw = library_path.read_bytes()
    library = json.loads(raw.decode("utf-8-sig"))
    templates = library.get("templates", [])
    if not templates:
        print("JSON 中无 templates，跳过 registry 同步")
        return

    own_session = False
    if db is None:
        # 延迟导入避免脚本独立运行时路径问题
        sys.path.insert(0, str(ROOT / "backend"))
        from app.core.database import async_session
        db = async_session()
        own_session = True

    try:
        upsert_sql = text("""
            INSERT INTO wp_template_registry (wp_code, wp_name, cycle, source_origin)
            VALUES (:wp_code, :wp_name, :cycle, :source_origin)
            ON CONFLICT (wp_code) DO UPDATE SET
                wp_name = EXCLUDED.wp_name,
                cycle = EXCLUDED.cycle,
                source_origin = EXCLUDED.source_origin
        """)

        count = 0
        for tpl in templates:
            code = tpl.get("code", tpl.get("wp_code", ""))
            if not code:
                continue
            await db.execute(upsert_sql, {
                "wp_code": code,
                "wp_name": tpl.get("name", tpl.get("wp_name", "")),
                "cycle": tpl.get("cycle_prefix", code[0] if code else ""),
                "source_origin": "gt_template_library_json",
            })
            count += 1

        await db.commit()
        print(f"registry 同步完成：{count} 条 upsert → wp_template_registry")
    finally:
        if own_session:
            await db.close()


if __name__ == "__main__":
    scan()
    # scan 完成后同步 registry（需要数据库连接）
    try:
        asyncio.run(sync_registry_from_json())
    except Exception as e:
        logging.warning(f"registry 同步跳过（数据库不可用）: {e}")
