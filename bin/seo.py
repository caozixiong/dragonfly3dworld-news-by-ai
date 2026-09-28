#!/usr/bin/env python3
"""给 dragonfly-news GitHub Pages 站点做 SEO：注入 head 标签、生成 robots.txt 和 sitemap.xml。

幂等：已含 <meta name="description"> 的页面会跳过注入。
用法：
  python3 bin/seo.py            # 全部：注入所有页面 + robots.txt + sitemap.xml
"""
import html
import json
import os
import re

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_BASE = "https://caozixiong.github.io/dragonfly3dworld-news-by-ai/"
SITE_NAME = "Dragonfly 3D World News"
KEYWORDS = ("Dragonfly 3D World,Dragonfly,三维图像处理,CT 图像分析,micro-CT,"
            "显微 CT,工业 CT,论文,学术动态,3D image analysis")

INDEX_DESC = ("Dragonfly 3D World 新闻与学术动态，每日中英双语速览："
              "Dragonfly 官方博客、行业媒体与学术论文中提及 Dragonfly 3D World 的内容，"
              "附可搜索论文资料库与中文播客。")
LIBRARY_DESC = ("可搜索的 Dragonfly 3D World 论文资料库：收录全部历史学术论文，"
                "支持中英文关键词搜索与六类主题筛选，每条附原文与日报链接。")


def esc(s):
    return html.escape(s or "", quote=True)


def head_block(*, title, desc, url, og_type="website", published=None, jsonld_extra=""):
    lines = [
        f'  <meta name="description" content="{esc(desc)}">',
        f'  <meta name="keywords" content="{esc(KEYWORDS)}">',
        f'  <link rel="canonical" href="{esc(url)}">',
        f'  <meta property="og:site_name" content="{esc(SITE_NAME)}">',
        f'  <meta property="og:title" content="{esc(title)}">',
        f'  <meta property="og:description" content="{esc(desc)}">',
        f'  <meta property="og:type" content="{og_type}">',
        f'  <meta property="og:url" content="{esc(url)}">',
        '  <meta property="og:locale" content="zh_CN">',
        '  <meta name="twitter:card" content="summary">',
        f'  <meta name="twitter:title" content="{esc(title)}">',
        f'  <meta name="twitter:description" content="{esc(desc)}">',
    ]
    if published:
        lines.append(f'  <meta property="article:published_time" content="{published}">')
    jsonld = ('  <script type="application/ld+json">\n'
              f'  {{"@context":"https://schema.org",{jsonld_extra}}}\n'
              '  </script>')
    lines.append(jsonld)
    return "\n".join(lines)


def inject(path, block):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if 'name="description"' in content:
        return False  # 已注入，跳过
    new = content.replace("</head>", block + "\n</head>", 1)
    if new == content:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return True


def zh_date(date_str):
    y, m, d = date_str.split("-")
    return f"{y}年{int(m)}月{int(d)}日"


def main():
    changed = []

    # 首页
    p = os.path.join(WORKDIR, "index.html")
    block = head_block(
        title=SITE_NAME, desc=INDEX_DESC, url=SITE_BASE,
        jsonld_extra=f'"@type":"WebSite","name":"{SITE_NAME}","url":"{SITE_BASE}",'
                     f'"inLanguage":"zh-CN","description":"{esc(INDEX_DESC)}"')
    if inject(p, block):
        changed.append("index.html")

    # 资料库
    p = os.path.join(WORKDIR, "library.html")
    if os.path.exists(p):
        block = head_block(
            title=f"论文资料库｜{SITE_NAME}", desc=LIBRARY_DESC,
            url=SITE_BASE + "library.html",
            jsonld_extra=f'"@type":"CollectionPage","name":"论文资料库｜{SITE_NAME}",'
                         f'"url":"{SITE_BASE}library.html","inLanguage":"zh-CN",'
                         f'"description":"{esc(LIBRARY_DESC)}"')
        if inject(p, block):
            changed.append("library.html")

    # 日报页：描述取自当天条目标题
    news_json = os.path.join(WORKDIR, "data", "news.json")
    days = []
    if os.path.exists(news_json):
        with open(news_json, encoding="utf-8") as f:
            days = json.load(f).get("days", [])
    for day in days:
        date = day.get("date", "")
        page = day.get("page") or f"news/{date}.html"
        p = os.path.join(WORKDIR, page)
        if not os.path.exists(p):
            continue
        titles = [it.get("title", "") for it in day.get("items", []) if it.get("title")]
        if titles:
            desc = f"{zh_date(date)} Dragonfly 3D World 日报（{len(titles)}条）：{'；'.join(titles)}"
        else:
            desc = f"{zh_date(date)} Dragonfly 3D World 日报：今日无新增收录。"
        if len(desc) > 160:
            desc = desc[:157] + "…"
        title = f"{date} 日报｜{SITE_NAME}"
        url = SITE_BASE + page
        block = head_block(
            title=title, desc=desc, url=url, og_type="article",
            published=f"{date}T09:39:00+08:00",
            jsonld_extra=f'"@type":"NewsArticle","headline":"{esc(title)}",'
                         f'"url":"{esc(url)}","datePublished":"{date}",'
                         f'"inLanguage":"zh-CN","description":"{esc(desc)}",'
                         f'"author":{{"@type":"Organization","name":"{SITE_NAME}"}}')
        if inject(p, block):
            changed.append(page)

    # robots.txt
    robots = os.path.join(WORKDIR, "robots.txt")
    if not os.path.exists(robots):
        with open(robots, "w", encoding="utf-8") as f:
            f.write("User-agent: *\nAllow: /\n\n"
                    f"Sitemap: {SITE_BASE}sitemap.xml\n")
        changed.append("robots.txt")

    # sitemap.xml（每次全量重建）
    entries = []
    entries.append(f"  <url><loc>{SITE_BASE}</loc></url>")
    if os.path.exists(os.path.join(WORKDIR, "library.html")):
        entries.append(f"  <url><loc>{SITE_BASE}library.html</loc></url>")
    for day in days:
        date = day.get("date", "")
        page = day.get("page") or f"news/{date}.html"
        if os.path.exists(os.path.join(WORKDIR, page)):
            entries.append(
                f"  <url><loc>{SITE_BASE}{page}</loc>"
                f"<lastmod>{date}</lastmod></url>")
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "\n".join(entries) +
               '\n</urlset>\n')
    with open(os.path.join(WORKDIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)
    changed.append("sitemap.xml")

    print("SEO done. changed:", ", ".join(changed) if changed else "(none)")


if __name__ == "__main__":
    main()
