document.getElementById("send").addEventListener("click", () => {
  const result = document.getElementById("result");
  chrome.runtime.sendMessage({ type: "sendTab" }, (reply) => {
    if (chrome.runtime.lastError) {
      result.textContent = chrome.runtime.lastError.message;
      return;
    }
    result.textContent = reply && reply.ok ? "Sent." : "Not sent.";
  });
});
