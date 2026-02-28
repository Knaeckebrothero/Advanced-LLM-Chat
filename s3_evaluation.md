# S3-Compatible Object Storage Evaluation

This document evaluates options for migrating file storage from the local filesystem to an S3-compatible object store.

## Current Architecture

Files are currently stored in a flat filesystem directory (`./files/` or `FILES_DIR`):

```
./files/
├── file_1703615234567_a1b2c3d4.pdf          # Original PDF
├── file_1703615234567_a1b2c3d4_text.txt     # Extracted text
├── file_1703615234567_a1b2c3d4_page_1.png   # Page 1 image
├── file_1703615234567_a1b2c3d4_page_2.png   # Page 2 image
├── file_1703615234568_b2c3d4e5.mp3          # Original audio
├── file_1703615234568_b2c3d4e5_transcript.txt # Transcript
└── file_1703615234569_c3d4e5f6.txt          # Text file
```

### Current Implementation Summary

| Component | Location | Changes Required |
|-----------|----------|------------------|
| File API handlers | `backend/api/files.py` | Major (4 functions) |
| Document processing | `backend/services/document_handler.py` | Moderate |
| Audio processing | `backend/services/audio_handler.py` | Moderate |
| File retrieval | `backend/services/file_retrieval_service.py` | Minor |
| Configuration | `backend/config.py` | Add S3 credentials |
| New abstraction | `backend/services/storage_service.py` | ~100-150 LOC |

**Migration difficulty**: Moderate - well-architected for it, ~300-500 lines of backend changes. Frontend unchanged.

---

## Option 1: MinIO

**Image**: `quay.io/minio/minio:latest`
**License**: GNU AGPL v3

### Pros
- Near-complete S3 API compatibility
- Built-in web console (port 9001) for debugging and management
- Excellent `mc` CLI tool
- Very mature, widely adopted in industry
- Extensive documentation and community support
- Native health checks (`mc ready local`)

### Cons
- Larger resource footprint (~175 MB image)
- Designed for enterprise/cluster deployments
- More features than needed for simple use cases

### Docker Compose Configuration

```yaml
services:
  minio:
    image: quay.io/minio/minio:latest
    container_name: fessi-minio
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"  # S3 API
      - "9001:9001"  # Web console
    environment:
      - MINIO_ROOT_USER=fessi
      - MINIO_ROOT_PASSWORD=fessi_minio_dev
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - app-network
    restart: unless-stopped

  # Auto-create bucket on startup
  minio-init:
    image: quay.io/minio/mc:latest
    container_name: fessi-minio-init
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set minio http://minio:9000 fessi fessi_minio_dev;
      mc mb minio/fessi-files --ignore-existing;
      exit 0;
      "
    networks:
      - app-network

volumes:
  minio_data:
```

### Backend Environment Variables

```bash
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=fessi
MINIO_SECRET_KEY=fessi_minio_dev
MINIO_BUCKET=fessi-files
MINIO_USE_SSL=false
```

### Local Development (without Docker)

```bash
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=fessi
MINIO_SECRET_KEY=fessi_minio_dev
MINIO_BUCKET=fessi-files
MINIO_USE_SSL=false
```

---

## Option 2: Garage

**Image**: `dxflrs/garage:v2.1.0`
**License**: GNU AGPL v3

### Pros
- Extremely lightweight (~30 MB image, minimal CPU/RAM)
- Designed for single-node and edge deployments
- Runs on ARM devices (Raspberry Pi)
- No external dependencies (built-in consensus)
- EU-funded development (NLnet/NGI0 Commons Fund 2025)
- Simple architecture

### Cons
- No web console (CLI only)
- Requires separate TOML configuration file
- Manual bucket/key setup via CLI
- Smaller community, less documentation
- S3 API coverage is substantial but not complete

### Docker Compose Configuration

```yaml
services:
  garage:
    image: dxflrs/garage:v2.1.0
    container_name: fessi-garage
    ports:
      - "3900:3900"  # S3 API
      - "3901:3901"  # RPC
      - "3903:3903"  # Admin API
    volumes:
      - ./garage.toml:/etc/garage.toml:ro
      - garage_meta:/var/lib/garage/meta
      - garage_data:/var/lib/garage/data
    networks:
      - app-network
    restart: unless-stopped

volumes:
  garage_meta:
  garage_data:
```

### garage.toml Configuration

```toml
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "sqlite"

replication_factor = 1

rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"
rpc_secret = "<generate-with-openssl-rand-hex-32>"

[s3_api]
s3_region = "garage"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"

[admin]
api_bind_addr = "[::]:3903"
admin_token = "<generate-with-openssl-rand-base64-32>"
metrics_token = "<generate-with-openssl-rand-base64-32>"
```

### Initial Setup (after container starts)

```bash
# Connect to container
podman exec -it fessi-garage /bin/sh

# Get node ID and configure layout
garage status
garage layout assign -z dc1 -c 1G <node-id>
garage layout apply

# Create bucket and access key
garage bucket create fessi-files
garage key create fessi-app-key
garage bucket allow --read --write fessi-files --key fessi-app-key
garage key info fessi-app-key  # Get access key and secret
```

---

## Comparison Matrix

| Aspect | MinIO | Garage |
|--------|-------|--------|
| **Image size** | ~175 MB | ~30 MB |
| **Memory usage** | Higher | Very low |
| **CPU usage** | Moderate | Minimal |
| **S3 compatibility** | Near-complete | Substantial subset |
| **Web console** | Yes (built-in) | No |
| **Setup complexity** | Low (auto bucket init) | Medium (manual setup) |
| **Documentation** | Extensive | Good but smaller |
| **Community** | Very large | Growing |
| **Best for** | Standard deployments | Resource-constrained environments |

---

## Recommendation

**For this project: MinIO**

Rationale:
1. Built-in web console simplifies debugging during development
2. Auto-bucket initialization via `mc` container reduces setup friction
3. Better tooling and documentation for Python integration (`boto3`)
4. More developers are familiar with it
5. Resource overhead is acceptable for a dev environment
6. Health checks integrate cleanly with existing docker-compose pattern

Garage would be preferable if:
- Running on very limited hardware (Raspberry Pi, edge devices)
- Minimizing container footprint is critical
- You prefer simpler, smaller codebases

---

## Implementation Plan

### Phase 1: Infrastructure
1. Add MinIO service to `docker/docker-compose.yml`
2. Add `minio-init` service for bucket creation
3. Update `.env.example` with S3 configuration variables
4. Update `backend/config.py` with S3 settings

### Phase 2: Storage Abstraction
1. Create `backend/services/storage_service.py` with interface:
   - `upload(file_id, content, content_type) -> str`
   - `download(file_id) -> bytes`
   - `stream(file_id) -> Iterator[bytes]`
   - `delete(file_id)`
   - `exists(file_id) -> bool`
   - `list_by_prefix(prefix) -> List[str]`
2. Implement S3 backend using `boto3`
3. Optionally keep filesystem backend for local dev without containers

### Phase 3: API Migration
1. Update `backend/api/files.py`:
   - `upload_files()` - save to S3
   - `get_file()` - stream from S3
   - `get_file_text()` - retrieve processed files from S3
   - `delete_file()` - delete from S3 with prefix matching
2. Update processing services to use temp files + S3 upload

### Phase 4: Testing & Documentation
1. Test file upload/download/delete flows
2. Test PDF and audio processing with S3 storage
3. Update CLAUDE.md with new environment variables
4. Update README if present

---

## References

- [MinIO Official Docker Compose](https://github.com/minio/minio/blob/master/docs/orchestration/docker-compose/docker-compose.yaml)
- [MinIO Docker Setup Guide](https://medium.com/@murisuu/self-host-s3-minio-docker-compose-setup-48588b2f9bcd)
- [Auto-creating MinIO Buckets](https://banach.net.pl/posts/2025/creating-bucket-automatically-on-local-minio-with-docker-compose/)
- [Garage Quick Start](https://garagehq.deuxfleurs.fr/documentation/quick-start/)
- [Garage Docker Hub](https://hub.docker.com/r/dxflrs/garage)
- [Garage Overview (UnixHost)](https://unixhost.pro/blog/2025/09/garage-s3-a-lightweight-alternative-for-self-hosted-object-storage/)
