# Spot execution and interruption handling

## What this does
Makes jobs survive AWS Spot interruptions. A watcher polls the instance
metadata for the interruption notice (about 2 minutes of warning), the job saves
a checkpoint to S3, and a later run resumes from it. Also collects Spot
price history and measures how often interruptions happen. The scheduler
uses our observed interruption rate. We do not use assumed numbers.

## Key facts (from the AWS Spot interruption notice page)
- Notice arrives 2 minutes before stop/terminate (best effort, not guaranteed).
- Read via IMDSv2: PUT /latest/api/token, then GET /latest/meta-data/spot/instance-action.
- Returns 404 until a notice exists. Check about every 5 seconds.
- Use terminate/stop behavior, not hibernate (hibernate gives no 2 minutes).

## Folder contents
- price_history/   script that saves Spot price history to S3
- checkpoint_job/  toy job with atomic checkpoints
- watcher/         interruption watcher + fake metadata server for testing

## Instance types
c7i-flex.large
m7i-flex.large
t3.small

## Access needed from the AWS person
IAM access, write access to the raw-data S3 bucket, permission to launch and
terminate Spot instances in the 4 regions with the project tag, spot vCPU quota status.

## Measurement log
timestamp, region, instance type, runtime before stopping, checkpoint size,
checkpoint save time, restart delay.

## Rules
- Never leave instances running. Always cancel Spot requests.
- Keep checkpoints small (cross-region transfer costs money).
- Claims: "estimated emissions of the workloads we schedule". No savings number before we measure it.

## Price history

First collection run: 2026-11-02
Oldest record: 2026-08-04   Newest record: 2026-11-02
Regions: us-east-1, us-west-1, eu-central-1, eu-north-1
Types: c7i-flex.large, m7i-flex.large, t3.small (approved by accounting)
Records per file: 721 to 1814
Files uploaded: 12 of 12
Files with 0 records: none

Script: spot/collect_prices.sh (run in AWS CloudShell)
Stored at: s3://project1-raw-data-fa-2026/raw/spot_price_history/
File name format: <region>-<instance type>-<YYYYMMDD of the run>.json

Gaps: none in collection. This was the first run, and the data covers
Aug 4 to Nov 2.
Note: price history lists price changes only, so a long time between two
records means the price stayed the same, not that data is missing.
Each run re-downloads the whole window, so runs overlap. Remove duplicates
when merging (same region + zone + type + timestamp).

Schedule: run once a week (calendar reminder every Sunday).
A gap appears only if more than about 90 days pass between runs.

Run log:
| Date       | Result | Notes               |
|------------|--------|---------------------|
| 2026-11-02 | OK     | First run, 12 files |



## Checkpoint job (step C)
File: spot/checkpoint_job/toy_job.py
Tested: 2026-11-02, Windows laptop, Python 3.13
Method: counts 2000 items, saves a checkpoint about every 3 s (write temp
file, flush to disk, rename). On start it resumes from checkpoint.json.

Test: two runs. Run 1: killed once with Ctrl+C. Run 2: killed 5 times at
random moments with Ctrl+C. Every restart resumed from the last saved item
(297, 474, 591, 704, 821 in run 2), never from 0.
Result: both runs finished with total 1999000 = expected, printed CORRECT.
Work done after the last save and before a kill (up to about 3 s) is redone
after restart. This is expected and does not change the result.

Measurements (64 saves over the two runs):
- Checkpoint size: 39 to 44 bytes (toy state, tiny by design)
- Save time: median about 0.07 s (run 1) and 0.11 s (run 2); most saves
  0.04 to 0.5 s
- Slowest saves: 4.56 s (run 1), 1.70 s (run 2). Cause not confirmed
  (probably disk or antivirus on the laptop).
Raw data: spot/results/checkpoint_log_laptop_2026-11-02.csv

Notes:
- Laptop numbers only. Real jobs have bigger checkpoints and S3 uploads
  take extra time. Measure again on AWS (step E).
- Even the worst save is small compared with the 120 s interruption notice,
  but save time is not constant, so quote the slowest value in the report.


  ## D. Interruption watcher
File: spot/watcher/watcher_demo.py (single-file test, no AWS needed)
Tested: 2026-11-02, Windows laptop, Python 3.13

Method: a fake AWS metadata server answers 404 ("no notice") for 5 s, then
returns a notice. The watcher gets a token first, then asks for
/latest/meta-data/spot/instance-action (IMDSv2 style) every 1 s. On notice:
the job saves a checkpoint, the checkpoint is copied to a local folder
standing in for S3, and a second job resumes from that copy.

Result: PASS in 3 of 3 runs. The resumed job finished with the exact
expected total every time (CORRECT).
Time from notice to saved + uploaded: 0.58 s, 0.12 s, 0.10 s.
Largest = 0.58 s (budget: 120 s). Checkpoint size 34 to 35 bytes.
The first run was the slowest (probably a cold start of the laptop disk;
cause not confirmed).

Limits of this test:
- Upload goes to a local folder, not real S3. The real S3 upload is tested
  in step E.
- The fake server is polled every 1 s. On AWS the advised interval is about
  5 s, so allow up to 5 s extra for detection.
- Laptop timings only. A real instance and real S3 will be slower.
- Time budget on AWS: up to 5 s detection + save + upload must fit well
  inside 120 s.
