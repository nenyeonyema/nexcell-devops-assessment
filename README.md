# NexCell DevOps Internship Assessment

## About Me
* **Name:** Chinenye Genevieve Onyema
* **Time Spent:** 3 hours

### AI Tools Used
I used ChatGPT as a development and review assistant to help reason through the assessment requirements, review implementation decisions, and identify inconsistencies between the Dockerfile, Docker Compose configuration, and the required deployment behaviour.

I did not treat generated suggestions as the final implementation. I reviewed the decisions against the assessment requirements and kept the implementation deliberately small because the task specifically asks for a minimal stub application and warns against overbuilding.

One deliberate decision was to keep the database migration as a small `app/migrate.py` script rather than introducing a full migration framework. The purpose of the stub is to demonstrate safe migration ordering, not to implement the customer's complete business database.

---

## 1. Solution Overview

I built a minimal containerised FastAPI application representing the API and background worker described in the assessment.

### Delivered
* **FastAPI Monitoring:** `/health` liveness endpoint and `/ready` readiness endpoint.
* **Health Checks:** PostgreSQL and Redis connectivity checks.
* **Queue Processing:** Redis-backed background worker.
* **Database Management:** One-off PostgreSQL migration executed before API/worker startup.
* **Containerization:** Production-oriented Docker image shared by API and worker.
* **Orchestration:** Docker Compose health checks, dependency ordering, resource limits, restart policies, and log rotation.
* **Testing:** Smoke tests covering API, Redis, and worker.
* **Configuration:** `.env.example` for runtime configuration without committing secrets.
* **CI/CD:** GitHub Actions workflow with image build, testing, and an AWS OIDC deployment path.

*The implementation is intentionally small because the assessment requires a representative application rather than business functionality.*

---

## 2. Build and Run

```bash
cp .env.example .env
docker compose build
docker compose up -d
```

### Startup Order

```text
PostgreSQL
    ↓ healthy
Migration
    ↓ successful
API + Worker
```

### Verify the API

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

**Expected liveness response:**
```json
{"status":"alive"}
```

### Run the Complete Smoke Test

```bash
bash smoke_test.sh
```

*The test returns a non-zero exit code when a required check fails.*

---

## 3. Dockerfile and Compose Decisions

The supplied development-oriented Dockerfile was changed to a production-oriented image.

### Key Decisions
* Pinned Python base image and application dependencies for reproducible builds.
* Installed dependencies before copying application code to improve Docker layer caching.
* Runs as a dedicated non-root `appuser`.
* No secrets are embedded in the image.
* Removed development `--reload` behaviour.
* Added container health checking.
* One image is used for both API and worker; Compose overrides the worker command.

### Dependencies (`requirements.txt`)
```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
redis==5.0.8
psycopg2-binary==2.9.9
```

### Migration Safety
Migration is a separate Compose service. It waits for PostgreSQL to become healthy and must complete successfully before API and worker services start. This directly prevents the deployment-order problem identified in the assessment.

### Resource and Reliability Controls
Long-running services have:
* CPU and memory limits matching the assessment's workload requirements.
* `restart: unless-stopped`.
* Log rotation.

*The migration service uses `restart: "no"` so a failed migration does not repeatedly retry against an uncertain database state.*

---

## 4. CI/CD

The CI pipeline:
1. Builds the production image.
2. Tags the image with the Git commit SHA.
3. Starts the complete Compose stack.
4. Runs the smoke tests.
5. Proceeds to deployment only after build and tests succeed.

The deployment path uses GitHub Actions OIDC $\rightarrow$ AWS IAM role rather than long-lived AWS access keys.

```text
GitHub Actions
      ↓ OIDC
AWS IAM Role
      ↓ temporary credentials
AWS Resources
```

*Using commit SHA image tags makes deployed artifacts traceable to the exact source revision.*

---

## 5. AWS Production Design

I would deploy the application using ECS Fargate rather than introducing Kubernetes, keeping the production design consistent with the assessment and avoiding unnecessary complexity.

```text
                    Internet
                       │
                  CloudFront
                       │
                      ALB
                       │
             ┌─────────┴─────────┐
             │                   │
        ECS API             ECS Worker
             │                   │
             └─────────┬─────────┘
                       │
                ┌──────┴──────┐
                │             │
           ElastiCache    Managed DB
              Redis       PostgreSQL
```

* **ECR** $\rightarrow$ Images
* **Secrets Manager** $\rightarrow$ Secrets
* **CloudWatch** $\rightarrow$ Logs/Alarms
* **IAM/OIDC** $\rightarrow$ CI/CD

ECS tasks would run in private subnets across multiple Availability Zones. Only the ALB would be publicly accessible. Redis, PostgreSQL, and ECS tasks would not have direct public access.

Security controls include least-privilege IAM, security groups, Secrets Manager, and OIDC authentication for CI/CD.

### Deployment and Rollback

```text
Build + Test
     ↓
Build SHA-tagged image
     ↓
Push to ECR
     ↓
New ECS task revision
     ↓
Health checks
     ↓
Traffic shifted to healthy tasks
```

*A failed deployment remains protected by ECS health checks and rolling deployment behaviour, allowing the previous healthy revision to remain available.*

### Initial Monitoring Alarms

| Alarm | Initial Threshold | Reason |
| :--- | :--- | :--- |
| **API 5xx errors** | >5% for 5 minutes | Detect application failures |
| **API latency** | >1 second for 5 minutes | Detect degraded customer experience |
| **Worker queue depth** | >100 jobs for 5 minutes | Detect processing backlog |

*These are initial thresholds and should be adjusted using production baselines.*

---

## 6. Cost Review

The assessment gives an AWS cost of approximately £1,415/month for 20 customers. To achieve the required £45/customer/month target, AWS costs must be below approximately £900/month.

| Area | Current | Target | Saving |
| :--- | :--- | :--- | :--- |
| **Staging** | £260 | £80 | £180 |
| **Workers** | £190 | £100 | £90 |
| **NAT Gateway** | £140 | £70 | £70 |
| **API** | £210 | £150 | £60 |
| **CloudWatch** | £95 | £40 | £55 |
| **Redis** | £150 | £100 | £50 |
| **Admin instance** | £55 | £20 | £35 |
| **Vector DB** | £130 | £110 | £20 |

**Projected AWS cost:** £855/month  
**At 20 customers:**

$$
\frac{£855}{20} = £42.75/\text{customer/month}
$$

The main savings come from scheduling staging/admin workloads, right-sizing API/worker/Redis capacity, reducing unnecessary NAT traffic, and controlling CloudWatch log volume and retention.

I would **not** remove production observability purely to reduce cost. Instead, I would control log levels, retention, and unnecessary ingestion.

*The separate £900/month LLM API cost is excluded because it is identified separately from the AWS total in the assessment.*

---

## 7. Production Considerations

### Scaling to 100 Customers
API and worker capacity can scale independently. ECS autoscaling can respond to API resource/request metrics, while worker capacity can respond to Redis queue depth.

Infrastructure should therefore scale according to actual workload rather than assuming that five times the customers automatically requires five times the infrastructure.

### Biggest Production Risk
The main risk identified in the assessment is unsafe database/application deployment ordering. The deployment sequence is therefore:

```text
Database healthy
      ↓
Migration succeeds
      ↓
Application starts
      ↓
Health checks pass
      ↓
Traffic shifts
```

*Backward-compatible database changes should also be used where possible so old and new application versions can coexist during rolling deployments.*

### Intentionally Kept Simple
I did not introduce Kubernetes, Terraform, or a large application framework because the assessment explicitly states that they are not required and asks candidates to avoid overbuilding.

**With additional time, I would add:**
1. Alembic database migrations.
2. Container/image vulnerability scanning.
3. Worker integration tests.
4. An ECS deployment proof of concept.
5. Validation of AWS cost estimates against actual usage/pricing.

---

## 8. Repository Structure

```text
nexcell-devops-assessment/
├── app/
│   ├── main.py
│   ├── worker.py
│   └── migrate.py
├── .github/
│   └── workflows/
│       └── ci.yml
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── README.md
├── requirements.txt
└── smoke_test.sh
```


