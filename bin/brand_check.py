#!/usr/bin/env python3
"""品牌用语检查：页面可见文本中不得出现 'by AI'、'由 AI'、'auto-curated'。

检查 news/*.html、index.html、library.html 的可见文本（文本节点 + title/alt/
meta content/aria-label/placeholder 等属性；跳过 <script>/<style>）。
仓库名子串 'dragonfly3dworld-news-by-ai'（出现在 URL 里）不算命中。

用法：python3 bin/brand_check.py [文件...]   有命中则退出码 1。
"""
import glob
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = [re.compile(r"by[\s\u00a0\-_]*AI\b", re.I),
            re.compile(r"由\s*AI", re.I),
            re.compile(r"auto[\s\-]*curated", re.I)]
REPO_NAME = re.compile(r"dragonfly3dworld-news-by-ai", re.I)
VISIBLE_ATTRS = {"title", "alt", "content", "aria-label", "placeholder", "value",
                 "data-title-zh", "data-title-en"}


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.chunks = []  # (line, text)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        for k, v in attrs:
            if v and (k in VISIBLE_ATTRS or k.startswith("data-") and k.endswith(("-zh", "-en"))):
                self.chunks.append((self.getpos()[0], v))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.chunks.append((self.getpos()[0], data))


def check(path):
    p = Visible()
    with open(path, encoding="utf-8") as f:
        p.feed(f.read())
    hits = []
    for line, text in p.chunks:
        t = REPO_NAME.sub(" ", text)
        for pat in PATTERNS:
            for m in pat.finditer(t):
                ctx = t[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
                hits.append((line, m.group(0), ctx.strip()))
    return hits


def main(argv):
    files = argv or sorted(glob.glob(os.path.join(ROOT, "news", "*.html"))) + [
        os.path.join(ROOT, "index.html"), os.path.join(ROOT, "library.html")]
    total = 0
    for fp in files:
        if not os.path.exists(fp):
            continue
        for line, word, ctx in check(fp):
            total += 1
            print(f"{os.path.relpath(fp, ROOT)}:{line}: '{word}' … {ctx}")
    print(f"brand_check: {'FAIL' if total else 'OK'} hits={total} files={len(files)}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
