#!/usr/bin/env python3
"""重试博客园发布失败队列（48 小时内自动重试）。

用户立规（2026-10-17）：以后每次博客园发布失败，自动在两天内重试。
机制：
  - publish_cnblogs.py 发布失败时把该日期记入 .cnblogs_failed.json，成功时清除。
  - 本脚本由每日任务 dragonfly-news-daily 步骤 7 开头执行（每天一次），
    逐条重试 48 小时内的失败项；已同步的直接清队列；超过 48 小时仍失败的
    记入 .cnblogs_failed_expired.json 并从待重试队列移除，同时非零退出，
    由当日任务在汇报中提醒用户人工处理。
  - 防重复：重试走 publish_cnblogs.py 本身，它会按 .cnblogs_synced.json
    跳过已同步日期，不会重复发帖。

用法：
  python3 retry_cnblogs.py                  # 重试全部 48 小时内待重试项
  python3 retry_cnblogs.py --dry-run        # 只列出待重试项，不真正发布
  python3 retry_cnblogs.py --max-age-hours 48
"""
import argparse
import json
import os
import subprocess
import sys
import time

WORKDIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WORKDIR)
DEFAULT_FAILED = os.path.join(ROOT, ".cnblogs_failed.json")
DEFAULT_SYNCED = os.path.join(ROOT, ".cnblogs_synced.json")
DEFAULT_EXPIRED = os.path.join(ROOT, ".cnblogs_failed_expired.json")
PUBLISH_SCRIPT = os.path.join(WORKDIR, "publish_cnblogs.py")


def load_dict(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_dict(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    with open(path, encoding="utf-8") as f:
        json.load(f)  # 写入后校验，防静默 JSON 损坏


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--failed-file", default=DEFAULT_FAILED)
    ap.add_argument("--state-file", default=DEFAULT_SYNCED)
    ap.add_argument("--expired-file", default=DEFAULT_EXPIRED)
    ap.add_argument("--config", default=None,
                    help="透传给 publish_cnblogs.py 的 --config（默认用其默认凭据文件）")
    ap.add_argument("--max-age-hours", type=float, default=48,
                    help="首次失败起多少小时内重试（默认 48，即两天）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    failed = load_dict(args.failed_file)
    if not failed:
        print("retry: 失败队列为空，无需重试")
        return 0

    now = int(time.time())
    max_age = args.max_age_hours * 3600
    expired = load_dict(args.expired_file)
    n_ok = n_still_pending = n_expired = n_cleared_synced = 0
    changed = False

    for date_key in sorted(list(failed.keys())):
        entry = failed.get(date_key) or {}
        # 已同步 -> 直接清队列（publish_cnblogs 的防重复兜底）
        synced = load_dict(args.state_file)
        if date_key in synced:
            print(f"retry: {date_key} 已在同步记录中（postid {synced[date_key].get('postid')}），清除失败记录")
            del failed[date_key]
            save_dict(args.failed_file, failed)  # 立刻落盘，避免后一轮重读覆盖
            n_cleared_synced += 1
            changed = True
            continue
        first = entry.get("first_failed_at") or now
        age_h = (now - first) / 3600.0
        if age_h > args.max_age_hours:
            print(f"retry EXPIRED: {date_key} 首次失败距今 {age_h:.1f} 小时，已超 {args.max_age_hours:.0f} 小时仍未成功，需人工处理。"
                  f"最后错误：{entry.get('last_error', '')[:200]}")
            expired[date_key] = {**entry, "expired_at": now,
                                 "expired_reason": f"超过 {args.max_age_hours:.0f} 小时未成功"}
            del failed[date_key]
            save_dict(args.failed_file, failed)  # 立刻落盘，避免后一轮重读覆盖
            save_dict(args.expired_file, expired)
            n_expired += 1
            changed = True
            continue
        html_file = entry.get("html_file") or os.path.join(ROOT, "news", f"{date_key}.html")
        if not os.path.exists(html_file):
            print(f"retry: {date_key} 本地 HTML 不存在（{html_file}），跳过本轮，保留在队列中")
            n_still_pending += 1
            continue
        if args.dry_run:
            print(f"retry DRY-RUN: {date_key} 将重试（首次失败 {age_h:.1f} 小时前，"
                  f"已尝试 {entry.get('attempts', 0)} 次）：{html_file}")
            n_still_pending += 1
            continue
        print(f"retry: {date_key} 正在重试（首次失败 {age_h:.1f} 小时前，"
              f"已尝试 {entry.get('attempts', 0)} 次）：{html_file}")
        cmd = [sys.executable, PUBLISH_SCRIPT, "--html-file", html_file,
               "--state-file", args.state_file, "--failed-file", args.failed_file]
        if args.config:
            cmd += ["--config", args.config]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        print((proc.stdout or "").strip())
        if proc.stderr.strip():
            print((proc.stderr or "").strip()[:1000])
        synced = load_dict(args.state_file)
        if proc.returncode == 0 and date_key in synced:
            print(f"retry OK: {date_key} 已补发，postid {synced[date_key].get('postid')}")
            n_ok += 1
            # publish_cnblogs 成功时已清除失败记录；重读以防万一
            failed = load_dict(args.failed_file)
            changed = False  # 文件已由 publish 脚本更新
        else:
            # publish 脚本失败时已更新失败队列（attempts+1）；重读最新队列
            failed = load_dict(args.failed_file)
            changed = False
            print(f"retry FAILED: {date_key} 本轮重试仍失败（退出码 {proc.returncode}），保留在队列中，下次继续重试")
            n_still_pending += 1

    if changed:
        save_dict(args.failed_file, failed)
    if n_expired:
        save_dict(args.expired_file, expired)
    print(f"retry 汇总：成功 {n_ok}，已同步清队列 {n_cleared_synced}，"
          f"仍待重试 {n_still_pending}，超期需人工处理 {n_expired}")
    # 超期未成功必须让每日任务注意到：非零退出
    return 1 if n_expired else 0


if __name__ == "__main__":
    sys.exit(main())
