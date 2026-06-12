"""Standalone disease detection API for NuroAgro.

Run this service separately when the main Flask application should call YOLO
over HTTP instead of loading the model in the web process.
"""

import base64
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename


SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DISEASE_INFERENCE_SUBPROCESS', 'true')
os.environ.setdefault('YOLO_CONFIG_DIR', str(SERVICE_DIR / '.yolo_config'))

load_dotenv(PROJECT_ROOT / '.env')
load_dotenv(SERVICE_DIR / '.env')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif'}


def allowed_file(filename):
    return '.' in (filename or '') and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def configured_model_path():
    model_path = os.environ.get('DISEASE_MODEL_PATH') or os.environ.get('YOLO_MODEL_PATH') or str(PROJECT_ROOT / 'best.pt')
    path = Path(model_path).expanduser()
    if not path.is_absolute():
        service_relative = (SERVICE_DIR / path).resolve()
        root_relative = (PROJECT_ROOT / path).resolve()
        path = service_relative if service_relative.exists() else root_relative
    return str(path)


def require_service_key():
    expected = (os.environ.get('DISEASE_SERVICE_API_KEY') or '').strip()
    if not expected:
        return True
    supplied = request.headers.get('X-Disease-Service-Key', '').strip()
    return supplied == expected


def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('DISEASE_SERVICE_MAX_CONTENT_LENGTH', 16 * 1024 * 1024))

    @app.get('/')
    @app.get('/api/health')
    def health():
        return jsonify({
            'ok': True,
            'service': 'nuroagro-disease-detection',
            'model_path': configured_model_path(),
            'model_exists': Path(configured_model_path()).exists(),
        })

    @app.post('/api/analyze')
    def analyze():
        if not require_service_key():
            return jsonify({'error': 'Invalid disease service API key.'}), 401

        if 'image' not in request.files:
            return jsonify({'error': 'No image provided.'}), 400

        image = request.files['image']
        if image.filename == '':
            return jsonify({'error': 'No image selected.'}), 400
        if not allowed_file(image.filename):
            return jsonify({'error': 'Unsupported image type.'}), 400

        started_at = perf_counter()
        with TemporaryDirectory(prefix='nuroagro_disease_') as temp_dir:
            filename = secure_filename(image.filename)
            image_path = Path(temp_dir) / filename
            image.save(image_path)

            from disease_ml import analyze_image_for_disease_guarded, analyze_image_with_visual_fallback

            os.environ['DISEASE_MODEL_PATH'] = configured_model_path()
            result = analyze_image_for_disease_guarded(str(image_path), logger=app.logger)
            fallback_enabled = os.environ.get('DISEASE_FALLBACK_ON_ERROR', 'true').lower() not in {'0', 'false', 'no', 'off'}
            if fallback_enabled and result.get('error'):
                result = analyze_image_with_visual_fallback(str(image_path), logger=app.logger, reason=result.get('error'))
            result['service_elapsed_seconds'] = round(perf_counter() - started_at, 3)

            annotated_path = result.get('annotated_image_path')
            if annotated_path and Path(annotated_path).exists():
                with open(annotated_path, 'rb') as annotated_file:
                    result['annotated_image_base64'] = base64.b64encode(annotated_file.read()).decode('ascii')

        status_code = 503 if result.get('error') else 200
        return jsonify(result), status_code

    return app


app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('DISEASE_SERVICE_PORT', os.environ.get('PORT', '5055')))
    app.run(host=os.environ.get('DISEASE_SERVICE_HOST', '0.0.0.0'), port=port)
