# NuroAgro Disease Detection Service

This folder is a standalone Flask API for the YOLO disease model. Deploy it as a separate Python web service, then point the main NuroAgro app at it with `DISEASE_SERVICE_URL`.

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

## Deploy Command

When deploying from the repo root:

```bash
pip install -r disease_service/requirements.txt
gunicorn "disease_service.app:create_app()" --bind 0.0.0.0:$PORT --workers 1 --timeout 180
```

Keep `best.pt` available in the repo root or set `DISEASE_MODEL_PATH` to the deployed model path.
