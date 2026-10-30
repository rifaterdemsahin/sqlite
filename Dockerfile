FROM python:3.13-slim

WORKDIR /app

# Copy application code and static assets
COPY sandbox.py index.html architecture.html README.md ./

# Pre-initialize the SQLite database file and verify ACID & file-copy proof during build
RUN python3 sandbox.py --cli-only

ENV HOST=0.0.0.0
ENV PORT=8080

EXPOSE 8080

CMD ["python3", "sandbox.py", "--host", "0.0.0.0", "--port", "8080"]
