// Sends the active tab to the phone via the native messaging host.
// Only http(s) is accepted here *and* on the receiving phone; nothing else is ever launched.

const HOST = "dev.continuity.handoff";

function notify(title, message) {
  chrome.notifications.create("", {
    type: "basic",
    iconUrl: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=",
    title,
    message
  });
}

function sendUrl(url, title) {
  if (!/^https?:\/\//i.test(url || "")) {
    notify("Continuity", "Only http(s) pages can be sent.");
    return;
  }
  chrome.runtime.sendNativeMessage(HOST, { url, title: title || "" }, (reply) => {
    if (chrome.runtime.lastError) {
      notify("Continuity", "Daemon/host unavailable: " + chrome.runtime.lastError.message);
      return;
    }
    if (reply && reply.ok) {
      notify("Continuity", "Sent to phone: " + url.slice(0, 80));
    } else {
      notify("Continuity", "Not sent: " + ((reply && reply.error) || "unknown error"));
    }
  });
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "continuity-send-tab",
    title: "Send tab to phone",
    contexts: ["page", "link"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const url = info.linkUrl || (tab && tab.url) || "";
  sendUrl(url, (tab && tab.title) || "");
});

chrome.action.onClicked.addListener((tab) => {
  if (tab) sendUrl(tab.url, tab.title);
});

chrome.runtime.onMessage.addListener((message, _sender, respond) => {
  if (message && message.type === "sendTab") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tab = tabs && tabs[0];
      if (!tab) {
        respond({ ok: false, error: "no active tab" });
        return;
      }
      sendUrl(tab.url, tab.title);
      respond({ ok: true });
    });
    return true;
  }
  return false;
});
