// Dragonfly 3D World News — 资料库搜索与主题筛选
// Pure, testable logic: filterItems(entries, query, topicKey, lang) -> sorted entries
// and cardHtml(entry, lang) -> HTML string.
var LibraryFilter = (function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hasCjk(q) {
    return /[\u4e00-\u9fff]/.test(q);
  }

  // Score how well an entry matches the query. Matches in the query's own
  // language weigh more; the other language still matches with less weight.
  function matchScore(e, q, lang) {
    q = q.trim().toLowerCase();
    if (!q) return 1;
    var qIsZh = hasCjk(q) || lang === "zh";
    var zhText = [e.title, e.summary, e.source, e.category]
      .concat(e.tags || []).join(" ").toLowerCase();
    var enText = [e.title_en, e.summary_en, e.source_en, e.category_en]
      .concat(e.tags_en || []).join(" ").toLowerCase();
    var zhHit = zhText.indexOf(q) !== -1;
    var enHit = enText.indexOf(q) !== -1;
    if (!zhHit && !enHit) return 0;
    var score = 0;
    if (qIsZh) {
      if (zhHit) score += 2;
      if (enHit) score += 1;
    } else {
      if (enHit) score += 2;
      if (zhHit) score += 1;
    }
    return score;
  }

  function topicHit(e, topicKey) {
    if (!topicKey || topicKey === "all") return true;
    return (e.topics || []).some(function (t) { return t.key === topicKey; });
  }

  function filterItems(entries, query, topicKey, lang) {
    var out = [];
    (entries || []).forEach(function (e) {
      if (!topicHit(e, topicKey)) return;
      var s = matchScore(e, query || "", lang || "zh");
      if (s > 0) out.push({ e: e, s: s });
    });
    out.sort(function (a, b) {
      if (b.s !== a.s) return b.s - a.s;
      if (b.e.digest_date !== a.e.digest_date)
        return b.e.digest_date < a.e.digest_date ? -1 : 1;
      if (b.e.date !== a.e.date) return b.e.date < a.e.date ? -1 : 1;
      return 0;
    });
    return out.map(function (x) { return x.e; });
  }

  function pick(e, zhKey, enKey, lang) {
    var v = lang === "en" ? e[enKey] : e[zhKey];
    return v || e[zhKey] || "";
  }

  function cardHtml(e, lang) {
    var title = pick(e, "title", "title_en", lang);
    var summary = pick(e, "summary", "summary_en", lang);
    var source = pick(e, "source", "source_en", lang);
    var category = pick(e, "category", "category_en", lang);
    var tags = lang === "en" ? (e.tags_en || e.tags || []) : (e.tags || []);
    var topicLabels = (e.topics || []).map(function (t) {
      return lang === "en" ? t.en : t.zh;
    });
    var tagHtml = topicLabels.concat(tags).map(function (tg) {
      return '<span class="tag">' + esc(tg) + "</span>";
    }).join("");
    var origLabel = lang === "en" ? "🔗 Original article" : "🔗 原文";
    var digestLabel = lang === "en"
      ? "📰 Digest of " + esc(e.digest_date)
      : "📰 " + esc(e.digest_date) + " 日报";
    return (
      '<article class="card">' +
      '<h2><a href="' + esc(e.url) + '" target="_blank" rel="noopener">' + esc(title) + "</a></h2>" +
      '<div class="meta"><span>' + esc(source) + "</span><span>" + esc(e.date) + "</span><span>" +
      esc(category) + "</span></div>" +
      '<div class="summary"><p>' + esc(summary) + "</p></div>" +
      '<div class="tags">' + tagHtml + "</div>" +
      '<div class="lib-links"><a href="' + esc(e.url) + '" target="_blank" rel="noopener">' +
      origLabel + '</a><a href="' + esc(e.digest_page) + '">' + digestLabel + "</a></div>" +
      "</article>"
    );
  }

  // Node.js export for testing; harmless in browsers.
  var api = {
    esc: esc,
    matchScore: matchScore,
    topicHit: topicHit,
    filterItems: filterItems,
    cardHtml: cardHtml
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  return api;
})();
