# Serverless Pixel Canvas

A comprehensive r/place clone built with AWS Serverless services, featuring real-time WebSocket broadcasts, Discord integration, and production-ready observability.

## 📚 Documentation

### Getting Started
- **[Architecture Overview](DOC.md)** - System design, data models, services
- **[Deployment Guide](DEPLOYMENT.md)** - Step-by-step AWS SAM deployment
- **[API Reference](API.md)** - Complete REST & WebSocket API documentation

### Operations & Development  
- **[Environment Variables](ENVIRONMENT.md)** - Configuration reference for all services
- **[Monitoring & Runbook](MONITORING.md)** - Health checks, alerts, troubleshooting
- **[Progress Report](PROGRESS.md)** - Improvement status (16/20 items complete, 80% quality score)

### For Service Owners
Each serverless function has a detailed README:
- [auth/](serverless/auth) - Discord OAuth2
- [authorizer/](serverless/authorizer) - JWT validation
- [web_proxy/](serverless/web_proxy) - REST API entry
- [pixel_worker/](serverless/pixel_worker) - Pixel processing with rate limiting
- [broadcast_worker/](serverless/broadcast_worker) - WebSocket broadcasts (SQS fan-out)
- [canvas_reader/](serverless/canvas_reader) - Canvas state retrieval
- [snapshot_worker/](serverless/snapshot_worker) - PNG generation
- [discord_notifier/](serverless/discord_notifier) - Discord notifications (circuit breaker)
- [discord_proxy/](serverless/discord_proxy) - Slash command handling
- [websocket_manager/](serverless/websocket_manager) - Connection lifecycle
- [dlq_processor/](serverless/dlq_processor) - Failed message recovery

---

## 🚀 Quick Start

### Prerequisites
- AWS CLI configured with credentials
- AWS SAM CLI, Node.js, Python 3.12
- Discord Developer account

### Deploy Backend
```bash
# 1. Create AWS secrets
aws secretsmanager create-secret \
  --name DiscordSecrets \
  --secret-string '{"ClientId":"...","ClientSecret":"...","PublicKey":"...","AppId":"..."}'

aws secretsmanager create-secret \
  --name AppSecrets \
  --secret-string '{"JwtSecret":"your-random-secret"}'

# 2. Build & deploy
sam build
sam deploy --guided

# 3. Set CORS for production
sam deploy --parameter-overrides AllowedOrigin="'https://your-domain.com'"
```

### Deploy Frontend
```bash
cd frontend
npm install
npm run build
aws s3 sync dist/ s3://your-bucket/
```

---

## 📊 Project Quality

**Improvement Status:** Phase 1 ✅ | Phase 2 ✅ | Phase 3 (4/8) ⏳

| Category | Before | After | Impact |
|----------|--------|-------|--------|
| Test Coverage | 50% | 74% | +24% |
| Quality Score | 6.5/10 | 8.5/10 | +31% |
| Max Connections | 5k | 100k+ | 20× |
| Broadcast Efficiency | 100k API calls | 200 invocations | 500× |

See [PROGRESS.md](PROGRESS.md) for detailed improvements.

---

## 🛠️ Architecture Highlights

- **WebSocket Scaling:** 100k connections via SQS fan-out (Phase 2.9)
- **Circuit Breaker:** Automatic retries + DLQ recovery (Phase 2.11)
- **Auto-Cleanup:** TTL-based connection expiry (Phase 2.8)
- **Security:** Input validation, CORS restrictions, JWT auth (Phase 1)
- **Monitoring:** CloudWatch alarms, structured logging, incident runbooks (Phase 3.16)

---

## 📖 Key Features

✅ **Real-time Canvas:** 1000×1000 pixel grid updated live via WebSocket  
✅ **User Authentication:** Discord OAuth2 with JWT tokens  
✅ **Rate Limiting:** 20 pixels/minute per user with smart backoff  
✅ **Canvas Snapshots:** PNG generation + Discord slash command integration  
✅ **Production Ready:** Comprehensive tests, monitoring, and runbooks  

---

## 🔗 Useful Links

- **GitHub:** [Your repo]
- **Live Demo:** [Your deployment URL]
- **API Docs:** [Swagger UI if configured]
- **Discord Community:** [Your server]

