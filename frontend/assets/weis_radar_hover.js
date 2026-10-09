// Sigma Radar: hovering a symbol row loads its chart (same as clicking it).
// Dash can't listen for hover natively, so one delegated listener forwards a
// short, deliberate hover (180 ms) to the row's existing click handler.
(function () {
  var timer = null, lastRow = null;
  function rowOf(t) {
    while (t && t !== document) {
      if (t.id && typeof t.id === 'string' && t.id.indexOf('weis-radar-row') !== -1) return t;
      t = t.parentNode;
    }
    return null;
  }
  document.addEventListener('mouseover', function (e) {
    var row = rowOf(e.target);
    if (!row || row === lastRow) return;
    clearTimeout(timer);
    timer = setTimeout(function () { lastRow = row; row.click(); }, 180);
  }, true);
  document.addEventListener('mouseout', function (e) {
    var row = rowOf(e.target);
    if (row && !row.contains(e.relatedTarget)) clearTimeout(timer);
  }, true);
})();
