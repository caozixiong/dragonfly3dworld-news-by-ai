#!/usr/bin/env python3
"""把 dragonfly-news 的日报页面同步发布到博客园 (cnblogs.com)。

原理：博客园支持 MetaWeblog 协议 (XML-RPC)，endpoint 为
  https://rpc.cnblogs.com/metaweblog/{用户名}
认证用"用户名 + 访问令牌"(令牌在博客园 设置->博客设置 里生成，不是登录密码)。

发布内容为中文版：自动去掉页面里的英文(t-en)部分、语言切换按钮和关键词过滤框，
相对链接转为绝对链接。

用法：
  python3 publish_cnblogs.py --html-file news/2026-09-23.html
  python3 publish_cnblogs.py --html-file news/2026-09-23.html --title "自定义标题" --categories "随笔,日报"
  python3 publish_cnblogs.py --html-file news/2026-09-23.html --dry-run   # 只打印清洗后的HTML，不发布
  python3 publish_cnblogs.py --delete <postid>   # 删除文章(用于清理测试文章)

凭据文件 (默认 ~/workspace/dragonfly-news/.cnblogs.json，权限 600，不进 git)：
  {"username": "你的博客园用户名", "token": "在博客设置里生成的访问令牌"}
"""
import argparse
import json
import os
import re
import sys
import xmlrpc.client
from html.parser import HTMLParser
from urllib.parse import urljoin

WORKDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(os.path.dirname(WORKDIR), ".cnblogs.json")
SITE_BASE = "https://caozixiong.github.io/dragonfly3dworld-news-by-ai/"

SKIP_IDS = {"langToggle", "filter"}
SKIP_TAGS = {"script", "style"}


class CnblogsCleaner(HTMLParser):
    """抽取中文正文：跳过 t-en 分支、脚本、语言切换按钮和过滤输入框。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip_depth = 0  # >0 表示正在跳过子树

    def _is_skip_start(self, tag, attrs):
        d = dict(attrs)
        cls = d.get("class", "")
        if tag in SKIP_TAGS:
            return True
        if "t-en" in cls.split():
            return True
        if d.get("id") in SKIP_IDS:
            return True
        return False

    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            self.skip_depth += 1
            return
        if self._is_skip_start(tag, attrs):
            self.skip_depth = 1
            return
        if tag == "link":
            return  # 去掉外部 CSS 引用
        kept = []
        for k, v in attrs:
            if k in ("href", "src"):
                v = urljoin(SITE_BASE, v)
                kept.append((k, v))
            elif k in ("target", "rel", "alt", "title"):
                kept.append((k, v))
            # class/id/style 等全部丢掉，用博客园自带主题样式
        attr_str = "".join(f' {k}="{v}"' for k, v in kept)
        self.out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag):
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == "link":
            return
        self.out.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if self.skip_depth:
            return
        if self._is_skip_start(tag, attrs):
            return
        if tag == "link":
            return
        kept = []
        for k, v in attrs:
            if k in ("href", "src"):
                kept.append((k, urljoin(SITE_BASE, v)))
            elif k in ("alt", "title"):
                kept.append((k, v))
        attr_str = "".join(f' {k}="{v}"' for k, v in kept)
        self.out.append(f"<{tag}{attr_str}/>")

    def handle_data(self, data):
        if not self.skip_depth:
            self.out.append(data)

    def result(self):
        return "".join(self.out)


def extract_title(html):
    m = re.search(r'data-title-zh="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m.group(1).strip() if m else "Dragonfly 3D World 日报"


def extract_body(html):
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    return m.group(1) if m else html


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    username = cfg.get("username", "").strip()
    token = cfg.get("token", "").strip()
    if not username or not token:
        sys.exit(f"凭据文件 {path} 缺少 username 或 token")
    return username, token


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html-file")
    ap.add_argument("--title")
    ap.add_argument("--categories", default="")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--blogid", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delete")
    args = ap.parse_args()

    username, token = load_config(args.config)
    endpoint = f"https://rpc.cnblogs.com/metaweblog/{username}"
    server = xmlrpc.client.ServerProxy(endpoint, allow_none=True)

    if args.delete:
        # blogger.deletePost(appkey, postid, username, password, publish)
        ok = server.blogger.deletePost("", args.delete, username, token, True)
        print("deleted:" , bool(ok))
        return

    if not args.html_file:
        sys.exit("需要 --html-file 或 --delete")

    with open(args.html_file, encoding="utf-8") as f:
        html = f.read()
    title = args.title or extract_title(html)

    cleaner = CnblogsCleaner()
    cleaner.feed(extract_body(html))
    content = cleaner.result()
    # 去掉连续空行，压缩体积
    content = re.sub(r"\n\s*\n+", "\n", content)

    if args.dry_run:
        print("TITLE:", title)
        print(content[:3000])
        return

    post = {"title": title, "description": content}
    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    if cats:
        post["categories"] = cats
    postid = server.metaWeblog.newPost(args.blogid, username, token, post, True)
    print("published postid:", postid)
    print(f"https://www.cnblogs.com/{username}/p/{postid}.html")


if __name__ == "__main__":
    main()
