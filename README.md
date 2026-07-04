# YoChat Deploy-Ready Version

This cleaned version separates the project into two deployable parts:

- `frontend/` — React + Vite user interface
- `backend/` — FastAPI WebSocket backend for Gemini Live audio conversation

The old Express/Node backend files were removed from the active app structure to avoid deployment conflicts.

## 1. Local backend test

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# add your GEMINI_API_KEY in .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000/health
```

Expected result:

```json
{"status":"healthy","key_configured":true}
```

## 2. Local frontend test

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open:

```text
http://localhost:5173
```

## 3. Deploy backend on Render

Create a new **Web Service** from GitHub.

Use these settings:

```text
Root Directory: backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Add this environment variable in Render:

```text
GEMINI_API_KEY=your_real_key
```

After deploy, test:

```text
https://your-render-service.onrender.com/health
```

## 4. Deploy frontend on Vercel

Create a new Vercel project.

Use these settings:

```text
Root Directory: frontend
Build Command: npm run build
Output Directory: dist
```

Add this environment variable in Vercel:

```text
VITE_BACKEND_URL=https://your-render-service.onrender.com
```

Do not add `/ws/live` at the end. The React app adds it automatically.

## 5. Important deployment note

For microphone and WebSocket audio to work online, the frontend must be on HTTPS and the backend WebSocket must use WSS. This is handled automatically when `VITE_BACKEND_URL` starts with `https://`.
