# Security Considerations — DreamHome Realty AI Sales Agent

## Overview

This document outlines security considerations for the AI Sales Voice Agent.
The current implementation is an MVP for local development and demonstration.
Production deployments require additional security measures.

---

## 1. API Key Protection

### Current Implementation
- Gemini API key stored in `.env` file (never in source code)
- `.gitignore` excludes `.env` from version control
- Key accessed via `python-dotenv` at runtime
- API key value never displayed in the UI

### Production Requirements
- Use cloud secrets management: AWS Secrets Manager, GCP Secret Manager, or Azure Key Vault
- Rotate API keys regularly (every 90 days recommended)
- Use service accounts with minimum required permissions
- Monitor API key usage for anomalies

```bash
# WRONG - never hardcode keys
GEMINI_API_KEY = "AIza..."  # ❌

# CORRECT - use environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # ✅
```

---

## 2. Environment Variable Security

### Current Implementation
- `.env.example` documents required variables without real values
- `.env` is in `.gitignore`
- Configuration validated at startup

### Production Requirements
- Inject secrets via CI/CD pipeline environment variables
- Never log environment variable values
- Audit all code for accidental secret logging

---

## 3. Customer Data Minimization

### Current Implementation
- Only collects data voluntarily provided by customers
- No tracking, analytics, or profiling beyond stated purpose
- Sample customers use fictional data only
- No real personal information in the codebase

### Production Requirements
- **Consent**: Collect explicit consent before recording voice or storing data
- **Purpose limitation**: Use data only for stated real estate advisory purpose
- **Retention policy**: Define and enforce data retention limits
- **Right to deletion**: Implement customer data deletion API

---

## 4. Audio Data Policy

### Current Implementation
- Audio processed locally by Faster-Whisper
- Temporary audio files stored in `audio_temp/` (not committed to git)
- TTS audio generated per-request and not persisted beyond the session

### Production Requirements
- Define audio retention policy (e.g., 30 days or delete immediately after transcription)
- Encrypt stored audio files
- Never send audio to third-party services without explicit consent disclosure
- If using cloud STT APIs, review their data retention terms

---

## 5. Database Security

### Current Implementation
- SQLite database excluded from git via `.gitignore`
- Parameterized SQL queries throughout (no string concatenation)
- No passwords or API keys stored in database
- WAL mode and foreign key constraints enabled

### Production Requirements
- **Encryption at rest**: PostgreSQL with TDE or encrypted storage volumes
- **Encryption in transit**: TLS/SSL for all database connections
- **Access control**: Database user with minimum required permissions
- **Backup encryption**: Encrypted database backups
- **Audit logging**: Log all database access

---

## 6. Web Application Security

### Current Implementation (Streamlit)
- Streamlit runs locally with no network exposure by default
- No user authentication implemented (MVP scope)

### Production Requirements
- **HTTPS only**: TLS certificates via Let's Encrypt or cloud provider
- **Authentication**: JWT-based auth or OAuth 2.0 (Google, GitHub SSO)
- **RBAC**: Separate roles for agents, managers, and admins
- **CSRF protection**: Built into modern frameworks (FastAPI, Django)
- **XSS prevention**: Escape all user-generated content
- **Rate limiting**: Prevent brute force and abuse
- **WAF**: Block common attack patterns

---

## 7. Logging Policy

### Current Implementation
- Logs written to `logs/app.log`
- Log level configurable via environment variable
- No customer PII in log messages at INFO level

### Production Requirements
- **Structured logging**: JSON format for log aggregation
- **No PII in logs**: Mask phone numbers, emails, and financial data
- **Log retention**: Define retention period (e.g., 90 days)
- **Centralized logging**: ELK Stack, CloudWatch, or Datadog
- **Alerting**: Alert on error rate spikes or suspicious patterns

---

## 8. Privacy Considerations

### GDPR / PDPA Compliance (for production)
- Obtain informed consent before data collection
- Publish a clear Privacy Policy
- Allow customers to request their data (data portability)
- Allow customers to delete their data (right to erasure)
- Appoint a Data Protection Officer if required
- Report data breaches within 72 hours

### Voice Data Specifically
- Inform customers that conversations are recorded or processed by AI
- Obtain consent before voice interaction begins
- Do not use voice data for training AI models without explicit consent

---

## 9. Infrastructure Security (Production)

- **Network segmentation**: Separate VPC/subnet for database tier
- **Security groups**: Restrict inbound traffic to only required ports
- **IAM roles**: Use least-privilege IAM roles for cloud services
- **Vulnerability scanning**: Regular dependency audits (`pip audit`, Snyk)
- **Penetration testing**: Annual third-party pen test for production
- **DDoS protection**: AWS Shield / GCP Armor

---

## 10. What This MVP Does NOT Include

The following are known limitations of the MVP:

| Feature | MVP Status | Production Requirement |
|---------|-----------|----------------------|
| User authentication | ❌ Not implemented | Required |
| HTTPS | ❌ Local HTTP | Required |
| Data encryption at rest | ❌ Plaintext SQLite | Required |
| Audit logging | ❌ Basic logs only | Required |
| Rate limiting | ❌ Not implemented | Required |
| Customer consent flow | ❌ Not implemented | Required |
| GDPR compliance | ❌ Not applicable (demo) | Required for production |
| Penetration testing | ❌ Not performed | Required |

---

## Summary

The MVP is designed for demonstration purposes on a local machine.
It demonstrates architectural good practices (no hardcoded keys, parameterized queries,
`.gitignore` protection) but requires significant additional security work
before any production deployment involving real customer data.
