"""
Deterministic Python QA for YouTube scripts. No LLM involved — all counting,
detection and measuring happens here (same philosophy as LinkedInQAChecker).
"""

import re

# Per-format word-count bounds and structural expectations.
_FORMAT_SPEC = {
    "full": {"min_words": 1200, "max_words": 2000, "min_visual_cues": 2, "require_b_roll": True, "hook_max_words": 25},
    "short": {"min_words": 40, "max_words": 320, "min_visual_cues": 1, "require_b_roll": False, "hook_max_words": 15},
}
HOOK_SEARCH_LINES = 4


class YouTubeQAChecker:
    def check(self, script: str, video_format: str = "full") -> dict:
        spec = _FORMAT_SPEC.get(video_format, _FORMAT_SPEC["full"])
        text = script or ""
        words = text.split()
        word_count = len(words)

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        first_lines = lines[:HOOK_SEARCH_LINES]
        hook_line = ""
        for ln in first_lines:
            # Skip pure tag/heading lines when hunting for the spoken hook.
            stripped = re.sub(r"\[[^\]]*\]", "", ln).strip("# ").strip()
            if stripped:
                hook_line = stripped
                break
        hook_ok = bool(hook_line) and len(hook_line.split()) <= spec["hook_max_words"]

        visual_cues = len(re.findall(r"\[VISUAL CUE", text, re.IGNORECASE))
        b_roll = len(re.findall(r"\[B-?ROLL", text, re.IGNORECASE))
        energy_marks = len(re.findall(r"\[ENERGY:", text, re.IGNORECASE))
        has_cta = bool(re.search(r"\bCTA\b|\[CTA", text[-1500:], re.IGNORECASE)) or bool(
            re.search(r"subscribe|follow|next video|next level|here's what to do", text[-1500:], re.IGNORECASE)
        )

        checks = {
            "word_count_ok": spec["min_words"] <= word_count <= spec["max_words"],
            "hook_ok": hook_ok,
            "has_visual_cues": visual_cues >= spec["min_visual_cues"],
            "has_energy_marks": energy_marks >= 1,
            "has_cta": has_cta,
        }
        # B-roll is only required for full-length videos.
        if spec["require_b_roll"]:
            checks["has_b_roll"] = b_roll >= 1

        return {
            "video_format": video_format,
            "word_count": word_count,
            "first_line": hook_line,
            "visual_cue_count": visual_cues,
            "b_roll_count": b_roll,
            "energy_mark_count": energy_marks,
            "checks": checks,
            "overall_pass": all(checks.values()),
        }
