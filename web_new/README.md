# CustomBuild API v2

Modern FastAPI-based API for custom ArduPilot firmware builds.

## Quick Start

```bash
# Install dependencies
pip install fastapi uvicorn pydantic

# Run the application
python -m app.main

# Or use uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Base URLs
- Root: `/`
- Health: `/health`
- API v1: `/api/v1`

### Vehicles API (`/api/v1/vehicles`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/vehicles` | List all vehicles |
| GET | `/vehicles/{vehicle_id}` | Get specific vehicle |
| GET | `/vehicles/{vehicle_id}/versions` | List versions for vehicle |
| GET | `/vehicles/{vehicle_id}/versions/{version_id}` | Get specific version |
| GET | `/vehicles/{vehicle_id}/versions/{version_id}/boards` | List boards |
| GET | `/vehicles/{vehicle_id}/versions/{version_id}/boards/{board_id}` | Get specific board |
| GET | `/vehicles/{vehicle_id}/versions/{version_id}/features` | List features |
| GET | `/vehicles/{vehicle_id}/versions/{version_id}/features/{feature_id}` | Get specific feature |
| GET | `/vehicles/{vehicle_id}/versions/{version_id}/boards/{board_id}/defaults` | List default feature settings |
| GET | `/vehicles/{vehicle_id}/versions/{version_id}/boards/{board_id}/defaults/{feature_id}` | Get specific default |

### Builds API (`/api/v1/builds`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/builds` | Create new build |
| GET | `/builds` | List builds (with filters) |
| GET | `/builds/{build_id}` | Get build details |
| DELETE | `/builds/{build_id}` | Cancel build |
| GET | `/builds/{build_id}/logs` | Get build logs |
| GET | `/builds/{build_id}/artifact` | Download firmware artifact |

#### Build Filters (Query Parameters)
- `vehicle_id` - Filter by vehicle
- `board_id` - Filter by board
- `state` - Filter by state (PENDING, RUNNING, SUCCESS, FAILURE, CANCELLED)
- `limit` - Max results (1-100, default: 20)
- `offset` - Pagination offset

### Admin API (`/api/v1/admin`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/admin/refresh_remotes` | Refresh remote metadata | Bearer Token |

#### Authentication
Admin endpoints require bearer token authentication:
```bash
curl -X POST http://localhost:8000/api/v1/admin/refresh_remotes \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Project Structure

```
web_new/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py  # Exports main router
│   │       ├── router.py    # Main v1 router (aggregates all sub-routers)
│   │       ├── vehicles.py  # Vehicle endpoints
│   │       ├── builds.py    # Build endpoints
│   │       └── admin.py     # Admin endpoints
│   ├── schemas/
│   │   ├── __init__.py      # Exports all schemas
│   │   ├── vehicles.py      # Vehicle Pydantic models
│   │   ├── builds.py        # Build Pydantic models
│   │   └── admin.py         # Admin Pydantic models
│   └── services/
│       ├── __init__.py
│       ├── vehicles.py      # Vehicle business logic (TODO)
│       ├── builds.py        # Build business logic (TODO)
│       └── admin.py         # Admin business logic (TODO)
├── tests/
└── README.md
```

## Schemas

### Vehicle Schemas
- `VehicleBase` - Basic vehicle info
- `VersionBase` / `VersionOut` - Version info
- `BoardBase` / `BoardOut` - Board info
- `CategoryBase` - Feature category
- `FeatureBase` / `FeatureOut` - Feature/flag info
- `DefaultsBase` / `DefaultsOut` - Default feature settings

### Build Schemas
- `BuildRequest` - Create build request
- `BuildOut` - Build response
- `BuildProgress` - Build progress status
- `RemoteInfo` - Git remote info

### Admin Schemas
- `RefreshRemotesResponse` - Refresh operation result

## Example Usage

### Create a Build
```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/builds",
    json={
        "vehicle_id": "copter",
        "board_id": "SPEDIXF405",
        "version_id": "stable-4.5",
        "selected_features": [
            "HAL_EXTERNAL_AHRS_ENABLED",
            "AP_CAMERA_ENABLED"
        ]
    }
)

build = response.json()
print(f"Build ID: {build['build_id']}")
```

### List Builds
```python
response = requests.get(
    "http://localhost:8000/api/v1/builds",
    params={
        "vehicle_id": "copter",
        "state": "SUCCESS",
        "limit": 10
    }
)

builds = response.json()
```

### Get Vehicle Versions
```python
response = requests.get(
    "http://localhost:8000/api/v1/vehicles/copter/versions"
)

versions = response.json()
```

## Development Status

✅ **Completed:**
- API schemas (Pydantic models)
- API routes (endpoints)
- Request/response validation
- API documentation structure
- Authentication framework

🚧 **TODO:**
- Service layer implementation
- Database integration
- Build queue management
- File storage handling
- Token verification
- Error handling refinement
- Unit tests
- Integration tests

## Next Steps

1. Implement service layer (`app/services/`)
2. Add database models and migrations
3. Implement token authentication
4. Add build queue with Celery/Redis
5. Implement file storage for artifacts
6. Add comprehensive error handling
7. Write tests
8. Add rate limiting
9. Add logging and monitoring
10. Deploy with Docker
