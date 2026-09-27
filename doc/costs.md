# Expected AWS costs (~100 API calls/day)

**Bottom line: effectively $0/month.** At this volume, every AWS service
this stack uses (Lambda, DynamoDB on-demand, Cognito, API Gateway,
CloudWatch Logs) is either fully inside its free tier or charges a
fraction of a cent — the realistic total is **under $0.01–0.05/month**,
and this architecture has **no fixed/idle cost** at all (no NAT Gateway,
no always-on compute, no provisioned database capacity) - you only pay
for requests actually made.

## Assumptions

- **100 API calls/day ≈ 3,000/month, ≈ 36,500/year.**
- Lambda: 512 MB memory (`infrastructure/variables.tf`
  `lambda_memory_size`), arm64, ~300ms average execution (warm; a cold
  start after idle periods runs longer but is rare at this volume and
  still trivial in cost).
- DynamoDB: roughly 3 read/write operations per API call on average (a
  quote lookup + a progress/like check/update, etc.) → ~9,000 DynamoDB
  requests/month.
- A handful of registered users (this is a personal project) - nowhere
  near any per-user pricing threshold.
- Note: this Lambda also serves the app's static assets (`app/static/css`,
  `app/static/js`) via Flask's own static route, so a single page view
  can be more than one Lambda invocation (HTML + CSS + JS + HTMX fragment
  calls) until the browser caches them. Even at 5-10x the stated 100/day
  figure, every number below stays in the same "pennies or free" range -
  see the scaling table at the end for how far this actually has to grow
  before it costs real money.
- Pricing below is AWS's published **us-east-1 (N. Virginia)** rate as a
  reference point (`aws.amazon.com/*/pricing/`, fetched while writing this
  doc). This project deploys to **eu-central-1 (Frankfurt)**
  (`infrastructure/variables.tf` `aws_region`), where DynamoDB and
  CloudWatch rates typically run 10-25% higher and Lambda/API
  Gateway/Cognito request pricing is generally the same. At this volume
  that difference is still pennies - use the
  [AWS Pricing Calculator](https://calculator.aws) for exact eu-central-1
  figures if you want them precise.

## Per-service breakdown

| Service | Pricing model | Free tier | Estimated monthly cost at 100 calls/day |
|---|---|---|---|
| **Lambda** | $0.20 / 1M requests + $0.0000166667 / GB-second (x86; arm64 is ~20% cheaper) | 1,000,000 requests + 400,000 GB-seconds/month, **always-free** (not a 12-month trial) | 3,000 requests and ~450 GB-seconds - both **≈0.1% of the free tier**. **$0.00** |
| **API Gateway** (HTTP API) | $1.00 / 1M requests | 1,000,000 requests/month, but **only for your account's first 12 months** | Year 1: **$0.00** (inside free tier). After: 3,000/1,000,000 × $1.00 ≈ **$0.003/month** |
| **DynamoDB** (on-demand, 3 tables) | $0.625 / 1M write request units, $0.125 / 1M eventually-consistent read request units, $0.25/GB-month storage, $0.20/GB-month for point-in-time recovery | 25 GB storage + 25 WCU/RCU, but **does not apply to on-demand tables** per AWS's own pricing page | ~9,000 requests/month (mixed read/write) ≈ **$0.003-$0.01/month**. Storage and PITR: table data is a few hundred quotes + a handful of users, well under 1 MB → rounds to **$0.00** |
| **Cognito** (User Pool, Essentials tier) | $0.015 / MAU above the free tier | **10,000 Monthly Active Users/month, always-free** (explicitly not tied to the account's 12-month trial) | A handful of users, nowhere near 10,000 → **$0.00** |
| **CloudWatch Logs** (Lambda + API Gateway access logs, 30-day retention) | $0.50/GB ingestion, $0.03/GB-month storage | 5 GB ingestion+storage/month | ~100 invocations/day × a few KB of logs each ≈ 5-10 MB/month, ~0.1-0.2% of the free tier → **$0.00** |
| **IAM** | n/a | n/a | Always free. **$0.00** |
| **S3 + DynamoDB** (Terraform remote state, `infrastructure/backend.tf`) | Storage + request pricing | 5 GB S3 storage free | A few KB of state file, shared with your other Terraform-managed projects → **$0.00** incremental |

**Total: effectively $0/month during your account's first year (API
Gateway's free tier covers everything), and well under $0.05/month after
that** - realistically closer to $0.01/month once API Gateway starts
charging its per-request rate, since DynamoDB/Cognito/CloudWatch/Lambda
all stay inside their (perpetual) free tiers at this volume regardless of
account age.

## Why this stays this cheap: no idle/fixed costs

Every resource in `infrastructure/` is consumption-based - there is
nothing in this stack that bills a flat monthly rate whether or not it's
used:

- **DynamoDB tables are `PAY_PER_REQUEST`** (`infrastructure/dynamodb.tf`)
  - no provisioned read/write capacity sitting idle.
- **Lambda has no provisioned concurrency** - it scales to zero between
  requests and you pay nothing while idle.
- **No NAT Gateway.** The Lambda isn't deployed into a VPC
  (`infrastructure/lambda.tf` has no `vpc_config`), so its outbound calls
  to ZenQuotes go out directly - avoiding what is usually the single
  biggest "surprise" cost in a serverless AWS stack (a NAT Gateway alone
  is roughly **$32-36/month** just to exist, before any per-GB data
  processing charges, completely independent of traffic volume).
- **No RDS, ALB, ElastiCache, or other always-on compute/database.**
- Cognito, CloudWatch, and S3 are all pay-as-you-go with no minimum
  commitment either.

## What would actually move the needle

None of this changes until traffic grows by orders of magnitude, you add
resources not currently in `infrastructure/`, or you turn on optional
paid features:

| If you... | Cost impact |
|---|---|
| Grow to ~10,000+ Monthly Active Users | Cognito starts charging $0.015/MAU above the free 10,000 |
| Grow traffic ~300-1000x (to ~30,000-100,000 calls/day) | Still mostly inside free tiers; API Gateway becomes the first line item to actually show up on a bill, at low single-digit dollars/month |
| Add a custom domain | Route 53 hosted zone (~$0.50/month) + ACM certificate (free) |
| Enable Cognito Advanced Security Features (risk-based auth, compromised-credential checks) | Separate paid add-on, priced per MAU |
| Put the Lambda in a VPC (e.g. to reach a private resource) | Reintroduces NAT Gateway cost (~$32-36/month fixed + data processing) unless you use VPC endpoints instead |
| Add S3 + CloudFront for a separate static frontend | Small (~$0.01-1/month at this scale) but non-zero, and not currently part of this architecture (see `doc/architecture.md` - this Lambda serves its own HTML/HTMX directly) |
| Turn on DynamoDB provisioned capacity instead of on-demand | Could actually be *more* expensive at this low, spiky volume - on-demand is the right choice here |

For reference, even at **100x today's volume (10,000 calls/day, 300,000/month)**
this stack would still cost roughly **$1-3/month total** - Lambda and
DynamoDB stay free or near-free, and API Gateway's $1/million-requests
rate is the only line that becomes noticeable.

## Keeping an eye on actual spend

Estimates are estimates - to see real numbers and catch anything
unexpected early:

- Set an **AWS Budget** with an alert (e.g. "notify me if forecasted
  spend exceeds $5/month") - Billing and Cost Management → Budgets.
- Check **Cost Explorer** monthly, filtered by tag or by the resource
  names this project's Terraform creates (`quote-aws-lambda-python*`).
- The `infrastructure/outputs.tf` resource names/ARNs make it easy to
  find this project's specific line items in a shared AWS account.

## Sources and caveats

Figures above come from AWS's public pricing pages (`aws.amazon.com/lambda/pricing`,
`/api-gateway/pricing`, `/dynamodb/pricing/on-demand`, `/cognito/pricing`,
`/cloudwatch/pricing`), read at the time this doc was written, for
**us-east-1**, and are rounded/approximate - not a quote. AWS pricing and
free-tier terms change over time and vary by region; confirm current,
region-specific numbers with the
[AWS Pricing Calculator](https://calculator.aws) before treating any
figure here as exact.
