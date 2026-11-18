# Chrome Web Store Listing: VidIQ Pulse — Channel AI Copilot

*Last updated: 2026-09-17*

---

## 1. Store Metadata

- **Extension Name**: VidIQ Pulse — Channel AI Copilot
- **Short Name**: VidIQ Pulse
- **Summary / Short Description** (≤ 132 characters):
  AI-powered video recommendations, SEO scores, and channel niche insights grounded in your personal YouTube video database.
- **Detailed Description**:
  VidIQ Pulse is an intelligent YouTube growth copilot that connects directly with your personal creator account database to give you tailored recommendations for every video you watch or edit.

  Unlike generic AI tools that give the same advice to every creator, VidIQ Pulse analyzes your channel's actual performance history:
  - Your exact channel niche classification
  - Your highest-performing keyword clusters and topics
  - Your baseline average views and retention rates
  - Your custom creator rules and directives

  ### Key Features:
  - **In-Page YouTube Widget**: Docked right beside the YouTube player or Studio editor.
  - **100-Point SEO Audit**: Instant evaluation of titles, description depth, tag volume, and niche alignment.
  - **High-CTR Alternative Titles**: AI-crafted titles tailored specifically to your channel's target audience.
  - **High-Retention Opening Hooks**: 0-10 second script rewrites to minimize early viewer drop-off.
  - **Thumbnail Visual Prompts**: Specific contrast, subject, framing, and text overlay ideas.
  - **Opportunity Tags**: High-traction niche tags with 1-click individual and "Copy All" buttons.
  - **Previous Video Library**: Search and filter your synced videos by views, likes, and SEO scores directly in the extension popup.

- **Category**: Productivity / Social & Communication
- **Primary Language**: English

---

## 2. Permissions Justification

| Permission | Justification |
|---|---|
| `storage` | Required to securely store user authentication tokens, backend server URL, and cached channel profile locally in the browser. |
| `tabs` | Required to read the active tab URL (`youtube.com/watch?v=...`) to identify the video currently being viewed and display its SEO audit and recommendations. |
| `https://*.youtube.com/*` | Required to inject the in-page VidIQ Pulse analysis sidebar and recommendation widget onto YouTube watch and Studio edit pages. |
| `http://localhost:8000/*` | Required to communicate with your local creator database and AI recommendations API server. |
| `http://127.0.0.1:8000/*` | Required to communicate with your local creator database and AI recommendations API server. |

---

## 3. Privacy & Data Use Disclosures

- **Single Purpose**: Provide data-grounded video recommendations and SEO scores for YouTube creators based on their own channel database.
- **Data Collection**:
  - Website content: Scrapes publicly visible video titles, descriptions, and tags on YouTube watch pages to calculate the SEO score.
  - User credentials: Email and password used strictly to authenticate with the creator's backend API.
- **Data Sharing**: No data is sold or shared with third parties. All requests are processed securely between the browser and the user's configured backend server.
- **Remote Code**: None. All extension scripts (`background/service-worker.js`, `content/content.js`, `popup/popup.js`) are packaged locally within the extension.
