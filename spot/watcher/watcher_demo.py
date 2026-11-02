"""Step D demo (everything in ONE file, no AWS needed).

It pretends to be AWS and does the whole sequence on your laptop:
  1. a fake "AWS metadata server" says 'no notice' for a few seconds, then 'notice!'
  2. a toy job counts items and saves checkpoints
  3. the watcher asks the server every second (token first, like IMDSv2)
  4. on the notice the job saves, the checkpoint is "uploaded" to the folder fake_s3/
  5. a new job resumes from the uploaded checkpoint and must finish with the right answer
  6. the timings are printed and one row is added to measurement_log.csv
"""
import csv
import json
import os
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8169
NOTICE_AFTER_SECONDS = 5      # the fake server shows the notice after this long
POLL_SECONDS = 1              # real AWS advice: about 5 seconds
TOTAL_ITEMS = 1000
WORK_PER_ITEM = 0.01
CHECKPOINT = "demo_checkpoint.json"
LOG_FILE = "measurement_log.csv"
START = time.time()
TOKENS = set()


class FakeAWS(BaseHTTPRequestHandler):
    def reply(self, code, text=""):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):                                   # step 1 of IMDSv2: get a token
        token = secrets.token_urlsafe(16)
        TOKENS.add(token)
        self.reply(200, token)

    def do_GET(self):                                   # step 2: ask for the notice, using the token
        if self.headers.get("X-aws-ec2-metadata-token") not in TOKENS:
            return self.reply(401, "Unauthorized")
        if time.time() - START < NOTICE_AFTER_SECONDS:
            return self.reply(404, "Not Found")         # no notice yet
        self.reply(200, json.dumps({"action": "terminate", "time": "soon"}))

    def log_message(self, *args):
        pass


def save_checkpoint(path, next_item, total):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"next_item": next_item, "total": total}, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run_job(path, stop_event, done_event, result, first_item_time=None):
    """Counts items. Saves every second. Saves and stops when stop_event is set."""
    next_item, total = 0, 0
    if os.path.exists(path):
        data = json.load(open(path))
        next_item, total = data["next_item"], data["total"]
    last = time.monotonic()
    while next_item < TOTAL_ITEMS:
        if stop_event.is_set():
            t = time.perf_counter()
            save_checkpoint(path, next_item, total)
            result["save_s"] = time.perf_counter() - t
            done_event.set()
            return
        total += next_item
        next_item += 1
        if first_item_time is not None and "first_item" not in first_item_time:
            first_item_time["first_item"] = time.perf_counter()
        time.sleep(WORK_PER_ITEM)
        if time.monotonic() - last >= 1:
            save_checkpoint(path, next_item, total)
            last = time.monotonic()
    result["finished_total"] = total


def read_notice():
    base = f"http://127.0.0.1:{PORT}"
    req = urllib.request.Request(base + "/latest/api/token", method="PUT",
                                 headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"})
    token = urllib.request.urlopen(req, timeout=2).read().decode()
    req = urllib.request.Request(base + "/latest/meta-data/spot/instance-action",
                                 headers={"X-aws-ec2-metadata-token": token})
    try:
        return urllib.request.urlopen(req, timeout=2).read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None                                 # 404 = no notice (this is what real AWS does)
        raise


def main():
    for p in (CHECKPOINT, "fake_s3"):
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else (os.path.exists(p) and os.remove(p))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), FakeAWS)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    stop, done, res = threading.Event(), threading.Event(), {}
    threading.Thread(target=run_job, args=(CHECKPOINT, stop, done, res), daemon=True).start()
    print("job started; watcher is polling the fake AWS server...")
    job_start = time.monotonic()
    while True:
        note = read_notice()
        if note:
            break
        time.sleep(POLL_SECONDS)
    t_notice = time.perf_counter()
    ran_for = time.monotonic() - job_start
    print(f"NOTICE received after {ran_for:.1f} s: {note}")

    stop.set()                                          # tell the job: save now and stop
    done.wait(timeout=100)
    t_saved = time.perf_counter()
    os.makedirs("fake_s3", exist_ok=True)               # pretend this folder is the S3 bucket
    shutil.copyfile(CHECKPOINT, os.path.join("fake_s3", "checkpoint.json"))
    t_uploaded = time.perf_counter()
    size = os.path.getsize(CHECKPOINT)
    total_s = t_uploaded - t_notice
    print(f"checkpoint saved in {t_saved - t_notice:.4f} s, uploaded in {t_uploaded - t_saved:.4f} s, "
          f"total {total_s:.4f} s out of the 120 s AWS gives you ({size} bytes)")

    # "second machine": resume from the uploaded copy
    second = os.path.join("fake_s3", "checkpoint.json")
    marks, res2 = {}, {}
    t_restart = time.perf_counter()
    run_job(second, threading.Event(), threading.Event(), res2, marks)
    restart_delay = marks["first_item"] - t_restart
    expected = TOTAL_ITEMS * (TOTAL_ITEMS - 1) // 2
    ok = res2.get("finished_total") == expected
    print(f"resumed job finished: total={res2.get('finished_total')} expected={expected} -> "
          f"{'CORRECT' if ok else 'WRONG'}")

    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp_utc", "test_type", "region", "instance_type", "ran_before_stop_s",
                        "checkpoint_bytes", "checkpoint_save_s", "upload_s", "notice_to_done_s",
                        "restart_delay_s", "interruption_source", "notes"])
        w.writerow([time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "watcher_demo", "laptop", "laptop",
                    f"{ran_for:.1f}", size, f"{t_saved - t_notice:.4f}", f"{t_uploaded - t_saved:.4f}",
                    f"{total_s:.4f}", f"{restart_delay:.4f}", "fake local server", "laptop test, not AWS"])
    print("PASS" if ok and total_s < 120 else "FAIL", "- row added to", LOG_FILE)


main()
