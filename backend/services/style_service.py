"""
style_service.py
Video style and format presets for DashClip V3 B4.
Styles influence clip duration hints, subtitle styling, music mood, voiceover style.
"""

STYLES = {
    "cinematic": {
        "id": "cinematic",
        "label": "Cinematic",
        "description": "Slow, dramatic, filmic pacing",
        "duration_hint": 8.0,
        "subtitle_preset": "cinematic",
        "music_mood": "epic cinematic orchestral",
        "voiceover_style": "en-US-ChristopherNeural",
        "pacing": "slow",
        "color": "#a78bfa",
    },
    "youtube": {
        "id": "youtube",
        "label": "YouTube",
        "description": "Energetic, fast, hook-driven",
        "duration_hint": 4.0,
        "subtitle_preset": "minimal",
        "music_mood": "upbeat energetic pop",
        "voiceover_style": "en-US-GuyNeural",
        "pacing": "fast",
        "color": "#f87171",
    },
    "documentary": {
        "id": "documentary",
        "label": "Documentary",
        "description": "Thoughtful, informative, measured",
        "duration_hint": 7.0,
        "subtitle_preset": "cinematic",
        "music_mood": "documentary ambient thoughtful",
        "voiceover_style": "en-GB-RyanNeural",
        "pacing": "medium",
        "color": "#60a5fa",
    },
    "educational": {
        "id": "educational",
        "label": "Educational",
        "description": "Clear, structured, engaging",
        "duration_hint": 6.0,
        "subtitle_preset": "minimal",
        "music_mood": "calm focus background study",
        "voiceover_style": "en-US-AriaNeural",
        "pacing": "medium",
        "color": "#4ade80",
    },
    "storytelling": {
        "id": "storytelling",
        "label": "Storytelling",
        "description": "Emotional, narrative, personal",
        "duration_hint": 7.0,
        "subtitle_preset": "cinematic",
        "music_mood": "emotional storytelling piano",
        "voiceover_style": "en-US-JennyNeural",
        "pacing": "medium",
        "color": "#f5a623",
    },
    "minimal": {
        "id": "minimal",
        "label": "Minimal",
        "description": "Clean, simple, understated",
        "duration_hint": 5.0,
        "subtitle_preset": "minimal",
        "music_mood": "minimal ambient lofi",
        "voiceover_style": "en-US-AriaNeural",
        "pacing": "slow",
        "color": "#6a6460",
    },
}

FORMATS = {
    "landscape": {"id": "landscape", "label": "Landscape (16:9)", "width": 1920, "height": 1080},
    "portrait":  {"id": "portrait",  "label": "Portrait (9:16)",  "width": 1080, "height": 1920},
    "square":    {"id": "square",    "label": "Square (1:1)",      "width": 1080, "height": 1080},
}


def get_styles() -> list[dict]:
    return list(STYLES.values())


def get_formats() -> list[dict]:
    return list(FORMATS.values())


def get_style(style_id: str) -> dict:
    return STYLES.get(style_id, STYLES["cinematic"])


def get_format(format_id: str) -> dict:
    return FORMATS.get(format_id, FORMATS["landscape"])


def apply_style_to_scenes(scenes: list[dict], style_id: str) -> list[dict]:
    """Override duration_hint on all scenes based on selected style."""
    style = get_style(style_id)
    for s in scenes:
        s["duration_hint"] = style["duration_hint"]
    return scenes
