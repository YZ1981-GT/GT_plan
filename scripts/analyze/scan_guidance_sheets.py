"""扫描底稿模板文件，统计「编制说明」sheet 覆盖率

用法：
    .venv\\Scripts\\python.exe scripts/analyze/scan_guidance_sheets.py

功能：
1. 遍历 backend/wp_templates/ 下所有 xlsx/docx 文件
2. 检查每个文件是否包含编制说明相关内容
3. 输出覆盖率报告（总计 + 高复杂度底稿）
4. 若覆盖率 < 50%，为 top 20 高复杂度底稿创建静态指引 JSON
"""
import json
import re
import sys
from pathlib import Path

# python_calamine 用于快速读取 xlsx sheet 名称和内容
from python_calamine import CalamineWorkbook

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = ROOT / "backend" / "wp_templates"
LIBRARY_PATH = ROOT / "backend" / "data" / "gt_template_library.json"
GUIDANCE_DIR = ROOT / "backend" / "data" / "wp_guidance"

# 编制说明 sheet 名称匹配（大小写不敏感）
GUIDANCE_SHEET_NAMES = {"编制说明", "说明", "instructions"}

# 高复杂度底稿模式
HIGH_COMPLEXITY_PATTERNS = [
    re.compile(r"^A17$", re.IGNORECASE),
    re.compile(r"^B60$", re.IGNORECASE),
    re.compile(r"^B50$", re.IGNORECASE),
    re.compile(r"^B51$", re.IGNORECASE),
    re.compile(r"^[A-Z]\d+-1$", re.IGNORECASE),  # 审定表 *-1
    re.compile(r"^[A-Z]\d+A$", re.IGNORECASE),    # 程序表 *A (如 D0A, E1A)
    re.compile(r"^[A-Z]\d+-?\d*A$", re.IGNORECASE),  # 如 D0A, F1A
]

# 程序表匹配更宽泛：文件名含"程序表"
PROGRAM_TABLE_PATTERN = re.compile(r"程序表")


def is_high_complexity(code: str, filename: str = "") -> bool:
    """判断底稿编码是否为高复杂度"""
    for pat in HIGH_COMPLEXITY_PATTERNS:
        if pat.match(code):
            return True
    # 额外：文件名含"程序表"的也视为高复杂度
    if PROGRAM_TABLE_PATTERN.search(filename):
        return True
    return False


def check_xlsx_guidance(filepath: Path) -> dict:
    """检查 xlsx 文件是否含编制说明 sheet

    Returns:
        dict with keys: has_guidance, source, sheet_name
    """
    try:
        wb = CalamineWorkbook.from_path(str(filepath))
        sheet_names = wb.sheet_names
        # 检查是否有编制说明 sheet
        for name in sheet_names:
            if name.strip().lower() in GUIDANCE_SHEET_NAMES:
                return {
                    "has_guidance": True,
                    "source": "template_sheet",
                    "sheet_name": name,
                }
        # 没有专属 sheet，检查首 sheet 前 5 行是否有说明文本
        if sheet_names:
            rows = wb.get_sheet_by_index(0).to_python()
            header_text = ""
            for row in rows[:5]:
                for cell in row:
                    if cell and isinstance(cell, str) and len(str(cell).strip()) > 20:
                        header_text += str(cell).strip() + "\n"
            if header_text and len(header_text) > 50:
                return {
                    "has_guidance": True,
                    "source": "template_header",
                    "sheet_name": None,
                }
        return {"has_guidance": False, "source": None, "sheet_name": None}
    except Exception as e:
        return {"has_guidance": False, "source": None, "sheet_name": None, "error": str(e)}


def check_docx_guidance(filepath: Path) -> dict:
    """检查 docx 文件是否含编制说明段落（第一个表格之前的段落）"""
    try:
        from docx import Document
        doc = Document(str(filepath))
        # 收集第一个表格之前的段落
        instruction_text = []
        for element in doc.element.body:
            if element.tag.endswith("}tbl"):
                break  # 遇到第一个表格停止
            if element.tag.endswith("}p"):
                # 段落文本
                text = element.text.strip() if hasattr(element, "text") else ""
                if not text:
                    # 尝试从子元素获取
                    texts = []
                    for child in element.iter():
                        if child.text:
                            texts.append(child.text)
                        if child.tail:
                            texts.append(child.tail)
                    text = "".join(texts).strip()
                if text and len(text) > 10:
                    instruction_text.append(text)

        if instruction_text and len("\n".join(instruction_text)) > 30:
            return {"has_guidance": True, "source": "docx_instructions"}
        return {"has_guidance": False, "source": None}
    except Exception as e:
        return {"has_guidance": False, "source": None, "error": str(e)}



def scan_templates() -> list[dict]:
    """扫描所有模板文件，返回结果列表"""
    if not TEMPLATE_DIR.exists():
        print(f"错误：模板目录不存在: {TEMPLATE_DIR}")
        sys.exit(1)

    results = []
    seen_paths = set()

    # 扫描所有 xlsx 文件
    for filepath in sorted(TEMPLATE_DIR.rglob("*.xlsx")):
        if filepath.name.startswith("~$"):
            continue
        if filepath in seen_paths:
            continue
        seen_paths.add(filepath)

        code = _extract_code(filepath.name)
        rel_path = filepath.relative_to(ROOT).as_posix()
        guidance_info = check_xlsx_guidance(filepath)

        results.append({
            "code": code or filepath.stem,
            "filename": filepath.name,
            "file_type": "xlsx",
            "rel_path": rel_path,
            "high_complexity": is_high_complexity(code or "", filepath.name),
            **guidance_info,
        })

    # 扫描所有 docx 文件
    for filepath in sorted(TEMPLATE_DIR.rglob("*.docx")):
        if filepath.name.startswith("~$"):
            continue
        if filepath in seen_paths:
            continue
        seen_paths.add(filepath)

        code = _extract_code(filepath.name)
        rel_path = filepath.relative_to(ROOT).as_posix()
        guidance_info = check_docx_guidance(filepath)

        results.append({
            "code": code or filepath.stem,
            "filename": filepath.name,
            "file_type": "docx",
            "rel_path": rel_path,
            "high_complexity": is_high_complexity(code or "", filepath.name),
            **guidance_info,
        })

    # 也扫描 .doc 文件（较少）
    for filepath in sorted(TEMPLATE_DIR.rglob("*.doc")):
        if filepath.name.startswith("~$"):
            continue
        if filepath.suffix == ".docx":
            continue
        if filepath in seen_paths:
            continue
        seen_paths.add(filepath)

        code = _extract_code(filepath.name)
        rel_path = filepath.relative_to(ROOT).as_posix()

        results.append({
            "code": code or filepath.stem,
            "filename": filepath.name,
            "file_type": "doc",
            "rel_path": rel_path,
            "high_complexity": is_high_complexity(code or "", filepath.name),
            "has_guidance": False,
            "source": None,
            # .doc 格式无法用 python-docx 读取
        })

    return results


# 从文件名提取底稿编码（复用 scan_wp_templates 的模式）
CODE_PATTERN = re.compile(r'^([A-Z]\d+(?:-\d+)?(?:[A-Za-z])?)')


def _extract_code(filename: str) -> str | None:
    stem = Path(filename).stem
    if stem.startswith("~$"):
        return None
    m = CODE_PATTERN.match(stem)
    return m.group(1) if m else None


def print_report(results: list[dict]):
    """输出覆盖率报告"""
    total = len(results)
    with_guidance = [r for r in results if r.get("has_guidance")]
    without_guidance = [r for r in results if not r.get("has_guidance")]

    high_complexity = [r for r in results if r.get("high_complexity")]
    high_with = [r for r in high_complexity if r.get("has_guidance")]
    high_without = [r for r in high_complexity if not r.get("has_guidance")]

    coverage = len(with_guidance) / total * 100 if total > 0 else 0
    high_coverage = len(high_with) / len(high_complexity) * 100 if high_complexity else 0

    print("=" * 60)
    print("  底稿模板「编制说明」覆盖率分析报告")
    print("=" * 60)
    print()
    print(f"  扫描目录: {TEMPLATE_DIR}")
    print(f"  文件总数: {total}")
    print()
    print("─" * 60)
    print("  整体覆盖率")
    print("─" * 60)
    print(f"  有编制说明: {len(with_guidance)} ({coverage:.1f}%)")
    print(f"  无编制说明: {len(without_guidance)} ({100-coverage:.1f}%)")
    print()

    # 按来源分类
    by_source = {}
    for r in with_guidance:
        src = r.get("source", "unknown")
        by_source.setdefault(src, []).append(r)
    print("  来源分布:")
    for src, items in sorted(by_source.items()):
        print(f"    {src}: {len(items)} 个")
    print()

    print("─" * 60)
    print("  高复杂度底稿覆盖率")
    print("─" * 60)
    print(f"  高复杂度总数: {len(high_complexity)}")
    print(f"  有编制说明: {len(high_with)} ({high_coverage:.1f}%)")
    print(f"  无编制说明: {len(high_without)} ({100-high_coverage:.1f}%)")
    print()

    if high_without:
        print("  高复杂度无编制说明列表:")
        for r in high_without[:30]:
            print(f"    {r['code']:12s} | {r['filename']}")
    print()

    print("─" * 60)
    print(f"  总覆盖率: {coverage:.1f}%")
    if coverage < 50:
        print("  ⚠️  覆盖率低于 50%，将为 top 20 高复杂度底稿创建静态指引")
    else:
        print("  ✅ 覆盖率达标（≥ 50%）")
    print("=" * 60)

    return coverage, high_without


def create_static_guidance_files(high_without: list[dict], limit: int = 20):
    """为无编制说明的高复杂度底稿创建静态指引 JSON"""
    GUIDANCE_DIR.mkdir(parents=True, exist_ok=True)

    # 已有的 guidance 文件
    existing = {p.stem for p in GUIDANCE_DIR.glob("*.json") if not p.stem.startswith("_")}

    created = 0
    for item in high_without[:limit]:
        code = item["code"]
        if not code or code in existing:
            continue

        # 根据底稿类型生成基础指引
        guidance = _generate_basic_guidance(code, item.get("filename", ""))
        out_path = GUIDANCE_DIR / f"{code}.json"
        out_path.write_text(
            json.dumps(guidance, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        created += 1
        print(f"  创建: {out_path.name}")

    print(f"\n  共创建 {created} 个静态指引文件 → {GUIDANCE_DIR}")


def _generate_basic_guidance(code: str, filename: str) -> dict:
    """根据底稿编码和文件名生成基础静态指引"""
    # 从文件名提取底稿名称
    stem = Path(filename).stem if filename else code
    # 去掉编码前缀提取名称
    name = stem
    if " " in stem:
        name = stem.split(" ", 1)[1]

    # 根据底稿类型生成不同内容（关键底稿优先匹配）
    if code in ("A17", "B60", "B50", "B51"):
        return _guidance_key_workpaper(code, name)
    elif code.endswith("-1") or "审定表" in filename:
        return _guidance_determination_table(code, name)
    elif code.endswith("A") or "程序表" in filename:
        return _guidance_program_table(code, name)
    else:
        return _guidance_generic(code, name)


def _guidance_determination_table(code: str, name: str) -> dict:
    """审定表类底稿指引"""
    return {
        "wp_code": code,
        "title": f"{name} — 编制说明",
        "sections": [
            {
                "heading": "一、编制目的",
                "content": f"本审定表用于汇总{name}的审计结论，确认各科目金额的真实性和完整性。"
            },
            {
                "heading": "二、取数来源",
                "content": "期初数：从上年审定数或本期期初余额表取得。\n本期数：从序时账/明细账汇总取得，经审计调整后得到审定数。"
            },
            {
                "heading": "三、编制步骤",
                "content": "1. 获取相关科目的明细账和余额表数据\n2. 核对期初余额与上年审定数\n3. 复核本期发生额的合理性\n4. 确认审计调整事项（AJE/RJE）\n5. 计算审定金额并与报表核对"
            },
            {
                "heading": "四、注意事项",
                "content": "• 审定金额应与试算平衡表一致\n• 重分类调整仅影响列报不影响损益\n• 关注科目余额方向是否异常"
            }
        ],
        "source": "static_json"
    }


def _guidance_program_table(code: str, name: str) -> dict:
    """程序表类底稿指引"""
    return {
        "wp_code": code,
        "title": f"{name} — 编制说明",
        "sections": [
            {
                "heading": "一、编制目的",
                "content": f"本程序表列示{name}相关的审计程序，指导审计人员逐步完成各项审计工作。"
            },
            {
                "heading": "二、使用方法",
                "content": "1. 按顺序逐项执行各审计程序\n2. 在「执行情况」列记录执行结果\n3. 在「工作底稿索引号」列填写相关底稿编号\n4. 不适用的程序注明原因"
            },
            {
                "heading": "三、注意事项",
                "content": "• 每个步骤需标注完成状态\n• 关联底稿通过索引号链接\n• 特殊情况需在备注中说明\n• 程序的适用性应结合项目实际判断"
            }
        ],
        "source": "static_json"
    }


def _guidance_key_workpaper(code: str, name: str) -> dict:
    """关键底稿（A17/B60 等）指引"""
    content_map = {
        "A17": {
            "title": "重大事项概要 — 编制说明",
            "sections": [
                {"heading": "一、编制目的", "content": "汇总审计过程中发现的所有重大事项，形成审计结论的综合支撑文件。"},
                {"heading": "二、主要内容", "content": "包括：审计范围、独立性确认、重大错报风险应对、关键审计事项、持续经营评价、期后事项、审计结论等 16 个章节。"},
                {"heading": "三、编制步骤", "content": "1. 逐章填写各项内容\n2. 引用相关底稿索引号\n3. 确认各章节结论一致性\n4. 项目合伙人复核签字"},
            ]
        },
        "B60": {
            "title": "总体审计策略 — 编制说明",
            "sections": [
                {"heading": "一、编制目的", "content": "制定审计业务的总体策略，确定审计范围、时间安排和方向。"},
                {"heading": "二、主要内容", "content": "包括：审计范围界定、重要性水平确定、资源分配计划、时间预算安排、团队组成等。"},
                {"heading": "三、编制步骤", "content": "1. 确定审计范围和报告目标\n2. 确定重要性水平\n3. 识别重大错报风险领域\n4. 确定资源和时间预算\n5. 形成审计计划概要"},
            ]
        },
        "B50": {
            "title": "风险评估汇总 — 编制说明",
            "sections": [
                {"heading": "一、编制目的", "content": "汇总对被审计单位重大错报风险的评估结果，指导后续审计程序的设计。"},
                {"heading": "二、主要内容", "content": "包括：财务报表层面风险评估、认定层面风险评估、特别风险识别、风险应对策略。"},
                {"heading": "三、编制步骤", "content": "1. 汇总了解阶段识别的风险因素\n2. 评估各风险的可能性和影响程度\n3. 确定特别风险\n4. 设计总体应对措施\n5. 链接至各循环程序表"},
            ]
        },
        "B51": {
            "title": "会计估计风险评估 — 编制说明",
            "sections": [
                {"heading": "一、编制目的", "content": "评估被审计单位会计估计相关的重大错报风险，确定进一步审计程序。"},
                {"heading": "二、主要内容", "content": "包括：会计估计识别、估计不确定性评价、管理层偏向分析、固有风险因素评估。"},
                {"heading": "三、编制步骤", "content": "1. 识别涉及会计估计的报表项目\n2. 评估估计不确定性程度\n3. 分析管理层可能的偏向\n4. 确定需要特别关注的估计事项"},
            ]
        },
    }

    if code in content_map:
        return {
            "wp_code": code,
            "title": content_map[code]["title"],
            "sections": content_map[code]["sections"],
            "source": "static_json"
        }
    return _guidance_generic(code, name)


def _guidance_generic(code: str, name: str) -> dict:
    """通用底稿指引"""
    return {
        "wp_code": code,
        "title": f"{name} — 编制说明",
        "sections": [
            {
                "heading": "一、编制目的",
                "content": f"记录{name}相关审计工作的执行情况和结论。"
            },
            {
                "heading": "二、编制步骤",
                "content": "1. 参照模板格式填写各项内容\n2. 确保数据来源可追溯\n3. 记录审计发现和结论"
            }
        ],
        "source": "static_json"
    }


def main():
    print("\n开始扫描底稿模板编制说明覆盖率...\n")
    results = scan_templates()
    coverage, high_without = print_report(results)

    # 覆盖率 < 50% 时创建静态指引
    if coverage < 50:
        print("\n正在为高复杂度底稿创建静态指引文件...\n")
        create_static_guidance_files(high_without, limit=20)


if __name__ == "__main__":
    main()
