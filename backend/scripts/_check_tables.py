"""检查缺失的表"""
import psycopg2

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/audit_platform")
cur = conn.cursor()

tables_to_check = [
    'project_assignments', 'staff_members', 'work_hours',
    'review_conversations', 'review_messages', 'forum_posts', 'forum_comments',
    'cell_annotations', 'consol_snapshots', 'report_format_templates',
    'procedure_instances', 'procedure_trim_schemes',
    'note_section_instances', 'note_trim_schemes',
    'tb_aux_balance_summary',
]

for t in tables_to_check:
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=%s)", (t,))
    exists = cur.fetchone()[0]
    print(f"  {t}: {'EXISTS' if exists else 'MISSING'}")

cur.close()
conn.close()
