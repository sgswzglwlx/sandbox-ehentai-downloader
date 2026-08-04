#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BT 磁力下载执行器（GitHub Actions 用）"""
import os
import subprocess
import time
import json
import sys
import threading
import traceback

print("[DIAG] INPUT_MAGNET1 =", repr(os.environ.get('INPUT_MAGNET1', '')), flush=True)
print("[DIAG] INPUT_MAGNET2 =", repr(os.environ.get('INPUT_MAGNET2', '')), flush=True)
print("[DIAG] python:", sys.version.split()[0], flush=True)
print("[DIAG] cwd:", os.getcwd(), flush=True)

magnets = []
for key in ('INPUT_MAGNET1', 'INPUT_MAGNET2'):
    m = os.environ.get(key, '').strip()
    if m:
        magnets.append(m)
print(f"[INFO] 收到 {len(magnets)} 个磁力链接", flush=True)

trackers = ",".join([
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tracker.tiny-vps.com:6969/announce",
    "http://tracker.opentrackr.org:1337/announce",
    "https://tracker.gbitt.info:443/announce",
    "http://tracker.gbitt.info:80/announce",
])

MAX_SIZE = 350 * 1024 * 1024
PER_TASK_TIMEOUT = 2400


def dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    return total


def pump(proc, tag):
    try:
        for line in proc.stdout:
            print(f"[{tag}] {line.rstrip()}", flush=True)
    except Exception:
        pass


results = []
try:
    os.makedirs("out", exist_ok=True)
    for idx, mag in enumerate(magnets, 1):
        outdir = f"out/task{idx}"
        os.makedirs(outdir, exist_ok=True)
        info = {"index": idx, "magnet": mag, "status": "running", "size": 0}
        results.append(info)
        print(f"[INFO] 任务{idx} 开始: {mag[:80]}...", flush=True)
        cmd = [
            "aria2c", "--dir=" + outdir,
            "--enable-dht=true", "--dht-listen-port=6881-6999",
            "--dht-entry-point=router.bittorrent.com:6881",
            "--enable-peer-exchange=true", "--bt-enable-lpd=true",
            "--bt-tracker=" + trackers,
            "--max-connection-per-server=16", "--split=16",
            "--seed-time=0", "--bt-save-metadata=true",
            "--console-log-level=error", "--summary-interval=0",
            "--log=" + f"out/aria{idx}.log",
            mag,
        ]
        try:
            logf = open(f"out/aria{idx}.log", "a")
            proc = subprocess.Popen(
                cmd, stdout=logf, stderr=subprocess.STDOUT,
                text=True
            )
        except Exception as e:
            print(f"[ERROR] 任务{idx} Popen失败: {e}", flush=True)
            info["status"] = f"popen_err:{e}"
            continue
        start = time.time()
        try:
            while proc.poll() is None:
                if dir_size(outdir) > MAX_SIZE:
                    print(f"[LIMIT] 任务{idx} 超限停止", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        proc.kill()
                    info["status"] = "size_limit"
                    break
                if time.time() - start > PER_TASK_TIMEOUT:
                    print(f"[TIMEOUT] 任务{idx} 超时停止", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        proc.kill()
                    info["status"] = "timeout"
                    break
                time.sleep(5)
            if info["status"] == "running":
                rc = proc.wait(timeout=15)
                info["status"] = "done" if rc == 0 else f"exit_{rc}"
                print(f"[INFO] 任务{idx} aria2退出码: {rc}", flush=True)
        except Exception as e:
            proc.kill()
            info["status"] = f"err:{e}"
            print(f"[ERROR] 任务{idx}: {e}", flush=True)
        info["size"] = dir_size(outdir)
        print(f"[RESULT] 任务{idx}: {info['status']} size={info['size']/1048576:.1f}MiB", flush=True)

    with open("out/manifest.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total = dir_size("out")
    print(f"[TOTAL] {total/1048576:.1f} MiB", flush=True)
    if total > 380 * 1024 * 1024:
        os.makedirs("parts", exist_ok=True)
        subprocess.run(["zip", "-r", "-s", "300m", "parts/bt.zip", "out"], check=False)
        print("[PACK] 已分卷打包到 parts/", flush=True)
except Exception:
    traceback.print_exc()
    sys.exit(1)
print("[DONE] 脚本结束", flush=True)
