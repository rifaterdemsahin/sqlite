FROM python:3.13-slim

# Install the native sqlite3 command-line tool inside the Fly.io container
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application code, reusable nav component, and all HTML pages
COPY sandbox.py nav.js index.html architecture.html files-and-run.html sql-playground.html fly-persistence.html fly-costs.html README.md ./

# Pre-initialize the local fallback SQLite database file and verify ACID & file-copy proof during build
RUN python3 sandbox.py --cli-only

ENV HOST=0.0.0.0
ENV PORT=8080
ENV SANDBOX_DATA_DIR=/data

EXPOSE 8080

CMD ["python3", "sandbox.py", "--host", "0.0.0.0", "--port", "8080"]
