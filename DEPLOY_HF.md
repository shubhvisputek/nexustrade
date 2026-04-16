# Deploying NexusTrade to Hugging Face Spaces

A free, always-on demo of the full NexusTrade dashboard + FastAPI in a single
Hugging Face Space. Setup time: **~15 minutes**. Cost: **$0/month**.

---

## What you'll end up with

- **Live demo URL**: `https://huggingface.co/spaces/<your-username>/nexustrade-demo`
- Streamlit dashboard on the front
- FastAPI backend on `localhost:8085` inside the container
- Real Redis via Upstash (free)
- Bring-Your-Own LLM key — visitors paste their own Anthropic / OpenAI / Groq key
- Auto-redeploys every time you push to `main`

---

## Prerequisites

You should already have:

1. ✅ A Hugging Face account — <https://huggingface.co/join>
2. ✅ A Hugging Face access token with **Write** scope —
   <https://huggingface.co/settings/tokens>
3. ✅ An Upstash Redis database — <https://console.upstash.com>
4. ✅ Push access to this GitHub repository

---

## Step 1: Create the Hugging Face Space (3 min)

1. Go to <https://huggingface.co/new-space>
2. Fill in:
   - **Space name**: `nexustrade-demo`
   - **License**: `Apache 2.0`
   - **Space SDK**: select **Docker → Blank**
   - **Hardware**: `CPU basic — 16 GB RAM, free`
   - **Visibility**: `Public`
3. Click **Create Space**
4. You'll land on an empty Space repo. Leave it — the GitHub Action will fill it.

---

## Step 2: Add secrets to the Hugging Face Space (2 min)

These secrets are exposed as environment variables to your container.

1. Open your Space → **Settings** tab → **Variables and secrets**
2. Click **New secret** for each of the following:

| Name | Value | Required? |
|------|-------|-----------|
| `REDIS_URL` | Your Upstash connection string (`rediss://default:...@...upstash.io:6379`) | Recommended |
| `ANTHROPIC_API_KEY` | Optional — only if you want a default key for visitors | Optional |
| `OPENAI_API_KEY` | Optional — only if you want a default key for visitors | Optional |
| `GROQ_API_KEY` | Optional — Groq's free tier works well for demos | Optional |

> **Recommendation**: leave the LLM keys **unset**. Visitors will paste their
> own key in the dashboard's BYO-key panel — you pay nothing for inference.

---

## Step 3: Add secrets to GitHub (3 min)

The deploy workflow needs these to push to your Space.

1. Open your GitHub repo → **Settings** → **Secrets and variables** →
   **Actions** → **New repository secret**
2. Add each:

| Name | Value |
|------|-------|
| `HF_TOKEN` | The token you generated in prerequisites (`hf_xxxxx...`) |
| `HF_USERNAME` | Your Hugging Face username |
| `HF_SPACE` | The Space name you used in Step 1 (e.g. `nexustrade-demo`) |

---

## Step 4: Trigger the first deploy (1 min)

You have two options:

### Option A — Push to main
```bash
git push origin main
```
The `Deploy to Hugging Face Spaces` workflow runs automatically.

### Option B — Run manually
1. Go to GitHub → **Actions** tab
2. Pick **Deploy to Hugging Face Spaces** in the left sidebar
3. Click **Run workflow** → **Run workflow**

Either way, monitor progress in the Actions tab. The push step takes ~30 seconds.

---

## Step 5: Watch the Space build (5–8 min, first time only)

1. Open `https://huggingface.co/spaces/<your-username>/nexustrade-demo`
2. The Space shows **Building...** while Docker builds the image
3. First build takes 5–8 minutes (downloading dependencies)
4. Subsequent builds are 1–2 minutes (cached layers)

When ready, the Streamlit dashboard appears in the embedded preview.

---

## Step 6: Try it

1. Open the Space URL
2. Navigate to **Configuration** in the left sidebar
3. Use the **Bring Your Own LLM Key** panel:
   - Pick a provider (Groq is free, Anthropic gives a $5 trial)
   - Paste your key, click **Save key for this session**
4. Go to **Agents & Signals** and trigger an analysis
5. Watch the agents debate, then see the aggregated signal in **Portfolio &
   Trading**. Paper-trading only — no real orders are ever sent.

---

## Updating the demo

Just push to `main`:
```bash
git push origin main
```

The GitHub Action triggers, the Space rebuilds. No manual steps.

---

## Troubleshooting

### "Build failed" in the Space
- Click **Logs** in the Space UI to see the Docker build output.
- Most common cause: a Python dependency missing from the `[web,agents,
  execution]` extras. Add it to `pyproject.toml` and push again.

### Dashboard loads but says "Backend unreachable"
- The FastAPI process inside the container takes ~15 s to start. Refresh.
- Check Space logs for `[nexustrade] FastAPI is healthy` — if missing, the
  start script timed out waiting for `/health`.

### "Sign in required" when visitors load it
- Your Space is set to **Private**. Open Space settings → **Visibility** →
  **Public**.

### Want to add Ollama (local LLM)?
- The free CPU tier doesn't have enough disk space for an 8B model.
- Upgrade to a paid GPU Space, OR switch to Oracle Cloud Free Tier
  (4 ARM cores, 24 GB RAM) which can host the full `docker-compose` stack
  including Ollama.

---

## Cost summary

| Component | Plan | Cost |
|-----------|------|------|
| Hugging Face Space | CPU basic (free) | $0/mo |
| Upstash Redis | Free tier (256 MB) | $0/mo |
| LLM inference | BYO-key | $0/mo (paid by visitor) |
| GitHub Actions | Public repo | $0/mo |
| **Total** | | **$0/mo** |

---

## What if I outgrow the free tier?

| Need | Upgrade path | Cost |
|------|--------------|------|
| More RAM / faster CPU | HF Space → CPU upgrade | $0.03/hr (~$22/mo if always on) |
| Local LLM (Ollama) | HF Space → Nvidia T4 small | $0.40/hr (~$290/mo) |
| Larger Redis | Upstash → Pro Redis | $0.20/100k cmds |
| Self-host full stack | Oracle Cloud Free Tier ARM VM | $0/mo (always free) |

---

## Reference

- HF Spaces docs: <https://huggingface.co/docs/hub/spaces>
- Docker Spaces docs: <https://huggingface.co/docs/hub/spaces-sdks-docker>
- Upstash Redis docs: <https://upstash.com/docs/redis>
