from pathlib import Path

p = Path(r"d:\GT_plan\audit-platform\frontend\src\components\workpaper\composables\useF2Analysis.ts")
t = p.read_text(encoding="utf-8")
start = t.index("// ─── F2-18")
end = t.index("// ─── F2-19")
new_block = """// ─── F2-18 总体分析（实现见 useF2OverallAnalysis.ts）──────────────────────
export {
  useF2OverallAnalysis,
  F2_INDICATOR_DEFS,
  type F2CompositionRow,
  type F2StructureRow,
  type F2OverallPack,
  type F2AnomalyItem,
} from './useF2OverallAnalysis'

"""
text = t[:start] + new_block + t[end:]
text = text.replace("\nexport default useF2OverallAnalysis\n", "\n")
# Drop unused imports left from old F2-18 block if unused
p.write_text(text, encoding="utf-8")
print("ok", len(text))
