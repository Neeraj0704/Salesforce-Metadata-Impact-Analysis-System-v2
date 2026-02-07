"""FastAPI app entrypoint."""

import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.api.routes import auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="Salesforce Metadata Impact Analysis", version="0.1.0")
app.include_router(auth.router)


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    """Simple homepage with Sign in with Salesforce."""
    return """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Metadata Impact Analysis</title></head>
<body>
  <h1>Salesforce Metadata Impact Analysis</h1>
  <p><a href="/auth/salesforce">Sign in with Salesforce</a></p>
</body>
</html>
"""