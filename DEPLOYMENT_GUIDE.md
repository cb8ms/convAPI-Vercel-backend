# Deploying to Vercel

## Steps to Deploy:

1. **Install Vercel CLI**:
   \`\`\`bash
   npm i -g vercel
   \`\`\`

2. **Set Environment Variables in Vercel**:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET` 
   - `REDIRECT_URI` (should be your Vercel domain + /api/auth/callback)
   - `PROJECT_ID`
   - `FRONTEND_URL` (your frontend domain)

3. **Deploy**:
   \`\`\`bash
   vercel --prod
   \`\`\`

## Key Changes Made:

- Added `mangum` adapter to convert FastAPI to ASGI for Vercel
- Created `vercel.json` configuration for Python runtime
- Updated CORS settings for production
- Modified redirect URLs to use environment variables
- Added `api/index.py` as the main entry point

## Environment Variables Setup:

In your Vercel dashboard, add these environment variables:
- Set `REDIRECT_URI` to `https://your-domain.vercel.app/api/auth/callback`
- Set `FRONTEND_URL` to your frontend domain
- Add all your Google OAuth credentials

## File Structure:
\`\`\`
/api
  ├── index.py (main FastAPI app with Mangum handler)
  ├── auth.py (updated with production URLs)
  ├── agents.py (unchanged)
  ├── chat.py (unchanged)
  └── chart_utils.py (unchanged)
vercel.json (Vercel configuration)
requirements.txt (added mangum dependency)
