// Dragonfly 3D World News by AI — 双语切换 + 关键词过滤
(function () {
  var root = document.documentElement;

  // 尽早应用保存的语言，避免闪烁（head 内联脚本已做首选设置，这里做兜底）
  function getLang() {
    return root.getAttribute("data-lang") === "en" ? "en" : "zh";
  }
  function setLang(lang) {
    root.setAttribute("data-lang", lang);
    root.setAttribute("lang", lang === "en" ? "en" : "zh-CN");
    try { localStorage.setItem("df-lang", lang); } catch (e) {}
    var btn = document.getElementById("langToggle");
    if (btn) btn.textContent = lang === "en" ? "中文" : "English";
    var filter = document.getElementById("filter");
    if (filter) filter.placeholder = lang === "en" ? "Filter by keyword…" : "关键词过滤…";
    document.title = lang === "en"
      ? (root.getAttribute("data-title-en") || document.title)
      : (root.getAttribute("data-title-zh") || document.title);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("langToggle");
    if (btn) {
      btn.addEventListener("click", function () {
        setLang(getLang() === "en" ? "zh" : "en");
      });
      // 初始化按钮文字
      setLang(getLang());
    }

    // 关键词过滤（同时搜中英文）
    var input = document.getElementById("filter");
    if (input) {
      var cards = Array.prototype.slice.call(document.querySelectorAll("article.card"));
      input.addEventListener("input", function () {
        var q = input.value.trim().toLowerCase();
        cards.forEach(function (c) {
          c.style.display = c.textContent.toLowerCase().indexOf(q) !== -1 ? "" : "none";
        });
      });
    }
  });
})();
