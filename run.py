"""Start Job Dedo: python run.py  ->  http://localhost:8000"""

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

if __name__ == "__main__":
    if not (Path(__file__).parent / "web" / "dist" / "index.html").exists():
        sys.exit("The web app isn't built yet. Run once:  cd web && npm install && npm run build")
    parser = argparse.ArgumentParser(description="Run the Job Dedo web app")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, (url,)).start()
    print(f"Job Dedo running at {url}  (Ctrl+C to stop)")
    # 127.0.0.1 only: your keys and contacts are never reachable from other machines
    uvicorn.run("job_applier.api:app", host="127.0.0.1", port=args.port, reload=args.reload, log_level="warning")
