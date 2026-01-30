# Deployment Guide

Step-by-step instructions for deploying the 0DTE GEX Monitor to production.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Vercel       │────▶│    Railway      │────▶│   PostgreSQL    │
│   (Frontend)    │     │   (Backend)     │     │   (Railway)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## Prerequisites

- GitHub account with repository access
- [Vercel](https://vercel.com) account
- [Railway](https://railway.app) account
- [Polygon.io](https://polygon.io) API key (free tier works)

---

## Backend Deployment (Railway)

### Step 1: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository
4. Railway will auto-detect the `backend` folder

### Step 2: Configure Build Settings

If auto-detection fails, set manually in Railway dashboard:

| Setting        | Value                                              |
| -------------- | -------------------------------------------------- |
| Root Directory | `backend`                                          |
| Build Command  | `pip install -r requirements.txt`                  |
| Start Command  | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

### Step 3: Add PostgreSQL Database

1. In your Railway project, click **"New"** → **"Database"** → **"PostgreSQL"**
2. Railway automatically sets the `DATABASE_URL` environment variable

### Step 4: Set Environment Variables

In Railway dashboard → **Variables** tab:

| Variable          | Value                             | Required |
| ----------------- | --------------------------------- | -------- |
| `POLYGON_API_KEY` | Your Polygon.io API key           | ✅ Yes   |
| `ENVIRONMENT`     | `production`                      | ✅ Yes   |
| `DEBUG`           | `false`                           | ✅ Yes   |
| `CORS_ORIGINS`    | `["https://your-app.vercel.app"]` | ✅ Yes   |
| `DATABASE_URL`    | Auto-set by Railway               | Auto     |

> **Important:** Update `CORS_ORIGINS` with your actual Vercel domain after deploying frontend.

### Step 5: Deploy

1. Railway auto-deploys on push to main branch
2. Check **Deployments** tab for build logs
3. Get your backend URL from **Settings** → **Domains**

**Expected URL format:** `https://your-project.up.railway.app`

### Step 6: Verify Backend

```bash
# Health check
curl https://your-project.up.railway.app/health

# Expected response:
{
  "status": "healthy",
  "environment": "production",
  "checks": {
    "api": "healthy",
    "polygon_api_key": "configured",
    "cache": "healthy"
  }
}
```

---

## Frontend Deployment (Vercel)

### Step 1: Import Project

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click **"Add New..."** → **"Project"**
3. Import your GitHub repository
4. Set **Root Directory** to `frontend`

### Step 2: Configure Build Settings

Vercel auto-detects Next.js. Verify settings:

| Setting          | Value        |
| ---------------- | ------------ |
| Framework Preset | Next.js      |
| Root Directory   | `frontend`   |
| Build Command    | `pnpm build` |
| Output Directory | `.next`      |

### Step 3: Set Environment Variables

In Vercel dashboard → **Settings** → **Environment Variables**:

| Variable              | Value                                  | Required |
| --------------------- | -------------------------------------- | -------- |
| `NEXT_PUBLIC_API_URL` | `https://your-project.up.railway.app`  | ✅ Yes   |
| `NEXT_PUBLIC_WS_URL`  | `wss://your-project.up.railway.app/ws` | ✅ Yes   |

> **Note:** Use `wss://` (secure WebSocket) for production.

### Step 4: Deploy

1. Click **"Deploy"**
2. Vercel builds and deploys automatically
3. Get your frontend URL from the dashboard

**Expected URL format:** `https://your-app.vercel.app`

### Step 5: Update Backend CORS

After frontend deploys, update Railway backend:

```bash
# In Railway Variables:
CORS_ORIGINS=["https://your-app.vercel.app"]
```

Redeploy backend to apply changes.

---

## Custom Domain (Optional)

### Vercel (Frontend)

1. Go to **Settings** → **Domains**
2. Add your domain (e.g., `gex.yourdomain.com`)
3. Configure DNS:
   ```
   CNAME  gex  cname.vercel-dns.com
   ```

### Railway (Backend)

1. Go to **Settings** → **Domains**
2. Add custom domain (e.g., `api.yourdomain.com`)
3. Configure DNS:
   ```
   CNAME  api  your-project.up.railway.app
   ```

---

## Environment Variables Summary

### Backend (Railway)

```env
# Required
POLYGON_API_KEY=pk_xxxxx
ENVIRONMENT=production
DEBUG=false
CORS_ORIGINS=["https://your-app.vercel.app"]

# Auto-set by Railway
DATABASE_URL=postgresql+asyncpg://...
PORT=...

# Optional
API_RATE_LIMIT=100
WS_AUTH_ENABLED=false
```

### Frontend (Vercel)

```env
# Required
NEXT_PUBLIC_API_URL=https://your-backend.up.railway.app
NEXT_PUBLIC_WS_URL=wss://your-backend.up.railway.app/ws

# Optional
NEXT_PUBLIC_GA_ID=G-XXXXXXXXXX
```

---

## Troubleshooting

### Backend Issues

| Issue                     | Solution                                    |
| ------------------------- | ------------------------------------------- |
| `503 Service Unavailable` | Check `POLYGON_API_KEY` is set              |
| CORS errors               | Verify `CORS_ORIGINS` includes frontend URL |
| WebSocket fails           | Use `wss://` instead of `ws://`             |
| Health check fails        | Check Railway deployment logs               |

### Frontend Issues

| Issue          | Solution                                |
| -------------- | --------------------------------------- |
| API calls fail | Verify `NEXT_PUBLIC_API_URL` is correct |
| Build fails    | Check Node version compatibility        |
| Blank page     | Check browser console for errors        |

### Database Issues

| Issue              | Solution                                |
| ------------------ | --------------------------------------- |
| Connection refused | Ensure PostgreSQL is running in Railway |
| Auth failed        | Check `DATABASE_URL` format             |

---

## Monitoring

### Railway Metrics

- CPU/Memory usage in Railway dashboard
- Request logs in **Deployments** tab

### Vercel Analytics

- Enable Vercel Analytics for Core Web Vitals
- View in **Analytics** tab

### Health Endpoint

Monitor `/health` endpoint for uptime:

- Use services like UptimeRobot, Pingdom, or Railway's built-in monitoring

---

## Rollback

### Railway

1. Go to **Deployments** tab
2. Find previous successful deployment
3. Click **"Redeploy"**

### Vercel

1. Go to **Deployments** tab
2. Find previous deployment
3. Click **"..."** → **"Promote to Production"**

---

## Cost Estimates

| Service        | Free Tier                        | Paid             |
| -------------- | -------------------------------- | ---------------- |
| **Vercel**     | 100GB bandwidth, 100 deployments | $20/mo (Pro)     |
| **Railway**    | $5 credit/mo, 500 hours          | Pay-as-you-go    |
| **Polygon.io** | 5 req/min, delayed data          | $29/mo (Starter) |

> **Tip:** Free tiers are sufficient for demo/portfolio projects.
