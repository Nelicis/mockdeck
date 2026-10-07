FROM python:3.13-slim

WORKDIR /app

# Copy package metadata and source code
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install mockdeck
RUN pip install --no-cache-dir .

# Create /data directory and generate default starter database
WORKDIR /data
RUN mockdeck init /data/db.json

EXPOSE 8000

ENTRYPOINT ["mockdeck"]
CMD ["serve", "-H", "0.0.0.0", "-p", "8000", "/data/db.json"]
