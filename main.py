#!/usr/bin/env python3
"""Automated Job Search Pipeline — daily collect, filter, score, and deliver."""

import logging
import os
import sys

from ai_scorer import score_top_jobs
from archive import save_daily_report
from dashboard import generate_dashboard
from dedup import init_db, is_duplicate, mark_as_sent, was_previously_sent
from filters import passes_hard_filters
from models import JobListing
from scorer import rule_based_score
from sources.builtin import BuiltInSource
from sources.crowdstrike import CrowdStrikeSource
from sources.greenhouse import GreenhouseSource
from sources.linkedin_alerts import LinkedInAlertsSource
from sources.remoteok import RemoteOKSource
from sources.weworkremotely import WeWorkRemotelySource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join("data", "seen_jobs.db") if os.path.isdir("data") else "seen_jobs.db"


def run_pipeline():
    """Execute the full job search pipeline."""

    # --- Phase 0: Initialize ---
    init_db(DB_PATH)

    # --- Phase 1: Collect ---
    logger.info("=== Phase 1: COLLECT ===")
    sources = [
        GreenhouseSource(),
        CrowdStrikeSource(),
        RemoteOKSource(),
        BuiltInSource(),
        WeWorkRemotelySource(),
        LinkedInAlertsSource(),
    ]

    raw_jobs = []
    for source in sources:
        raw_jobs.extend(source.safe_collect())

    logger.info(f"Collected {len(raw_jobs)} raw listings from {len(sources)} sources")

    if not raw_jobs:
        logger.warning("No jobs collected from any source. Exiting.")
        report = save_daily_report([])
        logger.info(f"Empty report saved to {report}")
        return []

    # --- Phase 2: Filter & Deduplicate ---
    logger.info("=== Phase 2: FILTER & DEDUPLICATE ===")

    # Hard filters
    filtered = [job for job in raw_jobs if passes_hard_filters(job)]
    logger.info(f"After hard filters: {len(filtered)} of {len(raw_jobs)} remain")

    # Cross-source dedup
    unique = []
    for job in filtered:
        if not is_duplicate(job, unique):
            unique.append(job)
    logger.info(f"After dedup: {len(unique)} unique listings")

    # Remove previously sent
    new_jobs = [job for job in unique if not was_previously_sent(job, DB_PATH)]
    logger.info(f"After seen-check: {len(new_jobs)} new listings")

    if not new_jobs:
        logger.info("No new jobs to report today.")
        report = save_daily_report([])
        logger.info(f"Empty report saved to {report}")
        return []

    # --- Phase 3: Score & Rank ---
    logger.info("=== Phase 3: SCORE (rule-based) ===")

    rule_scores = [rule_based_score(job) for job in new_jobs]

    logger.info("=== Phase 3b: SCORE (AI) ===")
    ai_results = score_top_jobs(new_jobs, rule_scores, top_n=15)

    # Combine into final scored list
    scored_jobs = []
    for job, r_score, ai_result in zip(new_jobs, rule_scores, ai_results):
        if ai_result and ai_result.get("fit_score"):
            total_score = r_score + ai_result["fit_score"]
            priority = ai_result.get("priority", "low")
            summary = ai_result.get("summary", "")
            key_matches = ai_result.get("key_matches", [])
            gaps = ai_result.get("gaps", [])
        else:
            total_score = r_score
            # Priority from rule-based score alone
            if r_score >= 30:
                priority = "high"
            elif r_score >= 20:
                priority = "medium"
            else:
                priority = "low"
            summary = ""
            key_matches = []
            gaps = []

        scored_jobs.append({
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "source": job.source,
            "score": total_score,
            "priority": priority,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "location": job.location,
            "posted_date": job.posted_date.isoformat(),
            "description": job.description[:3000],
            "summary": summary,
            "key_matches": key_matches,
            "gaps": gaps,
        })

    # Sort by score descending
    scored_jobs.sort(key=lambda j: j["score"], reverse=True)

    high = sum(1 for j in scored_jobs if j["priority"] == "high")
    med = sum(1 for j in scored_jobs if j["priority"] == "medium")
    logger.info(f"Scored {len(scored_jobs)} jobs: {high} high, {med} medium priority")

    # --- Phase 4: Deliver ---
    logger.info("=== Phase 4: DELIVER ===")

    # Archive as markdown report
    report = save_daily_report(scored_jobs)
    logger.info(f"Report saved to {report}")

    # Generate HTML dashboard
    dash = generate_dashboard(scored_jobs)
    logger.info(f"Dashboard saved to {dash}")

    # Mark all delivered jobs as seen
    for job_data in scored_jobs:
        stub = JobListing(
            title=job_data["title"],
            company=job_data["company"],
            url=job_data["url"],
            source=job_data["source"],
        )
        mark_as_sent(stub, score=job_data["score"], db_path=DB_PATH)

    logger.info(f"Marked {len(scored_jobs)} jobs as seen in database")
    logger.info("=== Pipeline complete ===")

    # Print summary
    print(f"\n{'='*50}")
    print(f"Daily Job Search Report")
    print(f"{'='*50}")
    print(f"Sources queried: {len(sources)}")
    print(f"Raw listings: {len(raw_jobs)}")
    print(f"After filtering: {len(new_jobs)}")
    print(f"High priority: {high}")
    print(f"Medium priority: {med}")
    print(f"Report: {report}")
    print(f"{'='*50}")

    return scored_jobs


def serve_dashboard(port: int = 8080):
    """Serve the reports directory over HTTP with an API to trigger new searches."""
    import http.server
    import json as _json
    import os
    import socketserver
    import threading
    import webbrowser

    import config
    from dashboard import generate_landing_page
    from user_profile import PROFILE_PATH, reload_profile

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")

    # Generate the landing page (index.html) on startup
    generate_landing_page(output_dir=reports_dir)
    project_dir = os.path.dirname(__file__)
    search_lock = threading.Lock()

    class DashboardHandler(http.server.SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=reports_dir, **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path == "/" or self.path == "":
                self.path = "/index.html"
            super().do_GET()

        def _check_origin(self):
            """Reject requests from non-localhost origins (CSRF protection)."""
            origin = self.headers.get("Origin", "")
            if origin and not origin.startswith(("http://localhost:", "http://127.0.0.1:")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Forbidden: non-localhost origin"}')
                return False
            return True

        def do_PUT(self):
            if not self._check_origin():
                return
            if self.path == "/api/profile":
                self._handle_save_profile()
            else:
                self.send_error(404)

        def do_POST(self):
            if not self._check_origin():
                return
            if self.path == "/api/search":
                self._handle_search()
            elif self.path == "/api/parse-resume":
                self._handle_parse_resume()
            elif self.path == "/api/analyze-text":
                self._handle_analyze_text()
            else:
                self.send_error(404)

        def _handle_save_profile(self):
            """Save profile JSON to disk."""
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"No request body"}')
                return
            if length > self._MAX_BODY:
                self.send_error(413, "Request body too large")
                return
            body = self.rfile.read(length)
            try:
                data = _json.loads(body)
            except _json.JSONDecodeError:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Invalid JSON"}')
                return
            if not self._validate_profile(data):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Invalid profile structure"}')
                return
            with open(PROFILE_PATH, "w") as f:
                _json.dump(data, f, indent=2)
            reload_profile()
            config.reload()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        _MAX_BODY = 1 * 1024 * 1024  # 1 MB for JSON endpoints

        def _validate_profile(self, data):
            """Validate profile JSON has correct structure and types."""
            if not isinstance(data, dict):
                return False
            if not isinstance(data.get("role_tags"), list):
                return False
            if not all(isinstance(t, str) for t in data["role_tags"]):
                return False
            sr = data.get("salary_range", {})
            if not isinstance(sr, dict):
                return False
            for key in ("min", "max", "floor"):
                if key in sr and not isinstance(sr[key], (int, float)):
                    return False
            # Field size limits
            summary = data.get("resume_summary", "")
            if isinstance(summary, str) and len(summary) > 10000:
                return False
            template = data.get("ai_prompt_template", "")
            if isinstance(template, str) and len(template) > 10000:
                return False
            for list_field in ("role_tags", "industry_tags", "skills", "priority_companies"):
                items = data.get(list_field, [])
                if isinstance(items, list) and len(items) > 50:
                    return False
            return True

        def _send_progress(self, message):
            """Send a progress line as NDJSON."""
            line = _json.dumps({"type": "progress", "message": message}) + "\n"
            try:
                self.wfile.write(line.encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _handle_search(self):
            # Read profile from request body
            length = int(self.headers.get("Content-Length", 0))
            if length > self._MAX_BODY:
                self.send_error(413, "Request body too large")
                return
            body = self.rfile.read(length) if length else b""

            if not search_lock.acquire(blocking=False):
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Search already in progress"}')
                return

            # Attach a log handler that streams progress to the client.
            # Uses root logger so all pipeline module logs are captured.
            # search_lock ensures only one search runs at a time, so no
            # cross-request pollution.
            class _ProgressHandler(logging.Handler):
                def __init__(self, callback):
                    super().__init__()
                    self._callback = callback
                def emit(self, record):
                    try:
                        self._callback(record.getMessage())
                    except Exception:
                        pass

            root_logger = logging.getLogger()
            stream_handler = _ProgressHandler(self._send_progress)
            stream_handler.setLevel(logging.INFO)

            try:
                # Start streaming response
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                root_logger.addHandler(stream_handler)

                # Save updated profile if provided
                profile_data = None
                if body:
                    profile_data = _json.loads(body)
                    if not self._validate_profile(profile_data):
                        profile_data = None

                if profile_data:
                    # If role tags changed, clear seen database so new keywords get fresh results
                    try:
                        with open(PROFILE_PATH) as f:
                            old_profile = _json.load(f)
                        old_tags = set(old_profile.get("role_tags", []))
                        new_tags = set(profile_data.get("role_tags", []))
                        if old_tags != new_tags:
                            db_path = os.path.join(project_dir, DB_PATH)
                            if os.path.exists(db_path):
                                os.remove(db_path)
                                self._send_progress("Role tags changed — cleared seen jobs database")
                    except (FileNotFoundError, _json.JSONDecodeError):
                        pass

                    with open(PROFILE_PATH, "w") as f:
                        _json.dump(profile_data, f, indent=2)
                    reload_profile()
                    config.reload()
                    self._send_progress("Profile updated")

                # Run the pipeline
                self._send_progress("Starting search pipeline...")
                scored_jobs = run_pipeline() or []

                # Send final result
                line = _json.dumps({"type": "result", "jobs": scored_jobs}) + "\n"
                self.wfile.write(line.encode())
                self.wfile.flush()

            except Exception as e:
                logger.error(f"Search pipeline failed: {e}", exc_info=True)
                try:
                    line = _json.dumps({"type": "error", "error": "Search pipeline failed"}) + "\n"
                    self.wfile.write(line.encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            finally:
                root_logger.removeHandler(stream_handler)
                search_lock.release()

        def _handle_parse_resume(self):
            """Handle resume file upload, extract text, generate profile tags via Ollama."""
            import base64

            from resume_parser import parse_resume

            MAX_UPLOAD = 15 * 1024 * 1024  # 15 MB (base64 overhead on 10 MB file)
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_UPLOAD:
                self.send_error(413, "Request body too large")
                return
            if not length:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"No request body"}')
                return

            body = self.rfile.read(length)

            try:
                data = _json.loads(body)
            except _json.JSONDecodeError:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Invalid JSON"}')
                return

            file_data = data.get("file")
            filename = data.get("filename", "resume.pdf")

            if not file_data:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Missing file field"}')
                return

            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".pdf", ".doc", ".docx"):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Unsupported file type. Upload a PDF or DOCX."}')
                return

            # Decode base64 (strip data URL prefix if present)
            try:
                if "," in file_data and file_data.startswith("data:"):
                    file_data = file_data.split(",", 1)[1]
                file_bytes = base64.b64decode(file_data)
            except Exception:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Invalid base64 data"}')
                return

            if len(file_bytes) > 10 * 1024 * 1024:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"File too large (max 10 MB)"}')
                return

            # Stream NDJSON response
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            try:
                result = parse_resume(
                    file_bytes, filename, progress_callback=self._send_progress
                )
                line = _json.dumps({"type": "result", "profile": result}) + "\n"
                self.wfile.write(line.encode())
                self.wfile.flush()

            except ValueError as e:
                line = _json.dumps({"type": "error", "error": str(e)}) + "\n"
                self.wfile.write(line.encode())
                self.wfile.flush()
            except Exception as e:
                logger.error(f"Resume parsing failed: {e}", exc_info=True)
                line = _json.dumps({"type": "error", "error": "Resume parsing failed"}) + "\n"
                self.wfile.write(line.encode())
                self.wfile.flush()

        def _handle_analyze_text(self):
            """Analyze pasted resume text and generate profile tags via Ollama."""
            from resume_parser import parse_resume_text

            length = int(self.headers.get("Content-Length", 0))
            if length > self._MAX_BODY:
                self.send_error(413, "Request body too large")
                return
            if not length:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"No request body"}')
                return

            body = self.rfile.read(length)

            try:
                data = _json.loads(body)
            except _json.JSONDecodeError:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"Invalid JSON"}')
                return

            text = data.get("text", "").strip()
            if not text:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"No resume text provided"}')
                return

            # Stream NDJSON response
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            try:
                result = parse_resume_text(
                    text, progress_callback=self._send_progress
                )
                line = _json.dumps({"type": "result", "profile": result}) + "\n"
                self.wfile.write(line.encode())
                self.wfile.flush()

            except ValueError as e:
                line = _json.dumps({"type": "error", "error": str(e)}) + "\n"
                self.wfile.write(line.encode())
                self.wfile.flush()
            except Exception as e:
                logger.error(f"Text analysis failed: {e}", exc_info=True)
                line = _json.dumps({"type": "error", "error": "Resume analysis failed"}) + "\n"
                self.wfile.write(line.encode())
                self.wfile.flush()

        def log_message(self, format, *args):
            # Suppress GET logs for cleaner output
            if "POST" in str(args):
                super().log_message(format, *args)

    bind_addr = os.environ.get("BIND_ADDR", "localhost")
    class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    with ThreadedHTTPServer((bind_addr, port), DashboardHandler) as server:
        url = f"http://localhost:{port}"
        print(f"Serving dashboard at {url}")
        print("Press Ctrl+C to stop")
        try:
            webbrowser.open(url)
        except Exception:
            pass  # No browser available (e.g. inside a container)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
        serve_dashboard(port)
    else:
        try:
            run_pipeline()
        except KeyboardInterrupt:
            logger.info("Pipeline interrupted by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            sys.exit(1)
