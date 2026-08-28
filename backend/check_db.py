from db import get_db
import sys

conn = get_db()
cur = conn.cursor()

# Check clip_ids column type
cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name='render_jobs' AND column_name='clip_ids'")
row = cur.fetchone()
print("clip_ids type:", row[0] if row else "COLUMN NOT FOUND")

# Fix it regardless
try:
    cur.execute("ALTER TABLE render_jobs ALTER COLUMN clip_ids TYPE JSONB USING clip_ids::text::jsonb")
    conn.commit()
    print("SUCCESS: clip_ids converted to JSONB")
except Exception as e:
    conn.rollback()
    print("ALTER failed:", e)
    # Try drop and recreate
    try:
        cur.execute("ALTER TABLE render_jobs DROP COLUMN IF EXISTS clip_ids")
        cur.execute("ALTER TABLE render_jobs ADD COLUMN clip_ids JSONB DEFAULT '[]'")
        conn.commit()
        print("SUCCESS: clip_ids recreated as JSONB")
    except Exception as e2:
        conn.rollback()
        print("Recreate also failed:", e2)

# Verify
cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name='render_jobs' AND column_name='clip_ids'")
row = cur.fetchone()
print("clip_ids type NOW:", row[0] if row else "NOT FOUND")
conn.close()
