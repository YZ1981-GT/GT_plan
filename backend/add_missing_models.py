"""
Script to add missing models to collaboration_models.py.
Missing classes:
  - ConfirmationLetter  (between ConfirmationResult and ConfirmationAttachment)
  - ConfirmationSummary  (after ConfirmationResult)
  - GoingConcern         (after GoingConcernIndicator, before ArchiveChecklist)
  - WorkpaperReviewRecord (after ArchiveModification)
"""
import sys
sys.path.insert(0, 'D:/GT_plan/backend')

with open(r'D:\GT_plan\backend\app\models\collaboration_models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# --- 1. Add ConfirmationLetter after ConfirmationResult ---
confirmation_letter_def = '''

class ConfirmationLetter(Base):
    """询证函模板/内容"""
    __tablename__ = "confirmation_letters"
    __table_args__ = (Index("ix_confirmation_letters_list", "confirmation_list_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmation_lists.id"), nullable=False
    )
    letter_format: Mapped[LetterFormat] = mapped_column(
        Enum(LetterFormat, name="letter_format_enum"), nullable=False
    )
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

'''

# Find end of ConfirmationResult class - look for next class or blank+class
import re

# Find ConfirmationResult end (after created_by field)
result_end_pattern = r'(    created_by: Mapped\[uuid\.UUID \| None\] = mapped_column\(ForeignKey\("users\.id"\), nullable=True\)\n\n\n)'
content = content.replace(
    '    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)\n\n\n',
    '    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)\n' + confirmation_letter_def,
    1
)
print("Added ConfirmationLetter")

# --- 2. Add ConfirmationSummary after ConfirmationLetter ---
confirmation_summary_def = '''

class ConfirmationSummary(Base):
    """询证函汇总"""
    __tablename__ = "confirmation_summaries"
    __table_args__ = (Index("ix_confirmation_summaries_list", "confirmation_list_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    confirmation_list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("confirmation_lists.id"), nullable=False
    )
    total_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_agreed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_discrepancies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

'''

# Add after ConfirmationLetter (find its end - created_at/updated_at block)
content = content.replace(
    '    created_at: Mapped[datetime] = mapped_column(\n        DateTime(timezone=True), server_default=sa.func.now(), nullable=False\n    )\n    updated_at: Mapped[datetime] = mapped_column(\n        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False\n    )\n\n\nclass ConfirmationAttachment',
    '    created_at: Mapped[datetime] = mapped_column(\n        DateTime(timezone=True), server_default=sa.func.now(), nullable=False\n    )\n    updated_at: Mapped[datetime] = mapped_column(\n        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False\n    )\n' + confirmation_summary_def + '\nclass ConfirmationAttachment',
    1
)
print("Added ConfirmationSummary")

# --- 3. Add GoingConcern after GoingConcernIndicator ---
going_concern_def = '''

class GoingConcern(Base):
    """持续经营评估（别名：GoingConcernEvaluation）"""
    __tablename__ = "going_concern_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    audit_period: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    conclusion: Mapped[GoingConcernConclusion] = mapped_column(
        Enum(GoingConcernConclusion, name="going_concern_conclusion"), nullable=False
    )
    key_indicators: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    management_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    auditor_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

'''

# Add after GoingConcernIndicator
content = content.replace(
    '    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)\n\n\n# ── Phase 010b',
    '    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)\n' + going_concern_def + '\n# ── Phase 010b',
    1
)
print("Added GoingConcern")

# --- 4. Add WorkpaperReviewRecord after ArchiveModification ---
workpaper_review_def = '''

class WorkpaperReviewRecord(Base):
    """工作底稿复核记录"""
    __tablename__ = "workpaper_review_records"
    __table_args__ = (Index("ix_workpaper_review_project", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    workpaper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workpaper_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="review_status_enum"), nullable=False
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
    )

'''

# Find end of ArchiveModification and add WorkpaperReviewRecord after
# The ArchiveModification ends with "created_by" field
content = content.replace(
    '    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)\n\n\n# ── Phase 010b ── Subsequent Events',
    '    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)\n' + workpaper_review_def + '\n# ── Phase 010b ── Subsequent Events',
    1
)
print("Added WorkpaperReviewRecord")

# --- Also add GoingConcernConclusion enum if missing ---
if 'class GoingConcernConclusion' not in content:
    # Insert before GoingConcern class
    content = content.replace(
        '\nclass GoingConcern(Base):',
        '\n\nclass GoingConcernConclusion(str, enum.Enum):\n    no_issue = "NO_ISSUE"\n    minor_doubt = "MINOR_DOUBT"\n    substantial_doubt = "SUBSTANTIAL_DOUBT"\n    mitigated = "MITIGATED"\n\n\nclass GoingConcern(Base):',
        1
    )
    print("Added GoingConcernConclusion enum")

with open(r'D:\GT_plan\backend\app\models\collaboration_models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
