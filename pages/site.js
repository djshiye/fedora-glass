// Fedora Glass project page: copy buttons on the install blocks, and no moving demo
// for people who asked their system for less motion. Nothing is sent anywhere.
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  for (const pre of document.querySelectorAll("pre[data-copy]")) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.addEventListener("click", async () => {
      const text = pre.querySelector("code").textContent;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
        button.classList.add("done");
      } catch {
        // No clipboard access: select the block so Ctrl+C works.
        const range = document.createRange();
        range.selectNodeContents(pre.querySelector("code"));
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        button.textContent = "Press Ctrl+C";
      }
      setTimeout(() => { button.textContent = "Copy"; button.classList.remove("done"); }, 2000);
    });
    const wrap = document.createElement("div");
    wrap.className = "code-wrap";
    pre.replaceWith(wrap);
    wrap.append(pre, button);
  }

  const video = document.querySelector("video.demo");
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (video && calm.matches) {
    video.removeAttribute("autoplay");
    video.pause();
  } else if (video && video.paused) {
    // Some browsers hold back autoplay until asked again; it is muted, so this is allowed.
    video.play().catch(() => {});
  }
});
