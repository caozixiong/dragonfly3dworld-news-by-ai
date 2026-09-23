#!/usr/bin/env python3
"""定向检索提及 Dragonfly 3D World 的学术论文（免费 API 聚合，无需 key）。

数据源：
  1. arXiv API            — 预印本，全字段检索
  2. OpenAlex             — 跨出版社元数据（标题/摘要）
  3. Crossref             — 出版商元数据
  4. Semantic Scholar     — 标题/摘要检索
  5. Europe PMC           — 支持开放获取全文检索（能抓到"方法"章节里的提及），含 PubMed
  6. OpenAIRE             — 欧洲开放获取聚合（best effort）

用法：
    paper_search.py --since 2026-08-24 [--out results.json]

输出 JSON 数组，每项：
    {title, authors, date, doi, url, abstract, venue, source_db}
按日期倒序，已按 DOI/标题去重。
"""
import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

QUERY = "Dragonfly 3D World"
QUERY_VARIANTS = ["Dragonfly 3D World", "ORS Dragonfly"]
UA = {"User-Agent": "DragonflyNewsBot/1.0 (academic digest; contact: digest bot)"}


def http_get(url, timeout=30, retries=4):
    """带指数退避重试的 GET，应对 429/5xx/连接中断；429 时尊重 Retry-After。"""
    import time, urllib.error
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code and e.code < 500 and e.code != 429:
                raise
            wait = 2 ** attempt * 3
            if e.code == 429:
                ra = e.headers.get("Retry-After")
                if ra and ra.isdigit():
                    wait = min(int(ra) + 2, 60)
            time.sleep(wait)
        except Exception as e:
            last = e
            time.sleep(2 ** attempt * 2)
    raise last


SOFTWARE_RE = re.compile(
    r"dragonfly[^.\n]{0,40}3d world"      # Dragonfly 3D World / Dragonfly (3D World)
    r"|ors[-\s]?dragonfly"                 # ORS Dragonfly
    r"|dragonfly[^.\n]{0,40}comet"         # Dragonfly … Comet (Yxlon)
    r"|object research systems",          # 开发商原名
    re.IGNORECASE,
)


def mentions_software(item):
    """过滤掉蜻蜓昆虫、dragonfly 算法等噪音，只保留真正提到该软件的条目。"""
    text = " ".join([item.get("title", ""), item.get("abstract", ""),
                     item.get("venue", "")])
    return bool(SOFTWARE_RE.search(text))


def norm_doi(doi):
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def norm_title(t):
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def fetch_arxiv(since):
    """arXiv: search_query 全字段，按提交日期倒序，客户端按日期过滤。"""
    out = []
    q = " OR ".join(f'all:"{v}"' for v in QUERY_VARIANTS)
    params = urllib.parse.urlencode({
        "search_query": q,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": 100,
    })
    data = http_get("http://export.arxiv.org/api/query?" + params)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in ET.fromstring(data).findall("a:entry", ns):
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        published = (e.findtext("a:published", default="", namespaces=ns) or "")[:10]
        if published < since:
            continue
        authors = [a.findtext("a:name", default="", namespaces=ns)
                   for a in e.findall("a:author", ns)]
        link = ""
        for l in e.findall("a:link", ns):
            if l.get("rel") == "alternate":
                link = l.get("href", "")
        doi = (e.findtext("a:doi", default="", namespaces=ns) or "").strip()
        out.append({
            "title": re.sub(r"\s+", " ", title),
            "authors": ", ".join(a for a in authors if a)[:300],
            "date": published,
            "doi": norm_doi(doi),
            "url": link or (f"https://doi.org/{doi}" if doi else ""),
            "abstract": re.sub(r"\s+", " ", e.findtext("a:summary", default="", namespaces=ns) or "").strip()[:600],
            "venue": "arXiv",
            "source_db": "arXiv",
            "phrase_confirmed": True,
        })
    return out


def fetch_openalex(since):
    params = urllib.parse.urlencode({
        "search": QUERY,
        "filter": f"from_publication_date:{since}",
        "per-page": 50,
        "select": "title,publication_date,doi,authorships,primary_location,abstract_inverted_index",
    })
    data = json.loads(http_get("https://api.openalex.org/works?" + params))
    out = []
    for w in data.get("results", []):
        inv = w.get("abstract_inverted_index") or {}
        abstract = ""
        if inv:
            pos = {}
            for word, idxs in inv.items():
                for i in idxs:
                    pos[i] = word
            abstract = " ".join(pos[i] for i in sorted(pos))[:600]
        authors = ", ".join(
            (a.get("author") or {}).get("display_name", "")
            for a in w.get("authorships", [])[:6]
        )
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        out.append({
            "title": w.get("title", ""),
            "authors": authors,
            "date": (w.get("publication_date") or "")[:10],
            "doi": norm_doi(w.get("doi")),
            "url": (w.get("doi") or loc.get("landing_page_url") or ""),
            "abstract": abstract,
            "venue": src.get("display_name", ""),
            "source_db": "OpenAlex",
        })
    return out


def fetch_crossref(since):
    params = urllib.parse.urlencode({
        "query": QUERY,
        "filter": f"from-pub-date:{since}",
        "rows": 50,
        "select": "title,author,published,DOI,URL,abstract,container-title",
    })
    data = json.loads(http_get("https://api.crossref.org/works?" + params))
    out = []
    for w in data.get("message", {}).get("items", []):
        pub = w.get("published") or w.get("created") or {}
        parts = pub.get("date-parts", [[]])[0]
        date = "-".join(f"{p:02d}" for p in parts[:3]) if parts else ""
        authors = ", ".join(
            " ".join(x for x in (a.get("given", ""), a.get("family", "")) if x)
            for a in w.get("author", [])[:6]
        )
        titles = w.get("title") or []
        containers = w.get("container-title") or []
        out.append({
            "title": titles[0] if titles else "",
            "authors": authors,
            "date": date,
            "doi": norm_doi(w.get("DOI")),
            "url": w.get("URL", ""),
            "abstract": re.sub(r"<[^>]+>", "", w.get("abstract", "") or "")[:600],
            "venue": containers[0] if containers else "",
            "source_db": "Crossref",
        })
    return out


def fetch_semanticscholar(since):
    params = urllib.parse.urlencode({
        "query": QUERY,
        "fields": "title,authors,year,abstract,url,openAccessPdf,externalIds,publicationDate,venue",
        "limit": 50,
    })
    data = json.loads(http_get(
        "https://api.semanticscholar.org/graph/v1/paper/search?" + params))
    out = []
    for p in data.get("data", []):
        pubdate = p.get("publicationDate") or ""
        if pubdate and pubdate[:10] < since:
            continue
        ext = p.get("externalIds") or {}
        doi = norm_doi(ext.get("DOI"))
        pdf = p.get("openAccessPdf") or {}
        out.append({
            "title": p.get("title", ""),
            "authors": ", ".join(a.get("name", "")
                                 for a in (p.get("authors") or [])[:6]),
            "date": pubdate[:10] or str(p.get("year") or ""),
            "doi": doi,
            "url": p.get("url") or pdf.get("url") or (f"https://doi.org/{doi}" if doi else ""),
            "abstract": (p.get("abstract") or "")[:600],
            "venue": p.get("venue", ""),
            "source_db": "SemanticScholar",
        })
    return out


def fetch_europepmc(since):
    """Europe PMC 全文检索（含 PubMed/MEDLINE + bioRxiv/medRxiv）。
    注意：FIRST_PDATE 日期过滤在服务端不稳定，改为客户端按 firstPublicationDate 过滤。"""
    params = urllib.parse.urlencode({
        "query": f'"{QUERY}"',
        "format": "json",
        "pageSize": 100,
        "resultType": "core",
    })
    data = json.loads(http_get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + params))
    out = []
    for r in data.get("resultList", {}).get("result", []):
        pubdate = (r.get("firstPublicationDate") or "")[:10]
        if pubdate and pubdate < since:
            continue
        doi = norm_doi(r.get("doi"))
        out.append({
            "title": r.get("title", ""),
            "authors": r.get("authorString", "")[:300],
            "date": pubdate,
            "doi": doi,
            "url": (f"https://doi.org/{doi}" if doi
                    else f"https://europepmc.org/article/{r.get('source', '')}/{r.get('id', '')}"),
            "abstract": (r.get("abstractText") or "")[:600],
            "venue": r.get("journalTitle", "") or r.get("bookOrReportDetails", ""),
            "source_db": "EuropePMC",
            "phrase_confirmed": True,
        })
    return out


def fetch_openaire(since):
    params = urllib.parse.urlencode({
        "format": "json",
        "size": 50,
        "title": QUERY,
    })
    data = json.loads(http_get(
        "https://api.openaire.eu/search/publications?" + params))
    out = []
    resp = data.get("response") or {}
    results = (resp.get("results") or {}).get("result", []) or []

    def first_text(node):
        """取 OpenAIRE 节点的文本：可能是 str、{'$': str} 或 [{' $': str}]。"""
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            v = node.get("$", "")
            return v if isinstance(v, str) else ""
        if isinstance(node, list) and node:
            return first_text(node[0])
        return ""

    for item in results:
        md = (item.get("metadata", {}).get("oaf:entity", {})
              .get("oaf:result", {}))
        if not md:
            continue
        title = first_text(md.get("title"))
        date = first_text(md.get("dateofacceptance"))[:10]
        if date and date < since:
            continue
        doi = ""
        pid = md.get("pid")
        pids = pid if isinstance(pid, list) else [pid]
        for p in pids:
            if isinstance(p, dict) and p.get("@classname") == "doi":
                doi = norm_doi(first_text(p))
        out.append({
            "title": title,
            "authors": "",
            "date": date,
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else "",
            "abstract": first_text(md.get("description"))[:600],
            "venue": "",
            "source_db": "OpenAIRE",
        })
    return out


FETCHERS = [
    ("arXiv", fetch_arxiv),
    ("OpenAlex", fetch_openalex),
    ("Crossref", fetch_crossref),
    ("SemanticScholar", fetch_semanticscholar),
    ("EuropePMC", fetch_europepmc),
    ("OpenAIRE", fetch_openaire),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=(dt.date.today() - dt.timedelta(days=30)).isoformat(),
                    help="只收录该日期之后发表/收录的论文，默认 30 天前")
    ap.add_argument("--out", default="", help="输出 JSON 文件路径，默认 stdout")
    args = ap.parse_args()

    all_items, errors = [], {}
    for name, fn in FETCHERS:
        try:
            items = fn(args.since)
            all_items.extend(items)
        except Exception as e:  # 单个源失败不影响其他源
            errors[name] = f"{type(e).__name__}: {e}"

    # 去重：先过滤噪音，再按 DOI / 标题去重
    seen, uniq = set(), []
    for it in all_items:
        if not it.pop("phrase_confirmed", False) and not mentions_software(it):
            continue
        key = ("doi:" + it["doi"]) if it["doi"] else ("t:" + norm_title(it["title"]))
        if not key or key in seen or not it["title"]:
            continue
        seen.add(key)
        uniq.append(it)
    uniq.sort(key=lambda x: x["date"], reverse=True)

    report = {"since": args.since, "count": len(uniq),
              "errors": errors, "items": uniq}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}: {len(uniq)} items, errors={list(errors)}")
    else:
        print(text)


if __name__ == "__main__":
    main()
