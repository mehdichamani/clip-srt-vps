import asyncio
import html
import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, Depends, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from telegram import Update

from app.config import settings
from app.telegram_bot import create_telegram_application
from app.services.job_tracker import job_tracker

# Configure Structured Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("clip_srt_bot")

ptb_app = None
effective_admin_password: Optional[str] = None
security = HTTPBasic(auto_error=False)


def get_effective_admin_password() -> str:
    """Returns configured ADMIN_PASSWORD or generates a session password printed to logs."""
    global effective_admin_password
    if effective_admin_password is None:
        if settings.admin_password:
            effective_admin_password = settings.admin_password
            logger.info("Using configured ADMIN_PASSWORD from environment for /dashboard access.")
        else:
            effective_admin_password = secrets.token_hex(4)  # Simple 8-char random password
            logger.info("==========================================================")
            logger.info("🔑 ADMIN_PASSWORD not set in environment.")
            logger.info(f"🔑 Generated session admin password for /dashboard access: {effective_admin_password}")
            logger.info(f"🔑 Access dashboard at: /dashboard?key={effective_admin_password}")
            logger.info("==========================================================")
    return effective_admin_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to handle Telegram Bot initialization & Webhook registration."""
    global ptb_app
    logger.info("Starting up Clip SRT Bot v2...")
    
    # Initialize / log effective admin password
    get_effective_admin_password()
    
    settings.validate_keys()

    # Initialize JobTracker database persistence if DATABASE_URL is configured
    job_tracker.init_db()
    
    # Initialize Telegram Bot Application with retry resilience
    ptb_app = create_telegram_application()
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Initializing Telegram Application (attempt {attempt}/{max_retries})...")
            await ptb_app.initialize()
            await ptb_app.start()
            break
        except Exception as e:
            logger.error(f"Failed to initialize Telegram Application on attempt {attempt}: {e}")
            if attempt == max_retries:
                logger.critical("Maximum initialization retries reached. Raising exception.")
                raise
            await asyncio.sleep(2 * attempt)

    # Automatically set Telegram Webhook URL if RENDER_EXTERNAL_URL is provided
    if settings.render_external_url:
        base_url = settings.render_external_url.rstrip("/")
        webhook_url = f"{base_url}/webhook"
        logger.info(f"Setting Telegram webhook URL to: {webhook_url}")
        
        kwargs = {"url": webhook_url}
        if settings.webhook_secret:
            kwargs["secret_token"] = settings.webhook_secret
            
        for attempt in range(1, max_retries + 1):
            try:
                await ptb_app.bot.set_webhook(**kwargs)
                logger.info("Telegram webhook URL set successfully.")
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt} to set Telegram webhook failed: {e}")
                if attempt == max_retries:
                    logger.error("Failed to set Telegram webhook after multiple attempts. Continuing startup.")
                else:
                    await asyncio.sleep(2 * attempt)
    else:
        logger.warning(
            "RENDER_EXTERNAL_URL is not configured. Telegram webhook URL was not auto-set. "
            "Please set RENDER_EXTERNAL_URL in your environment or set webhook manually."
        )

    yield

    # Clean shutdown
    logger.info("Shutting down Telegram Bot Application...")
    if ptb_app:
        try:
            await ptb_app.stop()
            await ptb_app.shutdown()
        except Exception as e:
            logger.error(f"Error during Telegram bot shutdown: {e}")
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Clip SRT Bot v2",
    description="Cloud-native Telegram Bot for video subtitle generation and Persian translation",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
@app.head("/")
@app.get("/health")
@app.head("/health")
async def health_check():
    """Health check endpoint for Render service monitoring."""
    return {
        "status": "healthy",
        "service": "clip-srt-bot-v2",
        "webhook_configured": bool(settings.render_external_url)
    }


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None)
):
    """Explicit Telegram Webhook endpoint receiving HTTP POST updates."""
    if not ptb_app:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram Application is not initialized."
        )

    # Webhook secret validation using constant-time comparison
    if settings.webhook_secret:
        if not x_telegram_bot_api_secret_token or not secrets.compare_digest(
            x_telegram_bot_api_secret_token, settings.webhook_secret
        ):
            logger.warning("Received webhook request with invalid secret token.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid secret token"
            )

    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        # Process update asynchronously in background task to avoid Telegram webhook timeout
        asyncio.create_task(ptb_app.process_update(update))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing Telegram webhook update: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}


@app.get("/admin")
async def admin_redirect(key: Optional[str] = Query(None), password: Optional[str] = Query(None)):
    """Redirect /admin to /dashboard preserving query authentication parameters."""
    target = "/dashboard"
    param = key or password
    if param:
        target += f"?key={param}"
    return RedirectResponse(url=target)


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(
    key: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
    credentials: Optional[HTTPBasicCredentials] = Depends(security)
):
    """Dashboard UI visualizing in-memory job operations and status logs."""
    expected_password = get_effective_admin_password()
    provided_pass = key or password

    authenticated = False
    if provided_pass and secrets.compare_digest(provided_pass, expected_password):
        authenticated = True
    elif credentials and credentials.password and secrets.compare_digest(credentials.password, expected_password):
        authenticated = True

    if not authenticated:
        return HTMLResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="Dashboard Access"'},
            content="""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <title>401 Unauthorized - Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen">
    <div class="bg-slate-900 border border-slate-800 p-8 rounded-2xl max-w-md text-center shadow-2xl">
        <div class="text-4xl mb-4">🔒</div>
        <h1 class="text-2xl font-bold text-white mb-2">Access Denied</h1>
        <p class="text-slate-400 text-sm mb-6">You must provide a valid admin password or query parameter to access the dashboard.</p>
        <p class="text-xs text-slate-500 font-mono bg-slate-950 py-2 px-3 rounded-lg border border-slate-800">
            Use: /dashboard?key=YOUR_PASSWORD or HTTP Basic Auth
        </p>
    </div>
</body>
</html>"""
        )

    stats = job_tracker.get_stats()
    jobs = job_tracker.get_jobs()

    # Build Table Rows HTML
    table_rows = []
    if not jobs:
        table_rows.append("""
            <tr>
                <td colspan="6" class="px-6 py-8 text-center text-slate-500 italic">
                    No bot requests recorded yet. Incoming jobs will appear here in real-time.
                </td>
            </tr>
        """)
    else:
        for job in jobs:
            st = job.get("status", "pending")
            if st == "done":
                badge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Done</span>'
            elif st == "processing":
                badge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse">Processing</span>'
            elif st == "pending":
                badge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">Pending</span>'
            elif st == "canceled":
                badge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">Canceled</span>'
            else:
                badge = '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">Error</span>'

            job_id_esc = html.escape(str(job.get("job_id", "")))
            user_id_esc = html.escape(str(job.get("user_id", "")))
            username_esc = html.escape(str(job.get("username", "")))
            input_esc = html.escape(str(job.get("input_url_or_file", "")))
            err_esc = html.escape(str(job.get("error_message", "")))
            time_esc = html.escape(str(job.get("formatted_time", "")))

            table_rows.append(f"""
                <tr class="hover:bg-slate-800/40 transition-colors">
                    <td class="px-6 py-4 font-mono text-xs text-indigo-400 font-semibold">{job_id_esc}</td>
                    <td class="px-6 py-4">
                        <div class="font-medium text-slate-200">{username_esc}</div>
                        <div class="text-xs text-slate-500 font-mono">ID: {user_id_esc}</div>
                    </td>
                    <td class="px-6 py-4 max-w-xs truncate" title="{input_esc}">{input_esc}</td>
                    <td class="px-6 py-4">{badge}</td>
                    <td class="px-6 py-4 max-w-xs text-xs text-rose-400 font-mono truncate" title="{err_esc}">{err_esc or '<span class="text-slate-600">-</span>'}</td>
                    <td class="px-6 py-4 text-right text-xs text-slate-400 font-mono whitespace-nowrap">{time_esc}</td>
                </tr>
            """)

    rows_html = "".join(table_rows)
    has_active_processing = stats["pending_processing"] > 0
    pulse_indicator = '<span class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping inline-block ml-1"></span>' if has_active_processing else ''

    db_active = stats.get("db_active", False)
    storage_subtext = "Persisted in PostgreSQL DB" if db_active else "Tracked in memory (max 100)"
    storage_badge = '<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"><span class="w-2 h-2 rounded-full bg-indigo-400"></span>PostgreSQL DB</span>' if db_active else '<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-800 text-slate-400 border border-slate-700">In-Memory</span>'

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="10">
    <title>Clip SRT Bot - Operations Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://rsms.me/inter/inter.css">
    <style>
        body {{ font-family: 'Inter', sans-serif; }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
    <!-- Header -->
    <header class="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center space-x-3">
                <div class="w-10 h-10 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 text-xl font-bold">
                    🎬
                </div>
                <div>
                    <h1 class="text-xl font-bold text-white tracking-tight">Clip SRT Bot — Dashboard</h1>
                    <p class="text-xs text-slate-400">Live Bot Operations & Request Monitoring</p>
                </div>
            </div>
            <div class="flex items-center space-x-4 text-xs text-slate-400">
                {storage_badge}
                <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                    System Active
                </span>
                <span class="hidden sm:inline">Auto-refreshes every 10s</span>
                <button onclick="window.location.reload()" class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition flex items-center gap-1.5 shadow-sm">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                    Refresh
                </button>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <!-- Summary Cards Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <!-- Total Requests -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg shadow-black/20">
                <div class="flex items-center justify-between text-slate-400 mb-3">
                    <span class="text-xs font-semibold uppercase tracking-wider">Total Requests</span>
                    <div class="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center">📊</div>
                </div>
                <div class="text-3xl font-extrabold text-white">{stats['total']}</div>
                <div class="text-xs text-slate-500 mt-2">{storage_subtext}</div>
            </div>

            <!-- Completed -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg shadow-black/20">
                <div class="flex items-center justify-between text-slate-400 mb-3">
                    <span class="text-xs font-semibold uppercase tracking-wider">Completed</span>
                    <div class="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">✅</div>
                </div>
                <div class="text-3xl font-extrabold text-emerald-400">{stats['completed']}</div>
                <div class="text-xs text-slate-500 mt-2">Successfully delivered</div>
            </div>

            <!-- Pending / Processing -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg shadow-black/20">
                <div class="flex items-center justify-between text-slate-400 mb-3">
                    <span class="text-xs font-semibold uppercase tracking-wider">Pending / Processing</span>
                    <div class="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">⏳</div>
                </div>
                <div class="text-3xl font-extrabold text-amber-400 flex items-center">
                    {stats['pending_processing']} {pulse_indicator}
                </div>
                <div class="text-xs text-slate-500 mt-2">Currently in pipeline</div>
            </div>

            <!-- Failed / Canceled -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg shadow-black/20">
                <div class="flex items-center justify-between text-slate-400 mb-3">
                    <span class="text-xs font-semibold uppercase tracking-wider">Failed / Canceled</span>
                    <div class="w-8 h-8 rounded-lg bg-rose-500/10 text-rose-400 flex items-center justify-center">❌</div>
                </div>
                <div class="text-3xl font-extrabold text-rose-400">{stats['failed']}</div>
                <div class="text-xs text-slate-500 mt-2">Errors or user cancellations</div>
            </div>
        </div>

        <!-- Data Table Section -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl overflow-hidden shadow-xl shadow-black/30">
            <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/40">
                <h2 class="text-base font-semibold text-white flex items-center gap-2">
                    <span>📋</span> Recent Request Log
                </h2>
                <span class="text-xs text-slate-400 font-mono">Total: {len(jobs)} requests</span>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-950/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                        <tr>
                            <th scope="col" class="px-6 py-3.5">Job ID</th>
                            <th scope="col" class="px-6 py-3.5">User</th>
                            <th scope="col" class="px-6 py-3.5">Input / Media</th>
                            <th scope="col" class="px-6 py-3.5">Status</th>
                            <th scope="col" class="px-6 py-3.5">Details / Error</th>
                            <th scope="col" class="px-6 py-3.5 text-right">Timestamp</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-800/60 bg-slate-900/20">
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    </main>
</body>
</html>"""
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
