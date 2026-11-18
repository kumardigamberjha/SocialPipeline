# ⚡ VidIQ Pulse — Channel AI Copilot (Chrome Extension)

A VidIQ-like Chrome extension (Manifest V3) that integrates directly with your creator account database (`youtube_videos_live`, channel niche, keyword clusters, baseline views, and creator directives) to deliver intelligent real-time recommendations for each video directly on YouTube and inside your browser toolbar.

---

## Features

- **🎯 Personal Database Grounding**:
  - Automatically queries your logged-in creator database to extract your channel niche, baseline views, top keywords, and retention trends.
  - Compares any video against your channel's actual performance benchmarks (e.g. `2.4x Channel Average`).
- **💡 Real-Time AI Recommendations**:
  - **High-CTR Titles**: 3-5 alternative titles crafted for your channel's specific niche audience.
  - **High-Retention Hook Rewrite**: Opening 0-10s script to prevent early drop-off.
  - **Thumbnail Visual Concepts**: Actionable composition, contrast, subject, and text overlay prompts.
  - **Missing & High-Opportunity Tags**: Keyword gap tags with 1-click individual and "Copy All" buttons.
  - **Ranked Priority Actions**: Top 3 fixes to execute immediately.
- **📊 100-Point SEO Audit & Score Meter**:
  - Circular animated dial (0-100) on YouTube watch and Studio edit pages.
  - Broken down into Title (25 pts), Description (25 pts), Tags (25 pts), and Channel Niche Alignment (25 pts).
- **📺 In-Page YouTube & Studio Overlay**:
  - Seamlessly embedded in YouTube's right sidebar on any video.
  - Handles YouTube's Single Page Application (SPA) navigation (`yt-navigate-finish`) automatically.
  - Collapsible / minimizable into a compact badge.
- **🗂️ Previous Videos Library**:
  - Search, sort, and browse your entire synced video catalogue with views, likes, CTR, duration, and SEO scores.
  - Click any past video in the popup to inspect recommendations.

---

## How to Install in Chrome

1. Open Google Chrome.
2. Navigate to `chrome://extensions/`.
3. In the top-right corner, toggle **Developer mode** to **ON**.
4. Click **Load unpacked** in the top-left corner.
5. Select the `extension` folder from this repository:
   ```
   /media/digamber-jha/G13/MyEmpire/Content Creator/extension
   ```
6. The extension **VidIQ Pulse — Channel AI Copilot** will appear in your extensions list and toolbar!

---

## How to Use

1. **Sign In**:
   - Click the VidIQ Pulse icon in your Chrome toolbar.
   - Go to the **Settings** tab.
   - Ensure the server URL is `http://localhost:8000` (or your production API URL).
   - Enter your account email and password to connect to your database.
2. **Browse YouTube**:
   - Open any video on `https://www.youtube.com/watch?v=...` (your own video or a competitor's).
   - You will see the **VidIQ Pulse** widget docked in the right sidebar beside the video.
   - Switch between **💡 AI Recommendations**, **📊 SEO Audit**, and **🎯 Niche Intel**.
3. **Inspect Active Videos via Popup**:
   - Open the popup while on any YouTube page to see instant recommendations or search through your synced past videos.
