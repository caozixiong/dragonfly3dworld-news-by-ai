# Dragonfly 3D World News by AI

关于 Dragonfly 3D World（三维图像处理与分析软件）的新闻与学术动态，由 AI 每天自动搜集并整理成中文摘要，发布到 GitHub Pages。

- 🌐 在线地址：https://caozixiong.github.io/dragonfly3dworld-news-by-ai/
- 🤖 更新方式：每天定时任务自动搜索、生成中文摘要、推送到 `main` 分支，Pages 自动发布

## 目录结构

```
dragonfly3dworld-news-by-ai/
├── index.html             ← 首页（含归档列表）
├── news/
│   ├── 2026-09-23.html    ← 每日速览页
│   └── ...
├── data/
│   └── news.json          ← 结构化新闻数据（供去重与检索）
└── assets/
    ├── css/style.css
    └── js/app.js
```

## 数据来源

- Dragonfly 官方博客与官网（dragonfly.comet.tech）
- 行业媒体：Metal AM、Metrology News、AZoM 等
- 学术出版物中提及 Dragonfly 3D World 的论文

## 学术检索脚本

`bin/paper_search.py` 聚合 6 个免费学术 API 定向检索提及 Dragonfly 3D World 的论文（无需 key）：

| 数据源 | 特点 |
|---|---|
| arXiv | 预印本，全字段短语检索 |
| OpenAlex | 跨出版社元数据 |
| Crossref | 出版商元数据 |
| Semantic Scholar | 标题/摘要检索 |
| Europe PMC | 开放获取全文检索（能抓到方法章节的提及），含 PubMed 与 bioRxiv/medRxiv |
| OpenAIRE | 欧洲开放获取聚合 |

用法：`python3 bin/paper_search.py --since 2026-08-24 --out results.json`
脚本自带跨源去重（DOI/标题）、噪音过滤（排除蜻蜓昆虫、dragonfly 算法等）与失败重试，单个源失败不影响其他源。
