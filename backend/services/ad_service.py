"""
ad_service.py
Architecture placeholder for future ad integration.
No real ads are served in V1.

Future ad slots:
  1. after_clip_finding  — shown after Pexels clips load
  2. before_render       — shown before render starts
  3. before_advanced_edit — shown when advanced features are accessed
"""

AD_SLOTS = [
    {"id": "after_clip_finding",   "label": "After clip selection",   "enabled": False},
    {"id": "before_render",        "label": "Before render",          "enabled": False},
    {"id": "before_advanced_edit", "label": "Before advanced editing","enabled": False},
]


def get_ad_config() -> list[dict]:
    """Return ad slot configuration (all disabled in V1)."""
    return AD_SLOTS


def should_show_ad(slot_id: str) -> bool:
    """Returns True if a given ad slot is enabled."""
    slot = next((s for s in AD_SLOTS if s["id"] == slot_id), None)
    return slot["enabled"] if slot else False


def record_ad_impression(slot_id: str, user_id: str | None = None):
    """Placeholder — log ad impression for future analytics."""
    # TODO: write to ad_impressions table when real ads are integrated
    pass
