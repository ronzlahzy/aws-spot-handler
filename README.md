# spot/ — Spot execution and interruption handling

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
To be agreed with the accounting person.

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
Types: c7i-flex.large, m7i-flex.large, t3.small
Records per file: (721 to 1814)
