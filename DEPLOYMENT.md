# Deploy Cramly

This repo is set up for:

- Frontend: Vercel, deployed from `frontend/`
- Backend API: Render web service, deployed from `backend/`
- Database: Render Postgres
- File storage: Cloudflare R2, AWS S3, or another S3-compatible bucket

Do not deploy `.env`. Keep secrets in the hosting dashboards.

## 1. Prepare Storage

Create an S3-compatible bucket for uploads. Cloudflare R2 is a good beta option because it gives you an S3 endpoint, access key, secret key, and bucket name without running MinIO in production.

You need:

```text
S3_ENDPOINT_URL
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_BUCKET
```

## 2. Deploy Backend on Render

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from the GitHub repo.
3. Render will read `render.yaml` and create:
   - `cramly-api`
   - `cramly-postgres`
4. Fill every prompted secret:
   - `OPENAI_API_KEY`
   - `CORS_ORIGINS`
   - `S3_ENDPOINT_URL`
   - `S3_ACCESS_KEY_ID`
   - `S3_SECRET_ACCESS_KEY`
   - `S3_BUCKET`
   - `CRAMLY_INVITE_CODE`, only if you want invite-only signup

Use a temporary CORS value until the frontend exists:

```text
https://your-vercel-preview-url.vercel.app
```

After Render deploys, open:

```text
https://your-cramly-api.onrender.com/api/health
```

It should return JSON with `"ok": true`.

## 3. Deploy Frontend on Vercel

1. Import the same GitHub repo into Vercel.
2. Set the project Root Directory to `frontend`.
3. Keep the framework as Next.js.
4. Add environment variables:

```text
NEXT_PUBLIC_API_URL=https://your-cramly-api.onrender.com
NEXT_PUBLIC_REQUIRE_INVITE_CODE=false
NEXT_PUBLIC_ENABLE_DEV_RAG=false
```

If `CRAMLY_INVITE_CODE` is set on Render, set:

```text
NEXT_PUBLIC_REQUIRE_INVITE_CODE=true
```

Deploy the Vercel project.

## 4. Wire CORS

After Vercel gives you the real frontend URL, update Render:

```text
CORS_ORIGINS=https://your-cramly-frontend.vercel.app
```

Redeploy the backend after changing `CORS_ORIGINS`.

For a custom domain, put the final domain in both places:

```text
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
CORS_ORIGINS=https://yourdomain.com
```

## 5. Production Checklist

- `CRAMLY_ENV=beta` or `production`
- `CRAMLY_ALLOW_DEMO_MODE=false`
- `NEXT_PUBLIC_ENABLE_DEV_RAG=false`
- `CRAMLY_ENABLE_DEV_RAG` unset or `false`
- `JWT_SECRET` is long and private
- `.env` is never committed
- Uploads use S3/R2, not local MinIO
- `GET /api/health` works
- Register, login, upload, ask, flashcards, quizzes, and account deletion all work from the hosted frontend

## Notes

Render runs the API through Docker and the backend Dockerfile now binds to `${PORT:-8000}`. Vercel builds the Next.js frontend from `frontend/` and reads `NEXT_PUBLIC_*` variables at build time, so redeploy Vercel after changing those values.
