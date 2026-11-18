/**
 * VidIQ Pulse - Popup Logic
 * Coordinates authentication, channel profile, previous video library,
 * and active video recommendation inspection.
 */

document.addEventListener("DOMContentLoaded", async () => {
  const DEFAULT_SERVER_URL = "http://localhost:8000";

  // Elements
  const dot = document.getElementById("conn-status-dot");
  const statusText = document.getElementById("conn-status-text");
  const alertBox = document.getElementById("popup-alert");

  // Tab Buttons
  const tabBtns = document.querySelectorAll(".tab-btn");
  const views = document.querySelectorAll(".main-view");

  // Settings & Auth Elements
  const serverUrlInput = document.getElementById("setting-server-url");
  const btnSaveServerUrl = document.getElementById("btn-save-server-url");
  const accountLoggedIn = document.getElementById("account-logged-in");
  const accountLoggedOut = document.getElementById("account-logged-out");
  const loggedInEmail = document.getElementById("logged-in-email");
  const inputLoginEmail = document.getElementById("input-login-email");
  const inputLoginPass = document.getElementById("input-login-pass");
  const btnLoginSubmit = document.getElementById("btn-login-submit");
  const btnLogout = document.getElementById("btn-logout");
  const btnSyncChannel = document.getElementById("btn-sync-channel");

  // Channel Intel Elements
  const statTotalVideos = document.getElementById("stat-total-videos");
  const statTotalViews = document.getElementById("stat-total-views");
  const statWatchHours = document.getElementById("stat-watch-hours");
  const statBaselineViews = document.getElementById("stat-baseline-views");
  const nicheLabel = document.getElementById("niche-label");
  const badgeChannelTitle = document.getElementById("badge-channel-title");
  const channelNicheHeader = document.getElementById("channel-niche-header");
  const channelKeywordsCloud = document.getElementById("channel-keywords-cloud");
  const channelDirectivesBox = document.getElementById("channel-directives-box");

  // Previous Videos Elements
  const videoSearchInput = document.getElementById("video-search-input");
  const previousVideosList = document.getElementById("previous-videos-list");

  // Active Video Elements
  const activeVideoContainer = document.getElementById("active-video-container");
  const btnInspectActiveTab = document.getElementById("btn-inspect-active-tab");

  let allVideos = [];

  // Helper: Show Alert
  function showAlert(msg, type = "success") {
    alertBox.textContent = msg;
    alertBox.className = `msg-alert ${type}`;
    setTimeout(() => {
      alertBox.className = "msg-alert";
    }, 4000);
  }

  // Helper: Get API URL
  async function getServerUrl() {
    const data = await chrome.storage.local.get("serverUrl");
    return data.serverUrl || DEFAULT_SERVER_URL;
  }

  // Helper: Get Auth Token
  async function getToken() {
    const data = await chrome.storage.local.get("accessToken");
    return data.accessToken || null;
  }

  // Generic Authenticated API Request
  async function apiRequest(endpoint, method = "GET", body = null) {
    const serverUrl = await getServerUrl();
    const token = await getToken();

    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${serverUrl}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || `Request failed with status ${res.status}`);
    }

    return res.json();
  }

  // Tab Navigation
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      views.forEach((v) => v.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-view");
      const targetView = document.getElementById(targetId);
      if (targetView) targetView.classList.add("active");

      // Auto-load tab data
      if (targetId === "view-channel") loadChannelProfile();
      if (targetId === "view-videos") loadPreviousVideos();
      if (targetId === "view-active") inspectCurrentTab();
    });
  });

  // Check Auth State
  async function checkAuth() {
    const storage = await chrome.storage.local.get(["serverUrl", "accessToken", "user"]);
    serverUrlInput.value = storage.serverUrl || DEFAULT_SERVER_URL;

    if (storage.accessToken && storage.user) {
      dot.classList.add("connected");
      statusText.textContent = "Connected";
      accountLoggedIn.style.display = "block";
      accountLoggedOut.style.display = "none";
      loggedInEmail.textContent = storage.user.email;
      loadChannelProfile();
    } else {
      dot.classList.remove("connected");
      statusText.textContent = "Disconnected";
      accountLoggedIn.style.display = "none";
      accountLoggedOut.style.display = "block";
    }
  }

  // Save Server URL
  btnSaveServerUrl?.addEventListener("click", async () => {
    const url = serverUrlInput.value.trim().replace(/\/+$/, "");
    await chrome.storage.local.set({ serverUrl: url });
    showAlert("Server URL saved successfully.");
    checkAuth();
  });

  // Login Submit
  btnLoginSubmit?.addEventListener("click", async () => {
    const email = inputLoginEmail.value.trim();
    const password = inputLoginPass.value;

    if (!email || !password) {
      showAlert("Please enter both email and password.", "error");
      return;
    }

    btnLoginSubmit.textContent = "Signing in...";
    btnLoginSubmit.disabled = true;

    try {
      const serverUrl = await getServerUrl();
      const res = await fetch(`${serverUrl}/api/extension/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Authentication failed");
      }

      const data = await res.json();
      await chrome.storage.local.set({
        accessToken: data.access_token,
        user: data.user,
      });

      showAlert("Logged in successfully!");
      checkAuth();
      inspectCurrentTab();
    } catch (err) {
      showAlert(err.message, "error");
    } finally {
      btnLoginSubmit.textContent = "Sign In to Database";
      btnLoginSubmit.disabled = false;
    }
  });

  // Logout
  btnLogout?.addEventListener("click", async () => {
    await chrome.storage.local.remove(["accessToken", "user", "channelProfile"]);
    showAlert("Logged out successfully.");
    checkAuth();
  });

  // Sync Channel from YouTube Data API
  btnSyncChannel?.addEventListener("click", async () => {
    btnSyncChannel.textContent = "Syncing from YouTube...";
    btnSyncChannel.disabled = true;

    try {
      await apiRequest("/api/youtube-analytics/sync-live", "POST");
      showAlert("Channel sync complete! Reloading profile...");
      await loadChannelProfile();
      await loadPreviousVideos();
    } catch (err) {
      showAlert(`Sync failed: ${err.message}`, "error");
    } finally {
      btnSyncChannel.textContent = "⚡ Sync Channel from YouTube Data API";
      btnSyncChannel.disabled = false;
    }
  });

  // Load Channel Profile
  async function loadChannelProfile() {
    try {
      const profile = await apiRequest("/api/extension/channel-profile");
      await chrome.storage.local.set({ channelProfile: profile });

      badgeChannelTitle.textContent = profile.channel_title || "My Channel";
      channelNicheHeader.textContent = profile.niche || "Channel Copilot";
      nicheLabel.textContent = profile.niche || "--";

      statTotalVideos.textContent = Number(profile.total_videos || 0).toLocaleString();
      statTotalViews.textContent = Number(profile.total_views || 0).toLocaleString();
      statWatchHours.textContent = Number(profile.total_watch_hours || 0).toLocaleString();
      statBaselineViews.textContent = Number(profile.baseline_views || 0).toLocaleString();

      if (profile.top_keywords && profile.top_keywords.length > 0) {
        channelKeywordsCloud.innerHTML = profile.top_keywords
          .map((kw) => `<span class="keyword-pill">${kw}</span>`)
          .join("");
      }

      if (profile.directives) {
        channelDirectivesBox.textContent = profile.directives;
      }
    } catch (err) {
      console.warn("Could not load channel profile:", err);
    }
  }

  // Load Previous Videos
  async function loadPreviousVideos() {
    previousVideosList.innerHTML = `<div style="text-align: center; padding: 20px; font-size: 11px; color: var(--text-dim);">Loading videos from database...</div>`;

    try {
      const data = await apiRequest("/api/extension/videos?limit=50&sort_by=views");
      allVideos = data.videos || [];
      renderPreviousVideosList(allVideos);
    } catch (err) {
      previousVideosList.innerHTML = `<div style="text-align: center; padding: 20px; font-size: 11px; color: #f87171;">Failed to load videos: ${err.message}</div>`;
    }
  }

  // Render Video List
  function renderPreviousVideosList(videos) {
    if (!videos || videos.length === 0) {
      previousVideosList.innerHTML = `<div style="text-align: center; padding: 20px; font-size: 11px; color: var(--text-dim);">No previous videos found in database.</div>`;
      return;
    }

    previousVideosList.innerHTML = videos
      .map(
        (v) => `
      <div class="video-card-item" data-video-id="${v.video_id}">
        <img class="video-thumb" src="${v.thumbnail_url || 'icons/icon-48.png'}" alt="" onerror="this.src='icons/icon-48.png'"/>
        <div class="video-info">
          <div class="video-title" title="${escapeHtml(v.title)}">${escapeHtml(v.title)}</div>
          <div class="video-sub">
            <span>👁️ ${Number(v.views || 0).toLocaleString()}</span>
            <span>👍 ${Number(v.likes || 0).toLocaleString()}</span>
            <span class="seo-badge">SEO ${v.seo_title_score || 70}</span>
          </div>
        </div>
      </div>
    `
      )
      .join("");

    // Attach click listener to load video into Active Video inspector
    previousVideosList.querySelectorAll(".video-card-item").forEach((card) => {
      card.addEventListener("click", () => {
        const vid = card.getAttribute("data-video-id");
        const found = allVideos.find((x) => x.video_id === vid);
        if (found) {
          // Switch to active tab
          tabBtns[0].click();
          loadRecommendationsForVideo(found);
        }
      });
    });
  }

  // Search Filter
  videoSearchInput?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderPreviousVideosList(allVideos);
      return;
    }
    const filtered = allVideos.filter(
      (v) =>
        (v.title && v.title.toLowerCase().includes(q)) ||
        (Array.isArray(v.tags) && v.tags.some((t) => t.toLowerCase().includes(q)))
    );
    renderPreviousVideosList(filtered);
  });

  // Inspect Active Tab
  async function inspectCurrentTab() {
    activeVideoContainer.innerHTML = `
      <div class="glass-card" style="text-align: center; padding: 20px;">
        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">Analyzing current YouTube tab...</div>
      </div>
    `;

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.url || !tab.url.includes("youtube.com/watch")) {
        activeVideoContainer.innerHTML = `
          <div class="glass-card" style="text-align: center; padding: 24px 16px;">
            <div style="font-size: 28px; margin-bottom: 8px;">📺</div>
            <div style="font-size: 13px; font-weight: 600; margin-bottom: 6px;">No YouTube Video Detected</div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 14px;">
              Open any YouTube video in Chrome to see instant AI recommendations & SEO audit.
            </div>
            <button id="btn-browse-db-vids" class="btn-secondary">
              Browse Synced Channel Videos Instead
            </button>
          </div>
        `;
        document.getElementById("btn-browse-db-vids")?.addEventListener("click", () => {
          tabBtns[2].click();
        });
        return;
      }

      const url = new URL(tab.url);
      const videoId = url.searchParams.get("v");
      const cleanTitle = (tab.title || "").replace(" - YouTube", "").trim();

      loadRecommendationsForVideo({
        video_id: videoId,
        title: cleanTitle,
      });
    } catch (err) {
      activeVideoContainer.innerHTML = `<div style="padding: 16px; color: #f87171; font-size: 11px;">Error inspecting tab: ${err.message}</div>`;
    }
  }

  btnInspectActiveTab?.addEventListener("click", inspectCurrentTab);

  // Load Recommendations for a given Video
  async function loadRecommendationsForVideo(videoData) {
    activeVideoContainer.innerHTML = `
      <div class="glass-card" style="text-align: center; padding: 24px 16px;">
        <div style="font-size: 12px; color: var(--text-muted);">
          Grounded analysis: comparing against your channel niche & database benchmarks...
        </div>
      </div>
    `;

    try {
      const res = await apiRequest("/api/extension/video-recommendations", "POST", {
        video_id: videoData.video_id,
        title: videoData.title,
        description: videoData.description || "",
        tags: videoData.tags || [],
        views: videoData.views || 0,
      });

      renderActiveVideoRecommendations(res);
    } catch (err) {
      activeVideoContainer.innerHTML = `
        <div class="glass-card" style="text-align: center; padding: 16px;">
          <div style="color: #f87171; font-size: 12px; margin-bottom: 8px;">Failed to generate recommendations: ${err.message}</div>
          <button id="btn-retry-rec" class="btn-secondary">Retry</button>
        </div>
      `;
      document.getElementById("btn-retry-rec")?.addEventListener("click", () => loadRecommendationsForVideo(videoData));
    }
  }

  // Render Recommendations View
  function renderActiveVideoRecommendations(data) {
    const score = data.seo_score.total_score;
    let scoreColor = score >= 75 ? "#34d399" : score >= 50 ? "#fbbf24" : "#f87171";

    activeVideoContainer.innerHTML = `
      <!-- Video Header Card -->
      <div class="glass-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 8px;">
          <div style="font-size: 13px; font-weight: 700; color: #fff; line-height: 1.3;">
            ${escapeHtml(data.title)}
          </div>
          <div style="font-size: 16px; font-weight: 800; color: ${scoreColor}; background: rgba(0,0,0,0.3); padding: 4px 8px; border-radius: 6px; flex-shrink: 0;">
            ${score}/100
          </div>
        </div>
        <div style="font-size: 10px; color: var(--text-dim); display: flex; gap: 8px;">
          <span>🎯 Niche: ${escapeHtml(data.channel_niche)}</span>
          <span>⚡ ${data.views_vs_baseline_multiplier}x Channel Baseline</span>
        </div>
      </div>

      <!-- High-CTR Titles -->
      <div class="glass-card">
        <div class="card-title">💡 High-CTR Title Options</div>
        ${data.title_recommendations
          .map(
            (t) => `
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; background: rgba(0,0,0,0.2); padding: 6px 8px; border-radius: 4px;">
            <div style="font-size: 11px; color: #e2e8f0; line-height: 1.3;">${escapeHtml(t)}</div>
            <button class="btn-popup-copy" data-copy="${escapeHtml(t)}" style="background: rgba(99,102,241,0.2); border: 1px solid rgba(99,102,241,0.4); color: #c7d2fe; font-size: 9px; padding: 2px 6px; border-radius: 3px; cursor: pointer;">Copy</button>
          </div>
        `
          )
          .join("")}
      </div>

      <!-- Hook Rewrite -->
      <div class="glass-card">
        <div class="card-title">🎣 High-Retention Hook (0-10s)</div>
        <div style="font-size: 11px; color: #cbd5e1; font-style: italic; line-height: 1.4; margin-bottom: 8px;">
          "${escapeHtml(data.hook_rewrite)}"
        </div>
        <button class="btn-popup-copy btn-secondary" data-copy="${escapeHtml(data.hook_rewrite)}" style="font-size: 10px; padding: 4px 8px;">
          Copy Hook
        </button>
      </div>

      <!-- Recommended Tags -->
      <div class="glass-card">
        <div class="card-title">
          <span>🏷️ Niche Tags</span>
          <button id="popup-copy-all-tags" style="background: none; border: none; color: #818cf8; font-size: 10px; cursor: pointer; text-decoration: underline;">
            Copy All
          </button>
        </div>
        <div class="keyword-wrap">
          ${(data.tag_recommendations || [])
            .map(
              (tag) => `
            <span class="keyword-pill btn-popup-copy" data-copy="${escapeHtml(tag)}" style="cursor: pointer;">
              + ${escapeHtml(tag)}
            </span>
          `
            )
            .join("")}
        </div>
      </div>

      <!-- Thumbnail Visual Concepts -->
      <div class="glass-card">
        <div class="card-title">🖼️ Thumbnail Concepts</div>
        ${data.thumbnail_ideas
          .map(
            (idea, i) => `
          <div style="font-size: 11px; margin-bottom: 6px; line-height: 1.35;">
            <strong style="color: #a855f7;">#${i + 1}</strong> ${escapeHtml(idea)}
          </div>
        `
          )
          .join("")}
      </div>
    `;

    // Copy buttons
    activeVideoContainer.querySelectorAll(".btn-popup-copy").forEach((btn) => {
      btn.addEventListener("click", () => {
        const text = btn.getAttribute("data-copy");
        if (text) {
          navigator.clipboard.writeText(text).then(() => {
            const original = btn.textContent;
            btn.textContent = "✓ Copied";
            setTimeout(() => (btn.textContent = original), 1800);
          });
        }
      });
    });

    // Copy All Tags
    document.getElementById("popup-copy-all-tags")?.addEventListener("click", () => {
      const allTags = (data.tag_recommendations || []).join(", ");
      navigator.clipboard.writeText(allTags).then(() => {
        showAlert("All tags copied to clipboard!");
      });
    });
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial Run
  await checkAuth();
});
