# Scalability Strategy — DreamHome Realty AI Sales Agent

## From MVP to 1,00,000 Users

This document explains how the current MVP (suitable for local development
and demonstration) can be evolved to support production scale.

---

## Important Distinction: Registered vs. Concurrent Users

| Metric | Definition | Implication |
|--------|-----------|-------------|
| 1,00,000 Registered Users | Total accounts in the system | Database size, storage needs |
| 1,00,000 Concurrent Users | Active at the same moment | Server capacity, real-time load |

**The current MVP cannot support 1,00,000 concurrent users.** It runs on a
single process, uses SQLite (file-based), and has no load balancing.

A well-architected production system with horizontal scaling could handle
tens of thousands of concurrent users, but this requires substantial
infrastructure investment as described below.

---

## Current MVP Architecture (Local)

```
Customer Browser → Streamlit (single process) → SQLite + ChromaDB (local files)
```

**Limitations:**
- Single-threaded Streamlit server
- SQLite: not suitable for concurrent writes (WAL mode helps but has limits)
- ChromaDB local: no sharding or replication
- No authentication, rate limiting, or monitoring
- Whisper runs synchronously on CPU

---

## Target Production Architecture

```
                              ┌─────────────────┐
                              │   Load Balancer  │
                              │  (AWS ALB / GCP) │
                              └────────┬─────────┘
                                       │
                    ┌──────────────────┼───────────────────┐
                    ▼                  ▼                    ▼
             ┌──────────┐      ┌──────────┐         ┌──────────┐
             │ App Pod 1│      │ App Pod 2│         │ App Pod N│
             │(FastAPI) │      │(FastAPI) │         │(FastAPI) │
             └──────────┘      └──────────┘         └──────────┘
                    │                 │                    │
                    └─────────────────┴────────────────────┘
                                      │
              ┌───────────────────────┼──────────────────────┐
              ▼                       ▼                      ▼
    ┌──────────────────┐  ┌───────────────────┐  ┌──────────────────┐
    │  PostgreSQL RDS  │  │  Pinecone/Weaviate │  │   Redis Cache    │
    │  (Managed DB)    │  │  (Vector DB SaaS)  │  │  (Session store) │
    └──────────────────┘  └───────────────────┘  └──────────────────┘
              │
    ┌─────────┴──────────┐
    ▼                    ▼
┌───────┐          ┌──────────┐
│Celery │          │  S3 /    │
│Workers│          │ GCS Audio│
│(async)│          │ Storage  │
└───────┘          └──────────┘
```

---

## Key Scaling Strategies

### 1. Backend Framework Migration (Streamlit → FastAPI)
- Streamlit is excellent for prototypes but not designed for high concurrency
- **Migrate to FastAPI** for the backend API + React/Vue for the frontend
- FastAPI handles thousands of async requests per second
- WebSockets for real-time voice interaction

### 2. Docker Containerization
```dockerfile
# Example Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--workers", "4"]
```
- Package the application as Docker containers
- Deploy to Kubernetes (EKS, GKE, AKS) for orchestration
- Horizontal Pod Autoscaler scales pods based on CPU/memory

### 3. Database: SQLite → PostgreSQL
- SQLite: file-based, good for MVP, limited concurrent writes
- **PostgreSQL**: battle-tested, supports thousands of connections
- Use PgBouncer for connection pooling
- Read replicas for dashboard/reporting queries
- Partitioning for large tables (conversations, messages)

```
SQLite (MVP) → PostgreSQL (1,000 users) → Sharded PostgreSQL (1,00,000+ users)
```

### 4. Vector Database: ChromaDB → Pinecone/Weaviate
- Local ChromaDB doesn't support multi-node clustering
- **Pinecone (SaaS)**: fully managed, scales automatically
- **Weaviate**: self-hosted, supports billion-scale vectors
- Both support metadata filtering for property/knowledge search

### 5. Load Balancing and Horizontal Scaling
- AWS Application Load Balancer or GCP Cloud Load Balancing
- Distribute traffic across multiple application replicas
- Sticky sessions (or JWT tokens) for conversation state
- Regional deployment to minimize latency

### 6. Asynchronous Processing with Job Queues
Heavy operations should not block the main request:
- **Celery + Redis**: process Whisper transcription async
- **Background tasks**: TTS generation, summary creation, lead scoring
- **Job queue**: appointment reminders, follow-up emails

```
Request → API → Push to Queue → Worker processes → Response via WebSocket/polling
```

### 7. API Rate Limiting
- Per-user rate limits (e.g., 100 messages/hour)
- API gateway (AWS API Gateway, Kong): enforce limits before reaching app
- Redis for distributed rate limit counters
- Protect against abuse and cost overruns

### 8. Caching
- **Redis**: cache AI responses for common queries
- **CDN** (CloudFront): serve static assets
- **Response caching**: cache property listings (refresh every 15 min)
- **Embedding cache**: cache embeddings for frequently queried texts

### 9. Speech Processing at Scale
- **Whisper API (OpenAI)** or **Google Speech-to-Text API** instead of local Whisper
- Remove CPU bottleneck of running Whisper on each server
- Pay-per-use pricing scales with actual usage
- For TTS: **Google Cloud TTS** or **Azure Neural TTS** API

### 10. Monitoring and Logging
- **Prometheus + Grafana**: metrics dashboards
- **ELK Stack** (Elasticsearch + Logstash + Kibana): centralized logs
- **Sentry**: error tracking with alerting
- **CloudWatch / GCP Monitoring**: infrastructure metrics
- **OpenTelemetry**: distributed tracing across services

---

## Cost Considerations at Scale

### Local MVP (Current)
- Hardware: student laptop ✅ Free
- Gemini API: free tier (60 RPM) ✅ Free for development
- Storage: local disk ✅ Free

### Small Production (1,000 monthly active users)
- Cloud VM (2 vCPU, 4GB): ~\$30-50/month
- PostgreSQL RDS (smallest): ~\$15-25/month
- Gemini API (est. 10K calls/month): ~\$1-5/month (verify current pricing)
- Total estimated: ~\$50-80/month

### Medium Production (10,000 monthly active users)
- Kubernetes cluster (3 nodes): ~\$150-300/month
- PostgreSQL RDS Multi-AZ: ~\$100-200/month
- Redis (cache): ~\$30-50/month
- Pinecone (vector DB): ~\$70-100/month
- Gemini/Speech API: ~\$50-200/month (depends on usage)
- Total estimated: ~\$400-850/month

*Note: All prices are illustrative estimates. Verify current cloud provider pricing before budgeting.*

---

## Security at Scale

Additional requirements for production:
- **Authentication**: OAuth 2.0 / JWT tokens for agent login
- **Customer privacy**: GDPR/PDPA compliance for voice data
- **Data encryption**: TLS in transit, AES-256 at rest
- **Audit logging**: all data access logged
- **RBAC**: role-based access (agent, manager, admin)
- **API secrets management**: AWS Secrets Manager / GCP Secret Manager
- **WAF**: Web Application Firewall for DDoS protection

---

## Summary Table

| Component | MVP (Current) | Production Target |
|-----------|--------------|-------------------|
| Framework | Streamlit | FastAPI + React |
| Database | SQLite | PostgreSQL RDS |
| Vector DB | ChromaDB (local) | Pinecone / Weaviate |
| Cache | None | Redis |
| STT | Local Whisper | Google/Azure STT API |
| TTS | Edge TTS | Google/Azure TTS API |
| Deployment | Local Python | Docker + Kubernetes |
| Monitoring | Logs only | Prometheus + Grafana |
| Scale | 1 user | 10,000+ concurrent |
