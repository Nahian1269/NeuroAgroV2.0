# NuroAgro Disease Detection Service

This folder is a standalone Flask API for the YOLO disease model. Deploy it as a separate service, then point the main NuroAgro app at it with either `DISEASE_SERVICE_URL` or the private-network `DISEASE_SERVICE_HOST` + `DISEASE_SERVICE_PORT` pair.

## Local Run

```powershell
.\.venv\Scripts\python.exe disease_service\app.py
```

The service listens on `http://127.0.0.1:5055` by default.

## Main App Configuration

Set these variables in the main NuroAgro app:

```text
DISEASE_SERVICE_URL=http://127.0.0.1:5055
DISEASE_SERVICE_API_KEY=change-this-shared-key
DISEASE_SERVICE_TIMEOUT_SECONDS=90
```

If `DISEASE_SERVICE_URL` is empty, the main Flask app falls back to the local `disease_ml.py` worker.

## Render Deployment

The root `render.yaml` already deploys this as the private service `nuroagro-disease-api` and passes its private hostname to the main `nuroagro` web app. The private API binds to port `5055` because Render private-network traffic cannot use port `10000`.

If you create the service manually from the repo root:

```bash
pip install -r disease_service/requirements.txt
gunicorn "disease_service.app:create_app()" --bind 0.0.0.0:5055 --workers 1 --timeout 180
```

Keep `best.pt` available in the repo root or set `DISEASE_MODEL_PATH` to the deployed model path.
