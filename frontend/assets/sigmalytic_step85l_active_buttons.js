/* SIGMALYTIC STEP 85L
   Frontend-only UI fix:
   1. Prevents the first navigation tab, including Command Center, from being clipped.
   2. Adds visible active lighting for mutually exclusive tab/timeframe buttons.
   3. Stores the active visual state in sessionStorage so it survives Dash re-rendering.
*/

(function () {
  if (window.__SIGMALYTIC_STEP85L_UI_FIX_INSTALLED__) {
    return;
  }

  window.__SIGMALYTIC_STEP85L_UI_FIX_INSTALLED__ = true;

  const TAB_LABELS = [
    "Command Center",
    "Performance",
    "Behavioral Intelligence",
    "Campaigns",
    "Portfolio",
    "Journal",
    "Import History",
    "Radar Screen",
    "Scoreboard",
    "Divergence",
    "Billing",
    "Preferences",
    "Admin",
    "Setup"
  ];

  const TIMEFRAME_LABELS = ["1m", "5m", "15m", "1H", "1D", "1W"];

  const STORAGE_TAB = "sigmalytic.step85l.activeTab";
  const STORAGE_TF = "sigmalytic.step85l.activeTimeframe";

  function norm(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function visible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }

  function clickable(el) {
    if (!el || !visible(el)) return false;

    const tag = String(el.tagName || "").toLowerCase();
    const role = norm(el.getAttribute("role")).toLowerCase();
    const id = norm(el.id).toLowerCase();
    const cls = norm(el.className).toLowerCase();
    const style = window.getComputedStyle(el);

    return (
      tag === "button" ||
      tag === "a" ||
      role === "button" ||
      role === "tab" ||
      style.cursor === "pointer" ||
      /(^|[-_])btn($|[-_])/.test(id) ||
      /tab|button|timeframe|tf|nav/.test(id) ||
      /tab|button|timeframe|tf|nav/.test(cls)
    );
  }

  function allCandidateElements() {
    return Array.from(document.querySelectorAll("button, a, div, span, [role='button'], [role='tab']"))
      .filter(clickable);
  }

  function controlsForLabels(labels) {
    const wanted = new Set(labels.map(norm));
    return allCandidateElements().filter(function (el) {
      return wanted.has(norm(el.innerText || el.textContent));
    });
  }

  function addCandidateClasses() {
    controlsForLabels(TAB_LABELS).forEach(function (el) {
      el.classList.add("sig-step85l-control-candidate");
      el.classList.add("sig-step85l-tabs-candidate");
    });

    controlsForLabels(TIMEFRAME_LABELS).forEach(function (el) {
      el.classList.add("sig-step85l-control-candidate");
      el.classList.add("sig-step85l-timeframe-candidate");
    });
  }

  function findAncestorForNav(firstTab) {
    let node = firstTab;

    for (let depth = 0; node && depth < 8; depth += 1) {
      const txt = norm(node.innerText || node.textContent);
      const containsSeveralTabs =
        txt.includes("Command Center") &&
        txt.includes("Performance") &&
        txt.includes("Behavioral Intelligence");

      if (containsSeveralTabs) {
        return node;
      }

      node = node.parentElement;
    }

    return firstTab ? firstTab.parentElement : null;
  }

  function fixCommandCenterFraming() {
    const commandCenter = controlsForLabels(["Command Center"])[0];

    if (!commandCenter) {
      return;
    }

    const nav = findAncestorForNav(commandCenter);

    if (nav) {
      nav.classList.add("sig-step85l-nav-container");
      nav.style.marginLeft = "0px";
      nav.style.paddingLeft = "20px";
      nav.style.left = "0px";
      nav.style.transform = "none";
      nav.scrollLeft = 0;
    }

    let node = commandCenter.parentElement;
    for (let depth = 0; node && depth < 5; depth += 1) {
      const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
      if (rect && rect.left < 0) {
        node.style.marginLeft = "0px";
        node.style.left = "0px";
        node.style.transform = "none";
        node.style.paddingLeft = "20px";
        node.classList.add("sig-step85l-nav-container");
      }
      node = node.parentElement;
    }
  }

  function clearGroup(labels) {
    controlsForLabels(labels).forEach(function (el) {
      el.classList.remove("sig-active-control");
      el.setAttribute("aria-pressed", "false");
      el.setAttribute("aria-selected", "false");
    });
  }

  function setActive(labels, storageKey, label) {
    const cleanLabel = norm(label);
    if (!cleanLabel) return;

    clearGroup(labels);

    controlsForLabels(labels).forEach(function (el) {
      if (norm(el.innerText || el.textContent) === cleanLabel) {
        el.classList.add("sig-active-control");
        el.setAttribute("aria-pressed", "true");
        el.setAttribute("aria-selected", "true");
      }
    });

    try {
      window.sessionStorage.setItem(storageKey, cleanLabel);
    } catch (err) {
      /* no-op */
    }
  }

  function stored(storageKey, fallback) {
    try {
      return window.sessionStorage.getItem(storageKey) || fallback;
    } catch (err) {
      return fallback;
    }
  }

  function applyStoredState() {
    addCandidateClasses();

    const tab = stored(STORAGE_TAB, "");
    const tf = stored(STORAGE_TF, "");

    if (tab) {
      setActive(TAB_LABELS, STORAGE_TAB, tab);
    }

    if (tf) {
      setActive(TIMEFRAME_LABELS, STORAGE_TF, tf);
    }
  }

  function handleClick(event) {
    const target = event.target.closest("button, a, div, span, [role='button'], [role='tab']");
    if (!target) return;

    const label = norm(target.innerText || target.textContent);

    if (TAB_LABELS.includes(label)) {
      setActive(TAB_LABELS, STORAGE_TAB, label);
      setTimeout(fixCommandCenterFraming, 60);
      setTimeout(applyStoredState, 160);
      return;
    }

    if (TIMEFRAME_LABELS.includes(label)) {
      setActive(TIMEFRAME_LABELS, STORAGE_TF, label);
      setTimeout(applyStoredState, 80);
      return;
    }
  }

  function boot() {
    addCandidateClasses();
    fixCommandCenterFraming();

    if (!stored(STORAGE_TF, "")) {
      const visibleTf = controlsForLabels(TIMEFRAME_LABELS).find(function (el) {
        const bg = window.getComputedStyle(el).backgroundColor;
        return bg && bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent";
      });

      if (visibleTf) {
        setActive(TIMEFRAME_LABELS, STORAGE_TF, norm(visibleTf.innerText || visibleTf.textContent));
      }
    }

    applyStoredState();
  }

  document.addEventListener("click", handleClick, true);

  const observer = new MutationObserver(function () {
    window.clearTimeout(window.__SIGMALYTIC_STEP85L_MUTATION_TIMER__);
    window.__SIGMALYTIC_STEP85L_MUTATION_TIMER__ = window.setTimeout(function () {
      addCandidateClasses();
      fixCommandCenterFraming();
      applyStoredState();
    }, 80);
  });

  function startObserver() {
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      boot();
      startObserver();
    });
  } else {
    boot();
    startObserver();
  }

  window.setTimeout(boot, 500);
  window.setTimeout(boot, 1500);
})();
