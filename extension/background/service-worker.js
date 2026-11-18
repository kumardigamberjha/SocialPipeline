/**
 * Background Service Worker for VidIQ Pulse
 * Handles background messaging, token retrieval, badge updates, and caching.
 */

const DEFAULT_SERVER_URL = "http://localhost:8000";

// Ensure default settings exist in storage on install
chrome.runtime.onInstalled.addListener(async () => {
  const current = await chrome.storage.local.get(["serverUrl", "accessToken", "channelProfile"]);
  if (!current.serverUrl) {
    await chrome.storage.local.set({ serverUrl: DEFAULT_SERVER_URL });
  }
  console.log("VidIQ Pulse extension installed.");
});

// Update extension badge
async function updateBadge(text, color = "#6366F1") {
  try {
    await chrome.action.setBadgeText({ text: text ? String(text) : "" });
    if (text) {
      await chrome.action.setBadgeBackgroundColor({ color });
    }
  } catch (err) {
    console.warn("Could not set badge:", err);
  }
}

// Handle messages from content script or popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      if (message.type === "GET_AUTH_STATUS") {
        const data = await chrome.storage.local.get(["accessToken", "user", "serverUrl", "channelProfile"]);
        sendResponse({
          isAuthenticated: !!data.accessToken,
          user: data.user || null,
          serverUrl: data.serverUrl || DEFAULT_SERVER_URL,
          channelProfile: data.channelProfile || null,
        });
      } else if (message.type === "SET_BADGE") {
        await updateBadge(message.text, message.color);
        sendResponse({ success: true });
      } else if (message.type === "FETCH_API") {
        const { endpoint, method = "GET", body } = message;
        const storage = await chrome.storage.local.get(["serverUrl", "accessToken"]);
        const serverUrl = storage.serverUrl || DEFAULT_SERVER_URL;
        const token = storage.accessToken;

        const headers = {
          "Content-Type": "application/json",
        };
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const res = await fetch(`${serverUrl}${endpoint}`, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
        });

        if (!res.ok) {
          const errText = await res.text();
          sendResponse({ success: false, status: res.status, error: errText });
          return;
        }

        const data = await res.json();
        sendResponse({ success: true, data });
      } else {
        sendResponse({ error: "Unknown message type" });
      }
    } catch (err) {
      sendResponse({ success: false, error: err.message });
    }
  })();

  return true; // Keep channel open for async response
});
