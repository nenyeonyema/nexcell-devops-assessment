# NexCell DevOps Internship Assessment

## About Me
* **Name:** Chinenye Genevieve Onyema
* **Time Spent:** 3 hours

### AI Tools Used
I used ChatGPT as a development and review assistant to help reason through the assessment requirements, review implementation decisions, and identify inconsistencies between the Dockerfile, Docker Compose configuration, and the required deployment behaviour.

I did not treat generated suggestions as the final implementation. I reviewed the decisions against the assessment requirements and kept the implementation deliberately small because the task specifically asks for a minimal stub application and warns against overbuilding.

One deliberate decision was to keep the database migration as a small `app/migrate.py` script rather than introducing a full migration framework. The purpose of the stub is to demonstrate safe migration ordering, not to implement the customer's complete business database.

---

## Build and Run

### What I Delivered
I built a small containerised FastAPI application that represents the production API and background worker described in the assessment.

The implementation contains:
* `GET /health` for application liveness.
* `GET /ready` for dependency readiness.
* Redis connectivity checking.
* PostgreSQL connectivity checking.
* A Redis-backed worker that consumes jobs from the configured queue.
* A one-off PostgreSQL migration step that must complete successfully before the API and worker start.
* A production-oriented Docker image shared by the API and worker.
* Docker Compose health checks, dependency ordering, resource limits, restart policies, and log rotation.
* A smoke-test script that independently checks the API, Redis, and worker.
* An environment example file instead of committing secrets.

The application is intentionally small because the assessment does not require business logic; it requires a working representative application on which the containerisation and operational decisions can be demonstrated.

### Run Locally

1. **Create the local environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Build the application image:**
   ```bash
   docker compose build
   ```

3. **Start the stack:**
   ```bash
   docker compose up
   ```

#### Startup Order
```text
PostgreSQL
    │
    │ healthy
    ▼
Migration
    │
    │ successful
    ▼
API + Worker
```

4. **Access and verify the API:**
   * The API is available at: `http://localhost:8000`
   * Verify liveness:
     ```bash
     curl http://localhost:8000/health
     ```
     **Expected response:** `{"status":"alive"}`
   * Verify readiness:
     ```bash
     curl http://localhost:8000/ready
     ```

5. **Run the complete smoke test:**
   ```bash
   bash smoke_test.sh
   ```
   *The smoke test returns a non-zero exit code if any required check fails, making it suitable for CI.*

---

## Dockerfile Decisions

I replaced the supplied development-oriented Dockerfile with a production-oriented image.

### Key Changes
* **Pinned Base Image:** Used a pinned slim Python base image rather than `python:latest`, giving the build a predictable base.
* **Pinned Dependencies:** Pinned Python dependencies in `requirements.txt` for reproducible installations.
* **Dependency Caching:** Copied `requirements.txt` and installed dependencies before copying application code.
* **Security:** Executed using a dedicated, non-root `appuser`.
* **Secret Hygiene:** Kept secrets out of the image; environment-specific values are supplied at runtime.
* **Production ASGI Configuration:** Used Uvicorn without `--reload`.
* **Health Checks:** Configured container health checks using the `/health` endpoint.
* **Shared Image:** Utilized one image for both the API and worker, with the worker overriding the default command in Compose.

These changes directly address the supplied Dockerfile's use of an unpinned base image, embedded secret, development reload mode, and weaker dependency/build practices.

### Dependency Reproducibility
I pinned the application dependencies:
```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
redis==5.0.8
psycopg2-binary==2.9.9
```
This prevents a future build from silently installing different dependency versions when the application code has not changed.

### Migration Safety
* The Compose stack uses a separate one-off migration service.
* The migration waits for PostgreSQL to become healthy, runs the migration, and must exit successfully before the API and worker are allowed to start.
* This addresses the existing risk described in the assessment where application code and database migrations had previously been deployed in the wrong order.

## 3. docker-compose.yml
 
The main decision here was ordering: `migrate` has to finish successfully before `api` or `worker` start, not just be "started." I used the completion-condition form of `depends_on` rather than a healthcheck on `migrate` itself, because a migration isn't a long-running service with a meaningful health state — it either finishes cleanly or it doesn't, and the deploy should stop on the second case rather than proceeding against a schema that isn't ready. This is a direct fix for the failure mode described in the current-state notes, where migrations have shipped on the wrong side of the code change in both directions.
 
I set CPU and memory limits on every service to match the real task sizes from the current-state table (API at 1 vCPU / 2 GB, worker at 2 vCPU / 4 GB) rather than picking convenient round numbers, because the brief explicitly checks whether these numbers agree with the cost review — I wanted the compose file, the Dockerfile's worker count, and the README's numbers to all be telling the same story rather than three plausible-looking but inconsistent ones.
 
Log size limits and a `restart: unless-stopped` policy went on every long-running service; `migrate` gets `restart: "no"` deliberately, since a migration that failed shouldn't retry itself blindly on a crash loop.
 
---
 
## 4. CI/CD
 
I built this to answer one question honestly: does the pipeline stay green with no real AWS account behind it, while still proving the deploy path is real? The build-and-test job builds the production image, tags it with the commit SHA (so every artifact is traceable back to the exact code that produced it), starts the full stack, and runs the smoke test against it — this is meant to catch the same class of failure a reviewer running `docker compose up` locally would hit, before it reaches a PR review.
 
The deploy job is separate and gated on the first job passing. I used OIDC rather than access keys because that's the fix for a risk stated directly in the brief: long-lived keys sitting in GitHub secrets is a real, named problem in the current pipeline, not a hypothetical one. I made the deploy job skip cleanly rather than fail when there's no real role configured, because a placeholder deploy job that turns the whole pipeline red isn't proving anything useful about my CI design — it's just proving I don't have an AWS account for this exercise, which isn't the same thing.

---

## 5. smoke_test.sh
 
I wrote this to check liveness, readiness, Redis, and the worker as four separate, individually-reported checks rather than one pass/fail for "the stack." The reasoning: if this fails in CI, I want the failure message to tell me which of the four things broke, not just that something did. I set a short timeout on every network check so a hung dependency fails the test quickly instead of stalling the CI job.
 

---

## AWS Design

### Target Architecture
I would run the production application on AWS ECS Fargate without introducing Kubernetes, keeping the architecture consistent with the assessment's existing platform and its instruction not to overbuild.

```text
                         Internet
                            │
                       CloudFront
                            │
                            ▼
                           ALB
                            │
                ┌───────────┴───────────┐
                │                       │
          ECS Fargate API        ECS Fargate Worker
                │                       │
                └──────────┬────────────┘
                           │
                 ┌─────────┴─────────┐
                 │                   │
              Redis             PostgreSQL
            ElastiCache          managed DB

        Supporting services:
        ECR → container images
        Secrets Manager → application secrets
        CloudWatch → logs and alarms
        IAM/OIDC → CI/CD authentication
```

The ECS services would run in private subnets, with the ALB providing the application entry point. Redis and the application database would not be publicly accessible.
[O
### Networking and Security
* **VPC Setup:** A VPC spanning multiple Availability Zones.
* **Subnets:** Public subnets for the internet-facing ALB; private subnets for ECS tasks and internal services.
* **Access Control:** Security groups allowing only the required traffic between services. No direct public access to Redis, PostgreSQL, or ECS tasks.
* **Secrets & Identity:** AWS Secrets Manager for runtime secrets and IAM roles using least privilege.
* **CI/CD Authentication:** GitHub Actions authenticated to AWS using OIDC rather than long-lived AWS access keys.

#### OIDC Authentication Model
```text
GitHub Actions
      │
      │ OIDC identity
      ▼
AWS IAM role
      │
      │ temporary credentials
      ▼
AWS resources
```
This addresses the current use of long-lived AWS access keys in GitHub Secrets described in the assessment.

### Deployment and Rollback
Container images are built and tagged using the Git commit SHA rather than mutable tags such as `latest`.

```text
Pull Request
    │
    ▼
Build + Test + Smoke Test
    │
    ▼
Merge
    │
    ▼
Build immutable SHA image
    │
    ▼
Push to ECR
    │
    ▼
Deploy new ECS task revision
    │
    ▼
Health checks pass
    │
    ▼
Traffic moves to healthy tasks
```

ECS health checks and rolling deployment provide the zero-downtime mechanism. If the new revision fails health checks, the previous healthy revision remains available and can be restored.

### First Three Monitoring Alarms

| Alarm | Initial Threshold | Reason |
| :--- | :--- | :--- |
| **API 5xx error rate** | >5% for 5 minutes | Detect application failures |
| **API latency** | >1 second for 5 minutes | Detect degraded customer experience |
| **Worker queue depth** | >100 jobs for 5 minutes | Detect processing backlog |

*These thresholds are initial operational assumptions and should be tuned using real production baselines.*

---

## Cost Review

The assessment gives a current AWS cost of approximately £1,415/month for 20 customers, or about £70.75/customer/month. The target is below £45/customer/month, meaning AWS needs to be below approximately £900/month at today's customer count.

*Note: The following are planning estimates based on the costs supplied in the assessment, not AWS price quotations.*

### Main Savings

| Change | Current | Estimated New Cost | Estimated Saving | Risk |
| :--- | :--- | :--- | :--- | :--- |
| Schedule/right-size staging | £260 | £80 | £180 | Low/Medium |
| Right-size/scale workers according to queue demand | £190 | £100 | £90 | Medium |
| Reduce NAT Gateway usage where appropriate | £140 | £70 | £70 | Medium |
| Right-size API capacity | £210 | £150 | £60 | Medium |
| Reduce CloudWatch log volume and retention | £95 | £40 | £55 | Low |
| Right-size Redis | £150 | £100 | £50 | Medium |
| Schedule the office-hours admin instance | £55 | £20 | £35 | Low |
| Right-size vector DB instance | £130 | £110 | £20 | Medium |

### Projected AWS Cost

```text
Current AWS cost                         £1,415
Estimated total savings                   -£560
-----------------------------------------------
Projected AWS cost                        £855/month
```

**At 20 customers:**
$$\text{Cost per customer} = \frac{£855}{20} = £42.75/\text{customer/month}$$

This puts the projected AWS cost below the required **£45/customer/month** target.

### Why I Chose These Savings
1. **Staging:** The assessment says staging is a full copy of production and costs £260/month while running 24/7. Since production traffic has a strong weekday pattern, I would schedule staging to run during development/testing periods rather than maintaining a full production-sized environment continuously.
2. **Workers:** The queue is empty approximately 70% of the time. Rather than maintaining two large worker tasks continuously, I would scale worker capacity based on queue depth and maintain sufficient minimum capacity for required 24/7 processing.
3. **NAT Gateways:** NAT gateways are currently costing £140/month. I would reduce unnecessary NAT traffic by using appropriate VPC endpoints for AWS services such as ECR, S3, CloudWatch, and Secrets Manager where suitable, while keeping the network design secure.
4. **API:** The API averages only 12% CPU utilisation. I would right-size the service and use ECS autoscaling based on workload rather than permanently maintaining more capacity than required.
5. **CloudWatch Logs:** The assessment identifies DEBUG logging and approximately £95/month in CloudWatch Logs. I would use appropriate production log levels and defined retention periods while keeping enough logs for troubleshooting and incident investigation.
6. **Redis:** Redis is using only 8% of available memory. I would review actual memory, connection, and throughput requirements and move to an appropriately sized instance rather than paying for unused capacity.
7. **Admin Instance:** The admin tool is only required during office hours. I would schedule the instance to stop outside those hours while ensuring it can be started when required.
8. **Vector Database:** I would review the vector workload and right-size the EC2 instance based on actual CPU, memory, storage, and query requirements rather than maintaining excess capacity.

*The separate £900/month LLM API cost is not included in the AWS reduction calculation, because the assessment identifies it separately from the AWS total.*

### One Cost I Deliberately Would Not Cut
I would **not** remove production observability simply to reduce the bill.

Logs, metrics, and alarms are necessary to detect errors, latency problems, and queue backlogs before they become customer-facing incidents. Instead, I would control observability cost through:
* Appropriate log levels.
* Defined retention policies.
* Log filtering where appropriate.
* Useful metrics and alarms instead of collecting unnecessary DEBUG data indefinitely.

I would monitor CloudWatch usage and set a cost alert so that an unexpected increase in log ingestion or other AWS usage is detected early.

---

## Judgement

### Scaling from 20 to 100 Customers
* The design separates the API and worker workloads so that they can scale independently.
* For API traffic, ECS can scale tasks according to CPU, memory, and request/latency metrics.
* For background processing, worker capacity should respond to queue depth rather than simply running a fixed number of large tasks.
* Redis provides the queue/cache layer, while the database remains a managed dependency.
* The architecture therefore avoids assuming that five times the customers automatically requires five times the infrastructure. Capacity should be driven by actual workload.

### Biggest Production Risk
My biggest production risk would be an **unsafe application/database deployment**.

The assessment already identifies previous incidents where migrations and application code were deployed in the wrong order. My first fix is therefore to make migrations an explicit deployment step:

```text
Database healthy
       ↓
Migration succeeds
       ↓
Application starts
       ↓
Health checks pass
       ↓
Traffic is shifted
```

I would also use backward-compatible database changes where possible so that the old and new application versions can coexist during a rolling deployment.

### What I Intentionally Kept Simple
I intentionally did not introduce Kubernetes, Terraform, or a large application framework.

The assessment explicitly says that Kubernetes is not required, Terraform/CDK is not required, and overbuilding should be avoided. I kept the application to the minimum required API, worker, Redis, PostgreSQL, and migration components so that the assessment focuses on the DevOps problems rather than unnecessary application complexity.

### What I Would Do with Three More Hours
With additional time, I would:
1. Add a proper database migration framework such as Alembic.
2. Add automated container/image vulnerability scanning to CI.
3. Add integration tests that push a job into Redis and verify that the worker processes it.
4. Build a small ECS deployment proof of concept using GitHub Actions OIDC.
5. Validate the cost assumptions against actual AWS pricing and workload measurements.

---

## Repository Structure

```text
nexcell-devops-assessment/
│
├── app/
│   ├── main.py
│   ├── worker.py
│   └── migrate.py
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── README.md
├── requirements.txt
└── smoke_test.sh
```

---

## Final Verification

Before submission, I will verify:
```bash
docker compose config
docker compose build
docker compose up -d
bash smoke_test.sh
docker compose ps
docker compose logs
```

I will also verify that no real secrets are present in the repository or commit history before submitting.

The final repository will be submitted as `nexcell-devops-assessment` with the final commit SHA provided to NexCell as requested in the assessment.
