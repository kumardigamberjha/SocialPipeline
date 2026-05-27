"""
Test ComfyUI connectivity and Instagram image generation endpoint.

Run:  python test_comfy.py
"""

import asyncio
import aiohttp
import os
import sys

COMFY_HOST = os.getenv("COMFY_HOST", "127.0.0.1")
COMFY_PORT = int(os.getenv("COMFY_PORT", "8188"))
API_BASE = os.getenv("API_BASE", "http://localhost:8000")

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"


async def test_comfy_direct_health():
    """Test 1: Can we reach ComfyUI directly?"""
    url = f"http://{COMFY_HOST}:{COMFY_PORT}/system_stats"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                assert r.status == 200, f"Expected 200, got {r.status}"
                data = await r.json()
                assert "system" in data, "Missing 'system' key in response"
                print(f"  {PASS} ComfyUI reachable at {url}")
                return True
    except Exception as e:
        print(f"  {FAIL} ComfyUI NOT reachable at {url}: {e}")
        return False


async def test_comfy_client_health():
    """Test 2: Does ComfyClient.health_check() work?"""
    try:
        from app.services.comfy_client import ComfyClient
        client = ComfyClient(host=COMFY_HOST, port=COMFY_PORT)
        ok = await client.health_check()
        assert ok, "health_check() returned False"
        print(f"  {PASS} ComfyClient.health_check() returned True")
        return True
    except Exception as e:
        print(f"  {FAIL} ComfyClient.health_check() failed: {e}")
        return False


async def test_comfy_env_vars():
    """Test 3: Are COMFY_HOST/PORT env vars set correctly?"""
    host = os.getenv("COMFY_HOST")
    port = os.getenv("COMFY_PORT")
    ok = True

    if host:
        print(f"  {PASS} COMFY_HOST={host}")
    else:
        print(f"  {FAIL} COMFY_HOST not set (will default to 127.0.0.1)")
        ok = False

    if port:
        print(f"  {PASS} COMFY_PORT={port}")
    else:
        print(f"  {PASS} COMFY_PORT not set (will default to 8188)")

    return ok


async def test_api_instagram_endpoint():
    """Test 4: Does /api/instagram/generate return a non-503 response?"""
    url = f"{API_BASE}/api/instagram/generate"
    payload = {
        "topic": "test connectivity",
        "palette": "void_purple",
        "layout": "bottom_hero",
        "model": "sdxl_turbo",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 503:
                    body = await r.json()
                    print(f"  {FAIL} API returned 503: {body.get('detail', body)}")
                    return False
                # Any non-503 means ComfyUI is reachable from the API
                # (could still fail on missing model, but connectivity is fine)
                print(f"  {PASS} API endpoint reachable, status={r.status} (ComfyUI connected)")
                return True
    except Exception as e:
        print(f"  {FAIL} API endpoint error: {e}")
        return False


async def main():
    print("\n=== ComfyUI Connectivity Tests ===\n")

    results = []

    print("[1] Direct ComfyUI health check")
    results.append(await test_comfy_direct_health())

    print("[2] ComfyClient.health_check()")
    results.append(await test_comfy_client_health())

    print("[3] Environment variables")
    results.append(await test_comfy_env_vars())

    print("[4] API /api/instagram/generate endpoint")
    results.append(await test_api_instagram_endpoint())

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"Results: {passed}/{total} passed")

    if all(results):
        print("All tests passed!")
    else:
        print("Some tests failed — check output above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
