#!/usr/bin/env bash
# Dragonfly 3D World News 每日发布管道（生成后半段）。
# 前提：agent 已按 grok-daily-prompt.md 生成 news/<DATE>.html 并更新 data/news.json、index.html。
# 步骤：build_library.py -> seo.py -> brand_check.py -> git commit+push
#       -> publish_cnblogs.py（当天未同步时）-> retry_cnblogs.py
# 环境变量（只从环境读取，绝不写入仓库/日志）：
#   GITHUB_NEWS_TOKEN  推送用 GitHub 令牌（必需，除非 SKIP_PUSH=1）
#   CNBLOGS_TOKEN      博客园 MetaWeblog 访问令牌（必需，除非 SKIP_CNBLOGS=1）
#   CNBLOGS_USER       可选，默认读 cnblogs.config.json
#   NEWS_STATE_DIR     状态目录，默认 /workspace/news-state
#   DIGEST_MSG         可选，提交说明
# 用法：bin/daily.sh [YYYY-MM-DD]   （默认今天，America/Toronto）
# 最后一行输出机器可读汇总：DAILY_SUMMARY status=ok|fail ...
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DATE="${1:-$(TZ=America/Toronto date +%F)}"
export NEWS_STATE_DIR="${NEWS_STATE_DIR:-/workspace/news-state}"
mkdir -p "$NEWS_STATE_DIR"
PY="${PYTHON:-python3}"
S_SEO=- S_LIB=- S_BRAND=- S_PUSH=- S_CNB=- S_RETRY=-

summary() { echo "DAILY_SUMMARY status=$1 date=$DATE seo=$S_SEO library=$S_LIB brand=$S_BRAND push=$S_PUSH cnblogs=$S_CNB retry=$S_RETRY"; }
fail() { echo "daily.sh FAILED: $*" >&2; summary fail; exit 1; }

# 凭据助手：从环境变量取令牌，不把令牌写进 remote URL 或 git 配置
gitc() { git -c credential.helper= -c credential.helper='!f() { echo username=x-access-token; echo "password=$GITHUB_NEWS_TOKEN"; }; f' "$@"; }

# 注意：build_library.py 会重写 library.html（不带 SEO 标签），所以必须先建库再跑 seo.py
$PY bin/build_library.py >/dev/null || fail "build_library.py 出错"; S_LIB=ok
$PY bin/seo.py >/dev/null || fail "seo.py 出错"; S_SEO=ok
$PY bin/brand_check.py || { S_BRAND=fail; fail "brand_check 发现禁用字样（by AI / 由 AI / auto-curated），先修页面再跑"; }
S_BRAND=ok

if [ "${SKIP_PUSH:-0}" = 1 ]; then S_PUSH=skipped; else
  [ -n "${GITHUB_NEWS_TOKEN:-}" ] || fail "缺少环境变量 GITHUB_NEWS_TOKEN"
  git add -A news data index.html library.html sitemap.xml robots.txt assets 2>/dev/null
  if git diff --cached --quiet; then S_PUSH=nochange; else
    git commit -q -m "${DIGEST_MSG:-$DATE digest}" || fail "git commit 失败"
  fi
  gitc pull -q --rebase origin main || fail "git pull --rebase 失败（需人工解决冲突）"
  if [ "$(git rev-list --count origin/main..HEAD)" != 0 ]; then
    gitc push -q origin HEAD:main || fail "git push 失败"
    S_PUSH=$(git rev-parse --short HEAD)
  fi
fi

if [ "${SKIP_CNBLOGS:-0}" = 1 ]; then S_CNB=skipped; S_RETRY=skipped; else
  [ -n "${CNBLOGS_TOKEN:-}" ] || fail "缺少环境变量 CNBLOGS_TOKEN"
  HTML="news/$DATE.html"
  if [ ! -f "$HTML" ]; then S_CNB=no-page
  else
    OUT=$($PY bin/publish_cnblogs.py --html-file "$HTML" 2>&1); RC=$?
    echo "$OUT"
    [ $RC = 0 ] || { S_CNB=failed-queued; fail "publish_cnblogs.py 失败（已入 48h 重试队列）"; }
    if echo "$OUT" | grep -q '^skip:'; then S_CNB="already:$(echo "$OUT" | grep -o 'postid [0-9]*' | head -1 | cut -d' ' -f2)"
    else S_CNB="posted:$(echo "$OUT" | sed -n 's/^published postid: *//p')"; fi
  fi
  $PY bin/retry_cnblogs.py || { S_RETRY=expired; fail "retry_cnblogs.py：有超 48 小时仍未成功的项，需人工处理"; }
  S_RETRY=ok
fi
summary ok
