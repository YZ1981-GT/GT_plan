# 合并报表模块深度开发方案（三码树形 + 差额表 + 节点汇总 + 穿透 + 自定义查询）

## 一、核心架构设计

### 1.1 三码树形结构

```
最终控制方（ultimate_company_code）
  └── 上级企业（parent_company_code）
        ├── 本级企业 A（company_code）
        │     ├── 子公司 A1
        │     └── 子公司 A2
        └── 本级企业 B（company_code）
              └── 子公司 B1
```

**三码含义：**
- `company_code` — 本企业代码（唯一标识）
- `parent_company_code` — 直接上级企业代码（构建父子关系）
- `ultimate_company_code` — 最终控制方代码（集团顶层）

**树形构建规则：**
- 根节点：`company_code == ultimate_company_code`（最终控制方自身）
- 父子关系：子节点的 `parent_company_code == 父节点的 company_code`
- 层级：`consol_level` 表示在树中的深度（根=1，直接子公司=2，孙公司=3...）
- 最大支持 15 级嵌套

**数据来源：**
- 每个节点对应一个 `Project` 记录（`projects.company_code`）
- 合并项目通过 `projects.parent_project_id` 建立项目层级
- 企业元数据在 `companies` 表（持股比例/合并方式/功能货币等）

### 1.2 差额表合并模式

**核心思想：不直接汇总报表，而是通过"差额表"逐层合并。**

```
末端企业试算表（审定数）
  ↓ 作为叶子节点的 children_amount_sum
本级差额表 = 本级调整 + 本级抵消（差额表只记录调整和抵消，不含个别数）
本级合并数 = Σ(下级审定数/合并数) + 本级差额
  ↓ 作为上级节点的 children_amount_sum 的一部分
上级合并数 = Σ(直接下级合并数) + 上级差额
  ↓ 继续向上
顶层合并数 = Σ(直接下级合并数) + 顶层差额
```

**差额表结构（每个节点一张，只记录调整和抵消，不含个别数）：**

| 科目编码 | 科目名称 | 调整借方 | 调整贷方 | 抵消借方 | 抵消贷方 | 差额净额 |
|----------|----------|----------|----------|----------|----------|----------|
| 1001     | 货币资金 | 0        | 0        | 5        | 0        | 5        |
| 1122     | 应收账款 | 10       | 0        | 0        | 30       | -20      |

**差额净额 = 调整借方 - 调整贷方 + 抵消借方 - 抵消贷方**

**合并公式（从下到上）：**
```
本级合并数 = Σ(下级审定数) + Σ(本级差额)
           = Σ(所有直接下级的审定数/合并数) + (调整借方 - 调整贷方 + 抵消借方 - 抵消贷方)
```

**示例（三级结构）：**
```
集团 A（最终控制方）
  ├── 子公司 B（审定数：货币资金 100）
  └── 子公司 C（审定数：货币资金 200）

集团 A 的差额表：抵消借方 5（内部往来抵消）
集团 A 的合并数 = (100 + 200) + 5 = 305

如果 B 下面还有孙公司 D（审定数 50）：
  B 的合并数 = 50 + B的差额
  A 的合并数 = (B的合并数 + C的审定数) + A的差额
```

### 1.3 节点汇总模式（三种）

用户可选择汇总范围：
1. **本级节点** — 只看当前企业自身的数据
2. **直接下级节点** — 当前企业 + 所有直接子公司（不含孙公司）
3. **全部下级节点** — 当前企业 + 所有后代企业（递归到底）

### 1.4 穿透查询（从合并到末端）

```
合并报表某行金额 1000 万
  → 点击穿透
  → 显示构成明细：
      企业 A: 400 万（审定数 380 + 调整 20）
      企业 B: 350 万（审定数 350）
      企业 C: 250 万（审定数 280 - 抵消 30）
  → 继续点击企业 A
  → 跳转到企业 A 的试算表该科目行
  → 继续点击
  → 跳转到企业 A 的序时账（四表穿透）
```

---

## 二、数据库变更

### 2.1 新增 consol_worksheet 表（差额表）

```sql
CREATE TABLE IF NOT EXISTS consol_worksheet (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    year INTEGER NOT NULL,
    node_company_code VARCHAR(50) NOT NULL,       -- 当前节点企业代码
    standard_account_code VARCHAR(20) NOT NULL,    -- 科目编码
    account_name VARCHAR(200),
    account_category VARCHAR(20),
    
    -- 差额表只记录本级节点的调整和抵消（不含个别数）
    adjustment_debit NUMERIC(20,2) DEFAULT 0,      -- 本级调整借方
    adjustment_credit NUMERIC(20,2) DEFAULT 0,     -- 本级调整贷方
    elimination_debit NUMERIC(20,2) DEFAULT 0,     -- 本级抵消借方
    elimination_credit NUMERIC(20,2) DEFAULT 0,    -- 本级抵消贷方
    
    -- 差额净额 = adj_debit - adj_credit + elim_debit - elim_credit
    net_difference NUMERIC(20,2) DEFAULT 0,
    
    -- 下级汇总数（所有直接下级的合并数之和，末端节点=审定数）
    children_amount_sum NUMERIC(20,2) DEFAULT 0,
    
    -- 本级合并数 = children_amount_sum + net_difference
    consolidated_amount NUMERIC(20,2) DEFAULT 0,
    
    -- 元数据
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    
    UNIQUE(project_id, year, node_company_code, standard_account_code)
);

CREATE INDEX idx_consol_worksheet_node ON consol_worksheet(project_id, year, node_company_code)
    WHERE is_deleted = false;
```

### 2.2 新增 consol_query_template 表（自定义查询模板）

```sql
CREATE TABLE IF NOT EXISTS consol_query_template (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),       -- NULL 表示全局模板
    created_by UUID REFERENCES users(id),
    template_name VARCHAR(200) NOT NULL,
    
    -- 查询配置
    row_dimension VARCHAR(50) NOT NULL DEFAULT 'account',  -- 行维度：account/company/period
    col_dimension VARCHAR(50) NOT NULL DEFAULT 'company',  -- 列维度：account/company/period
    value_field VARCHAR(50) NOT NULL DEFAULT 'consolidated_amount',  -- 值字段
    
    -- 筛选条件
    filter_companies JSONB,          -- 企业代码列表
    filter_accounts JSONB,           -- 科目编码列表
    filter_periods JSONB,            -- 年度列表
    
    -- 汇总模式
    aggregation_mode VARCHAR(20) DEFAULT 'descendants',  -- self/children/descendants
    
    -- 转置
    is_transposed BOOLEAN DEFAULT false,
    
    -- 排序
    sort_field VARCHAR(50),
    sort_direction VARCHAR(4) DEFAULT 'asc',
    
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

### 2.3 ORM 模型

```python
# backend/app/models/consolidation_models.py 新增

class ConsolWorksheet(Base, SoftDeleteMixin, TimestampMixin):
    """合并差额表 — 每个节点每个科目一行，只记录调整和抵消"""
    __tablename__ = "consol_worksheet"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"))
    year: Mapped[int] = mapped_column(Integer)
    node_company_code: Mapped[str] = mapped_column(String(50))
    standard_account_code: Mapped[str] = mapped_column(String(20))
    account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    
    # 差额表：只记录本级调整和抵消
    adjustment_debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    adjustment_credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    elimination_debit: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    elimination_credit: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    
    # 差额净额 = adj_debit - adj_credit + elim_debit - elim_credit
    net_difference: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    
    # 下级汇总（直接下级的合并数之和，末端节点=审定数）
    children_amount_sum: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))
    
    # 本级合并数 = children_amount_sum + net_difference
    consolidated_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal(0))


class ConsolQueryTemplate(Base, SoftDeleteMixin, TimestampMixin):
    """自定义查询模板"""
    __tablename__ = "consol_query_template"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    template_name: Mapped[str] = mapped_column(String(200))
    row_dimension: Mapped[str] = mapped_column(String(50), default='account')
    col_dimension: Mapped[str] = mapped_column(String(50), default='company')
    value_field: Mapped[str] = mapped_column(String(50), default='consolidated_amount')
    filter_companies: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    filter_accounts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    filter_periods: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    aggregation_mode: Mapped[str] = mapped_column(String(20), default='descendants')
    is_transposed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_field: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_direction: Mapped[str] = mapped_column(String(4), default='asc')
```

---

## 三、后端服务层详细设计

### 3.1 树形构建服务（consol_tree_service.py）

```python
"""合并树形结构服务 — 基于三码体系构建企业树"""

from __future__ import annotations
from uuid import UUID
from decimal import Decimal
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from app.models.core import Project
from app.models.consolidation_models import Company


@dataclass
class ConsolTreeNode:
    """合并树节点"""
    company_code: str
    company_name: str
    parent_code: str | None
    ultimate_code: str
    consol_level: int
    project_id: UUID | None          # 关联的项目 ID（末端企业有项目）
    shareholding: Decimal | None
    consol_method: str | None
    children: list[ConsolTreeNode] = field(default_factory=list)
    
    # 运行时计算的汇总数据
    data: dict = field(default_factory=dict)  # {account_code: {individual, adj_d, adj_c, elim_d, elim_c, consol}}


class ConsolTreeService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def build_tree(self, project_id: UUID, year: int) -> ConsolTreeNode:
        """从三码体系构建完整的企业树。
        
        步骤：
        1. 从 projects 表找到合并项目及所有子项目
        2. 从 companies 表补充企业元数据
        3. 用 parent_company_code 构建父子关系
        4. 返回根节点（最终控制方）
        """
        # 1. 找到合并项目的企业代码
        root_project = await self.db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        root = root_project.scalar_one_or_none()
        if not root:
            raise ValueError("项目不存在")
        
        root_code = root.company_code or root.ultimate_company_code
        
        # 2. 加载所有关联企业
        companies_result = await self.db.execute(
            sa.select(Company).where(
                Company.project_id == project_id,
                Company.is_deleted == sa.false(),
                Company.is_active == sa.true(),
            ).order_by(Company.consol_level)
        )
        companies = companies_result.scalars().all()
        
        # 3. 同时加载子项目（通过 parent_project_id 关联）
        child_projects = await self.db.execute(
            sa.select(Project).where(
                Project.parent_project_id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project_map = {root.company_code: root.id}
        for cp in child_projects.scalars().all():
            if cp.company_code:
                project_map[cp.company_code] = cp.id
        
        # 4. 构建节点字典
        node_map: dict[str, ConsolTreeNode] = {}
        for c in companies:
            node = ConsolTreeNode(
                company_code=c.company_code,
                company_name=c.company_name,
                parent_code=c.parent_code,
                ultimate_code=c.ultimate_code,
                consol_level=c.consol_level,
                project_id=project_map.get(c.company_code),
                shareholding=c.shareholding,
                consol_method=c.consol_method.value if c.consol_method else None,
            )
            node_map[c.company_code] = node
        
        # 5. 构建父子关系
        root_node = None
        for code, node in node_map.items():
            if node.parent_code and node.parent_code in node_map:
                node_map[node.parent_code].children.append(node)
            if code == root_code:
                root_node = node
        
        if not root_node:
            # 兜底：找 consol_level 最小的作为根
            root_node = min(node_map.values(), key=lambda n: n.consol_level, default=None)
        
        return root_node
    
    def get_descendants(self, node: ConsolTreeNode) -> list[ConsolTreeNode]:
        """递归获取所有后代节点（不含自身）"""
        result = []
        for child in node.children:
            result.append(child)
            result.extend(self.get_descendants(child))
        return result
    
    def get_direct_children(self, node: ConsolTreeNode) -> list[ConsolTreeNode]:
        """获取直接子节点"""
        return node.children
    
    def find_node(self, root: ConsolTreeNode, company_code: str) -> ConsolTreeNode | None:
        """在树中查找指定企业代码的节点"""
        if root.company_code == company_code:
            return root
        for child in root.children:
            found = self.find_node(child, company_code)
            if found:
                return found
        return None
    
    def to_dict(self, node: ConsolTreeNode) -> dict:
        """将树节点转为可序列化的字典（含子节点递归）"""
        return {
            "company_code": node.company_code,
            "company_name": node.company_name,
            "parent_code": node.parent_code,
            "consol_level": node.consol_level,
            "project_id": str(node.project_id) if node.project_id else None,
            "shareholding": float(node.shareholding) if node.shareholding else None,
            "consol_method": node.consol_method,
            "children": [self.to_dict(c) for c in node.children],
            "data": node.data,
        }
```


### 3.2 差额表计算引擎（consol_worksheet_engine.py）

```python
"""合并差额表计算引擎 — 从下到上逐层汇总"""

from __future__ import annotations
from uuid import UUID, uuid4
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.models.consolidation_models import (
    ConsolWorksheet, EliminationEntry, ReviewStatusEnum,
)
from app.models.audit_platform_models import TrialBalance
from app.services.consol_tree_service import ConsolTreeService, ConsolTreeNode


class ConsolWorksheetEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def recalc_full(self, project_id: UUID, year: int) -> dict:
        """全量重算合并差额表（从叶子节点到根节点）。

        核心公式：
          差额表 = 本级调整 + 本级抵消（不含个别数）
          本级合并数 = Σ(下级审定数/合并数) + 本级差额净额

        步骤：
        1. 构建企业树
        2. 后序遍历（先算子节点，再算父节点）
        3. 叶子节点（末端企业）：
           - 差额 = 本级调整 + 本级抵消
           - children_amount_sum = 本企业审定数（从 trial_balance 取）
           - consolidated = children_amount_sum + 差额
        4. 中间节点（合并层）：
           - 差额 = 本级调整 + 本级抵消
           - children_amount_sum = Σ(直接下级的 consolidated_amount)
           - consolidated = children_amount_sum + 差额
        5. 根节点的 consolidated_amount 就是最终合并数
        """
        tree_svc = ConsolTreeService(self.db)
        root = await tree_svc.build_tree(project_id, year)

        # 清除旧数据
        await self.db.execute(
            sa.update(ConsolWorksheet).where(
                ConsolWorksheet.project_id == project_id,
                ConsolWorksheet.year == year,
            ).values(is_deleted=True)
        )

        # 收集所有科目编码
        all_codes = await self._collect_all_account_codes(project_id, year, root, tree_svc)

        # 后序遍历计算
        stats = {"nodes": 0, "rows": 0}
        await self._calc_node(project_id, year, root, all_codes, tree_svc, stats)

        await self.db.flush()
        return {"nodes_calculated": stats["nodes"], "rows_written": stats["rows"]}

    async def _calc_node(
        self, project_id: UUID, year: int,
        node: ConsolTreeNode, all_codes: set[str],
        tree_svc: ConsolTreeService, stats: dict,
    ):
        """递归计算单个节点（后序遍历：先算子节点）。

        关键区分：
        - 叶子节点：children_amount_sum = 本企业审定数
        - 中间节点：children_amount_sum = Σ(直接下级 consolidated_amount)
        """
        # 先递归计算所有子节点
        for child in node.children:
            await self._calc_node(project_id, year, child, all_codes, tree_svc, stats)

        is_leaf = len(node.children) == 0

        # 1. 取本级差额（调整 + 抵消）
        elim_map = await self._get_elimination_map(project_id, year, node.company_code)

        # 2. 计算 children_amount_sum
        if is_leaf:
            # 叶子节点：从 trial_balance 取本企业审定数
            individual_map = {}
            if node.project_id:
                tb_result = await self.db.execute(
                    sa.select(
                        TrialBalance.standard_account_code,
                        TrialBalance.account_name,
                        TrialBalance.audited_amount,
                    ).where(
                        TrialBalance.project_id == node.project_id,
                        TrialBalance.year == year,
                        TrialBalance.is_deleted == sa.false(),
                    )
                )
                for r in tb_result.all():
                    individual_map[r.standard_account_code] = {
                        "name": r.account_name,
                        "amount": r.audited_amount or Decimal(0),
                    }
            children_sum_map = {code: individual_map.get(code, {}).get("amount", Decimal(0)) for code in all_codes}
            name_map = {code: individual_map.get(code, {}).get("name", "") for code in all_codes}
        else:
            # 中间节点：Σ(直接下级的 consolidated_amount)
            children_sum_map = {}
            name_map = {}
            for child in node.children:
                child_ws = await self._get_node_worksheet(project_id, year, child.company_code)
                for code, row in child_ws.items():
                    children_sum_map[code] = children_sum_map.get(code, Decimal(0)) + row["consolidated_amount"]
                    if not name_map.get(code):
                        name_map[code] = row.get("account_name", "")

        # 3. 写入差额表
        for code in all_codes:
            elim = elim_map.get(code, {})
            elim_d = elim.get("debit", Decimal(0))
            elim_c = elim.get("credit", Decimal(0))
            # 差额净额 = 调整借方 - 调整贷方 + 抵消借方 - 抵消贷方
            # （当前调整和抵消都在 elimination_entries 中，后续可分开）
            net_diff = elim_d - elim_c

            children_sum = children_sum_map.get(code, Decimal(0))
            # 本级合并数 = Σ(下级) + 本级差额
            consolidated = children_sum + net_diff

            ws = ConsolWorksheet(
                id=uuid4(),
                project_id=project_id,
                year=year,
                node_company_code=node.company_code,
                standard_account_code=code,
                account_name=name_map.get(code, ""),
                elimination_debit=elim_d,
                elimination_credit=elim_c,
                net_difference=net_diff,
                children_amount_sum=children_sum,
                consolidated_amount=consolidated,
            )
            self.db.add(ws)
            stats["rows"] += 1

        stats["nodes"] += 1

    async def _get_elimination_map(
        self, project_id: UUID, year: int, company_code: str
    ) -> dict[str, dict]:
        """获取指定节点层级的抵消分录汇总（按科目）"""
        result = await self.db.execute(
            sa.select(
                EliminationEntry.account_code,
                sa.func.sum(EliminationEntry.debit_amount).label("total_debit"),
                sa.func.sum(EliminationEntry.credit_amount).label("total_credit"),
            ).where(
                EliminationEntry.project_id == project_id,
                EliminationEntry.year == year,
                EliminationEntry.is_deleted == sa.false(),
                EliminationEntry.review_status != ReviewStatusEnum.rejected,
                # 通过 related_company_codes 关联到当前节点
                sa.or_(
                    EliminationEntry.related_company_codes.contains([company_code]),
                    EliminationEntry.related_company_codes == sa.null(),
                ),
            ).group_by(EliminationEntry.account_code)
        )
        return {
            r.account_code: {"debit": r.total_debit or Decimal(0), "credit": r.total_credit or Decimal(0)}
            for r in result.all()
        }

    async def _get_node_worksheet(
        self, project_id: UUID, year: int, company_code: str
    ) -> dict[str, dict]:
        """获取指定节点已计算的差额表数据"""
        result = await self.db.execute(
            sa.select(ConsolWorksheet).where(
                ConsolWorksheet.project_id == project_id,
                ConsolWorksheet.year == year,
                ConsolWorksheet.node_company_code == company_code,
                ConsolWorksheet.is_deleted == sa.false(),
            )
        )
        return {
            r.standard_account_code: {
                "consolidated_amount": r.consolidated_amount,
                "account_name": r.account_name or "",
            }
            for r in result.scalars().all()
        }

    async def _collect_all_account_codes(
        self, project_id, year, root, tree_svc
    ) -> set[str]:
        """收集所有末端企业的科目编码合集"""
        all_nodes = [root] + tree_svc.get_descendants(root)
        project_ids = [n.project_id for n in all_nodes if n.project_id]
        if not project_ids:
            return set()
        result = await self.db.execute(
            sa.select(sa.distinct(TrialBalance.standard_account_code)).where(
                TrialBalance.project_id.in_(project_ids),
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        return {r[0] for r in result.all()}
```

### 3.3 节点汇总查询服务（consol_aggregation_service.py）

```python
"""合并节点汇总查询 — 支持本级/直接下级/全部下级三种模式"""

from __future__ import annotations
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from app.models.consolidation_models import ConsolWorksheet
from app.services.consol_tree_service import ConsolTreeService


class ConsolAggregationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def query_node(
        self, project_id: UUID, year: int,
        company_code: str,
        mode: str = "descendants",  # self / children / descendants
        account_codes: list[str] | None = None,
    ) -> list[dict]:
        """按汇总模式查询节点数据。

        mode:
          self        — 只返回当前节点自身的差额表
          children    — 当前节点 + 所有直接子节点的合并数之和
          descendants — 当前节点 + 所有后代节点的合并数之和
        """
        if mode == "self":
            return await self._query_self(project_id, year, company_code, account_codes)
        elif mode == "children":
            return await self._query_children(project_id, year, company_code, account_codes)
        else:  # descendants
            return await self._query_descendants(project_id, year, company_code, account_codes)

    async def _query_self(self, project_id, year, company_code, account_codes):
        """本级节点：直接返回差额表"""
        query = sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.year == year,
            ConsolWorksheet.node_company_code == company_code,
            ConsolWorksheet.is_deleted == sa.false(),
        )
        if account_codes:
            query = query.where(ConsolWorksheet.standard_account_code.in_(account_codes))
        result = await self.db.execute(query.order_by(ConsolWorksheet.standard_account_code))
        return [self._row_to_dict(r, "self") for r in result.scalars().all()]

    async def _query_children(self, project_id, year, company_code, account_codes):
        """直接下级：当前节点合并数 + 直接子节点合并数"""
        tree_svc = ConsolTreeService(self.db)
        root = await tree_svc.build_tree(project_id, year)
        node = tree_svc.find_node(root, company_code)
        if not node:
            return []

        codes_to_query = [company_code] + [c.company_code for c in node.children]
        return await self._aggregate_nodes(project_id, year, codes_to_query, account_codes)

    async def _query_descendants(self, project_id, year, company_code, account_codes):
        """全部下级：当前节点 + 所有后代节点"""
        tree_svc = ConsolTreeService(self.db)
        root = await tree_svc.build_tree(project_id, year)
        node = tree_svc.find_node(root, company_code)
        if not node:
            return []

        all_nodes = [node] + tree_svc.get_descendants(node)
        codes_to_query = [n.company_code for n in all_nodes]
        return await self._aggregate_nodes(project_id, year, codes_to_query, account_codes)

    async def _aggregate_nodes(self, project_id, year, company_codes, account_codes):
        """按科目汇总多个节点的差额表"""
        query = (
            sa.select(
                ConsolWorksheet.standard_account_code,
                sa.func.max(ConsolWorksheet.account_name).label("account_name"),
                sa.func.sum(ConsolWorksheet.children_amount_sum).label("total_children_sum"),
                sa.func.sum(ConsolWorksheet.adjustment_debit).label("total_adj_debit"),
                sa.func.sum(ConsolWorksheet.adjustment_credit).label("total_adj_credit"),
                sa.func.sum(ConsolWorksheet.elimination_debit).label("total_elim_debit"),
                sa.func.sum(ConsolWorksheet.elimination_credit).label("total_elim_credit"),
                sa.func.sum(ConsolWorksheet.net_difference).label("total_net_diff"),
                sa.func.sum(ConsolWorksheet.consolidated_amount).label("total_consolidated"),
            )
            .where(
                ConsolWorksheet.project_id == project_id,
                ConsolWorksheet.year == year,
                ConsolWorksheet.node_company_code.in_(company_codes),
                ConsolWorksheet.is_deleted == sa.false(),
            )
            .group_by(ConsolWorksheet.standard_account_code)
            .order_by(ConsolWorksheet.standard_account_code)
        )
        if account_codes:
            query = query.where(ConsolWorksheet.standard_account_code.in_(account_codes))

        result = await self.db.execute(query)
        return [
            {
                "account_code": r.standard_account_code,
                "account_name": r.account_name,
                "children_sum": float(r.total_children_sum or 0),
                "adj_debit": float(r.total_adj_debit or 0),
                "adj_credit": float(r.total_adj_credit or 0),
                "elim_debit": float(r.total_elim_debit or 0),
                "elim_credit": float(r.total_elim_credit or 0),
                "net_difference": float(r.total_net_diff or 0),
                "consolidated": float(r.total_consolidated or 0),
                "node_count": len(company_codes),
            }
            for r in result.all()
        ]

    def _row_to_dict(self, ws: ConsolWorksheet, mode: str) -> dict:
        return {
            "account_code": ws.standard_account_code,
            "account_name": ws.account_name,
            "children_sum": float(ws.children_amount_sum),
            "adj_debit": float(ws.adjustment_debit),
            "adj_credit": float(ws.adjustment_credit),
            "elim_debit": float(ws.elimination_debit),
            "elim_credit": float(ws.elimination_credit),
            "net_difference": float(ws.net_difference),
            "consolidated": float(ws.consolidated_amount),
            "mode": mode,
        }
```

### 3.4 穿透查询服务（consol_drilldown_service.py）

```python
"""合并穿透查询 — 从合并数层层穿透到末端企业序时账"""

from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from app.models.consolidation_models import ConsolWorksheet, EliminationEntry
from app.models.audit_platform_models import TrialBalance
from app.services.consol_tree_service import ConsolTreeService


class ConsolDrilldownService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def drill_to_companies(
        self, project_id: UUID, year: int,
        account_code: str, company_code: str | None = None,
    ) -> list[dict]:
        """第一层穿透：合并数 → 各企业构成明细。

        返回每个企业在该科目上的：个别数、调整、抵消、合并数。
        如果指定 company_code，只返回该节点及其下级。
        """
        tree_svc = ConsolTreeService(self.db)
        root = await tree_svc.build_tree(project_id, year)

        if company_code:
            node = tree_svc.find_node(root, company_code)
            if not node:
                return []
            nodes = [node] + tree_svc.get_descendants(node)
        else:
            nodes = [root] + tree_svc.get_descendants(root)

        codes = [n.company_code for n in nodes]
        result = await self.db.execute(
            sa.select(ConsolWorksheet).where(
                ConsolWorksheet.project_id == project_id,
                ConsolWorksheet.year == year,
                ConsolWorksheet.standard_account_code == account_code,
                ConsolWorksheet.node_company_code.in_(codes),
                ConsolWorksheet.is_deleted == sa.false(),
            ).order_by(ConsolWorksheet.node_company_code)
        )

        node_map = {n.company_code: n for n in nodes}
        return [
            {
                "company_code": ws.node_company_code,
                "company_name": node_map.get(ws.node_company_code, None)
                    and node_map[ws.node_company_code].company_name or "",
                "consol_level": node_map.get(ws.node_company_code, None)
                    and node_map[ws.node_company_code].consol_level or 0,
                "project_id": str(node_map[ws.node_company_code].project_id)
                    if node_map.get(ws.node_company_code) and node_map[ws.node_company_code].project_id
                    else None,
                "children_sum": float(ws.children_amount_sum),
                "adj_debit": float(ws.adjustment_debit),
                "adj_credit": float(ws.adjustment_credit),
                "elim_debit": float(ws.elimination_debit),
                "elim_credit": float(ws.elimination_credit),
                "net_difference": float(ws.net_difference),
                "consolidated": float(ws.consolidated_amount),
            }
            for ws in result.scalars().all()
        ]

    async def drill_to_eliminations(
        self, project_id: UUID, year: int,
        account_code: str, company_code: str,
    ) -> list[dict]:
        """第二层穿透：企业合并数 → 该企业相关的抵消分录明细"""
        result = await self.db.execute(
            sa.select(EliminationEntry).where(
                EliminationEntry.project_id == project_id,
                EliminationEntry.year == year,
                EliminationEntry.account_code == account_code,
                EliminationEntry.is_deleted == sa.false(),
                sa.or_(
                    EliminationEntry.related_company_codes.contains([company_code]),
                    EliminationEntry.related_company_codes == sa.null(),
                ),
            ).order_by(EliminationEntry.entry_no)
        )
        return [
            {
                "entry_id": str(e.id),
                "entry_no": e.entry_no,
                "entry_type": e.entry_type.value,
                "description": e.description,
                "debit": float(e.debit_amount),
                "credit": float(e.credit_amount),
                "review_status": e.review_status.value,
            }
            for e in result.scalars().all()
        ]

    async def drill_to_trial_balance(
        self, project_id: UUID, year: int, account_code: str,
    ) -> dict | None:
        """第三层穿透：跳转到末端企业的试算表行。
        返回 project_id + 科目信息，前端用这个跳转到 /projects/{id}/trial-balance。
        """
        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb = result.scalar_one_or_none()
        if not tb:
            return None
        return {
            "project_id": str(tb.project_id),
            "account_code": tb.standard_account_code,
            "account_name": tb.account_name,
            "unadjusted": float(tb.unadjusted_amount or 0),
            "rje": float(tb.rje_adjustment or 0),
            "aje": float(tb.aje_adjustment or 0),
            "audited": float(tb.audited_amount or 0),
            "drill_url": f"/projects/{tb.project_id}/trial-balance?highlight={account_code}",
        }
```

### 3.5 自定义查询引擎（consol_pivot_service.py）

```python
"""合并自定义查询 — 横向/纵向指标 + 转置 + Excel 导出"""

from __future__ import annotations
from uuid import UUID
from decimal import Decimal
from io import BytesIO
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from app.models.consolidation_models import ConsolWorksheet, ConsolQueryTemplate


# 可选的值字段
VALUE_FIELDS = {
    "children_amount_sum": "下级汇总",
    "adjustment_debit": "调整借方",
    "adjustment_credit": "调整贷方",
    "elimination_debit": "抵消借方",
    "elimination_credit": "抵消贷方",
    "net_difference": "差额净额",
    "consolidated_amount": "合并数",
}


class ConsolPivotService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_query(
        self, project_id: UUID, year: int,
        row_dim: str = "account",       # account / company / period
        col_dim: str = "company",       # account / company / period
        value_field: str = "consolidated_amount",
        filter_companies: list[str] | None = None,
        filter_accounts: list[str] | None = None,
        aggregation_mode: str = "descendants",
        is_transposed: bool = False,
    ) -> dict:
        """执行自定义透视查询。

        返回格式：
        {
            "row_headers": ["1001 货币资金", "1122 应收账款", ...],
            "col_headers": ["企业A", "企业B", "合计"],
            "data": [[100, 200, 300], [150, 250, 400], ...],
            "row_dim": "account",
            "col_dim": "company",
            "value_field": "consolidated_amount",
            "is_transposed": false,
        }
        """
        # 1. 构建基础查询
        query = sa.select(
            ConsolWorksheet.standard_account_code,
            ConsolWorksheet.account_name,
            ConsolWorksheet.node_company_code,
            getattr(ConsolWorksheet, value_field).label("value"),
        ).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        )

        if filter_companies:
            query = query.where(ConsolWorksheet.node_company_code.in_(filter_companies))
        if filter_accounts:
            query = query.where(ConsolWorksheet.standard_account_code.in_(filter_accounts))

        result = await self.db.execute(query.order_by(
            ConsolWorksheet.standard_account_code,
            ConsolWorksheet.node_company_code,
        ))
        rows = result.all()

        # 2. 构建透视表
        if row_dim == "account" and col_dim == "company":
            pivot = self._pivot_account_by_company(rows)
        elif row_dim == "company" and col_dim == "account":
            pivot = self._pivot_company_by_account(rows)
        else:
            pivot = self._pivot_account_by_company(rows)  # 默认

        # 3. 转置
        if is_transposed:
            pivot = self._transpose(pivot)

        return pivot

    def _pivot_account_by_company(self, rows) -> dict:
        """行=科目，列=企业"""
        accounts = {}  # {code: name}
        companies = set()
        data_map = {}  # {(account, company): value}

        for r in rows:
            code = r.standard_account_code
            company = r.node_company_code
            accounts[code] = r.account_name or code
            companies.add(company)
            data_map[(code, company)] = float(r.value or 0)

        sorted_accounts = sorted(accounts.keys())
        sorted_companies = sorted(companies)

        # 加合计列
        matrix = []
        for acc in sorted_accounts:
            row_data = []
            row_total = 0
            for comp in sorted_companies:
                val = data_map.get((acc, comp), 0)
                row_data.append(val)
                row_total += val
            row_data.append(row_total)
            matrix.append(row_data)

        return {
            "row_headers": [f"{c} {accounts[c]}" for c in sorted_accounts],
            "col_headers": sorted_companies + ["合计"],
            "data": matrix,
            "row_dim": "account",
            "col_dim": "company",
        }

    def _pivot_company_by_account(self, rows) -> dict:
        """行=企业，列=科目"""
        # 与上面相反
        accounts = {}
        companies = {}
        data_map = {}

        for r in rows:
            accounts[r.standard_account_code] = r.account_name or r.standard_account_code
            companies[r.node_company_code] = r.node_company_code
            data_map[(r.node_company_code, r.standard_account_code)] = float(r.value or 0)

        sorted_accounts = sorted(accounts.keys())
        sorted_companies = sorted(companies.keys())

        matrix = []
        for comp in sorted_companies:
            row_data = []
            row_total = 0
            for acc in sorted_accounts:
                val = data_map.get((comp, acc), 0)
                row_data.append(val)
                row_total += val
            row_data.append(row_total)
            matrix.append(row_data)

        return {
            "row_headers": sorted_companies,
            "col_headers": [f"{c} {accounts[c]}" for c in sorted_accounts] + ["合计"],
            "data": matrix,
            "row_dim": "company",
            "col_dim": "account",
        }

    def _transpose(self, pivot: dict) -> dict:
        """转置透视表"""
        data = pivot["data"]
        if not data:
            return {**pivot, "is_transposed": True}
        transposed = list(map(list, zip(*data)))
        return {
            "row_headers": pivot["col_headers"],
            "col_headers": pivot["row_headers"],
            "data": transposed,
            "row_dim": pivot["col_dim"],
            "col_dim": pivot["row_dim"],
            "is_transposed": True,
        }

    async def export_excel(
        self, project_id: UUID, year: int, **query_params
    ) -> BytesIO:
        """将查询结果导出为 Excel"""
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

        pivot = await self.execute_query(project_id, year, **query_params)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "合并查询"

        # 标题行样式
        header_font = Font(name="仿宋_GB2312", bold=True, size=10)
        header_fill = PatternFill(start_color="F0EBF8", end_color="F0EBF8", fill_type="solid")
        data_font = Font(name="Arial Narrow", size=10)
        thin_border = Border(
            top=Side(style="thin"), bottom=Side(style="thin"),
        )

        # 写表头
        ws.cell(row=1, column=1, value="").font = header_font
        for j, header in enumerate(pivot["col_headers"]):
            cell = ws.cell(row=1, column=j + 2, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        # 写数据
        for i, row_header in enumerate(pivot["row_headers"]):
            ws.cell(row=i + 2, column=1, value=row_header).font = header_font
            for j, val in enumerate(pivot["data"][i]):
                cell = ws.cell(row=i + 2, column=j + 2, value=val)
                cell.font = data_font
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal="right")

        # 列宽自适应
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    # ── 查询模板 CRUD ──

    async def save_template(self, project_id: UUID, user_id: UUID, data: dict) -> dict:
        tpl = ConsolQueryTemplate(
            project_id=project_id,
            created_by=user_id,
            template_name=data["template_name"],
            row_dimension=data.get("row_dimension", "account"),
            col_dimension=data.get("col_dimension", "company"),
            value_field=data.get("value_field", "consolidated_amount"),
            filter_companies=data.get("filter_companies"),
            filter_accounts=data.get("filter_accounts"),
            aggregation_mode=data.get("aggregation_mode", "descendants"),
            is_transposed=data.get("is_transposed", False),
        )
        self.db.add(tpl)
        await self.db.flush()
        return {"id": str(tpl.id), "name": tpl.template_name}

    async def list_templates(self, project_id: UUID) -> list[dict]:
        result = await self.db.execute(
            sa.select(ConsolQueryTemplate).where(
                sa.or_(
                    ConsolQueryTemplate.project_id == project_id,
                    ConsolQueryTemplate.project_id == sa.null(),
                ),
                ConsolQueryTemplate.is_deleted == sa.false(),
            ).order_by(ConsolQueryTemplate.template_name)
        )
        return [
            {"id": str(t.id), "name": t.template_name, "row_dim": t.row_dimension,
             "col_dim": t.col_dimension, "value_field": t.value_field,
             "is_transposed": t.is_transposed, "aggregation_mode": t.aggregation_mode}
            for t in result.scalars().all()
        ]
```

---

## 四、API 路由层设计

### 4.1 新增路由文件 consol_worksheet.py

```python
"""合并差额表 + 节点汇总 + 穿透 + 自定义查询 API"""

router = APIRouter(prefix="/api/consolidation/worksheet", tags=["合并差额表"])

# ── 树形结构 ──
GET  /tree?project_id=&year=                    → 返回完整企业树（JSON 嵌套）
GET  /tree/flat?project_id=&year=               → 返回扁平列表（含 parent_code/level）

# ── 差额表计算 ──
POST /recalc?project_id=&year=                  → 全量重算差额表（从叶子到根）
GET  /node/{company_code}?project_id=&year=     → 查询单个节点的差额表

# ── 节点汇总 ──
GET  /aggregate?project_id=&year=&company_code=&mode=self|children|descendants
     &account_codes=1001,1002                   → 按模式汇总查询

# ── 穿透查询 ──
GET  /drill/companies?project_id=&year=&account_code=&company_code=
     → 第一层：合并数 → 各企业构成
GET  /drill/eliminations?project_id=&year=&account_code=&company_code=
     → 第二层：企业 → 相关抵消分录
GET  /drill/trial-balance?project_id=&year=&account_code=
     → 第三层：跳转到末端企业试算表

# ── 自定义查询 ──
POST /pivot?project_id=&year=                   → 执行透视查询（body 含维度/筛选/转置配置）
GET  /pivot/export?project_id=&year=&...        → 导出 Excel
POST /pivot/templates                           → 保存查询模板
GET  /pivot/templates?project_id=               → 列出查询模板
```

### 4.2 路由实现

```python
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.deps import require_project_access, get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/consolidation/worksheet", tags=["合并差额表"])


@router.get("/tree")
async def get_consol_tree(
    project_id: UUID,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    from app.services.consol_tree_service import ConsolTreeService
    svc = ConsolTreeService(db)
    root = await svc.build_tree(project_id, year)
    return svc.to_dict(root)


@router.post("/recalc")
async def recalc_worksheet(
    project_id: UUID,
    year: int = Query(default=2025),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    from app.services.consol_worksheet_engine import ConsolWorksheetEngine
    engine = ConsolWorksheetEngine(db)
    result = await engine.recalc_full(project_id, year)
    await db.commit()
    return result


@router.get("/aggregate")
async def aggregate_node(
    project_id: UUID,
    year: int,
    company_code: str,
    mode: str = Query(default="descendants", regex="^(self|children|descendants)$"),
    account_codes: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    from app.services.consol_aggregation_service import ConsolAggregationService
    svc = ConsolAggregationService(db)
    codes = account_codes.split(",") if account_codes else None
    return await svc.query_node(project_id, year, company_code, mode, codes)


@router.get("/drill/companies")
async def drill_to_companies(
    project_id: UUID, year: int, account_code: str,
    company_code: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    from app.services.consol_drilldown_service import ConsolDrilldownService
    svc = ConsolDrilldownService(db)
    return await svc.drill_to_companies(project_id, year, account_code, company_code)


@router.get("/drill/eliminations")
async def drill_to_eliminations(
    project_id: UUID, year: int, account_code: str, company_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    from app.services.consol_drilldown_service import ConsolDrilldownService
    svc = ConsolDrilldownService(db)
    return await svc.drill_to_eliminations(project_id, year, account_code, company_code)


@router.get("/drill/trial-balance")
async def drill_to_trial_balance(
    project_id: UUID, year: int, account_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    from app.services.consol_drilldown_service import ConsolDrilldownService
    svc = ConsolDrilldownService(db)
    return await svc.drill_to_trial_balance(project_id, year, account_code)


@router.post("/pivot")
async def execute_pivot(
    project_id: UUID, year: int,
    body: dict,  # {row_dim, col_dim, value_field, filter_companies, filter_accounts, is_transposed}
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    from app.services.consol_pivot_service import ConsolPivotService
    svc = ConsolPivotService(db)
    return await svc.execute_query(
        project_id, year,
        row_dim=body.get("row_dim", "account"),
        col_dim=body.get("col_dim", "company"),
        value_field=body.get("value_field", "consolidated_amount"),
        filter_companies=body.get("filter_companies"),
        filter_accounts=body.get("filter_accounts"),
        aggregation_mode=body.get("aggregation_mode", "descendants"),
        is_transposed=body.get("is_transposed", False),
    )


@router.get("/pivot/export")
async def export_pivot_excel(
    project_id: UUID, year: int,
    row_dim: str = "account", col_dim: str = "company",
    value_field: str = "consolidated_amount",
    is_transposed: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    from app.services.consol_pivot_service import ConsolPivotService
    svc = ConsolPivotService(db)
    buf = await svc.export_excel(
        project_id, year,
        row_dim=row_dim, col_dim=col_dim,
        value_field=value_field, is_transposed=is_transposed,
    )
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=consol_pivot_{year}.xlsx"},
    )
```

---

## 五、前端页面设计

### 5.1 合并主页面改造（ConsolidationIndex.vue）

**从 7 个 Tab 改为 4 个核心 Tab + 工具栏：**

```
Tab 1: 集团架构（树形图 + 节点选择）
Tab 2: 合并差额表（差额表 + 节点汇总模式切换）
Tab 3: 穿透查询（从合并数层层穿透到末端）
Tab 4: 自定义查询（透视表 + 转置 + 导出）
```

### 5.2 Tab 1：集团架构树

```vue
<template>
  <div class="gt-consol-tree">
    <!-- 树形展示 -->
    <el-tree
      :data="treeData"
      :props="{ label: 'company_name', children: 'children' }"
      node-key="company_code"
      highlight-current
      default-expand-all
      @node-click="onNodeClick"
    >
      <template #default="{ data }">
        <div class="gt-tree-node">
          <span class="gt-tree-code">{{ data.company_code }}</span>
          <span class="gt-tree-name">{{ data.company_name }}</span>
          <el-tag v-if="data.shareholding" size="small" type="info">
            {{ data.shareholding }}%
          </el-tag>
          <el-tag size="small" :type="data.consol_method === 'full' ? 'success' : 'warning'">
            {{ data.consol_method === 'full' ? '全额合并' : '权益法' }}
          </el-tag>
          <span class="gt-tree-level">L{{ data.consol_level }}</span>
        </div>
      </template>
    </el-tree>

    <!-- 选中节点信息卡片 -->
    <div v-if="selectedNode" class="gt-node-card">
      <h4>{{ selectedNode.company_name }}</h4>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="企业代码">{{ selectedNode.company_code }}</el-descriptions-item>
        <el-descriptions-item label="上级企业">{{ selectedNode.parent_code || '—' }}</el-descriptions-item>
        <el-descriptions-item label="持股比例">{{ selectedNode.shareholding }}%</el-descriptions-item>
        <el-descriptions-item label="合并方式">{{ selectedNode.consol_method }}</el-descriptions-item>
        <el-descriptions-item label="层级">L{{ selectedNode.consol_level }}</el-descriptions-item>
        <el-descriptions-item label="关联项目">
          <el-button v-if="selectedNode.project_id" text type="primary" size="small"
            @click="goToProject(selectedNode.project_id)">
            查看项目 →
          </el-button>
          <span v-else class="text-muted">未关联</span>
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>
```

### 5.3 Tab 2：合并差额表

```vue
<template>
  <div class="gt-consol-worksheet">
    <!-- 工具栏 -->
    <div class="gt-ws-toolbar">
      <el-select v-model="selectedCompany" placeholder="选择节点" filterable style="width: 240px">
        <el-option v-for="n in flatNodes" :key="n.company_code"
          :label="`${'　'.repeat(n.consol_level - 1)}${n.company_code} ${n.company_name}`"
          :value="n.company_code" />
      </el-select>

      <el-radio-group v-model="aggregationMode" size="small">
        <el-radio-button value="self">本级节点</el-radio-button>
        <el-radio-button value="children">直接下级</el-radio-button>
        <el-radio-button value="descendants">全部下级</el-radio-button>
      </el-radio-group>

      <el-button @click="onRecalc" :loading="recalcLoading" type="primary" size="small">
        重算差额表
      </el-button>
      <el-button @click="onExport" size="small">导出 Excel</el-button>
    </div>

    <!-- 差额表 -->
    <el-table :data="worksheetData" border stripe v-loading="loading"
      :row-class-name="rowClassName" show-summary :summary-method="getSummary">
      <el-table-column prop="account_code" label="科目编码" width="110" fixed />
      <el-table-column prop="account_name" label="科目名称" min-width="180" fixed />
      <el-table-column label="下级汇总" width="140" align="right">
        <template #default="{ row }">{{ fmtAmt(row.children_sum) }}</template>
      </el-table-column>
      <el-table-column label="调整借方" width="120" align="right">
        <template #default="{ row }">
          <span class="debit">{{ fmtAmt(row.adj_debit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="调整贷方" width="120" align="right">
        <template #default="{ row }">
          <span class="credit">{{ fmtAmt(row.adj_credit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="抵消借方" width="120" align="right">
        <template #default="{ row }">
          <span class="debit">{{ fmtAmt(row.elim_debit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="抵消贷方" width="120" align="right">
        <template #default="{ row }">
          <span class="credit">{{ fmtAmt(row.elim_credit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差额净额" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'debit': row.net_difference > 0, 'credit': row.net_difference < 0 }">
            {{ fmtAmt(row.net_difference) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="合并数" width="140" align="right">
        <template #default="{ row }">
          <span class="consolidated clickable" @click="onDrill(row)">
            {{ fmtAmt(row.consolidated) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
```

### 5.4 Tab 3：穿透查询

```vue
<template>
  <div class="gt-consol-drill">
    <!-- 面包屑导航 -->
    <div class="gt-drill-breadcrumb">
      <span v-for="(crumb, i) in breadcrumbs" :key="i"
        class="gt-crumb" :class="{ active: i === breadcrumbs.length - 1 }"
        @click="navigateTo(i)">
        {{ crumb.label }}
        <span v-if="i < breadcrumbs.length - 1" class="sep">/</span>
      </span>
    </div>

    <!-- 第一层：各企业构成 -->
    <template v-if="drillLevel === 'companies'">
      <el-table :data="companyBreakdown" border stripe>
        <el-table-column prop="company_code" label="企业代码" width="120" />
        <el-table-column prop="company_name" label="企业名称" min-width="200" />
        <el-table-column prop="consol_level" label="层级" width="60" align="center">
          <template #default="{ row }">L{{ row.consol_level }}</template>
        </el-table-column>
        <el-table-column label="下级汇总" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.children_sum) }}</template>
        </el-table-column>
        <el-table-column label="调整净额" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.adj_debit - row.adj_credit) }}</template>
        </el-table-column>
        <el-table-column label="抵消净额" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.elim_debit - row.elim_credit) }}</template>
        </el-table-column>
        <el-table-column label="合并数" width="140" align="right">
          <template #default="{ row }">
            <span class="clickable" @click="drillToEliminations(row)">
              {{ fmtAmt(row.consolidated) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button v-if="row.project_id" text type="primary" size="small"
              @click="drillToTrialBalance(row)">
              穿透到试算表 →
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 第二层：抵消分录明细 -->
    <template v-if="drillLevel === 'eliminations'">
      <el-table :data="eliminationDetails" border stripe>
        <el-table-column prop="entry_no" label="分录编号" width="140" />
        <el-table-column prop="entry_type" label="类型" width="100" />
        <el-table-column prop="description" label="摘要" min-width="200" />
        <el-table-column label="借方" width="130" align="right">
          <template #default="{ row }"><span class="debit">{{ fmtAmt(row.debit) }}</span></template>
        </el-table-column>
        <el-table-column label="贷方" width="130" align="right">
          <template #default="{ row }"><span class="credit">{{ fmtAmt(row.credit) }}</span></template>
        </el-table-column>
        <el-table-column prop="review_status" label="状态" width="80" />
      </el-table>
    </template>
  </div>
</template>
```

### 5.5 Tab 4：自定义查询（透视表）

```vue
<template>
  <div class="gt-consol-pivot">
    <!-- 查询配置面板 -->
    <div class="gt-pivot-config">
      <el-form :inline="true" size="small">
        <el-form-item label="行维度">
          <el-select v-model="pivotConfig.row_dim" style="width: 120px">
            <el-option label="科目" value="account" />
            <el-option label="企业" value="company" />
          </el-select>
        </el-form-item>
        <el-form-item label="列维度">
          <el-select v-model="pivotConfig.col_dim" style="width: 120px">
            <el-option label="企业" value="company" />
            <el-option label="科目" value="account" />
          </el-select>
        </el-form-item>
        <el-form-item label="值字段">
          <el-select v-model="pivotConfig.value_field" style="width: 140px">
            <el-option label="合并数" value="consolidated_amount" />
            <el-option label="下级汇总" value="children_amount_sum" />
            <el-option label="差额净额" value="net_difference" />
            <el-option label="抵消借方" value="elimination_debit" />
            <el-option label="抵消贷方" value="elimination_credit" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-switch v-model="pivotConfig.is_transposed" active-text="转置" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onExecuteQuery" :loading="pivotLoading">查询</el-button>
          <el-button @click="onExportExcel">导出 Excel</el-button>
          <el-button @click="onSaveTemplate">保存模板</el-button>
        </el-form-item>
      </el-form>

      <!-- 筛选条件 -->
      <div class="gt-pivot-filters">
        <el-select v-model="pivotConfig.filter_companies" multiple filterable
          placeholder="筛选企业" style="width: 300px">
          <el-option v-for="n in flatNodes" :key="n.company_code"
            :label="n.company_name" :value="n.company_code" />
        </el-select>
        <el-select v-model="pivotConfig.filter_accounts" multiple filterable
          placeholder="筛选科目" style="width: 300px">
          <el-option v-for="a in accountList" :key="a.code"
            :label="`${a.code} ${a.name}`" :value="a.code" />
        </el-select>
      </div>

      <!-- 已保存模板 -->
      <div v-if="templates.length" class="gt-pivot-templates">
        <span class="label">已保存模板：</span>
        <el-tag v-for="t in templates" :key="t.id" size="small" closable
          @click="loadTemplate(t)" @close="deleteTemplate(t.id)"
          style="cursor: pointer; margin-right: 6px">
          {{ t.name }}
        </el-tag>
      </div>
    </div>

    <!-- 透视表结果 -->
    <div v-if="pivotResult" class="gt-pivot-result">
      <el-table :data="pivotTableData" border stripe size="small"
        max-height="600" :show-summary="true">
        <el-table-column prop="_rowHeader" :label="pivotResult.row_dim === 'account' ? '科目' : '企业'"
          fixed width="200" />
        <el-table-column v-for="(col, ci) in pivotResult.col_headers" :key="ci"
          :label="col" width="130" align="right">
          <template #default="{ row }">
            {{ fmtAmt(row._values[ci]) }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>
```

---

## 六、开发任务清单

```
Phase A：基础设施（5 天）
  A1. 创建 consol_worksheet + consol_query_template 两张表（ALTER TABLE）
  A2. ORM 模型新增 ConsolWorksheet + ConsolQueryTemplate
  A3. 实现 consol_tree_service.py（树形构建 + 节点查找 + 序列化）
  A4. 实现 consol_worksheet_engine.py（差额表全量重算 + 后序遍历）
  A5. 实现 consol_aggregation_service.py（三种汇总模式）

Phase B：穿透与查询（4 天）
  B1. 实现 consol_drilldown_service.py（三层穿透）
  B2. 实现 consol_pivot_service.py（透视查询 + 转置 + Excel 导出）
  B3. 实现 consol_worksheet.py 路由（12 个端点）
  B4. 注册路由到 router_registry.py

Phase C：前端页面（5 天）
  C1. 重建 consolidationApi.ts（完整 API 服务层）
  C2. 改造 ConsolidationIndex.vue（4 个 Tab + 横幅 + 工具栏）
  C3. 实现 Tab 1 集团架构树（el-tree + 节点信息卡片）
  C4. 实现 Tab 2 合并差额表（el-table + 汇总模式切换 + 重算按钮）
  C5. 实现 Tab 3 穿透查询（面包屑 + 三层穿透表格）
  C6. 实现 Tab 4 自定义查询（透视配置 + 结果表格 + 模板管理）

Phase D：集成验证（2 天）
  D1. 导航开放（去掉 developing 标记）
  D2. 端到端验证：建合并项目 → 添加子公司 → 导入数据 → 重算 → 穿透 → 导出
  D3. 性能验证：10 个子公司 × 200 个科目的重算耗时

总工期：约 16 个工作日
```
