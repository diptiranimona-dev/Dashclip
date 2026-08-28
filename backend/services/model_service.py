"""
model_service.py  —  Phase A (NEW FILE)
Detects installed Ollama models dynamically.
Allows user to select which model to use per task type.
Stores settings in model_settings table.
"""
import subprocess
import json
import re
from db import get_db, fetchone, fetchall, execute

DEFAULT_MODELS = {
    "script_model":    "llama3.2",
    "scene_model":     "llama3.2",
    "keyword_model":   "llama3.2",
    "narration_model": "llama3.2",
}


def get_installed_models() -> list[dict]:
    """Run 'ollama list' and return installed models."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        models = []
        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:  # Skip header row
            parts = line.split()
            if parts:
                models.append({
                    "name": parts[0],
                    "size": parts[2] if len(parts) > 2 else "unknown",
                })
        return models
    except Exception as e:
        print(f"Could not list Ollama models: {e}")
        return []


def get_model_settings() -> dict:
    """Get current model settings from DB. Returns defaults if not set."""
    conn = get_db()
    rows = fetchall(conn, "SELECT setting_key, setting_value FROM model_settings")
    conn.close()

    settings = dict(DEFAULT_MODELS)  # Start with defaults
    for row in rows:
        settings[row["setting_key"]] = row["setting_value"]
    return settings


def update_model_setting(key: str, value: str) -> bool:
    """Update a single model setting."""
    if key not in DEFAULT_MODELS:
        return False
    conn = get_db()
    execute(conn,
        """INSERT INTO model_settings (setting_key, setting_value)
           VALUES (%s, %s)
           ON CONFLICT (setting_key) DO UPDATE
           SET setting_value = EXCLUDED.setting_value,
               updated_at = NOW()""",
        (key, value)
    )
    conn.commit()
    conn.close()
    return True


def get_model_for_task(task: str) -> str:
    """Get the configured model for a specific task. Falls back to llama3.2."""
    conn = get_db()
    row = fetchone(conn,
        "SELECT setting_value FROM model_settings WHERE setting_key = %s",
        (f"{task}_model",)
    )
    conn.close()
    if row:
        return row["setting_value"]
    return DEFAULT_MODELS.get(f"{task}_model", "llama3.2")
