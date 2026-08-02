// Sigmalytic Quant Corporation -- PWA service worker
// Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
//
// Deliberately minimal and network-only: this app shows live prices,
// live campaign data, and other time-sensitive financial information.
// Caching any of that offline risks showing someone stale, misleading
// data without any indication it's stale. This service worker exists
// only to satisfy PWA installability requirements (a registered
// service worker is required for "Add to Home Screen" on most
// browsers) -- it does not intercept or cache any network requests.

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// No "fetch" event listener -- all requests pass straight through to
// the network exactly as if no service worker were present.
