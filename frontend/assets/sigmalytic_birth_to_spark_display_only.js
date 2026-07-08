/*
Sigmalytic V2 frontend display-only terminology adapter.
Purpose:
- Replace visible user-facing text "BIRTH" with "SPARK".
- Preserve internal engine/database/API state values.
- Do not mutate backend data.
- Do not write to Supabase.
- Do not confirm operator control.
- Do not authorize D3D.
- Do not change scores, ranks, probabilities, edge, or campaign states.
This is intentionally DOM-display-only because Dash may render some table cells
from raw internal state values after Python callbacks complete.
*/
(function () {
  "use strict";
  const DISPLAY_REPLACEMENTS = [
    [/\bBIRTH\b/g, "SPARK"],
    [/\bBirth\b/g, "Spark"],
    [/\bbirth\b/g, "spark"]
  ];
  const SKIP_TAGS = new Set([
    "SCRIPT",
    "STYLE",
    "TEXTAREA",
    "INPUT",
    "CODE",
    "PRE",
    "NOSCRIPT"
  ]);
  function convertText(value) {
    let next = value;
    for (const pair of DISPLAY_REPLACEMENTS) {
      next = next.replace(pair[0], pair[1]);
    }
    return next;
  }
  function shouldSkipNode(node) {
    if (!node) {
      return true;
    }
    const parent = node.parentElement;
    if (!parent) {
      return true;
    }
    return SKIP_TAGS.has(parent.tagName);
  }
  function convertTextNode(node) {
    if (shouldSkipNode(node)) {
      return;
    }
    const before = node.nodeValue;
    if (!before) {
      return;
    }
    const after = convertText(before);
    if (after !== before) {
      node.nodeValue = after;
    }
  }
  function walkAndConvert(root) {
    if (!root) {
      return;
    }
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function (node) {
          return shouldSkipNode(node)
            ? NodeFilter.FILTER_REJECT
            : NodeFilter.FILTER_ACCEPT;
        }
      }
    );
    const nodes = [];
    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }
    for (const node of nodes) {
      convertTextNode(node);
    }
  }
  function runDisplayAdapter() {
    walkAndConvert(document.body);
  }
  function startObserver() {
    runDisplayAdapter();
    const observer = new MutationObserver(function (mutations) {
      for (const mutation of mutations) {
        if (mutation.type === "characterData") {
          convertTextNode(mutation.target);
        }
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.TEXT_NODE) {
            convertTextNode(node);
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            walkAndConvert(node);
          }
        }
      }
    });
    observer.observe(document.body, {
      childList: true,
      characterData: true,
      subtree: true
    });
    window.__sigmalyticBirthToSparkDisplayOnlyObserver = observer;
    window.setTimeout(runDisplayAdapter, 250);
    window.setTimeout(runDisplayAdapter, 1000);
    window.setTimeout(runDisplayAdapter, 2500);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObserver);
  } else {
    startObserver();
  }
})();
