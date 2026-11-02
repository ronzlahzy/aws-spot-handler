# Run in AWS CloudShell:  bash collect_prices.sh
# Saves the last 90 days of Spot price history (Linux/UNIX) for 3 instance
# types in 4 regions to S3. Run once a week. File names include the run date.

for R in us-east-1 us-west-1 eu-central-1 eu-north-1; do
 for T in c7i-flex.large m7i-flex.large t3.small; do
  F="$R-$T-$(date -u +%Y%m%d).json"
  aws ec2 describe-spot-price-history --region $R --instance-types $T --product-descriptions "Linux/UNIX" --start-time $(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ) > $F
  aws s3 cp $F s3://project1-raw-data-fa-2026/raw/spot_price_history/$F
 done
done
