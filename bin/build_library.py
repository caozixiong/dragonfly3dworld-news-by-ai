#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the searchable Dragonfly paper/news library.

Reads data/news.json (maintained by the daily digest job) and generates:
  - data/library.json  (search index: entries + topic taxonomy)
  - library.html        (searchable, topic-filterable page)

Idempotent: entries are deduplicated by DOI/URL, so re-running with no new
digest items produces identical output. Safe to run after every daily digest.
"""
import json
import re
import html as htmlmod
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_JSON = ROOT / "data" / "news.json"
LIB_JSON = ROOT / "data" / "library.json"
LIB_HTML = ROOT / "library.html"

# Stable topic taxonomy: (key, zh label, en label, zh keywords, en keywords)
TOPICS = [
    ("life-sciences", "生命科学", "Life Sciences",
     ["生命科学", "珊瑚", "骨科", "骨骼", "病毒", "寄生虫", "形态学", "牙科",
      "根管", "肝纤维化", "卵母细胞", "显微成像", "灵长类", "组织学", "生物材料"],
     ["life science", "coral", "octocoral", "orthoped", "bone", "virus",
      "parasite", "morphology", "dental", "oocyte", "microscopy", "primate",
      "histology", "biological"]),
    ("materials-manufacturing", "材料与制造", "Materials & Manufacturing",
     ["增材制造", "电池", "铸件", "孔隙", "打印", "金属", "材料", "电极"],
     ["additive manufacturing", "battery", "casting", "porosity", "pore",
      "3d print", "metal", "manufacturing", "material", "electrode"]),
    ("geoscience-archaeology", "地球科学与考古", "Geoscience & Archaeology",
     ["地质", "考古", "古生物", "岩石", "沉积", "化石"],
     ["geolog", "archaeolog", "fossil", "paleontolog", "sediment", "rock"]),
    ("ai-deep-learning", "AI 与深度学习", "AI & Deep Learning",
     ["深度学习", "人工智能", "实例分割", "机器学习", "神经网络", "标注", "一键分割"],
     ["deep learning", "machine learning", "artificial intelligence", "sam",
      "cellpose", "instance segmentation", "neural network", "annotation"]),
    ("metrology-inspection", "计量与检测", "Metrology & Inspection",
     ["计量", "检测", "无损", "粗糙度", "汽车", "航空航天", "cad对比"],
     ["metrology", "inspection", "nondestructive", "non-destructive",
      "roughness", "automotive", "aerospace", "ndt", "cad comparison"]),
    ("releases-features", "版本与功能", "Releases & Features",
     ["2027", "2025", "2024", "新版", "功能", "发布", "更新", "网格", "报告", "查看器"],
     ["2027", "2025", "2024", "release", "version", "feature", "update",
      "mesh", "report builder", "viewer", "whats new"]),
    ("official", "官方动态", "Official Updates",
     ["官方", "会议", "研讨会", "用户故事", "访谈", "活动", "峰会"],
     ["official", "conference", "webinar", "event", "summit", "interview",
      "user story", "m&m"]),
]
FALLBACK_TOPIC = ("other", "其他", "Other")


def norm_en(text: str) -> str:
    text = text.lower().replace("'", "").replace("’", "")
    return re.sub(r"\s+", " ", text)


def tag_topics(item: dict) -> list:
    zh_text = " ".join(str(item.get(k, "") or "") for k in
                       ("title", "summary", "source", "category")) + \
              " " + " ".join(item.get("tags", []) or [])
    en_text = norm_en(" ".join(str(item.get(k, "") or "") for k in
                               ("title_en", "summary_en", "source_en", "category_en")) +
                      " " + " ".join(item.get("tags_en", []) or []))
    matched = []
    for key, zh, en, zh_keys, en_keys in TOPICS:
        hit = any(k in zh_text for k in zh_keys)
        if not hit:
            for k in en_keys:
                if re.search(r"\b" + re.escape(k) + r"\b", en_text):
                    hit = True
                    break
        if hit:
            matched.append({"key": key, "zh": zh, "en": en})
    if not matched:
        k, zh, en = FALLBACK_TOPIC
        matched.append({"key": k, "zh": zh, "en": en})
    return matched


def entry_key(item: dict) -> str:
    doi = (item.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    url = (item.get("url") or "").strip().rstrip("/")
    return "url:" + url.lower()


def build_entries(days: list) -> list:
    seen = {}
    for day in days:
        digest_date = day.get("date", "")
        digest_page = day.get("page") or f"news/{digest_date}.html"
        for it in day.get("items") or []:
            key = entry_key(it)
            if key in seen:
                continue
            seen[key] = {
                "id": key,
                "title": it.get("title", ""),
                "title_en": it.get("title_en", "") or it.get("title", ""),
                "summary": it.get("summary", ""),
                "summary_en": it.get("summary_en", "") or it.get("summary", ""),
                "url": it.get("url", ""),
                "doi": it.get("doi", ""),
                "date": it.get("date", ""),
                "digest_date": digest_date,
                "digest_page": digest_page,
                "source": it.get("source", ""),
                "source_en": it.get("source_en", "") or it.get("source", ""),
                "category": it.get("category", ""),
                "category_en": it.get("category_en", "") or it.get("category", ""),
                "tags": it.get("tags", []) or [],
                "tags_en": it.get("tags_en", []) or it.get("tags", []) or [],
                "topics": tag_topics(it),
            }
    entries = list(seen.values())
    entries.sort(key=lambda e: (e["digest_date"], e["date"]), reverse=True)
    return entries


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN" data-lang="zh" data-title-zh="论文资料库｜Dragonfly 3D World News" data-title-en="Paper Library | Dragonfly 3D World News">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>论文资料库｜Dragonfly 3D World News</title>
  <link rel="stylesheet" href="assets/css/style.css">
  <script>
    try {
      var l = localStorage.getItem("df-lang");
      if (l === "en" || l === "zh") {
        document.documentElement.setAttribute("data-lang", l);
        document.documentElement.setAttribute("lang", l === "en" ? "en" : "zh-CN");
      }
    } catch (e) {}
  </script>
  <style>
    #q {
      margin-top: 10px; padding: 8px 12px; width: 100%; max-width: 420px;
      border: 1px solid var(--border); border-radius: 8px;
      background: var(--surface); color: var(--text); font-size: .95rem;
    }
    .chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 4px; }
    .chip {
      font-size: .8rem; padding: 4px 14px; border-radius: 999px;
      border: 1px solid var(--border); background: var(--surface);
      color: var(--muted); cursor: pointer; font-family: inherit;
    }
    .chip:hover { border-color: var(--accent); }
    .chip.active {
      background: var(--accent-soft); color: var(--accent);
      border-color: var(--accent); font-weight: 600;
    }
    .lib-links { margin-top: 10px; font-size: .85rem; }
    .lib-links a { margin-right: 16px; }
    #countLine { margin-top: 8px; }
    .empty { color: var(--muted); padding: 32px 0; text-align: center; }
  </style>
</head>
<body>
<div class="container">
  <header class="site">
    <button id="langToggle" class="lang-toggle" aria-label="Switch language">English</button>
    <h1><a href="index.html">Dragonfly 3D World News</a></h1>
    <p>
      <span class="t-zh">论文与新闻资料库：搜索全部历史收录，按主题筛选</span>
      <span class="t-en">Paper &amp; news library: search everything ever collected, filter by topic</span>
    </p>
  </header>

  <div class="daily-head">
    <h2><span class="t-zh">📚 论文资料库</span><span class="t-en">📚 Paper Library</span></h2>
    <p id="countLine"></p>
    <p><input id="q" type="search" autocomplete="off"></p>
    <div id="topics" class="chip-row"></div>
  </div>

  <div id="results"></div>

  <footer class="site">
    <p><span class="t-zh">仅供学习参考。原文版权归各自来源所有。</span><span class="t-en">For reference only. All rights belong to the respective sources.</span></p>
    <p><a href="index.html"><span class="t-zh">← 返回首页</span><span class="t-en">← Back to home</span></a></p>
  </footer>
</div>
<script src="assets/js/app.js"></script>
<script src="assets/js/library.js"></script>
<script>
(function () {
  var DATA_URL = "data/library.json";
  var data = null;
  var state = { q: "", topic: "all" };

  function lang() {
    return document.documentElement.getAttribute("data-lang") === "en" ? "en" : "zh";
  }
  function t(zh, en) { return lang() === "en" ? en : zh; }

  function renderChips() {
    var box = document.getElementById("topics");
    box.innerHTML = "";
    var all = [{ key: "all", zh: "全部", en: "All" }].concat(data.topics);
    all.forEach(function (tp) {
      var b = document.createElement("button");
      b.className = "chip" + (state.topic === tp.key ? " active" : "");
      b.textContent = t(tp.zh, tp.en);
      b.addEventListener("click", function () {
        state.topic = tp.key;
        renderChips();
        render();
      });
      box.appendChild(b);
    });
  }

  function render() {
    var items = LibraryFilter.filterItems(data.entries, state.q, state.topic, lang());
    var box = document.getElementById("results");
    var count = document.getElementById("countLine");
    count.innerHTML = t(
      "共收录 " + data.count + " 条" + (items.length !== data.count ? "，当前筛选出 " + items.length + " 条" : ""),
      data.count + " items indexed" + (items.length !== data.count ? ", " + items.length + " shown" : "")
    );
    if (!items.length) {
      box.innerHTML = '<div class="empty">' + t("没有匹配的结果，换个关键词或主题试试。", "No matches — try another keyword or topic.") + "</div>";
      return;
    }
    box.innerHTML = items.map(function (e) { return LibraryFilter.cardHtml(e, lang()); }).join("");
  }

  function boot() {
    document.getElementById("q").placeholder = t("搜索标题、摘要、标签…", "Search titles, summaries, tags…");
    document.getElementById("q").addEventListener("input", function (ev) {
      state.q = ev.target.value;
      render();
    });
    document.getElementById("langToggle").addEventListener("click", function () {
      // app.js 切换语言后重渲染
      setTimeout(function () {
        document.getElementById("q").placeholder = t("搜索标题、摘要、标签…", "Search titles, summaries, tags…");
        renderChips();
        render();
      }, 0);
    });
    renderChips();
    render();
  }

  fetch(DATA_URL)
    .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
    .then(function (j) { data = j; boot(); })
    .catch(function () {
      document.getElementById("results").innerHTML =
        '<div class="empty">资料库数据加载失败，请稍后重试。</div>';
    });
})();
</script>
</body>
</html>
"""


def main() -> None:
    news = json.loads(NEWS_JSON.read_text(encoding="utf-8"))
    days = news.get("days", [])
    entries = build_entries(days)
    from collections import Counter
    counts = Counter()
    for e in entries:
        for t in e["topics"]:
            counts[t["key"]] += 1
    topics = [{"key": k, "zh": zh, "en": en} for k, zh, en, _, _ in TOPICS
              if counts.get(k)]
    if counts.get(FALLBACK_TOPIC[0]):
        topics.append({"key": FALLBACK_TOPIC[0], "zh": FALLBACK_TOPIC[1], "en": FALLBACK_TOPIC[2]})

    payload = {
        "updated": news.get("updated", ""),
        "site": news.get("site", "Dragonfly 3D World News"),
        "count": len(entries),
        "topics": topics,
        "entries": entries,
    }
    LIB_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    LIB_HTML.write_text(HTML_TEMPLATE, encoding="utf-8")
    print(f"library: {len(entries)} entries from {len(days)} digest days -> "
          f"{LIB_JSON.name}, {LIB_HTML.name}")


if __name__ == "__main__":
    main()
