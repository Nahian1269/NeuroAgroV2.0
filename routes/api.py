"""
    API Routes for NuroAgro
    Handles sensor data, device control, and API endpoints
"""

from flask import Blueprint, request, jsonify, current_app, session
from models import (
    db, User, Device, SensorReading, DeviceStatus,
    DiseaseDetection, Recommendation, Notification, Project, SystemLog,
    WeatherRecord, WeatherTrainingRun, ChatMessage, ForumPost, ForumReply
)
from datetime import datetime, timedelta
import base64
import json
import math
import os
from pathlib import Path
from functools import wraps
from threading import Thread
from time import perf_counter
# Lazy import disease_ml to avoid numpy/cv2 blocking during app startup
def _get_disease_functions():
    """Lazy load disease ML functions on first use."""
    from disease_ml import (
        analyze_image_for_disease_guarded,
        generate_disease_recommendations
    )
    return analyze_image_for_disease_guarded, generate_disease_recommendations
from sensor_agent import analyze_sensor_history
from supabase_bridge import check_connection, delete_records, insert_record, model_payload
from weather_agent import (
    WEATHER_FIELDS,
    chatgpt_crop_advice,
    evaluate_weather_training,
    predict_weather,
    summarize_weather,
)

try:
    import requests
except Exception:
    requests = None

api_bp = Blueprint('api', __name__, url_prefix='/api')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif'}


def mirror_disease_artifacts_async(app, detection_id, notification_id=None):
    """Mirror remote disease records without delaying the user's diagnosis response."""
    def worker():
        with app.app_context():
            try:
                detection = DiseaseDetection.query.get(detection_id)
                if detection:
                    mirror_disease_detection(detection)
                if notification_id:
                    notification = Notification.query.get(notification_id)
                    if notification:
                        mirror_notification(notification)
            except Exception as exc:
                app.logger.warning("Background disease mirror failed: %s", exc)

    Thread(target=worker, name=f'disease-mirror-{detection_id}', daemon=True).start()


def mirror_weather_records_async(app, record_ids):
    """Mirror weather rows without delaying prediction or geo sync responses."""
    ids = [record_id for record_id in record_ids if record_id]
    if not ids:
        return

    def worker():
        with app.app_context():
            for record_id in ids:
                try:
                    record = WeatherRecord.query.get(record_id)
                    if record:
                        mirror_weather_record(record)
                except Exception as exc:
                    app.logger.warning("Background weather mirror failed for %s: %s", record_id, exc)

    Thread(target=worker, name=f'weather-mirror-{ids[0]}', daemon=True).start()

# ==================== AUTHENTICATION DECORATOR ====================

def request_data():
    """Read JSON bodies first and fall back to form data."""
    return request.get_json(silent=True) or request.form.to_dict() or {}


def clean_text(value):
    return (value or '').strip()


def allowed_image_file(filename):
    return '.' in (filename or '') and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def upload_url_for_path(path):
    try:
        root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
        rel = Path(path).resolve().relative_to(root)
        return f"/uploads/{rel.as_posix()}"
    except Exception:
        return None


def public_image_url(value, fallback_path=None):
    """Normalize old static paths and current upload paths to the served /uploads URL."""
    for candidate in (value, fallback_path):
        if not candidate:
            continue
        mapped = upload_url_for_path(candidate)
        if mapped:
            return mapped
        text = str(candidate).replace('\\', '/')
        if text.startswith(('http://', 'https://')):
            return text
        if text.startswith('/uploads/'):
            return text
        if text.startswith('/static/uploads/'):
            return '/uploads/' + text[len('/static/uploads/'):]
        if 'static/uploads/' in text:
            return '/uploads/' + text.split('static/uploads/', 1)[1]
        if 'disease_images/' in text:
            return '/uploads/disease_images/' + text.split('disease_images/', 1)[1]
    return None


def disease_detection_payload(detection):
    item = detection.to_dict()
    item['image_url'] = public_image_url(detection.image_url, detection.image_path) or detection.image_url
    item['annotated_image_url'] = item['image_url']
    item['original_image_url'] = public_image_url(detection.image_path)
    item['is_from_camera'] = detection.is_from_camera
    return item


def disease_upload_folder():
    folder = Path(current_app.config['UPLOAD_FOLDER']) / 'disease_images'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def disease_detected(name, confidence):
    return bool(name) and str(name).strip().lower() not in {'healthy', 'background'} and (confidence or 0) >= 20


def configured_disease_service_url():
    """Return the external disease service URL when remote inference is enabled."""
    raw_url = (os.environ.get('DISEASE_SERVICE_URL') or '').strip()
    if not raw_url:
        return ''
    return raw_url.rstrip('/')


def save_remote_annotated_image(image_path, payload):
    """Persist an annotated image returned by the disease service next to the upload."""
    encoded_image = payload.pop('annotated_image_base64', None)
    if not encoded_image:
        return payload

    try:
        suffix = Path(image_path).suffix or '.jpg'
        annotated_path = str(Path(image_path).with_name(f'{Path(image_path).stem}_annotated{suffix}'))
        with open(annotated_path, 'wb') as annotated_file:
            annotated_file.write(base64.b64decode(encoded_image))
        payload['annotated_image_path'] = annotated_path
        payload['annotated_image_url'] = public_image_url(annotated_path)
    except Exception as exc:
        current_app.logger.warning("Could not save remote annotated disease image: %s", exc)

    return payload


def analyze_image_with_disease_service(image_path):
    """Forward an image to the separate disease model service."""
    if requests is None:
        return {'error': 'requests is unavailable, so the disease service cannot be called.'}

    service_url = configured_disease_service_url()
    if not service_url:
        return None

    endpoint = f"{service_url}/api/analyze"
    headers = {}
    api_key = (os.environ.get('DISEASE_SERVICE_API_KEY') or '').strip()
    if api_key:
        headers['X-Disease-Service-Key'] = api_key

    timeout = float(os.environ.get('DISEASE_SERVICE_TIMEOUT_SECONDS', os.environ.get('DISEASE_INFERENCE_TIMEOUT_SECONDS', '75')))
    try:
        with open(image_path, 'rb') as image_file:
            response = requests.post(
                endpoint,
                files={'image': (Path(image_path).name, image_file, 'application/octet-stream')},
                headers=headers,
                timeout=timeout,
            )
        try:
            payload = response.json()
        except ValueError:
            payload = {'error': response.text[:320] or 'Disease service returned a non-JSON response.'}
        if response.status_code >= 400:
            payload.setdefault('error', f'Disease service failed with HTTP {response.status_code}.')
        return save_remote_annotated_image(image_path, payload)
    except Exception as exc:
        current_app.logger.error("Disease service request failed: %s", exc)
        return {'error': f'Disease service unavailable: {exc}', 'primary_disease': None, 'confidence': 0, 'detections': {}, 'boxes': []}


def number_or_none(value):
    try:
        if value in (None, ''):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def bool_or_false(value):
    if isinstance(value, bool):
        return value
    if value in (None, ''):
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'motion'}


def first_present(data, *keys, default=None):
    for key in keys:
        if key in data and data.get(key) not in (None, ''):
            return data.get(key)
    return default


def require_admin_password():
    configured_password = current_app.config.get('ADMIN_PASSWORD') or current_app.config.get('SECRET_KEY')
    supplied_password = request.headers.get('X-Admin-Password') or request.args.get('password')
    return bool(supplied_password and supplied_password == configured_password)


def find_user_by_identifier(identifier):
    identifier = clean_text(identifier)
    return User.query.filter_by(username=identifier).first() or User.query.filter_by(email=identifier).first()


def next_device_id(user_id):
    number = max(user_id or 1, 1)
    while True:
        device_id = f"ESP32_{number:03d}"
        if not Device.query.filter_by(device_id=device_id).first():
            return device_id
        number += 1


def create_user_device(user, requested_device_id=None):
    device_id = clean_text(requested_device_id) or next_device_id(user.id)
    existing = Device.query.filter_by(device_id=device_id).first()

    if existing and existing.user_id != user.id:
        raise ValueError('Device ID is already registered to another account')

    if existing:
        status = DeviceStatus.query.filter_by(user_id=user.id, device_id=existing.device_id).first()
        if not status:
            status = DeviceStatus(user_id=user.id, device_id=existing.device_id)
            db.session.add(status)
            db.session.flush()
        return existing, status

    device = Device(
        device_id=device_id,
        user_id=user.id,
        device_name='Primary ESP32 Controller',
        device_type='ESP32-WROOM',
        is_active=True
    )
    db.session.add(device)
    db.session.flush()

    status = DeviceStatus(user_id=user.id, device_id=device.device_id)
    db.session.add(status)
    db.session.flush()
    return device, status


def ensure_user_devices(user):
    devices = Device.query.filter_by(user_id=user.id).order_by(Device.id.asc()).all()
    if devices:
        return devices

    device, status = create_user_device(user)
    db.session.commit()
    mirror_device(device)
    mirror_device_status(status)
    return [device]


def auth_payload(user):
    devices = ensure_user_devices(user)
    return {
        'authenticated': True,
        'user': user.to_dict(),
        'devices': [device.to_dict() for device in devices],
        'active_device_id': devices[0].device_id if devices else None
    }


def user_admin_payload(user):
    devices = Device.query.filter_by(user_id=user.id).order_by(Device.id.asc()).all()
    projects = Project.query.filter_by(user_id=user.id).order_by(Project.created_at.desc()).all()
    latest_reading = SensorReading.query.filter_by(user_id=user.id).order_by(SensorReading.timestamp.desc()).first()
    detections_count = DiseaseDetection.query.filter_by(user_id=user.id).count()
    recommendations_count = Recommendation.query.filter_by(user_id=user.id, is_active=True).count()
    payload = user.to_dict()
    payload.update({
        'devices': [device.to_dict() for device in devices],
        'projects': [project.to_dict() for project in projects],
        'latest_reading': latest_reading.to_dict() if latest_reading else None,
        'counts': {
            'devices': len(devices),
            'projects': len(projects),
            'sensor_readings': SensorReading.query.filter_by(user_id=user.id).count(),
            'disease_detections': detections_count,
            'recommendations': recommendations_count,
            'chat_messages': ChatMessage.query.filter_by(user_id=user.id).count(),
            'forum_posts': ForumPost.query.filter_by(user_id=user.id).count()
        }
    })
    return payload


@api_bp.route('/auth/register', methods=['POST'])
def api_register():
    """Register a user, create a first device, and start a session."""
    data = request_data()
    username = clean_text(data.get('username'))
    email = clean_text(data.get('email')).lower()
    password = data.get('password') or ''
    password_confirm = data.get('password_confirm') or data.get('passwordConfirm') or ''
    device_id = clean_text(data.get('device_id') or data.get('deviceId'))

    try:
        if not username or not email or not password or not password_confirm:
            return jsonify({'error': 'Username, email, password, and confirmation are required'}), 400
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        if '@' not in email:
            return jsonify({'error': 'Enter a valid email address'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if password != password_confirm:
            return jsonify({'error': 'Passwords do not match'}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 409
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 409
        if device_id and Device.query.filter_by(device_id=device_id).first():
            return jsonify({'error': 'Device ID is already registered'}), 409

        user = User(
            username=username,
            email=email,
            farm_name=clean_text(data.get('farm_name') or data.get('farmName')) or None,
            plant_type=clean_text(data.get('plant_type') or data.get('plantType')) or None,
            approval_status='pending'
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        device, status = create_user_device(user, device_id)
        db.session.commit()

        mirror_user(user)
        mirror_device(device)
        mirror_device_status(status)

        return jsonify({
            'status': 'pending_approval',
            'authenticated': False,
            'message': 'Account created. An administrator must accept this user before login.',
            'user': user.to_dict()
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"API registration failed: {str(exc)}")
        return jsonify({'error': 'Could not create account'}), 500


@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    """Login with username or email and start a session."""
    data = request_data()
    identifier = clean_text(data.get('identifier') or data.get('username') or data.get('email'))
    password = data.get('password') or ''

    if not identifier or not password:
        return jsonify({'error': 'Username/email and password are required'}), 400

    user = find_user_by_identifier(identifier)
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid username/email or password'}), 401

    if (user.approval_status or 'pending') != 'accepted':
        return jsonify({
            'error': 'Account is waiting for admin acceptance.',
            'approval_status': user.approval_status or 'pending'
        }), 403

    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session.permanent = True

    return jsonify(auth_payload(user)), 200


@api_bp.route('/auth/me', methods=['GET'])
def api_current_user():
    """Return the current logged-in user from the Flask session."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'authenticated': False}), 401

    user = User.query.get(user_id)
    if not user:
        session.clear()
        return jsonify({'authenticated': False}), 401

    return jsonify(auth_payload(user)), 200


@api_bp.route('/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'status': 'success', 'authenticated': False}), 200



@api_bp.route('/profile', methods=['GET', 'PUT'])
def user_profile():
    """Get or update the logged-in user's profile."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'GET':
        return jsonify({'profile': user.to_dict()}), 200

    data = request_data()
    user.full_name = clean_text(data.get('full_name') or data.get('fullName')) or user.full_name
    user.phone = clean_text(data.get('phone')) or None
    user.profile_notes = clean_text(data.get('profile_notes') or data.get('profileNotes')) or None
    user.farm_name = clean_text(data.get('farm_name') or data.get('farmName')) or user.farm_name
    user.plant_type = clean_text(data.get('plant_type') or data.get('plantType')) or user.plant_type
    farm_size_value = data.get('farm_size') if data.get('farm_size') is not None else data.get('farmSize')
    latitude_value = data.get('farm_location_lat') if data.get('farm_location_lat') is not None else data.get('latitude')
    longitude_value = data.get('farm_location_lon') if data.get('farm_location_lon') is not None else data.get('longitude')
    farm_size = number_or_none(farm_size_value)
    latitude = number_or_none(latitude_value)
    longitude = number_or_none(longitude_value)
    if farm_size is not None:
        user.farm_size = farm_size
    if latitude is not None:
        user.farm_location_lat = latitude
    if longitude is not None:
        user.farm_location_lon = longitude
    user.updated_at = datetime.utcnow()

    db.session.commit()
    mirror_user(user)
    return jsonify({'status': 'success', 'profile': user.to_dict()}), 200


@api_bp.route('/profile/dashboard', methods=['GET'])
def profile_dashboard():
    """Personal dashboard summary for the logged-in user."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    devices = Device.query.filter_by(user_id=user.id).all()
    latest_reading = SensorReading.query.filter_by(user_id=user.id).order_by(SensorReading.timestamp.desc()).first()
    latest_weather = WeatherRecord.query.filter_by(user_id=user.id).order_by(WeatherRecord.created_at.desc()).first()
    latest_disease = DiseaseDetection.query.filter_by(user_id=user.id).order_by(DiseaseDetection.timestamp.desc()).first()
    unread_chat = ChatMessage.query.filter_by(user_id=user.id, sender_role='admin', is_read=False).count()

    return jsonify({
        'profile': user.to_dict(),
        'counts': {
            'devices': len(devices),
            'projects': Project.query.filter_by(user_id=user.id).count(),
            'sensor_readings': SensorReading.query.filter_by(user_id=user.id).count(),
            'weather_records': WeatherRecord.query.filter_by(user_id=user.id).count(),
            'disease_detections': DiseaseDetection.query.filter_by(user_id=user.id).count(),
            'recommendations': Recommendation.query.filter_by(user_id=user.id, is_active=True).count(),
            'chat_unread': unread_chat,
            'forum_posts': ForumPost.query.filter_by(user_id=user.id).count()
        },
        'latest': {
            'sensor': latest_reading.to_dict() if latest_reading else None,
            'weather': latest_weather.to_dict() if latest_weather else None,
            'disease': latest_disease.to_dict() if latest_disease else None
        }
    }), 200

@api_bp.route('/projects', methods=['GET'])
def list_projects():
    """Return projects for the current user."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    projects = Project.query.filter_by(user_id=user_id).order_by(Project.created_at.desc()).all()
    return jsonify({'projects': [project.to_dict() for project in projects]}), 200


@api_bp.route('/projects', methods=['POST'])
def save_project():
    """Create or update a farming project and mirror it to Supabase."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    data = request_data()
    project_name = clean_text(data.get('project_name') or data.get('name'))
    if not project_name:
        return jsonify({'error': 'Project name is required'}), 400

    user = User.query.get(user_id)
    project_id = data.get('id')
    project = Project.query.filter_by(id=project_id, user_id=user_id).first() if project_id else None
    if not project:
        project = Project(user_id=user_id, project_name=project_name)
        db.session.add(project)

    project.project_name = project_name
    project.farming_mode = clean_text(data.get('farming_mode') or data.get('climate')) or None
    project.water_system = clean_text(data.get('water_system') or data.get('waterSystem')) or None
    project.land_area = number_or_none(data.get('land_area') or data.get('area'))
    project.vertical_stories = max(1, min(4, int(number_or_none(data.get('vertical_stories') or data.get('stories')) or 1)))
    project.latitude = number_or_none(data.get('latitude'))
    project.longitude = number_or_none(data.get('longitude'))

    ai_payload = build_project_advice(project)
    project.ai_suitability = json.dumps(ai_payload)
    project.recommended_plants = json.dumps(ai_payload.get('plants', []))
    project.recommended_fish = json.dumps(ai_payload.get('fish', []))
    project.weather_snapshot = json.dumps({
        'source': 'pending_weather_api',
        'latitude': project.latitude,
        'longitude': project.longitude
    })

    if user:
        user.farm_name = project.project_name
        user.farm_size = project.land_area
        user.farm_location_lat = project.latitude
        user.farm_location_lon = project.longitude
        user.farm_area_suitability = ai_payload.get('vertical_score')
        user.geolocation_analyzed = bool(project.latitude and project.longitude)

    db.session.commit()
    mirror_project(project)
    if user:
        mirror_user(user)

    return jsonify({'status': 'success', 'project': project.to_dict()}), 201



@api_bp.route('/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """Delete one project owned by the logged-in user."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    project = Project.query.filter_by(id=project_id, user_id=user_id).first()
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    WeatherRecord.query.filter_by(project_id=project.id).update({'project_id': None})
    db.session.delete(project)
    db.session.commit()
    delete_records('projects', {'local_id': project_id}, current_app.logger)
    return jsonify({'status': 'success', 'deleted_project_id': project_id}), 200


@api_bp.route('/history/<device_id>', methods=['GET'])
def device_history(device_id):
    """Return stored historical data for a device owner."""
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    if not has_device_access(device):
        return jsonify({'error': 'Login or valid device API key required'}), 401

    limit = min(request.args.get('limit', 120, type=int), 500)
    sensors = SensorReading.query.filter_by(user_id=device.user_id, device_id=device_id).order_by(SensorReading.timestamp.desc()).limit(limit).all()
    weather = WeatherRecord.query.filter_by(user_id=device.user_id, device_id=device_id).order_by(WeatherRecord.created_at.desc()).limit(limit).all()
    diseases = DiseaseDetection.query.filter_by(user_id=device.user_id).order_by(DiseaseDetection.timestamp.desc()).limit(limit).all()
    recs = Recommendation.query.filter_by(user_id=device.user_id).order_by(Recommendation.time_of_analysis.desc()).limit(limit).all()
    notes = Notification.query.filter_by(user_id=device.user_id).order_by(Notification.created_at.desc()).limit(limit).all()
    trainings = WeatherTrainingRun.query.filter_by(user_id=device.user_id, device_id=device_id).order_by(WeatherTrainingRun.started_at.desc()).limit(40).all()

    return jsonify({
        'device_id': device_id,
        'sensor_readings': [item.to_dict() for item in sensors],
        'weather_records': [item.to_dict() for item in weather],
        'disease_detections': [disease_detection_payload(item) for item in diseases],
        'recommendations': [item.to_dict() for item in recs],
        'notifications': [item.to_dict() for item in notes],
        'weather_training_runs': [item.to_dict() for item in trainings]
    }), 200

@api_bp.route('/admin/overview', methods=['GET'])
def admin_overview():
    """Password-protected admin overview for user/device/map dashboards."""
    if not require_admin_password():
        return jsonify({'error': 'Valid admin password required'}), 401

    users = User.query.order_by(User.created_at.desc()).all()
    devices = Device.query.all()
    readings_count = SensorReading.query.count()
    detections_count = DiseaseDetection.query.count()
    weather_count = WeatherRecord.query.count()
    visitor_count = SystemLog.query.filter_by(action='web_visit').count()
    approval_statuses = [user.approval_status or 'accepted' for user in users]
    accepted_count = len([status for status in approval_statuses if status == 'accepted'])
    pending_count = len([status for status in approval_statuses if status == 'pending'])
    rejected_count = len([status for status in approval_statuses if status == 'rejected'])

    return jsonify({
        'totals': {
            'users': len(users),
            'accepted': accepted_count,
            'pending': pending_count,
            'rejected': rejected_count,
            'visitors': visitor_count,
            'devices': len(devices),
            'sensor_readings': readings_count,
            'disease_detections': detections_count,
            'weather_records': weather_count,
            'projects': Project.query.count(),
            'recommendations': Recommendation.query.filter_by(is_active=True).count(),
            'chat_messages': ChatMessage.query.count(),
            'forum_posts': ForumPost.query.count()
        },
        'users': [user_admin_payload(user) for user in users],
        'devices': [device.to_dict() for device in devices]
    }), 200



@api_bp.route('/chat', methods=['GET', 'POST'])
def user_chat():
    """User chat with admin."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'POST':
        data = request_data()
        message = clean_text(data.get('message'))
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        chat = ChatMessage(user_id=user.id, sender_role='user', message=message, created_at=datetime.utcnow())
        db.session.add(chat)
        db.session.commit()
        mirror_chat_message(chat)
        return jsonify({'status': 'success', 'message': chat.to_dict()}), 201

    ChatMessage.query.filter_by(user_id=user.id, sender_role='admin', is_read=False).update({'is_read': True})
    db.session.commit()
    messages = ChatMessage.query.filter_by(user_id=user.id).order_by(ChatMessage.created_at.asc()).limit(200).all()
    return jsonify({'messages': [message.to_dict() for message in messages]}), 200


@api_bp.route('/admin/chat', methods=['GET'])
def admin_chat_overview():
    """Admin inbox grouped by user."""
    if not require_admin_password():
        return jsonify({'error': 'Valid admin password required'}), 401

    users = User.query.order_by(User.created_at.desc()).all()
    inbox = []
    for user in users:
        latest = ChatMessage.query.filter_by(user_id=user.id).order_by(ChatMessage.created_at.desc()).first()
        if latest:
            inbox.append({
                'user': user.to_dict(),
                'latest_message': latest.to_dict(),
                'unread_count': ChatMessage.query.filter_by(user_id=user.id, sender_role='user', is_read=False).count()
            })
    return jsonify({'threads': inbox}), 200


@api_bp.route('/admin/chat/<int:user_id>', methods=['GET', 'POST'])
def admin_chat_thread(user_id):
    """Admin reads or replies to one user's chat thread."""
    if not require_admin_password():
        return jsonify({'error': 'Valid admin password required'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'POST':
        data = request_data()
        message = clean_text(data.get('message'))
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        chat = ChatMessage(user_id=user.id, sender_role='admin', message=message, created_at=datetime.utcnow())
        db.session.add(chat)
        db.session.commit()
        mirror_chat_message(chat)
        create_notification(user, 'Admin replied to your support chat.', 'admin_chat')
        return jsonify({'status': 'success', 'message': chat.to_dict()}), 201

    ChatMessage.query.filter_by(user_id=user.id, sender_role='user', is_read=False).update({'is_read': True})
    db.session.commit()
    messages = ChatMessage.query.filter_by(user_id=user.id).order_by(ChatMessage.created_at.asc()).limit(200).all()
    return jsonify({'user': user.to_dict(), 'messages': [message.to_dict() for message in messages]}), 200


@api_bp.route('/community/posts', methods=['GET', 'POST'])
def community_posts():
    """Community forum post list and create endpoint."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    if request.method == 'POST':
        data = request_data()
        title_text = clean_text(data.get('title'))
        content = clean_text(data.get('content'))
        if not title_text or not content:
            return jsonify({'error': 'Title and content are required'}), 400
        user = User.query.get(user_id)
        post = ForumPost(
            user_id=user_id,
            title=title_text,
            category=clean_text(data.get('category')) or 'general',
            content=content,
            plant_type=clean_text(data.get('plant_type') or data.get('plantType')) or (user.plant_type if user else None),
            created_at=datetime.utcnow()
        )
        db.session.add(post)
        db.session.commit()
        mirror_forum_post(post)
        return jsonify({'status': 'success', 'post': post.to_dict()}), 201

    posts = ForumPost.query.order_by(ForumPost.updated_at.desc()).limit(100).all()
    return jsonify({'posts': [post.to_dict() for post in posts]}), 200


@api_bp.route('/community/posts/<int:post_id>/replies', methods=['POST'])
def community_reply(post_id):
    """Reply to a community forum post."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    post = ForumPost.query.get(post_id)
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    data = request_data()
    content = clean_text(data.get('content'))
    if not content:
        return jsonify({'error': 'Reply content is required'}), 400

    reply = ForumReply(post_id=post.id, user_id=user_id, content=content, created_at=datetime.utcnow())
    post.updated_at = datetime.utcnow()
    db.session.add(reply)
    db.session.commit()
    mirror_forum_reply(reply)
    if post.user_id != user_id:
        owner = User.query.get(post.user_id)
        if owner:
            create_notification(owner, f'New reply on your community post: {post.title}', 'community_reply')
    return jsonify({'status': 'success', 'reply': reply.to_dict(), 'post': post.to_dict()}), 201

@api_bp.route('/supabase/status', methods=['GET'])
def supabase_status():
    """Return backend Supabase configuration and table reachability without exposing keys."""
    return jsonify(check_connection([
        'users',
        'projects',
        'devices',
        'device_statuses',
        'sensor_readings',
        'recommendations',
        'notifications',
        'disease_detections',
        'weather_records',
        'weather_training_runs',
        'chat_messages',
        'forum_posts',
        'forum_replies'
    ], include_write=True)), 200


@api_bp.route('/admin/users', methods=['POST'])
def admin_create_user():
    """Create a user directly from the admin dashboard."""
    if not require_admin_password():
        return jsonify({'error': 'Valid admin password required'}), 401

    data = request_data()
    username = clean_text(data.get('username'))
    email = clean_text(data.get('email')).lower()
    password = data.get('password') or ''
    device_id = clean_text(data.get('device_id') or data.get('deviceId'))
    approval_status = clean_text(data.get('approval_status') or data.get('status') or 'accepted').lower()

    try:
        if not username or not email or not password:
            return jsonify({'error': 'Username, email, and password are required'}), 400
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        if '@' not in email:
            return jsonify({'error': 'Enter a valid email address'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if approval_status not in {'pending', 'accepted', 'rejected'}:
            return jsonify({'error': 'Status must be pending, accepted, or rejected'}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 409
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 409
        if device_id and Device.query.filter_by(device_id=device_id).first():
            return jsonify({'error': 'Device ID is already registered'}), 409

        user = User(
            username=username,
            email=email,
            farm_name=clean_text(data.get('farm_name') or data.get('farmName')) or None,
            plant_type=clean_text(data.get('plant_type') or data.get('plantType')) or None,
            approval_status=approval_status
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        device, status = create_user_device(user, device_id)
        db.session.commit()

        mirror_user(user)
        mirror_device(device)
        mirror_device_status(status)

        return jsonify({
            'status': 'success',
            'user': user_admin_payload(user),
            'device': device.to_dict()
        }), 201

    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Admin user creation failed: {str(exc)}")
        return jsonify({'error': 'Could not create user'}), 500


@api_bp.route('/admin/users/<int:user_id>', methods=['PATCH', 'DELETE'])
def admin_manage_user(user_id):
    """Approve/reject/delete users from the admin panel."""
    if not require_admin_password():
        return jsonify({'error': 'Valid admin password required'}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'DELETE':
        for table in [
            'sensor_readings',
            'device_statuses',
            'disease_detections',
            'recommendations',
            'notifications',
            'weather_records',
            'weather_training_runs',
            'chat_messages',
            'forum_replies',
            'forum_posts',
            'projects',
            'devices',
            'users'
        ]:
            field = 'local_id' if table == 'users' else 'user_id'
            delete_records(table, {field: user.id}, current_app.logger)
        db.session.delete(user)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'User deleted'}), 200

    data = request_data()
    approval_status = clean_text(data.get('approval_status') or data.get('status')).lower()
    if approval_status not in {'pending', 'accepted', 'rejected'}:
        return jsonify({'error': 'Status must be pending, accepted, or rejected'}), 400

    user.approval_status = approval_status
    db.session.commit()
    mirror_user(user)
    return jsonify({'status': 'success', 'user': user.to_dict()}), 200


def require_api_key(f):
    """Decorator to check API key for device requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or not verify_api_key(api_key):
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated_function

def verify_api_key(api_key):
    """Verify API key (implement your own logic)"""
    expected_key = current_app.config.get('DEVICE_API_KEY', 'farm-device-key')
    return api_key == expected_key

# ==================== SENSOR DATA ENDPOINTS ====================

@api_bp.route('/sensor-data', methods=['POST'])
@require_api_key
def receive_sensor_data():
    """
    Receive sensor data from ESP32 device
    
    Expected JSON:
    {
        "device_id": "ESP32_001",
        "temperature": 28.5,
        "humidity": 65.3,
        "soil_moisture": 456,
        "mq2": 200,
        "mq5": 150,
        "mq7": 100,
        "mq135": 350,
        "sound": 45,
        "light": 800,
        "pump_status": false,
        "light_status": true
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'device_id' not in data:
            return jsonify({'error': 'Missing device_id'}), 400
        
        device_id = data.get('device_id')
        
        # Find device and user
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        
        user = User.query.get(device.user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Update device heartbeat
        device.last_heartbeat = datetime.utcnow()
        
        # Create sensor reading record
        reading = SensorReading(
            user_id=user.id,
            device_id=device_id,
            temperature=data.get('temperature'),
            humidity=data.get('humidity'),
            soil_moisture=data.get('soil_moisture'),
            mq2_reading=first_present(data, 'mq2', 'mq02'),
            mq5_reading=first_present(data, 'mq5', 'mq05'),
            mq7_reading=first_present(data, 'mq7', 'mq07'),
            mq135_reading=first_present(data, 'mq135'),
            sound_level=first_present(data, 'sound', 'sound_level'),
            light_intensity=first_present(data, 'light', 'light_intensity', 'lux'),
            rain_level=first_present(data, 'rain', 'rain_level'),
            water_level=first_present(data, 'water', 'water_level'),
            motion_detected=bool_or_false(data.get('motion_detected') if 'motion_detected' in data else data.get('motion')),
            pump_status=data.get('pump_status', False),
            light_status=data.get('light_status', False)
        )

        status = DeviceStatus.query.filter_by(user_id=user.id, device_id=device_id).first()
        if not status:
            status = DeviceStatus(user_id=user.id, device_id=device_id)
            db.session.add(status)

        if status.auto_watering_enabled and reading.soil_moisture is not None:
            water_ok = reading.water_level is None or reading.water_level > 20
            if reading.soil_moisture < (status.moisture_threshold or 30) and water_ok:
                status.pump_on = True
                status.last_watering = datetime.utcnow()
                status.last_command = 'auto_pump_on'
                status.last_command_time = datetime.utcnow()
            elif reading.soil_moisture >= (status.moisture_threshold or 30) + 8:
                status.pump_on = False
                status.last_command = 'auto_pump_off'
                status.last_command_time = datetime.utcnow()

        db.session.add(reading)
        db.session.commit()

        mirror_device(device)
        mirror_sensor_reading(reading)
        mirror_device_status(status)
        
        # Check for alerts and thresholds
        check_sensor_thresholds(user, reading)
        record_realtime_weather_from_sensor(user, device_id, reading, data)
        maybe_create_hourly_farm_analysis(user, device_id)
        maybe_create_weather_prediction_notification(user, device_id, force=False)
        
        current_app.logger.info(f"Sensor data received from {device_id}")
        
        return jsonify({
            'status': 'success',
            'message': 'Sensor data received',
            'reading_id': reading.id
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error in receive_sensor_data: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/sensor-data/<device_id>', methods=['GET'])
def get_sensor_data(device_id):
    """
    Get sensor data for a device
    Query params:
    - limit: number of readings (default 100)
    - hours: get data from last N hours (default 24)
    """
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        
        limit = request.args.get('limit', 100, type=int)
        hours = request.args.get('hours', 24, type=int)
        
        # Get readings from specified time period
        time_threshold = datetime.utcnow() - timedelta(hours=hours)
        
        readings = SensorReading.query.filter(
            SensorReading.device_id == device_id,
            SensorReading.timestamp >= time_threshold
        ).order_by(SensorReading.timestamp.desc()).limit(limit).all()
        
        return jsonify({
            'device_id': device_id,
            'readings': [reading.to_dict() for reading in readings],
            'count': len(readings)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/demo/seed/<device_id>', methods=['POST'])
def seed_virtual_farm_data(device_id):
    """Create a realistic local reading so the product works without IoT hardware."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        device = Device.query.filter_by(device_id=device_id, user_id=user.id).first()
        if not device:
            device, status = create_user_device(user, device_id)
        else:
            status = DeviceStatus.query.filter_by(user_id=user.id, device_id=device.device_id).first()
            if not status:
                status = DeviceStatus(user_id=user.id, device_id=device.device_id)
                db.session.add(status)
                db.session.flush()

        now = datetime.utcnow()
        phase = (now.minute + now.second / 60) / 60
        temperature = 25.5 + 3.2 * phase
        humidity = 58 + 12 * (1 - phase)
        soil_moisture = 38 + 18 * phase
        light_intensity = 520 + 460 * phase
        rain_level = 6 + 18 * max(0, 0.55 - phase)
        water_level = 72 - 8 * phase

        reading = SensorReading(
            user_id=user.id,
            device_id=device.device_id,
            temperature=round(temperature, 2),
            humidity=round(humidity, 2),
            soil_moisture=round(soil_moisture, 2),
            mq5_reading=round(125 + 25 * phase, 2),
            mq7_reading=round(72 + 18 * phase, 2),
            mq135_reading=round(245 + 35 * phase, 2),
            light_intensity=round(light_intensity, 2),
            rain_level=round(rain_level, 2),
            water_level=round(water_level, 2),
            motion_detected=phase > 0.72,
            pump_status=soil_moisture < 42,
            light_status=light_intensity < 650,
            timestamp=now
        )

        status.pump_on = reading.pump_status
        status.light_on = reading.light_status
        status.uv_light_level = 62 if reading.light_status else 48
        status.last_command = 'virtual_farm_sample'
        status.last_command_time = now
        if reading.pump_status:
            status.last_watering = now
        device.last_heartbeat = now

        db.session.add(reading)
        db.session.commit()

        mirror_device(device)
        mirror_sensor_reading(reading)
        mirror_device_status(status)
        check_sensor_thresholds(user, reading)
        record_realtime_weather_from_sensor(user, device.device_id, reading, {
            'pressure': 1012.8,
            'rainfall': reading.rain_level
        })
        maybe_create_hourly_farm_analysis(user, device.device_id)
        prediction = create_weather_prediction_record(user, device, force=True, notify=False)

        create_notification(
            user,
            'Virtual Farm Mode added one demo reading. Connect ESP32 later with the same device ID.',
            'virtual_farm'
        )

        return jsonify({
            'status': 'success',
            'mode': 'virtual_farm',
            'device': device.to_dict(),
            'reading': reading.to_dict(),
            'device_status': status.to_dict(),
            'weather_prediction': prediction.to_dict() if prediction else None
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error seeding virtual farm data: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==================== DEVICE CONTROL ENDPOINTS ====================

@api_bp.route('/device-command', methods=['POST'])
def send_device_command():
    """
    Send control command to device
    
    Expected JSON:
    {
        "device_id": "ESP32_001",
        "command": "pump_on" | "pump_off" | "light_on" | "light_off" | "restart"
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'device_id' not in data or 'command' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        device_id = data.get('device_id')
        command = data.get('command')
        
        # Find device
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404

        api_key_ok = verify_api_key(request.headers.get('X-API-Key'))
        session_user_id = session.get('user_id')
        if not api_key_ok and session_user_id != device.user_id:
            return jsonify({'error': 'Login or valid device API key required'}), 401
        
        user = User.query.get(device.user_id)
        
        # Get or create device status
        status = DeviceStatus.query.filter_by(
            user_id=user.id,
            device_id=device_id
        ).first()
        
        if not status:
            status = DeviceStatus(user_id=user.id, device_id=device_id)
            db.session.add(status)
        
        # Process command
        if command == 'pump_on':
            status.pump_on = True
            status.last_watering = datetime.utcnow()
            create_notification(user, 'Pump turned ON', 'device_control')
            
        elif command == 'pump_off':
            status.pump_on = False
            create_notification(user, 'Pump turned OFF', 'device_control')
            
        elif command == 'pump_b_on':
            status.pump_b_on = True
            create_notification(user, 'Pump B turned ON', 'device_control')

        elif command == 'pump_b_off':
            status.pump_b_on = False
            create_notification(user, 'Pump B turned OFF', 'device_control')

        elif command == 'light_on':
            status.light_on = True
            create_notification(user, 'Light turned ON', 'device_control')
            
        elif command == 'light_off':
            status.light_on = False
            create_notification(user, 'Light turned OFF', 'device_control')

        elif command in {'auto_on', 'auto_watering_on'}:
            status.auto_watering_enabled = True
            create_notification(user, 'Automatic watering enabled', 'device_control')

        elif command in {'auto_off', 'auto_watering_off'}:
            status.auto_watering_enabled = False
            create_notification(user, 'Automatic watering disabled', 'device_control')

        elif command in {'uv_level', 'set_uv_level'}:
            uv_level = number_or_none(first_present(data, 'uv_light_level', 'level', 'value'))
            if uv_level is None:
                return jsonify({'error': 'uv_light_level is required'}), 400
            status.uv_light_level = max(0, min(100, uv_level))
            create_notification(user, f'UV light level set to {status.uv_light_level:.0f}%', 'device_control')

        elif command in {'camera_scan', 'capture_disease_image'}:
            create_notification(user, 'ESP camera disease scan requested. The camera module should upload the next plant image.', 'camera_scan')

        else:
            return jsonify({'error': 'Unknown command'}), 400
        
        status.last_command = command
        status.last_command_time = datetime.utcnow()
        
        db.session.commit()
        mirror_device_status(status)
        mirror_device(device)
        
        current_app.logger.info(f"Command '{command}' sent to {device_id}")
        
        return jsonify({
            'status': 'success',
            'message': f'Command {command} queued',
            'device_id': device_id
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/device-status/<device_id>', methods=['GET'])
def get_device_status(device_id):
    """Get current status of device"""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        
        status = DeviceStatus.query.filter_by(device_id=device_id).first()
        
        if not status:
            return jsonify({
                'device_id': device_id,
                'pump_on': False,
                'pump_b_on': False,
                'light_on': False,
                'uv_light_level': 65
            }), 200
        
        return jsonify(status.to_dict()), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/sensor-analysis/<device_id>', methods=['GET', 'POST'])
def analyze_stored_sensor_data(device_id):
    """Analyze stored sensor history and save recommendations."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404

        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 120, type=int)
        time_threshold = datetime.utcnow() - timedelta(hours=hours)
        readings = SensorReading.query.filter(
            SensorReading.device_id == device_id,
            SensorReading.timestamp >= time_threshold
        ).order_by(SensorReading.timestamp.desc()).limit(limit).all()

        user = User.query.get(device.user_id)
        result = analyze_sensor_history(readings, plant_type=user.plant_type if user else None)
        saved = []

        if user:
            for item in result['recommendations']:
                rec = save_sensor_recommendation(user, item, result['summary'])
                saved.append(rec.to_dict())

        return jsonify({
            'status': 'success',
            'device_id': device_id,
            'summary': result['summary'],
            'recommendations': result['recommendations'],
            'saved_recommendations': saved
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error in sensor analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/farm-analysis/<device_id>', methods=['POST'])
def run_manual_farm_analysis(device_id):
    """Manual full analysis: sensors, predicted weather, and crop planning."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        if not has_device_access(device):
            return jsonify({'error': 'Login or valid device API key required'}), 401

        user = User.query.get(device.user_id)
        hours = request.args.get('hours', 96, type=int)
        limit = request.args.get('limit', 180, type=int)
        time_threshold = datetime.utcnow() - timedelta(hours=hours)
        readings = SensorReading.query.filter(
            SensorReading.device_id == device_id,
            SensorReading.timestamp >= time_threshold
        ).order_by(SensorReading.timestamp.desc()).limit(limit).all()

        sensor_result = analyze_sensor_history(readings, plant_type=user.plant_type if user else None)
        saved = []
        if user:
            for item in sensor_result['recommendations'][:5]:
                rec = save_sensor_recommendation(user, item, sensor_result['summary'], 'manual_farm_analysis')
                saved.append(rec.to_dict())

        weather_record = create_weather_prediction_record(user, device, force=True, notify=True)

        return jsonify({
            'status': 'success',
            'device_id': device_id,
            'summary': sensor_result['summary'],
            'recommendations': sensor_result['recommendations'],
            'saved_recommendations': saved,
            'weather': weather_record.to_dict() if weather_record else None
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error in manual farm analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/weather/<device_id>', methods=['GET'])
def get_weather_records(device_id):
    """Return realtime and predicted weather records for a device owner."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        if not has_device_access(device):
            return jsonify({'error': 'Login or valid device API key required'}), 401

        user = User.query.get(device.user_id)
        geo_result = None
        if os.environ.get('WEATHER_GEO_AUTOSYNC', 'true').lower() not in {'0', 'false', 'no', 'off'}:
            try:
                geo_result = create_geo_weather_records(user, device, force=False)
            except Exception as exc:
                geo_result = {'status': 'error', 'error': str(exc)}
                current_app.logger.debug("Geo weather autosync skipped: %s", exc)

        limit = request.args.get('limit', 24, type=int)
        records = WeatherRecord.query.filter_by(user_id=device.user_id, device_id=device_id)\
            .order_by(WeatherRecord.created_at.desc()).limit(limit).all()
        latest_prediction = next((record for record in records if record.source == 'predicted'), None)
        latest_realtime = next((record for record in records if record.source in {'realtime', 'geo_realtime'}), None)
        daily_records = [record for record in records if record.source == 'geo_daily']
        training = WeatherTrainingRun.query.filter_by(user_id=device.user_id, device_id=device_id)\
            .order_by(WeatherTrainingRun.started_at.desc()).first()

        return jsonify({
            'device_id': device_id,
            'records': [record.to_dict() for record in records],
            'latest_prediction': latest_prediction.to_dict() if latest_prediction else None,
            'latest_realtime': latest_realtime.to_dict() if latest_realtime else None,
            'latest_geo_daily': daily_records[0].to_dict() if daily_records else None,
            'daily_records': [record.to_dict() for record in daily_records[:7]],
            'geo_status': geo_result,
            'latest_training_run': training.to_dict() if training else None,
            'latest_training': training.to_dict() if training else None,
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/weather/predict/<device_id>', methods=['POST'])
def predict_device_weather(device_id):
    """Run weather prediction immediately and notify the user."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        if not has_device_access(device):
            return jsonify({'error': 'Login or valid device API key required'}), 401

        user = User.query.get(device.user_id)
        try:
            create_geo_weather_records(user, device, force=False)
        except Exception as exc:
            current_app.logger.debug("Geo weather sync skipped before prediction: %s", exc)
        record = create_weather_prediction_record(user, device, force=True, notify=True)
        return jsonify({
            'status': 'success',
            'prediction': record.to_dict() if record else None
        }), 201

    except Exception as e:
        current_app.logger.error(f"Error in weather prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/weather/geo/<device_id>', methods=['POST'])
def sync_geo_weather(device_id):
    """Fetch and save geolocation-wise current and daily weather."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        if not has_device_access(device):
            return jsonify({'error': 'Login or valid device API key required'}), 401

        user = User.query.get(device.user_id)
        result = create_geo_weather_records(
            user,
            device,
            force=str(request.args.get('force', '')).lower() in {'1', 'true', 'yes', 'on'}
        )
        status = 201 if result.get('status') in {'success', 'updated'} else 200
        return jsonify(result), status

    except Exception as e:
        current_app.logger.error(f"Error in geo weather sync: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/weather/tick/<device_id>', methods=['POST'])
def weather_notification_tick(device_id):
    """Create a 30-minute weather notification only when the cadence is due."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        if not has_device_access(device):
            return jsonify({'error': 'Login or valid device API key required'}), 401

        user = User.query.get(device.user_id)
        record = maybe_create_weather_prediction_notification(user, device_id, force=False)
        return jsonify({
            'status': 'success',
            'prediction': record.to_dict() if record else None
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error in weather tick: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/weather/train/<device_id>', methods=['POST'])
def train_weather_model(device_id):
    """Quarterly user-triggered Transformer calibration from realtime weather data."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        if not has_device_access(device):
            return jsonify({'error': 'Login or valid device API key required'}), 401

        user = User.query.get(device.user_id)
        since = datetime.utcnow() - timedelta(days=92)
        records = WeatherRecord.query.filter(
            WeatherRecord.user_id == user.id,
            WeatherRecord.device_id == device_id,
            WeatherRecord.created_at >= since
        ).order_by(WeatherRecord.created_at.desc()).all()

        result = evaluate_weather_training(records)
        run = WeatherTrainingRun(
            user_id=user.id,
            device_id=device_id,
            samples_count=result.get('samples_count') or 0,
            accuracy_score=result.get('accuracy_score'),
            mean_absolute_error=result.get('mean_absolute_error'),
            status=result.get('status'),
            model_version='weather_prediction_transformer_model.keras',
            details=json.dumps(result.get('details', {})),
            completed_at=datetime.utcnow()
        )
        db.session.add(run)
        db.session.commit()
        mirror_weather_training_run(run)

        create_notification(
            user,
            f"Weather model training finished. Status: {run.status}. Accuracy: {run.accuracy_score or 'not enough data'}.",
            'weather_training'
        )

        return jsonify({
            'status': 'success',
            'training_run': run.to_dict(),
            'training': run.to_dict()
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error in weather training: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/recommendations/<device_id>', methods=['GET'])
def get_device_recommendations(device_id):
    """Return recent active recommendations for a device's owner."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404

        limit = request.args.get('limit', 20, type=int)
        recs = Recommendation.query.filter_by(user_id=device.user_id, is_active=True)\
            .order_by(Recommendation.time_of_analysis.desc()).limit(limit).all()

        return jsonify({
            'device_id': device_id,
            'recommendations': [rec.to_dict() for rec in recs]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/device-command/<device_id>', methods=['GET'])
@require_api_key
def get_pending_device_command(device_id):
    """ESP32 polling endpoint. Returns desired relay states and auto settings."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404

        device.last_heartbeat = datetime.utcnow()
        status = DeviceStatus.query.filter_by(device_id=device_id).first()
        if not status:
            status = DeviceStatus(user_id=device.user_id, device_id=device_id)
            db.session.add(status)
            db.session.commit()

        db.session.commit()
        mirror_device_status(status)

        return jsonify({
            'device_id': device_id,
            'pump_on': bool(status.pump_on),
            'pump_b_on': bool(status.pump_b_on),
            'light_on': bool(status.light_on),
            'uv_light_level': status.uv_light_level,
            'auto_watering_enabled': bool(status.auto_watering_enabled),
            'moisture_threshold': status.moisture_threshold,
            'last_command': status.last_command,
            'last_command_time': status.last_command_time.isoformat() if status.last_command_time else None
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/device-status/<device_id>', methods=['PUT'])
def update_device_status(device_id):
    """Update device status"""
    try:
        data = request.get_json()
        device = Device.query.filter_by(device_id=device_id).first()
        
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        
        status = DeviceStatus.query.filter_by(device_id=device_id).first()
        if not status:
            status = DeviceStatus(user_id=device.user_id, device_id=device_id)
            db.session.add(status)
        
        if 'moisture_threshold' in data:
            status.moisture_threshold = data['moisture_threshold']
        
        if 'auto_watering_enabled' in data:
            status.auto_watering_enabled = data['auto_watering_enabled']

        if 'pump_on' in data:
            status.pump_on = bool_or_false(data['pump_on'])

        if 'pump_b_on' in data:
            status.pump_b_on = bool_or_false(data['pump_b_on'])

        if 'light_on' in data:
            status.light_on = bool_or_false(data['light_on'])

        if 'uv_light_level' in data:
            uv_level = number_or_none(data.get('uv_light_level'))
            if uv_level is not None:
                status.uv_light_level = max(0, min(100, uv_level))
        
        db.session.commit()
        mirror_device_status(status)
        
        return jsonify({
            'status': 'success',
            'message': 'Device status updated'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== DISEASE DETECTION ENDPOINTS ====================

@api_bp.route('/upload-disease-image', methods=['POST'])
@require_api_key
def upload_disease_image():
    """
    Upload image for disease detection
    Can be from user upload or IoT camera
    """
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400
        
        device_id = request.form.get('device_id')
        user_id = request.form.get('user_id')
        
        image_file = request.files['image']
        
        if image_file.filename == '':
            return jsonify({'error': 'No image selected'}), 400
        if not allowed_image_file(image_file.filename):
            return jsonify({'error': 'Unsupported image type. Use PNG, JPG, JPEG, WEBP, BMP, GIF, or AVIF.'}), 400
        
        # Save image
        from werkzeug.utils import secure_filename
        
        filename = secure_filename(f"{datetime.utcnow().timestamp()}_{image_file.filename}")
        upload_folder = disease_upload_folder()
        filepath = str(upload_folder / filename)
        image_file.save(filepath)
        
        # Save detection record
        device = Device.query.filter_by(device_id=device_id).first() if device_id else None
        if device:
            device.last_heartbeat = datetime.utcnow()
            device.is_active = True

        user = User.query.get(user_id) if user_id else (device.user if device else None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404

        started_at = perf_counter()
        detection_results = analyze_image_for_disease(filepath)
        current_app.logger.info("Disease inference finished in %.2fs for %s", perf_counter() - started_at, filename)
        if detection_results.get('error'):
            return jsonify({
                'error': detection_results.get('error'),
                'status': 'disease_worker_failed',
                'primary_disease': None,
                'confidence': 0
            }), 503
        original_image_url = public_image_url(filepath) or f'/uploads/disease_images/{filename}'
        diagnosis_image_url = (
            public_image_url(detection_results.get('annotated_image_path'))
            or detection_results.get('annotated_image_url')
            or original_image_url
        )
        
        detection = DiseaseDetection(
            user_id=user.id,
            device_id=device_id,
            image_path=filepath,
            image_url=diagnosis_image_url,
            is_from_camera=bool(device_id),
            primary_disease=detection_results.get('primary_disease'),
            disease_confidence=detection_results.get('confidence'),
            detections=json.dumps(detection_results.get('detections', {})),
            recommendations=json.dumps(detection_results.get('recommendations', [])),
            severity_level=detection_results.get('severity')
        )
        
        db.session.add(detection)
        db.session.commit()
        notification_id = None
        
        # Create notification if disease detected
        if disease_detected(detection.primary_disease, detection.disease_confidence):
            notification = create_notification(
                user,
                f"Disease Detected: {detection.primary_disease} ({detection.disease_confidence:.1f}% confidence)",
                'disease_alert',
                mirror_remote=False
            )
            notification_id = notification.id if notification else None
        mirror_disease_artifacts_async(current_app._get_current_object(), detection.id, notification_id)
        
        current_app.logger.info(f"Disease image analyzed: {detection.primary_disease}")
        
        return jsonify({
            'status': 'success',
            'detection_id': detection.id,
            'image_url': detection.image_url,
            'annotated_image_url': detection.image_url,
            'original_image_url': original_image_url,
            'primary_disease': detection.primary_disease,
            'confidence': detection.disease_confidence,
            'severity': detection.severity_level,
            'detections': detection_results.get('detections', {}),
            'possible_detections': detection_results.get('possible_detections', {}),
            'boxes': detection_results.get('boxes', []),
            'discarded_low_confidence': detection_results.get('discarded_low_confidence', 0),
            'confidence_threshold': detection_results.get('confidence_threshold'),
            'possible_confidence_threshold': detection_results.get('possible_confidence_threshold'),
            'recommendations': detection_results.get('recommendations', [])
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error in upload_disease_image: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/disease-detection', methods=['POST'])
def upload_user_disease_image():
    """Analyze a user-uploaded plant image with YOLO and save the result."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login required'}), 401

    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({'error': 'No image selected'}), 400
    if not allowed_image_file(image_file.filename):
        return jsonify({'error': 'Unsupported image type. Use PNG, JPG, JPEG, WEBP, BMP, GIF, or AVIF.'}), 400

    try:
        from werkzeug.utils import secure_filename

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        device_id = clean_text(request.form.get('device_id')) or None
        device = Device.query.filter_by(device_id=device_id, user_id=user.id).first() if device_id else None
        if device:
            device.last_heartbeat = datetime.utcnow()
            device.is_active = True

        filename = secure_filename(f"{datetime.utcnow().timestamp()}_{image_file.filename}")
        upload_folder = disease_upload_folder()
        filepath = str(upload_folder / filename)
        image_file.save(filepath)

        started_at = perf_counter()
        detection_results = analyze_image_for_disease(filepath)
        current_app.logger.info("Disease inference finished in %.2fs for %s", perf_counter() - started_at, filename)
        if detection_results.get('error'):
            return jsonify({
                'error': detection_results.get('error'),
                'status': 'disease_worker_failed',
                'primary_disease': None,
                'confidence': 0
            }), 503
        original_image_url = public_image_url(filepath) or f'/uploads/disease_images/{filename}'
        diagnosis_image_url = (
            public_image_url(detection_results.get('annotated_image_path'))
            or detection_results.get('annotated_image_url')
            or original_image_url
        )

        detection = DiseaseDetection(
            user_id=user.id,
            device_id=device.device_id if device else device_id,
            image_path=filepath,
            image_url=diagnosis_image_url,
            is_from_camera=False,
            primary_disease=detection_results.get('primary_disease'),
            disease_confidence=detection_results.get('confidence'),
            detections=json.dumps(detection_results.get('detections', {})),
            recommendations=json.dumps(detection_results.get('recommendations', [])),
            severity_level=detection_results.get('severity')
        )

        db.session.add(detection)
        db.session.commit()
        notification_id = None

        if disease_detected(detection.primary_disease, detection.disease_confidence):
            notification = create_notification(
                user,
                f"Disease Detected: {detection.primary_disease} ({detection.disease_confidence:.1f}% confidence)",
                'disease_alert',
                mirror_remote=False
            )
            notification_id = notification.id if notification else None
        mirror_disease_artifacts_async(current_app._get_current_object(), detection.id, notification_id)

        return jsonify({
            'status': 'success',
            'detection_id': detection.id,
            'image_url': detection.image_url,
            'annotated_image_url': detection.image_url,
            'original_image_url': original_image_url,
            'primary_disease': detection.primary_disease,
            'confidence': detection.disease_confidence,
            'severity': detection.severity_level,
            'detections': detection_results.get('detections', {}),
            'possible_detections': detection_results.get('possible_detections', {}),
            'boxes': detection_results.get('boxes', []),
            'discarded_low_confidence': detection_results.get('discarded_low_confidence', 0),
            'confidence_threshold': detection_results.get('confidence_threshold'),
            'possible_confidence_threshold': detection_results.get('possible_confidence_threshold'),
            'recommendations': detection_results.get('recommendations', [])
        }), 201

    except Exception as e:
        current_app.logger.error(f"Error in upload_user_disease_image: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/disease-detections/<device_id>', methods=['GET'])
def get_disease_detections(device_id):
    """Return manual and ESP camera disease detections for a device owner."""
    try:
        device = Device.query.filter_by(device_id=device_id).first()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        if not has_device_access(device):
            return jsonify({'error': 'Login or valid device API key required'}), 401

        limit = request.args.get('limit', 20, type=int)
        detections = DiseaseDetection.query.filter_by(user_id=device.user_id)\
            .order_by(DiseaseDetection.timestamp.desc()).limit(limit).all()
        return jsonify({
            'device_id': device_id,
            'detections': [disease_detection_payload(detection) for detection in detections]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def analyze_image_for_disease(image_path):
    """Analyze image for crop diseases using YOLO"""
    try:
        remote_result = analyze_image_with_disease_service(image_path)
        if remote_result is not None:
            return remote_result

        run_disease_analysis, _ = _get_disease_functions()
        return run_disease_analysis(image_path, logger=current_app.logger)
        
    except Exception as e:
        current_app.logger.error(f"Error analyzing image: {str(e)}")
        return {'error': str(e), 'primary_disease': None, 'confidence': 0, 'detections': {}, 'boxes': []}


def generate_disease_recommendations(disease, confidence):
    """Generate treatment recommendations for detected disease"""
    _, build_disease_recommendations = _get_disease_functions()
    return build_disease_recommendations(disease, confidence)


# ==================== GEOLOCATION ANALYSIS ENDPOINTS ====================

@api_bp.route('/analyze-geolocation', methods=['POST'])
def analyze_geolocation():
    """
    Analyze farm location suitability for vertical farming
    
    Expected JSON:
    {
        "user_id": 1,
        "latitude": 40.7128,
        "longitude": -74.0060,
        "area_size": 100.0
    }
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        area_size = data.get('area_size')
        
        if not all([user_id, latitude, longitude, area_size]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Analyze geolocation
        analysis_result = analyze_location_for_farming(latitude, longitude, area_size)
        
        # Update user
        user.farm_location_lat = latitude
        user.farm_location_lon = longitude
        user.farm_size = area_size
        user.farm_area_suitability = analysis_result['suitability_score']
        user.geolocation_analyzed = True
        
        # Create recommendations
        created_recs = []
        for plant in analysis_result['recommended_plants']:
            rec = Recommendation(
                user_id=user.id,
                recommendation_type='plant_suggestion',
                suitable_plants=json.dumps([plant['name']]),
                plant_score=plant['score'],
                expected_yield=plant.get('expected_yield'),
                cost_estimate=plant.get('cost_estimate'),
                growing_period=plant.get('growing_period'),
                reason=plant.get('reason'),
                based_on_factors=json.dumps(analysis_result['climate_factors'])
            )
            db.session.add(rec)
            created_recs.append(rec)
        
        db.session.commit()
        mirror_user(user)
        for rec in created_recs:
            mirror_recommendation(rec)
        
        # Create notification
        create_notification(
            user,
            f"Geolocation Analysis Complete: {analysis_result['suitability_score']}% suitable for vertical farming",
            'geolocation_analysis'
        )
        
        return jsonify({
            'status': 'success',
            'suitability_score': analysis_result['suitability_score'],
            'location_status': analysis_result['location_status'],
            'recommended_plants': analysis_result['recommended_plants'],
            'climate_factors': analysis_result['climate_factors']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def analyze_location_for_farming(latitude, longitude, area_size):
    """
    Analyze location for vertical farming suitability
    This would integrate with real ML model in production
    """
    try:
        # Get climate data (would use API like OpenWeatherMap in production)
        # For now, using dummy data
        
        # Basic suitability scoring
        suitability_score = 70  # Default score
        
        # Simple rules
        if area_size < 50:
            location_status = "Small indoor area - suitable for compact systems"
            suitability_score -= 10
        elif area_size < 200:
            location_status = "Medium area - ideal for vertical farming"
        else:
            location_status = "Large area - highly suitable for vertical farming"
            suitability_score += 10
        
        # Sample recommended plants based on location
        recommended_plants = [
            {
                'name': 'Lettuce',
                'score': 85,
                'expected_yield': 50,
                'cost_estimate': 200,
                'growing_period': 30,
                'reason': 'High demand, fast growth, low maintenance'
            },
            {
                'name': 'Spinach',
                'score': 80,
                'expected_yield': 45,
                'cost_estimate': 180,
                'growing_period': 35,
                'reason': 'Nutritious, good yield, suitable for vertical systems'
            },
            {
                'name': 'Tomato',
                'score': 75,
                'expected_yield': 60,
                'cost_estimate': 300,
                'growing_period': 60,
                'reason': 'Higher value crop, requires more resources'
            },
            {
                'name': 'Basil',
                'score': 88,
                'expected_yield': 30,
                'cost_estimate': 150,
                'growing_period': 25,
                'reason': 'Herbs are profitable, fast growing'
            },
            {
                'name': 'Cucumber',
                'score': 70,
                'expected_yield': 40,
                'cost_estimate': 250,
                'growing_period': 45,
                'reason': 'Good for vertical trellising systems'
            }
        ]
        
        climate_factors = {
            'temperature_optimal': '18-24Â°C',
            'humidity_optimal': '60-70%',
            'light_requirement': '12-16 hours/day',
            'water_requirement': 'Consistent moisture',
            'latitude': latitude,
            'longitude': longitude
        }
        
        return {
            'suitability_score': suitability_score,
            'location_status': location_status,
            'recommended_plants': recommended_plants,
            'climate_factors': climate_factors
        }
        
    except Exception as e:
        current_app.logger.error(f"Error in analyze_location_for_farming: {str(e)}")
        return {
            'suitability_score': 50,
            'location_status': 'Unable to analyze',
            'recommended_plants': [],
            'climate_factors': {}
        }


# ==================== UTILITY FUNCTIONS ====================

def has_device_access(device):
    """Allow the owning browser session or an ESP32 with the device API key."""
    return verify_api_key(request.headers.get('X-API-Key')) or session.get('user_id') == device.user_id


def check_sensor_thresholds(user, reading):
    """Check if any sensor readings exceed thresholds and create alerts"""
    alerts = []
    
    if reading.soil_moisture is not None and reading.soil_moisture < 30:
        alerts.append("Low soil moisture! Consider watering.")

    if reading.soil_moisture is not None and reading.soil_moisture > 82:
        alerts.append("Soil is heavily saturated. Pause irrigation and check drainage.")

    if reading.water_level is not None and reading.water_level < 20:
        alerts.append("Reservoir water level is low. Refill before automatic watering.")

    if reading.rain_level is not None and reading.rain_level > 60:
        alerts.append("Rain detected. Outdoor irrigation should stay paused.")

    if reading.motion_detected:
        alerts.append("Motion detected near the farm. Check the camera feed or field entry point.")
    
    if reading.temperature is not None and reading.temperature > 35:
        alerts.append("High temperature! Improve cooling or ventilation.")
    
    if reading.humidity is not None and reading.humidity < 40:
        alerts.append("Low humidity! Increase moisture in the environment.")
    
    if reading.mq135_reading is not None and reading.mq135_reading > 400:
        alerts.append("Air quality low! Check ventilation system.")
    
    for alert in alerts:
        create_notification(user, alert, 'sensor_alert')


def maybe_create_sensor_agent_recommendation(user, device_id):
    """Analyze recent readings periodically after sensor ingestion."""
    latest_rec = Recommendation.query.filter_by(
        user_id=user.id,
        recommendation_type='sensor_agent',
        is_active=True
    ).order_by(Recommendation.time_of_analysis.desc()).first()

    if latest_rec and datetime.utcnow() - latest_rec.time_of_analysis < timedelta(minutes=30):
        return

    readings = SensorReading.query.filter_by(user_id=user.id, device_id=device_id)\
        .order_by(SensorReading.timestamp.desc()).limit(80).all()

    if len(readings) < 3:
        return

    result = analyze_sensor_history(readings, plant_type=user.plant_type)
    for item in result['recommendations'][:3]:
        save_sensor_recommendation(user, item, result['summary'])


def maybe_create_hourly_farm_analysis(user, device_id):
    """Analyze stored conditions at most once per hour for automatic guidance."""
    latest_rec = Recommendation.query.filter_by(
        user_id=user.id,
        recommendation_type='hourly_farm_analysis',
        is_active=True
    ).order_by(Recommendation.time_of_analysis.desc()).first()

    if latest_rec and datetime.utcnow() - latest_rec.time_of_analysis < timedelta(hours=1):
        return

    readings = SensorReading.query.filter_by(user_id=user.id, device_id=device_id)\
        .order_by(SensorReading.timestamp.desc()).limit(120).all()

    if len(readings) < 3:
        return

    result = analyze_sensor_history(readings, plant_type=user.plant_type)
    for item in result['recommendations'][:3]:
        save_sensor_recommendation(user, item, result['summary'], 'hourly_farm_analysis')


def save_sensor_recommendation(user, item, summary, recommendation_type='sensor_agent'):
    rec = Recommendation(
        user_id=user.id,
        recommendation_type=recommendation_type,
        plant_score=priority_score(item.get('priority')),
        reason=f"{item.get('title')}: {item.get('reason')} Action: {item.get('action')}",
        based_on_factors=json.dumps(summary),
        time_of_analysis=datetime.utcnow(),
        is_active=True
    )
    db.session.add(rec)
    db.session.commit()
    mirror_recommendation(rec)
    create_notification(user, item.get('title', 'Sensor recommendation'), recommendation_type)
    return rec


def latest_project_for_user(user):
    return Project.query.filter_by(user_id=user.id).order_by(Project.updated_at.desc()).first()


def valid_location_pair(lat, lon):
    lat = number_or_none(lat)
    lon = number_or_none(lon)
    if lat is None or lon is None:
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if abs(lat) < 0.0001 and abs(lon) < 0.0001:
        return None
    return lat, lon


def weather_location(user, device=None, project=None):
    candidates = []
    if project:
        candidates.append((project.latitude, project.longitude))
    if user:
        candidates.append((user.farm_location_lat, user.farm_location_lon))
    if device:
        candidates.append((device.device_location_lat, device.device_location_lon))

    for lat, lon in candidates:
        location = valid_location_pair(lat, lon)
        if location:
            return location
    return None


def parse_forecast_date(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        try:
            return datetime.strptime(str(value), '%Y-%m-%d')
        except Exception:
            return datetime.utcnow()


def daily_value(daily, key, index):
    values = daily.get(key) or []
    if index >= len(values):
        return None
    return number_or_none(values[index])


def local_geo_weather_values(latitude, longitude, day_index=0):
    day = datetime.utcnow() + timedelta(days=day_index)
    seasonal = 0.5 + 0.5 * math.sin(((day.timetuple().tm_yday - 82) / 365) * math.tau)
    latitude_cool = min(18, abs(latitude) * 0.18)
    base = 29 - latitude_cool + seasonal * 7
    coastal_moisture = max(0, 1 - min(abs(longitude) / 180, 1))
    rain = max(0, 2 + coastal_moisture * 7 + (0.5 - seasonal) * 5 + (day_index % 3) * 1.6)
    humidity = max(35, min(92, 52 + coastal_moisture * 22 + rain * 1.2))
    return {
        'max_temperature': round(base + 2.8, 2),
        'min_temperature': round(base - 5.4, 2),
        'apparent_temperature': round(base + (humidity - 55) / 28, 2),
        'humidity': round(humidity, 2),
        'pressure': round(1013.25 - (base - 22) * 0.25, 2),
        'rainfall': round(rain, 2),
    }


def create_geo_fallback_weather_records(user, device, project, location, reason='open_meteo_unavailable'):
    latitude, longitude = location
    now = datetime.utcnow()
    saved = []
    current_values = local_geo_weather_values(latitude, longitude, 0)
    current_record = WeatherRecord(
        user_id=user.id,
        device_id=device.device_id,
        project_id=project.id if project else None,
        source='geo_realtime',
        horizon_minutes=0,
        max_temperature=current_values['max_temperature'],
        min_temperature=current_values['min_temperature'],
        apparent_temperature=current_values['apparent_temperature'],
        humidity=current_values['humidity'],
        pressure=current_values['pressure'],
        rainfall=current_values['rainfall'],
        confidence=58,
        model_status='local_geo_weather_fallback',
        raw_payload=json.dumps({
            'provider': 'local_geo_fallback',
            'reason': reason,
            'location': {'latitude': latitude, 'longitude': longitude}
        }),
        agent_summary='Local geolocation weather fallback saved because live weather API was unavailable.',
        forecast_for=now,
        created_at=now
    )
    db.session.add(current_record)
    saved.append(current_record)

    for day_index in range(7):
        values = local_geo_weather_values(latitude, longitude, day_index)
        forecast_for = (now + timedelta(days=day_index)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_start = forecast_for
        existing = WeatherRecord.query.filter(
            WeatherRecord.user_id == user.id,
            WeatherRecord.device_id == device.device_id,
            WeatherRecord.source == 'geo_daily',
            WeatherRecord.forecast_for >= day_start,
            WeatherRecord.forecast_for < day_start + timedelta(days=1)
        ).first()
        record = existing or WeatherRecord(
            user_id=user.id,
            device_id=device.device_id,
            project_id=project.id if project else None,
            source='geo_daily',
            forecast_for=forecast_for
        )
        record.horizon_minutes = max(0, int((forecast_for - now).total_seconds() // 60))
        record.max_temperature = values['max_temperature']
        record.min_temperature = values['min_temperature']
        record.apparent_temperature = values['apparent_temperature']
        record.humidity = values['humidity']
        record.pressure = values['pressure']
        record.rainfall = values['rainfall']
        record.confidence = 58
        record.model_status = 'local_geo_daily_fallback'
        record.raw_payload = json.dumps({
            'provider': 'local_geo_fallback',
            'reason': reason,
            'location': {'latitude': latitude, 'longitude': longitude}
        })
        record.agent_summary = f'Local geo fallback for {forecast_for.date()}: max {record.max_temperature} C, min {record.min_temperature} C, rainfall {record.rainfall} mm.'
        record.created_at = now
        if not existing:
            db.session.add(record)
        saved.append(record)

    db.session.commit()
    mirror_weather_records_async(current_app._get_current_object(), [record.id for record in saved])
    return {
        'status': 'fallback',
        'reason': reason,
        'location': {'latitude': latitude, 'longitude': longitude},
        'records': [record.to_dict() for record in saved]
    }


def create_geo_weather_records(user, device, force=False):
    """Fetch Open-Meteo current/daily weather for the farm location and save DB rows."""
    if not user or not device:
        return {'status': 'missing_user_or_device', 'records': []}

    project = latest_project_for_user(user)
    location = weather_location(user, device, project)
    if not location:
        return {'status': 'missing_location', 'records': []}

    latest_geo = WeatherRecord.query.filter(
        WeatherRecord.user_id == user.id,
        WeatherRecord.device_id == device.device_id,
        WeatherRecord.source.in_(['geo_realtime', 'geo_daily']),
        WeatherRecord.created_at >= datetime.utcnow() - timedelta(hours=6)
    ).order_by(WeatherRecord.created_at.desc()).limit(8).all()
    if latest_geo and not force:
        return {
            'status': 'cached',
            'location': {'latitude': location[0], 'longitude': location[1]},
            'records': [record.to_dict() for record in latest_geo]
        }

    if requests is None:
        return create_geo_fallback_weather_records(user, device, project, location, reason='requests_unavailable')

    latitude, longitude = location
    params = {
        'latitude': latitude,
        'longitude': longitude,
        'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,pressure_msl',
        'daily': 'temperature_2m_max,temperature_2m_min,apparent_temperature_max,precipitation_sum,precipitation_probability_max,weather_code',
        'timezone': 'auto',
        'forecast_days': 7
    }

    try:
        response = requests.get(
            'https://api.open-meteo.com/v1/forecast',
            params=params,
            timeout=float(os.environ.get('GEO_WEATHER_TIMEOUT_SECONDS', '8')),
            headers={'User-Agent': 'NuroAgro/1.0 weather-sync'}
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        current_app.logger.warning("Open-Meteo geo weather failed; using local fallback: %s", exc)
        return create_geo_fallback_weather_records(user, device, project, location, reason=str(exc)[:180])
    saved = []
    now = datetime.utcnow()

    current = payload.get('current') or {}
    current_temp = number_or_none(current.get('temperature_2m'))
    current_rain = first_present(current, 'rain', 'precipitation')
    current_record = WeatherRecord(
        user_id=user.id,
        device_id=device.device_id,
        project_id=project.id if project else None,
        source='geo_realtime',
        horizon_minutes=0,
        max_temperature=current_temp,
        min_temperature=current_temp,
        apparent_temperature=number_or_none(current.get('apparent_temperature')),
        humidity=number_or_none(current.get('relative_humidity_2m')),
        pressure=number_or_none(current.get('pressure_msl')),
        rainfall=number_or_none(current_rain),
        confidence=96,
        model_status='open_meteo_current',
        raw_payload=json.dumps({
            'provider': 'open_meteo',
            'location': {'latitude': latitude, 'longitude': longitude},
            'current': current
        }),
        agent_summary='Geolocation current weather saved from Open-Meteo.',
        forecast_for=parse_forecast_date(current.get('time')) if current.get('time') else now,
        created_at=now
    )
    db.session.add(current_record)
    saved.append(current_record)

    daily = payload.get('daily') or {}
    days = daily.get('time') or []
    for index, day in enumerate(days[:7]):
        forecast_for = parse_forecast_date(day)
        day_start = forecast_for.replace(hour=0, minute=0, second=0, microsecond=0)
        existing = WeatherRecord.query.filter(
            WeatherRecord.user_id == user.id,
            WeatherRecord.device_id == device.device_id,
            WeatherRecord.source == 'geo_daily',
            WeatherRecord.forecast_for >= day_start,
            WeatherRecord.forecast_for < day_start + timedelta(days=1)
        ).first()

        record = existing or WeatherRecord(
            user_id=user.id,
            device_id=device.device_id,
            project_id=project.id if project else None,
            source='geo_daily',
            forecast_for=forecast_for
        )
        record.horizon_minutes = max(0, int((forecast_for - now).total_seconds() // 60))
        record.max_temperature = daily_value(daily, 'temperature_2m_max', index)
        record.min_temperature = daily_value(daily, 'temperature_2m_min', index)
        record.apparent_temperature = daily_value(daily, 'apparent_temperature_max', index)
        record.humidity = None
        record.pressure = None
        record.rainfall = daily_value(daily, 'precipitation_sum', index)
        record.confidence = 94
        record.model_status = 'open_meteo_daily_forecast'
        record.raw_payload = json.dumps({
            'provider': 'open_meteo',
            'location': {'latitude': latitude, 'longitude': longitude},
            'date': day,
            'precipitation_probability_max': daily_value(daily, 'precipitation_probability_max', index),
            'weather_code': daily_value(daily, 'weather_code', index)
        })
        record.agent_summary = f'Geo daily weather for {day}: max {record.max_temperature} C, min {record.min_temperature} C, rainfall {record.rainfall} mm.'
        record.created_at = now
        if not existing:
            db.session.add(record)
        saved.append(record)

    db.session.commit()
    mirror_weather_records_async(current_app._get_current_object(), [record.id for record in saved])

    return {
        'status': 'success',
        'location': {'latitude': latitude, 'longitude': longitude},
        'records': [record.to_dict() for record in saved]
    }


def record_realtime_weather_from_sensor(user, device_id, reading, raw_data=None):
    """Store realtime weather-like values from ESP32 and optional payload fields."""
    raw_data = raw_data or {}
    project = latest_project_for_user(user)
    temp = reading.temperature
    humidity = reading.humidity
    rainfall = first_present(raw_data, 'rainfall', 'rain_mm', 'weather_rainfall')
    pressure = first_present(raw_data, 'pressure', 'weather_pressure')

    record = WeatherRecord(
        user_id=user.id,
        device_id=device_id,
        project_id=project.id if project else None,
        source='realtime',
        horizon_minutes=0,
        max_temperature=number_or_none(first_present(raw_data, 'max_temperature', 'weather_max_temperature', default=temp)),
        min_temperature=number_or_none(first_present(raw_data, 'min_temperature', 'weather_min_temperature', default=temp)),
        apparent_temperature=number_or_none(first_present(raw_data, 'apparent_temperature', 'weather_apparent_temperature', default=temp)),
        humidity=number_or_none(first_present(raw_data, 'weather_humidity', default=humidity)),
        pressure=number_or_none(pressure),
        rainfall=number_or_none(rainfall) if rainfall is not None else (reading.rain_level * 0.42 if reading.rain_level is not None else None),
        confidence=100,
        model_status='realtime_sensor_payload',
        raw_payload=json.dumps(raw_data),
        forecast_for=datetime.utcnow(),
        created_at=datetime.utcnow()
    )
    db.session.add(record)
    db.session.commit()
    mirror_weather_records_async(current_app._get_current_object(), [record.id])
    return record


def maybe_create_weather_prediction_notification(user, device_id, force=False):
    device = Device.query.filter_by(device_id=device_id, user_id=user.id).first()
    if not device:
        return None

    latest = WeatherRecord.query.filter_by(user_id=user.id, device_id=device_id, source='predicted')\
        .order_by(WeatherRecord.created_at.desc()).first()
    if latest and not force and datetime.utcnow() - latest.created_at < timedelta(minutes=30):
        return latest

    return create_weather_prediction_record(user, device, force=True, notify=True)


def create_weather_prediction_record(user, device, force=False, notify=False):
    if not user or not device:
        return None

    project = latest_project_for_user(user)
    readings = SensorReading.query.filter_by(user_id=user.id, device_id=device.device_id)\
        .order_by(SensorReading.timestamp.desc()).limit(96).all()
    payload = predict_weather(readings, project=project, horizon_minutes=30)

    history = WeatherRecord.query.filter(
        WeatherRecord.user_id == user.id,
        WeatherRecord.created_at >= datetime.utcnow() - timedelta(days=92)
    ).order_by(WeatherRecord.created_at.desc()).limit(500).all()
    three_month_summary = summarize_weather(history)
    agent = chatgpt_crop_advice(payload, three_month_summary, project=project, plant_type=user.plant_type)

    try:
        forecast_for = datetime.fromisoformat(str(payload.get('forecast_for')).replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        forecast_for = datetime.utcnow() + timedelta(minutes=30)

    record = WeatherRecord(
        user_id=user.id,
        device_id=device.device_id,
        project_id=project.id if project else None,
        source='predicted',
        horizon_minutes=30,
        max_temperature=payload.get('max_temperature'),
        min_temperature=payload.get('min_temperature'),
        apparent_temperature=payload.get('apparent_temperature'),
        humidity=payload.get('humidity'),
        pressure=payload.get('pressure'),
        rainfall=payload.get('rainfall'),
        confidence=payload.get('confidence'),
        model_status=payload.get('model_status'),
        raw_payload=json.dumps(payload),
        agent_summary=agent.get('summary'),
        recommended_plants=json.dumps(agent.get('plants', [])),
        forecast_for=forecast_for,
        created_at=datetime.utcnow()
    )
    db.session.add(record)
    db.session.commit()
    mirror_weather_records_async(current_app._get_current_object(), [record.id])

    maybe_save_weather_crop_recommendation(user, record, agent, three_month_summary)

    if notify:
        create_notification(user, format_weather_notification(record, agent), 'weather_prediction')

    return record


def maybe_save_weather_crop_recommendation(user, record, agent, three_month_summary):
    latest = Recommendation.query.filter_by(
        user_id=user.id,
        recommendation_type='weather_crop_plan',
        is_active=True
    ).order_by(Recommendation.time_of_analysis.desc()).first()

    if latest and datetime.utcnow() - latest.time_of_analysis < timedelta(hours=12):
        return latest

    rec = Recommendation(
        user_id=user.id,
        recommendation_type='weather_crop_plan',
        suitable_plants=json.dumps(agent.get('plants', [])),
        plant_score=record.confidence,
        reason=agent.get('summary'),
        based_on_factors=json.dumps({
            'latest_prediction': record.to_dict(),
            'three_month_summary': three_month_summary,
            'agent_source': agent.get('source')
        }),
        recommended_month=datetime.utcnow().month,
        time_of_analysis=datetime.utcnow(),
        is_active=True
    )
    db.session.add(rec)
    db.session.commit()
    mirror_recommendation(rec)
    return rec


def format_weather_notification(record, agent):
    return (
        f"Max Temperature: {record.max_temperature} C\n"
        f"Min Temperature: {record.min_temperature} C\n"
        f"Apparent Temperature: {record.apparent_temperature} C\n"
        f"Humidity: {record.humidity} %\n"
        f"Pressure: {record.pressure} hPa\n"
        f"Rainfall: {record.rainfall} mm\n\n"
        f"{agent.get('summary') or 'Weather prediction saved.'}"
    )


def priority_score(priority):
    return {'high': 90, 'medium': 70, 'low': 45}.get(priority, 50)


def build_project_advice(project):
    area = project.land_area or 0
    stories = project.vertical_stories or 1
    water_system = project.water_system or 'hybrid'
    compact_area = area and area < 200
    vertical_score = min(94, 58 + stories * 8 + (12 if compact_area else 4))
    conventional_score = max(42, 82 - stories * 7 + (10 if area > 1000 else 0))
    plants = (
        ['Lettuce', 'Basil', 'Spinach', 'Tomato', 'Strawberry']
        if compact_area
        else ['Tomato', 'Cucumber', 'Spinach', 'Basil', 'Strawberry']
    )
    fish = (
        ['Tilapia fry', 'Guppy', 'Molly', 'Zebra danio', 'Goldfish juveniles']
        if water_system in {'aquaponic', 'hybrid'}
        else ['Optional for aquaponic expansion']
    )

    return {
        'primary': (
            f"Recommended: vertical {water_system} farming"
            if vertical_score >= conventional_score
            else 'Recommended: conventional farming with smart automation'
        ),
        'vertical_score': vertical_score,
        'conventional_score': conventional_score,
        'plants': plants,
        'fish': fish,
        'reason': (
            f"Vertical score {vertical_score}/100 and conventional score "
            f"{conventional_score}/100 based on area, stories, location, and water system."
        )
    }


def create_notification(user, message, notification_type='info', mirror_remote=True):
    """Create notification for user"""
    try:
        notification = Notification(
            user_id=user.id,
            notification_type=notification_type,
            title=notification_type.replace('_', ' ').title(),
            message=message,
            triggered_by=notification_type
        )
        db.session.add(notification)
        db.session.commit()
        if mirror_remote:
            mirror_notification(notification)
        return notification
    except Exception as e:
        current_app.logger.error(f"Error creating notification: {str(e)}")
        return None


def mirror_sensor_reading(reading):
    payload = model_payload(reading, [
        'user_id', 'device_id', 'temperature', 'humidity', 'soil_moisture',
        'mq2_reading', 'mq5_reading', 'mq7_reading', 'mq135_reading',
        'sound_level', 'light_intensity', 'rain_level', 'water_level',
        'motion_detected', 'pump_status', 'light_status', 'timestamp'
    ])
    payload['local_id'] = reading.id
    insert_record('sensor_readings', payload, current_app.logger)


def mirror_user(user):
    payload = model_payload(user, [
        'username', 'email', 'farm_name', 'farm_location_lat', 'farm_location_lon',
        'farm_size', 'farm_area_suitability', 'geolocation_analyzed', 'plant_type',
        'approval_status', 'planting_date', 'created_at', 'updated_at'
    ])
    payload['local_id'] = user.id
    insert_record('users', payload, current_app.logger)


def mirror_device(device):
    payload = model_payload(device, [
        'device_id', 'user_id', 'device_name', 'device_type', 'is_active',
        'last_heartbeat', 'firmware_version', 'device_location_lat',
        'device_location_lon', 'created_at', 'updated_at'
    ])
    payload['local_id'] = device.id
    insert_record('devices', payload, current_app.logger)


def mirror_device_status(status):
    payload = model_payload(status, [
        'user_id', 'device_id', 'pump_on', 'pump_b_on', 'light_on', 'uv_light_level',
        'last_watering', 'next_scheduled_watering', 'auto_watering_enabled',
        'moisture_threshold', 'last_command', 'last_command_time', 'updated_at'
    ])
    payload['local_id'] = status.id
    insert_record('device_statuses', payload, current_app.logger)


def mirror_recommendation(rec):
    payload = model_payload(rec, [
        'user_id', 'recommendation_type', 'plant_score', 'expected_yield',
        'cost_estimate', 'growing_period', 'reason', 'recommended_month',
        'time_of_analysis', 'is_active', 'user_accepted'
    ])
    payload['local_id'] = rec.id
    payload['suitable_plants'] = json.loads(rec.suitable_plants) if rec.suitable_plants else None
    payload['based_on_factors'] = json.loads(rec.based_on_factors) if rec.based_on_factors else None
    insert_record('recommendations', payload, current_app.logger)


def mirror_notification(notification):
    payload = model_payload(notification, [
        'user_id', 'notification_type', 'title', 'message', 'triggered_by',
        'related_id', 'is_read', 'is_dismissed', 'created_at', 'read_at'
    ])
    payload['local_id'] = notification.id
    insert_record('notifications', payload, current_app.logger)


def mirror_disease_detection(detection):
    payload = model_payload(detection, [
        'user_id', 'device_id', 'image_path', 'image_url', 'is_from_camera',
        'primary_disease', 'disease_confidence', 'severity_level', 'timestamp'
    ])
    payload['local_id'] = detection.id
    payload['detections'] = json.loads(detection.detections) if detection.detections else None
    payload['recommendations'] = json.loads(detection.recommendations) if detection.recommendations else None
    insert_record('disease_detections', payload, current_app.logger)


def mirror_project(project):
    payload = model_payload(project, [
        'user_id', 'project_name', 'farming_mode', 'water_system', 'land_area',
        'vertical_stories', 'latitude', 'longitude', 'created_at', 'updated_at'
    ])
    payload['local_id'] = project.id
    payload['weather_snapshot'] = json.loads(project.weather_snapshot) if project.weather_snapshot else None
    payload['ai_suitability'] = json.loads(project.ai_suitability) if project.ai_suitability else None
    payload['recommended_plants'] = json.loads(project.recommended_plants) if project.recommended_plants else None
    payload['recommended_fish'] = json.loads(project.recommended_fish) if project.recommended_fish else None
    insert_record('projects', payload, current_app.logger)




def mirror_chat_message(message):
    payload = model_payload(message, [
        'user_id', 'sender_role', 'message', 'is_read', 'created_at'
    ])
    payload['local_id'] = message.id
    insert_record('chat_messages', payload, current_app.logger)


def mirror_forum_post(post):
    payload = model_payload(post, [
        'user_id', 'title', 'category', 'content', 'plant_type',
        'is_resolved', 'created_at', 'updated_at'
    ])
    payload['local_id'] = post.id
    insert_record('forum_posts', payload, current_app.logger)


def mirror_forum_reply(reply):
    payload = model_payload(reply, [
        'post_id', 'user_id', 'content', 'created_at'
    ])
    payload['local_id'] = reply.id
    insert_record('forum_replies', payload, current_app.logger)

def mirror_weather_record(record):
    payload = model_payload(record, [
        'user_id', 'device_id', 'project_id', 'source', 'horizon_minutes',
        'max_temperature', 'min_temperature', 'apparent_temperature',
        'humidity', 'pressure', 'rainfall', 'confidence', 'model_status',
        'agent_summary', 'forecast_for', 'created_at'
    ])
    payload['local_id'] = record.id
    payload['raw_payload'] = json.loads(record.raw_payload) if record.raw_payload else None
    payload['recommended_plants'] = json.loads(record.recommended_plants) if record.recommended_plants else None
    insert_record('weather_records', payload, current_app.logger)


def mirror_weather_training_run(run):
    payload = model_payload(run, [
        'user_id', 'device_id', 'samples_count', 'accuracy_score',
        'mean_absolute_error', 'status', 'model_version',
        'started_at', 'completed_at'
    ])
    payload['local_id'] = run.id
    payload['details'] = json.loads(run.details) if run.details else None
    insert_record('weather_training_runs', payload, current_app.logger)








