"""
Tests for the VidIQ Pulse Chrome Extension backend endpoints,
SEO scoring rubric, and Manifest V3 asset integrity.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.main import app
from app.routers.extension import (
    calculate_seo_score,
    get_channel_profile,
    get_video_recommendations,
    VideoRecommendationRequest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXT_DIR = REPO_ROOT / "extension"


# ── Manifest & Asset Integrity Tests ─────────────────────────────────────────


def test_manifest_v3_structure():
    """Manifest must be valid JSON and strictly Manifest V3."""
    manifest_path = EXT_DIR / "manifest.json"
    assert manifest_path.exists(), "manifest.json does not exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("manifest_version") == 3
    assert data.get("name") == "VidIQ Pulse — Channel AI Copilot"
    assert "icons" in data
    assert "action" in data
    assert "background" in data
    assert "content_scripts" in data


def test_extension_icons_exist_and_match_dimensions():
    """All icon files declared in manifest must exist and match exact pixel dimensions."""
    manifest_path = EXT_DIR / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    icons = data["icons"]
    for size_str, rel_path in icons.items():
        expected_size = int(size_str)
        full_path = EXT_DIR / rel_path
        assert full_path.exists(), f"Icon file missing: {full_path}"

        with Image.open(full_path) as img:
            assert img.size == (expected_size, expected_size), (
                f"Icon {rel_path} size {img.size} does not match {expected_size}x{expected_size}"
            )


def test_extension_files_exist():
    """All script and style assets must be present on disk."""
    required_files = [
        "background/service-worker.js",
        "content/content.js",
        "content/content.css",
        "popup/popup.html",
        "popup/popup.js",
        "popup/popup.css",
        "README.md",
    ]
    for rel_path in required_files:
        p = EXT_DIR / rel_path
        assert p.exists(), f"Required extension file missing: {rel_path}"


# ── SEO Score Rubric Tests ───────────────────────────────────────────────────


def test_calculate_seo_score_optimal():
    """High quality title, rich description, and niche tags should yield high SEO score."""
    title = "How to Build an AI Agent in Python: Complete Step-by-Step Guide"
    description = (
        "In this video, you will learn how to build an AI agent in Python using FastAPI and LLMs.\n\n"
        "Timestamps:\n00:00 - Introduction\n01:30 - Setup\n05:00 - Architecture\n10:00 - Demo\n\n"
        "Resources and Links:\nhttps://github.com/example/ai-agent\n"
    ) + (" Extra explanation content for description depth." * 15)
    tags = [
        "ai agent",
        "python tutorial",
        "fastapi",
        "llm tutorial",
        "python ai",
        "agentic ai",
        "machine learning",
        "build ai",
        "coding",
        "software engineering",
        "python project",
        "backend",
    ]
    niche_keywords = ["python", "ai", "fastapi", "agent"]

    result = calculate_seo_score(title, description, tags, niche_keywords)

    assert result.total_score >= 80
    assert result.title_score >= 20
    assert result.description_score >= 20
    assert result.tag_score >= 20
    assert result.niche_alignment_score == 25
    assert any(c["passed"] for c in result.checklist)


def test_calculate_seo_score_minimal():
    """Low quality or missing metadata yields lower score with failing checklist items."""
    title = "test"
    description = "short"
    tags = ["one"]
    niche_keywords = ["python", "machine learning"]

    result = calculate_seo_score(title, description, tags, niche_keywords)

    assert result.total_score < 40
    assert result.title_score < 10
    assert result.description_score < 10
    # Must contain failing checklist items
    failed_items = [c for c in result.checklist if not c["passed"]]
    assert len(failed_items) > 0


# ── API Endpoint Authentication Tests ─────────────────────────────────────────


@pytest.fixture
def client():
    return TestClient(app)


def test_extension_login_invalid_credentials(client):
    """Extension login with invalid credentials must reject with 401."""
    res = client.post(
        "/api/extension/auth/login",
        json={"email": "nonexistent_creator@example.com", "password": "wrongpassword123"},
    )
    assert res.status_code == 401


def test_extension_protected_routes_require_auth(client):
    """Protected extension endpoints must reject unauthenticated requests."""
    res = client.get("/api/extension/channel-profile")
    assert res.status_code in (401, 403)

    res = client.get("/api/extension/videos")
    assert res.status_code in (401, 403)

    res = client.post(
        "/api/extension/video-recommendations",
        json={"title": "Test Video"},
    )
    assert res.status_code in (401, 403)


# ── Unit Test for Recommendation Generation ───────────────────────────────────


def test_video_recommendations_logic():
    """Tests the recommendation generator combining SEO scores and AI cascade."""
    async def _run():
        mock_user = {"id": "test-user-id", "email": "creator@example.com"}
        payload = VideoRecommendationRequest(
            video_id=None,
            title="10 Secret Tips to Scale Your YouTube Channel in 2026",
            description="Here are 10 secret tips to scale your YouTube audience with consistency and high retention hooks. https://example.com",
            tags=["youtube growth", "content creator", "youtube tips", "video strategy"],
            views=5000,
        )

        mock_channel_profile = {
            "channel_title": "Creator Studio",
            "channel_id": "UC_TEST",
            "niche": "YouTube Growth / Video Creation",
            "baseline_views": 2500,
            "top_keywords": ["youtube", "creator", "growth", "video"],
            "directives": "Focus on high retention hooks and clear CTAs.",
        }

        with patch("app.routers.extension.get_channel_profile", new_callable=AsyncMock) as mock_get_profile:
            mock_get_profile.return_value = mock_channel_profile

            # Mock AI call to test response shaping
            with patch("app.services.youtube_ai_analysis.analyze_video_growth", new_callable=AsyncMock) as mock_ai:
                mock_ai.return_value = {
                    "verdict": "Solid performance at 2.0x channel baseline. Title hook is strong.",
                    "title_options": [
                        "How to 10x Your YouTube Views in 2026 (Proven Blueprint)",
                        "The YouTube Strategy That Actually Works Now",
                        "Stop Making These 5 YouTube Mistakes (Grow Faster)",
                    ],
                    "hook_rewrite": "Most creators quit because of this one mistake. Here's how to fix it in 60 seconds.",
                    "thumbnail_ideas": ["Before vs After split graphic with bold yellow text overlay"],
                    "description_fixes": ["Add timestamp chapters"],
                    "tag_fixes": ["Add long tail tag: youtube growth 2026"],
                    "priority_actions": ["Tighten title length", "Add chapters"],
                }

                res = await get_video_recommendations(
                    payload=payload,
                    current_user=mock_user,
                    session=AsyncMock(),
                )

                assert res.title == payload.title
                assert res.baseline_views == 2500
                assert res.views_vs_baseline_multiplier == 2.0
                assert res.seo_score.total_score > 0
                assert len(res.title_recommendations) == 3
                assert res.hook_rewrite.startswith("Most creators quit")
                assert len(res.tag_recommendations) > 0

    asyncio.run(_run())
