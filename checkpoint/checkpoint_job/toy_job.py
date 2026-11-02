import csv
import json
import os
import time

CHECKPOINT = "checkpoint.json"
TOTAL_ITEMS = 2000          # how many numbered items to process
WORK_PER_ITEM = 0.05        # fake work: seconds per item (2000 x 0.05 = 100 s)
SAVE_EVERY_SECONDS = 3      # save a checkpoint this often
LOG_FILE = "checkpoint_log.csv"


def load_checkpoint():
    """Return (next_item, total_so_far). Start from 0 if there is no good checkpoint."""
    try:
        with open(CHECKPOINT) as f:
            data = json.load(f)
        return data["next_item"], data["total_so_far"]
    except (FileNotFoundError, ValueError, KeyError):
        return 0, 0


def save_checkpoint(next_item, total_so_far):
    """Write to a temporary file first, then rename it, so a crash can never leave a broken checkpoint."""
    start = time.perf_counter()
    tmp = CHECKPOINT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"next_item": next_item, "total_so_far": total_so_far}, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CHECKPOINT)
    seconds = time.perf_counter() - start
    size = os.path.getsize(CHECKPOINT)
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([time.strftime("%Y-%m-%d %H:%M:%S"), next_item, size, f"{seconds:.6f}"])
    print(f"  saved checkpoint at item {next_item} ({size} bytes, {seconds:.6f} s)", flush=True)


next_item, total_so_far = load_checkpoint()
if next_item == 0:
    print("Starting fresh from item 0", flush=True)
else:
    print(f"Resuming from item {next_item}", flush=True)

last_save = time.monotonic()
while next_item < TOTAL_ITEMS:
    total_so_far += next_item          # "process" the item
    next_item += 1
    time.sleep(WORK_PER_ITEM)
    if time.monotonic() - last_save >= SAVE_EVERY_SECONDS:
        save_checkpoint(next_item, total_so_far)
        last_save = time.monotonic()

save_checkpoint(next_item, total_so_far)
expected = TOTAL_ITEMS * (TOTAL_ITEMS - 1) // 2
print(f"DONE. total = {total_so_far}, expected = {expected}, {'CORRECT' if total_so_far == expected else 'WRONG'}")
