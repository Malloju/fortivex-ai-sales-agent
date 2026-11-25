# Cost Estimation — DreamHome Realty AI Sales Agent

## Overview

This document provides cost estimates for running the AI Sales Agent.
All prices are illustrative estimates based on publicly known pricing models
as of late 2024. **Verify current pricing with each provider before budgeting.**

---

## 1. Local Development (Current MVP)

| Component | Cost |
|-----------|------|
| Hardware (student laptop) | ₹0 (already owned) |
| Python and open-source libraries | ₹0 (free) |
| Gemini API (free tier: 60 RPM, 1M TPD) | ₹0 for development |
| Edge TTS | ₹0 (uses Microsoft Edge servers, free for personal use) |
| Faster-Whisper (local CPU) | ₹0 (runs on device) |
| SQLite + ChromaDB (local files) | ₹0 |
| **Total MVP development cost** | **₹0** |

**Note**: The free Gemini tier is subject to rate limits. For heavy testing, a paid tier may be needed.

---

## 2. AI API Costs (Gemini)

Google AI pricing uses a per-token model. Prices below are illustrative.

**Formula**: Cost = (Input tokens + Output tokens) × Price per 1M tokens

**Assumptions for estimation**:
- Average conversation: 10 turns
- Average input per turn: ~500 tokens (context + profile + RAG)
- Average output per turn: ~200 tokens
- Tokens per conversation: ~7,000

| Usage Level | Conversations/month | Est. tokens | Approx. cost (USD) |
|-------------|--------------------|-----------|--------------------|
| Development | 100 | 700K | Free tier |
| Small Demo | 1,000 | 7M | ~$1-5* |
| Small Business | 10,000 | 70M | ~$10-50* |
| Medium Business | 1,00,000 | 700M | ~$100-500* |

*Verify exact current pricing at [Google AI Pricing](https://ai.google.dev/pricing)

---

## 3. Speech-to-Text Costs

### Faster-Whisper (Current — Local)
- **Cost: ₹0** (runs on device CPU)
- Limitation: Slower on CPU; requires compute time
- Suitable for: Development, demonstration

### Cloud STT (Production Alternative)

| Provider | Approx. price per minute | Notes |
|---------|--------------------------|-------|
| Google Cloud STT | ~$0.016/min (standard) | First 60 min/month free |
| Azure STT | ~$0.015/min | First 5 hours/month free |
| OpenAI Whisper API | ~$0.006/min | Most affordable cloud option |

**Estimation for 1,000 calls × 5 min average**:
- Google Cloud STT: ~$80/month
- OpenAI Whisper API: ~$30/month

---

## 4. Text-to-Speech Costs

### Edge TTS (Current)
- **Cost: ₹0** (uses Microsoft Edge infrastructure; free for personal/demo use)
- Limitation: Requires internet connection; not suitable for high-volume commercial use

### Cloud TTS (Production Alternative)

| Provider | Approx. price per million characters | Notes |
|---------|--------------------------------------|-------|
| Google Cloud TTS | ~$16/M chars (Standard), ~$160/M (Neural) | 1M chars/month free |
| Azure Neural TTS | ~$16/M chars | 500K chars/month free |
| AWS Polly | ~$16/M chars | 5M chars/month free (first year) |

**Estimation for 1,000 responses × 500 chars average**:
- 500K chars/month → Google Cloud free tier covers this
- Beyond free tier: ~$8-80/month depending on voice type

---

## 5. Database Costs

### SQLite (Current)
- **Cost: ₹0** (local file)

### PostgreSQL Production

| Provider | Tier | Approx. monthly cost (USD) |
|---------|------|---------------------------|
| AWS RDS PostgreSQL | db.t3.micro (1 vCPU, 1 GB) | ~$15-25 |
| AWS RDS PostgreSQL | db.t3.small (2 vCPU, 2 GB) | ~$30-50 |
| Supabase (managed) | Free (500MB limit) | $0 |
| Supabase (Pro) | 8 GB storage | ~$25 |
| Railway | Basic plan | ~$5+ |

---

## 6. Vector Database Costs

### ChromaDB Local (Current)
- **Cost: ₹0** (local file storage)

### Cloud Vector DB (Production)

| Provider | Free tier | Paid tier |
|---------|-----------|-----------|
| Pinecone | 1 index, 1M vectors | From ~$70/month |
| Weaviate Cloud | 14-day trial | From ~$25/month |
| Supabase pgvector | Included with Supabase | No additional cost |

---

## 7. Cloud Hosting Costs (Production)

### Small Deployment (1,000 MAU)

| Component | Service | Approx. monthly (USD) |
|-----------|---------|----------------------|
| Application server | AWS EC2 t3.small | ~$15-20 |
| Load balancer | AWS ALB | ~$16 |
| Database | RDS t3.micro | ~$20 |
| Cache | Redis (ElastiCache t3.micro) | ~$15 |
| Storage | S3 (audio files) | ~$1-5 |
| Networking/misc | Various | ~$5-10 |
| **Subtotal infrastructure** | | **~$72-86/month** |
| AI APIs (Gemini + STT + TTS) | | ~$20-50/month |
| **Total small production** | | **~$90-140/month** |

### Medium Deployment (10,000 MAU)

| Component | Approx. monthly (USD) |
|-----------|----------------------|
| Kubernetes cluster (3 nodes) | ~$150-300 |
| PostgreSQL RDS Multi-AZ | ~$100-200 |
| Redis cluster | ~$50-80 |
| Vector DB (Pinecone Starter) | ~$70 |
| AI APIs | ~$100-300 |
| Monitoring (Datadog/New Relic) | ~$30-80 |
| **Total medium production** | **~$500-1,030/month** |

---

## 8. Summary

| Stage | Monthly Cost (USD) | Monthly Cost (INR approx.) |
|-------|-------------------|---------------------------|
| Local MVP (development) | $0 | ₹0 |
| Demo / Testing | $0-5 | ₹0-420 |
| Small production (1K MAU) | $90-140 | ₹7,500-12,000 |
| Medium production (10K MAU) | $500-1,030 | ₹42,000-86,000 |
| Large production (1L MAU) | $5,000-15,000+ | ₹4.2L-12.5L+ |

---

## Disclaimer

All cost estimates are based on illustrative assumptions and publicly
available pricing as of late 2024. Cloud pricing changes frequently.
Always calculate costs based on your actual usage patterns using the
official pricing calculators of each cloud provider:

- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
- [AWS Pricing Calculator](https://calculator.aws)
- [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/)
- [Google AI Studio Pricing](https://ai.google.dev/pricing)
