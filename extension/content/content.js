/**
 * VidIQ Pulse - YouTube In-Page Content Script
 * Injects rich AI recommendations, SEO score, and channel niche comparison
 * directly onto YouTube video watch and Studio edit pages.
 */

(() => {
  let currentVideoId = null;
  let activeTab = "recs"; // 'recs' | 'audit' | 'channel'
  let cachedData = null;
  let isMinimized = false;

  console.log("[VidIQ Pulse] Content script loaded.");

  // Helper: Escape HTML
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Extract Video ID
  function getVideoId() {
    const url = new URL(window.location.href);
    if (url.searchParams.has("v")) {
      return url.searchParams.get("v");
    }
    // YouTube Studio edit URL: /video/{video_id}/edit
    const match = window.location.pathname.match(/\/video\/([a-zA-Z0-9_-]+)\/edit/);
    if (match) return match[1];
    return null;
  }

  // Scrape YouTube Video Metadata
  function scrapeVideoMetadata() {
    const videoId = getVideoId();

    // Title
    const titleEl =
      document.querySelector("h1.ytd-watch-metadata yt-formatted-string") ||
      document.querySelector("#title h1 yt-formatted-string") ||
      document.querySelector("h1.title yt-formatted-string") ||
      document.querySelector("meta[name='title']");
    let title = titleEl ? (titleEl.innerText || titleEl.content || "") : "";
    if (!title) {
      title = document.title.replace(" - YouTube", "").trim();
    }

    // Channel
    const channelEl =
      document.querySelector("#owner #channel-name a") ||
      document.querySelector("ytd-channel-name #text a") ||
      document.querySelector("#upload-info #channel-name a");
    const channelTitle = channelEl ? channelEl.innerText.trim() : "";

    // Views
    const viewsEl =
      document.querySelector("#info-strings yt-formatted-string") ||
      document.querySelector(".ytd-video-view-count-renderer") ||
      document.querySelector("#view-count");
    let views = 0;
    if (viewsEl) {
      const vText = viewsEl.innerText.replace(/[^0-9]/g, "");
      views = parseInt(vText, 10) || 0;
    }

    // Description
    const descEl =
      document.querySelector("#description-inline-expander yt-formatted-string") ||
      document.querySelector("#description yt-formatted-string") ||
      document.querySelector("#description");
    const description = descEl ? descEl.innerText : "";

    // Tags
    const tags = [];
    const metaKeywords = document.querySelector("meta[name='keywords']");
    if (metaKeywords && metaKeywords.content) {
      metaKeywords.content.split(",").forEach((t) => {
        const clean = t.trim();
        if (clean && !tags.includes(clean)) tags.push(clean);
      });
    }

    // Also hashtags from description
    const hashMatches = description.match(/#[a-zA-Z0-9_-]+/g);
    if (hashMatches) {
      hashMatches.forEach((h) => {
        const clean = h.replace("#", "").trim();
        if (clean && !tags.includes(clean)) tags.push(clean);
      });
    }

    return {
      video_id: videoId,
      title: title.trim(),
      channel_title: channelTitle,
      views,
      description: description.slice(0, 3000),
      tags,
    };
  }

  // Find or Create Root Container
  function getRootContainer() {
    let root = document.getElementById("vidiq-pulse-root");
    if (!root) {
      root = document.createElement("div");
      root.id = "vidiq-pulse-root";

      // Attempt to place inside YouTube's secondary sidebar
      const targetSidebar =
        document.querySelector("#secondary #secondary-inner") ||
        document.querySelector("#secondary") ||
        document.querySelector("#related");

      if (targetSidebar) {
        targetSidebar.insertBefore(root, targetSidebar.firstChild);
      } else {
        // Fallback: fixed positioning
        root.style.position = "fixed";
        root.style.top = "80px";
        root.style.right = "20px";
        root.style.width = "380px";
        root.style.maxWidth = "calc(100vw - 40px)";
        document.body.appendChild(root);
      }
    }
    return root;
  }

  // Render Loading Skeleton
  function renderLoading() {
    const root = getRootContainer();
    root.innerHTML = `
      <div class="vidiq-container">
        <div class="vidiq-header">
          <div class="vidiq-brand">
            <span class="vidiq-logo-badge">⚡ VidIQ Pulse</span>
            <span class="vidiq-app-title">Analyzing Channel & Video...</span>
          </div>
        </div>
        <div class="vidiq-loading">
          <div class="vidiq-spinner"></div>
          <div>Checking database metrics, channel niche & calculating AI recommendations...</div>
        </div>
      </div>
    `;
  }

  // Render Login Prompt
  function renderLoginPrompt(serverUrl) {
    const root = getRootContainer();
    root.innerHTML = `
      <div class="vidiq-container">
        <div class="vidiq-header">
          <div class="vidiq-brand">
            <span class="vidiq-logo-badge">⚡ VidIQ Pulse</span>
            <span class="vidiq-app-title">Connect Channel</span>
          </div>
        </div>
        <div class="vidiq-login-prompt">
          <div class="vidiq-login-title">Channel Database Not Connected</div>
          <div class="vidiq-login-desc">
            Sign in to compare this video against your channel's previous videos, niche keywords, and baseline retention.
          </div>
          <button id="vidiq-btn-open-popup" class="vidiq-btn-action">
            🔑 Open VidIQ Pulse Extension to Sign In
          </button>
        </div>
      </div>
    `;

    document.getElementById("vidiq-btn-open-popup")?.addEventListener("click", () => {
      alert("Click the VidIQ Pulse icon in your Chrome extensions toolbar to sign in.");
    });
  }

  // Render Full Widget
  function renderWidget(data) {
    const root = getRootContainer();
    const score = data.seo_score.total_score;

    // Dial color
    let strokeColor = "#10b981"; // green
    let verdictColor = "#34d399";
    if (score < 50) {
      strokeColor = "#ef4444";
      verdictColor = "#f87171";
    } else if (score < 75) {
      strokeColor = "#f59e0b";
      verdictColor = "#fbbf24";
    }

    const radius = 24;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (score / 100) * circumference;

    // Send score to service worker badge
    chrome.runtime.sendMessage({
      type: "SET_BADGE",
      text: String(score),
      color: strokeColor,
    });

    if (isMinimized) {
      root.innerHTML = `
        <div class="vidiq-container" style="cursor: pointer;" id="vidiq-expand-bar">
          <div class="vidiq-header">
            <div class="vidiq-brand">
              <span class="vidiq-logo-badge">⚡ ${score}</span>
              <span class="vidiq-app-title">VidIQ Pulse (Minimized)</span>
            </div>
            <button class="vidiq-btn-icon" title="Expand">▼</button>
          </div>
        </div>
      `;
      document.getElementById("vidiq-expand-bar")?.addEventListener("click", () => {
        isMinimized = false;
        renderWidget(data);
      });
      return;
    }

    root.innerHTML = `
      <div class="vidiq-container">
        <!-- Header -->
        <div class="vidiq-header">
          <div class="vidiq-brand">
            <div class="vidiq-logo-badge">⚡ VidIQ Pulse</div>
            <div class="vidiq-title-wrap">
              <div class="vidiq-app-title">Channel Copilot</div>
              <div class="vidiq-niche-badge" title="${escapeHtml(data.channel_niche)}">🎯 ${escapeHtml(data.channel_niche)}</div>
            </div>
          </div>
          <div class="vidiq-header-actions">
            <button class="vidiq-btn-icon" id="vidiq-refresh-btn" title="Refresh Recommendations">↻</button>
            <button class="vidiq-btn-icon" id="vidiq-toggle-min" title="Minimize">▲</button>
          </div>
        </div>

        <!-- Score Overview -->
        <div class="vidiq-score-row">
          <div class="vidiq-score-dial">
            <svg viewBox="0 0 58 58">
              <circle class="vidiq-dial-bg" cx="29" cy="29" r="${radius}"></circle>
              <circle class="vidiq-dial-progress" cx="29" cy="29" r="${radius}"
                style="stroke: ${strokeColor}; stroke-dasharray: ${circumference}; stroke-dashoffset: ${offset};">
              </circle>
            </svg>
            <div class="vidiq-score-number">
              <span>${score}</span>
              <small>SEO</small>
            </div>
          </div>
          <div class="vidiq-score-details">
            <div class="vidiq-score-verdict-title" style="color: ${verdictColor}">
              ${score >= 75 ? "Excellent Optimization" : score >= 50 ? "Moderate Opportunity" : "Needs Optimization"}
            </div>
            <div class="vidiq-score-verdict-text">${escapeHtml(data.verdict)}</div>
            <div class="vidiq-metric-chips">
              <span class="vidiq-chip ${data.views_vs_baseline_multiplier >= 1.0 ? "positive" : "accent"}">
                ${data.views_vs_baseline_multiplier}x Channel Avg
              </span>
              <span class="vidiq-chip">Base: ${Number(data.baseline_views).toLocaleString()} views</span>
              ${data.is_own_video ? `<span class="vidiq-chip positive">Your Video</span>` : ""}
            </div>
          </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="vidiq-tabs">
          <button class="vidiq-tab-btn ${activeTab === "recs" ? "active" : ""}" data-tab="recs">
            💡 AI Recommendations
          </button>
          <button class="vidiq-tab-btn ${activeTab === "audit" ? "active" : ""}" data-tab="audit">
            📊 SEO Audit
          </button>
          <button class="vidiq-tab-btn ${activeTab === "channel" ? "active" : ""}" data-tab="channel">
            🎯 Niche Intel
          </button>
        </div>

        <!-- Tab Body -->
        <div class="vidiq-tab-body">
          ${renderTabBody(data)}
        </div>
      </div>
    `;

    // Attach Tab Switch Handlers
    root.querySelectorAll(".vidiq-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.getAttribute("data-tab");
        renderWidget(data);
      });
    });

    // Minimize Handler
    document.getElementById("vidiq-toggle-min")?.addEventListener("click", () => {
      isMinimized = true;
      renderWidget(data);
    });

    // Refresh Handler
    document.getElementById("vidiq-refresh-btn")?.addEventListener("click", () => {
      fetchRecommendations(true);
    });

    // Copy Handlers
    root.querySelectorAll(".vidiq-btn-copy").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const textToCopy = btn.getAttribute("data-copy");
        if (textToCopy) {
          navigator.clipboard.writeText(textToCopy).then(() => {
            btn.innerText = "✓ Copied";
            btn.classList.add("copied");
            setTimeout(() => {
              btn.innerText = "Copy";
              btn.classList.remove("copied");
            }, 2000);
          });
        }
      });
    });

    // Copy All Tags Handler
    document.getElementById("vidiq-copy-all-tags")?.addEventListener("click", (e) => {
      const btn = e.target;
      const allTags = (data.tag_recommendations || []).join(", ");
      navigator.clipboard.writeText(allTags).then(() => {
        btn.innerText = "✓ All Tags Copied";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.innerText = "Copy All Tags";
          btn.classList.remove("copied");
        }, 2000);
      });
    });
  }

  // Render Active Tab Content
  function renderTabBody(data) {
    if (activeTab === "recs") {
      return `
        <!-- High-CTR Titles -->
        <div class="vidiq-section-title">
          <span>High-CTR Title Options</span>
        </div>
        ${data.title_recommendations
          .map(
            (t) => `
          <div class="vidiq-item-card">
            <div class="vidiq-card-flex">
              <div class="vidiq-card-text font-medium">${escapeHtml(t)}</div>
              <button class="vidiq-btn-copy" data-copy="${escapeHtml(t)}">Copy</button>
            </div>
          </div>
        `
          )
          .join("")}

        <!-- Hook Rewrite -->
        <div class="vidiq-section-title" style="margin-top: 14px;">
          <span>High-Retention Opening Hook (0-10s)</span>
        </div>
        <div class="vidiq-item-card">
          <div class="vidiq-card-flex">
            <div class="vidiq-card-text" style="color: #cbd5e1; font-style: italic;">
              "${escapeHtml(data.hook_rewrite)}"
            </div>
            <button class="vidiq-btn-copy" data-copy="${escapeHtml(data.hook_rewrite)}">Copy</button>
          </div>
        </div>

        <!-- Thumbnail Concepts -->
        <div class="vidiq-section-title" style="margin-top: 14px;">
          <span>Thumbnail Visual Concepts</span>
        </div>
        ${data.thumbnail_ideas
          .map(
            (idea, i) => `
          <div class="vidiq-item-card">
            <div class="vidiq-card-flex">
              <div class="vidiq-card-text">
                <strong style="color: #a855f7;">#${i + 1}</strong> ${escapeHtml(idea)}
              </div>
              <button class="vidiq-btn-copy" data-copy="${escapeHtml(idea)}">Copy</button>
            </div>
          </div>
        `
          )
          .join("")}

        <!-- Recommended Tags -->
        <div class="vidiq-section-title" style="margin-top: 14px;">
          <span>Niche & High-Traction Tags</span>
          <button id="vidiq-copy-all-tags" class="vidiq-btn-copy">Copy All Tags</button>
        </div>
        <div class="vidiq-tag-cloud">
          ${(data.tag_recommendations || [])
            .map(
              (tag) => `
            <span class="vidiq-tag-pill vidiq-btn-copy" data-copy="${escapeHtml(tag)}">
              + ${escapeHtml(tag)}
            </span>
          `
            )
            .join("")}
        </div>

        <!-- Priority Actions -->
        <div class="vidiq-section-title" style="margin-top: 14px;">
          <span>Ranked Priority Actions</span>
        </div>
        ${(data.priority_actions || [])
          .map(
            (action, idx) => `
          <div class="vidiq-item-card">
            <div class="vidiq-card-text">
              <strong style="color: #38bdf8;">${idx + 1}.</strong> ${escapeHtml(action)}
            </div>
          </div>
        `
          )
          .join("")}
      `;
    }

    if (activeTab === "audit") {
      const rubric = data.seo_score;
      return `
        <div class="vidiq-section-title">
          <span>Rubric Breakdown (Max 25 Each)</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px;">
          <div class="vidiq-item-card" style="text-align: center;">
            <div style="font-size: 10px; color: var(--vidiq-text-dim);">TITLE SCORE</div>
            <div style="font-size: 16px; font-weight: 700; color: #a5b4fc;">${rubric.title_score}/25</div>
          </div>
          <div class="vidiq-item-card" style="text-align: center;">
            <div style="font-size: 10px; color: var(--vidiq-text-dim);">DESC SCORE</div>
            <div style="font-size: 16px; font-weight: 700; color: #a5b4fc;">${rubric.description_score}/25</div>
          </div>
          <div class="vidiq-item-card" style="text-align: center;">
            <div style="font-size: 10px; color: var(--vidiq-text-dim);">TAG SCORE</div>
            <div style="font-size: 16px; font-weight: 700; color: #a5b4fc;">${rubric.tag_score}/25</div>
          </div>
          <div class="vidiq-item-card" style="text-align: center;">
            <div style="font-size: 10px; color: var(--vidiq-text-dim);">NICHE SCORE</div>
            <div style="font-size: 16px; font-weight: 700; color: #a5b4fc;">${rubric.niche_alignment_score}/25</div>
          </div>
        </div>

        <div class="vidiq-section-title">
          <span>Optimization Checklist</span>
        </div>
        ${rubric.checklist
          .map(
            (c) => `
          <div class="vidiq-check-item">
            <span class="vidiq-check-icon ${c.passed ? "pass" : "fail"}">
              ${c.passed ? "✓" : "✕"}
            </span>
            <span style="flex: 1; color: ${c.passed ? "#f8fafc" : "#94a3b8"};">
              ${escapeHtml(c.item)}
            </span>
            <span style="font-size: 10px; font-weight: 600; color: ${c.passed ? "#34d399" : "#64748b"};">
              +${c.score} pts
            </span>
          </div>
        `
          )
          .join("")}
      `;
    }

    if (activeTab === "channel") {
      return `
        <div class="vidiq-section-title">
          <span>Your Channel Baseline Intel</span>
        </div>
        <div class="vidiq-item-card">
          <div style="font-size: 12px; margin-bottom: 4px;">
            <strong>Detected Niche:</strong> <span style="color: #c4b5fd;">${escapeHtml(data.channel_niche)}</span>
          </div>
          <div style="font-size: 12px; margin-bottom: 4px;">
            <strong>Baseline Views:</strong> ${Number(data.baseline_views).toLocaleString()} views
          </div>
          <div style="font-size: 12px;">
            <strong>Performance Ratio:</strong>
            <span style="color: ${data.views_vs_baseline_multiplier >= 1.0 ? "#34d399" : "#f87171"}; font-weight: bold;">
              ${data.views_vs_baseline_multiplier}x
            </span>
          </div>
        </div>

        <div class="vidiq-section-title" style="margin-top: 12px;">
          <span>Description SEO Fixes</span>
        </div>
        ${data.description_fixes
          .map(
            (fix) => `
          <div class="vidiq-item-card">
            <div class="vidiq-card-text">🛠️ ${escapeHtml(fix)}</div>
          </div>
        `
          )
          .join("")}
      `;
    }

    return "";
  }

  // Fetch Recommendations from Backend
  async function fetchRecommendations(forceRefresh = false) {
    const videoId = getVideoId();
    if (!videoId) return;

    if (!forceRefresh && cachedData && cachedData.video_id === videoId) {
      renderWidget(cachedData);
      return;
    }

    renderLoading();

    // Check Auth
    chrome.runtime.sendMessage({ type: "GET_AUTH_STATUS" }, async (authStatus) => {
      if (!authStatus || !authStatus.isAuthenticated) {
        renderLoginPrompt(authStatus?.serverUrl);
        return;
      }

      const scraped = scrapeVideoMetadata();
      scraped.refresh = forceRefresh;

      chrome.runtime.sendMessage(
        {
          type: "FETCH_API",
          endpoint: "/api/extension/video-recommendations",
          method: "POST",
          body: scraped,
        },
        (res) => {
          if (res && res.success && res.data) {
            cachedData = res.data;
            renderWidget(res.data);
          } else {
            console.error("[VidIQ Pulse] Error fetching recommendations:", res?.error);
            const root = getRootContainer();
            root.innerHTML = `
              <div class="vidiq-container">
                <div class="vidiq-header">
                  <div class="vidiq-brand">
                    <span class="vidiq-logo-badge">⚡ VidIQ Pulse</span>
                    <span class="vidiq-app-title">Connection Notice</span>
                  </div>
                </div>
                <div style="padding: 16px; text-align: center; font-size: 12px; color: #f87171;">
                  Failed to fetch video recommendations: ${escapeHtml(res?.error || "Unknown server error")}.
                  <br/><br/>
                  <button id="vidiq-retry-btn" class="vidiq-btn-copy" style="font-size: 12px; padding: 6px 12px;">
                    ↻ Retry
                  </button>
                </div>
              </div>
            `;
            document.getElementById("vidiq-retry-btn")?.addEventListener("click", () => fetchRecommendations(true));
          }
        }
      );
    });
  }

  // Video Navigation Listener
  function onVideoChange() {
    const newId = getVideoId();
    if (newId && newId !== currentVideoId) {
      currentVideoId = newId;
      console.log("[VidIQ Pulse] Video switched to:", newId);
      setTimeout(() => fetchRecommendations(false), 800);
    }
  }

  // Listen to YouTube SPA Events
  window.addEventListener("yt-navigate-finish", onVideoChange);

  // Initial load check
  if (getVideoId()) {
    currentVideoId = getVideoId();
    setTimeout(() => fetchRecommendations(false), 1200);
  }
})();
