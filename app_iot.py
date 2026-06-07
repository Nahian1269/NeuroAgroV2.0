"""
    NuroAgro Flask Web Application
    Main application file with all route integrations
"""

import os
IS_VERCEL = bool(os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV'))
if IS_VERCEL:
    os.environ.setdefault('YOLO_CONFIG_DIR', '/tmp/yolo_config')
    os.environ.setdefault('WEATHER_CALIBRATION_PATH', '/tmp/weather_calibration.json')
else:
    os.environ.setdefault('YOLO_CONFIG_DIR', os.path.join(os.getcwd(), 'static', 'yolo_config'))

from flask import Flask, request, url_for, send_from_directory, jsonify, session, redirect, flash
from flask_cors import CORS
from flask_session import Session
from werkzeug.utils import secure_filename
import logging
from threading import Thread
from time import sleep
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
from sqlalchemy import inspect, text

# Import database and models
from models import (
    db, User, Device, SensorReading, DeviceStatus, DiseaseDetection,
    Notification, Recommendation, SystemLog, WeatherRecord, WeatherTrainingRun, ChatMessage, ForumPost, ForumReply
)
from routes.api import api_bp
from routes.api import (
    analyze_location_for_farming,
    create_notification,
    create_user_device,
    mirror_device,
    mirror_device_status,
    mirror_disease_detection,
    mirror_recommendation,
    mirror_user,
)
from disease_ml import analyze_image_for_disease as run_disease_analysis
from disease_ml import load_model as load_disease_model

# ==================== FLASK APP CONFIGURATION ====================

load_dotenv()
app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or ('sqlite:////tmp/vertical_farming.db' if IS_VERCEL else 'sqlite:///vertical_farming.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nuroagro-dev-secret-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.environ.get('SESSION_FILE_DIR') or ('/tmp/flask_session' if IS_VERCEL else 'flask_session')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER') or ('/tmp/nuroagro_uploads' if IS_VERCEL else 'static/uploads/')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['DEVICE_API_KEY'] = os.environ.get('DEVICE_API_KEY', 'farm-device-key')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', app.config['SECRET_KEY'])
FRONTEND_DIST = os.path.join(app.root_path, 'frontend_jsx', 'dist')
FRONTEND_ASSETS = os.path.join(FRONTEND_DIST, 'assets')

# Allowed extensions for uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# ==================== INITIALIZATION ====================

# Initialize extensions
default_frontend_origins = [
    'http://127.0.0.1:5001',
    'http://localhost:5001',
    'http://127.0.0.1:5173',
    'http://localhost:5173',
    'http://127.0.0.1:5174',
    'http://localhost:5174',
    'http://127.0.0.1:5175',
    'http://localhost:5175',
    'http://127.0.0.1:5176',
    'http://localhost:5176',
    'http://127.0.0.1:3000',
    'http://localhost:3000',
]
configured_frontend_origins = os.environ.get(
    'FRONTEND_ORIGINS',
    ','.join(default_frontend_origins)
).split(',')
frontend_origins = sorted({
    origin.strip()
    for origin in [*default_frontend_origins, *configured_frontend_origins]
    if origin.strip()
})
CORS(app, supports_credentials=True, resources={
    r"/api/*": {"origins": frontend_origins},
    r"/disease-detection": {"origins": frontend_origins}
})
Session(app)
db.init_app(app)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create runtime directories. Vercel functions can only write to /tmp.
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'disease_images'), exist_ok=True)
os.makedirs(os.environ.get('YOLO_CONFIG_DIR', '/tmp/yolo_config' if IS_VERCEL else os.path.join(os.getcwd(), 'static', 'yolo_config')), exist_ok=True)

model = None
model_load_error = None
model_preload_started = False


def load_yolo_model():
    """Load YOLO only when disease detection is requested."""
    global model, model_load_error
    if model is not None or model_load_error is not None:
        return model
    try:
        model = load_disease_model("best.pt")
        logger.info("YOLO model loaded successfully")
        logger.info(f"Model class names: {model.names}")
    except Exception as exc:
        model_load_error = str(exc)
        logger.error(f"Failed to load YOLO model: {exc}")
        model = None
    return model


def warm_disease_model_async():
    """Load the disease model after startup so the first scan is not cold."""
    global model_preload_started
    if model_preload_started or os.environ.get('DISEASE_MODEL_PRELOAD', 'false').lower() in {'0', 'false', 'no', 'off'}:
        return
    model_preload_started = True

    def preload():
        try:
            sleep(float(os.environ.get('DISEASE_MODEL_PRELOAD_DELAY', '5')))
            load_yolo_model()
        except Exception as exc:
            logger.warning("Disease model preload skipped: %s", exc)

    Thread(target=preload, name='disease-model-preload', daemon=True).start()

# ==================== ROUTE REGISTRATION ====================

# Register API blueprint
app.register_blueprint(api_bp)


@app.context_processor
def inject_template_helpers():
    """Expose small helpers for any legacy Flask responses."""
    return {'now': datetime.utcnow}


def frontend_dist_available():
    return os.path.exists(os.path.join(FRONTEND_DIST, 'index.html'))


def is_react_browser_request():
    protected_prefixes = ('/api/', '/static/', '/assets/')
    return (
        frontend_dist_available()
        and request.method == 'GET'
        and not request.path.startswith(protected_prefixes)
    )


def serve_react_app():
    response = send_from_directory(FRONTEND_DIST, 'index.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def record_visitor_once():
    if session.get('visitor_logged'):
        return

    session['visitor_logged'] = True
    try:
        db.session.add(SystemLog(
            user_id=session.get('user_id'),
            action='web_visit',
            log_type='info',
            details=json.dumps({
                'path': request.path,
                'user_agent': request.headers.get('User-Agent'),
                'remote_addr': request.remote_addr
            })
        ))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.debug("Visitor log skipped: %s", exc)


@app.route('/api/health')
def health_check():
    """Small readiness endpoint for dev scripts and uptime checks."""
    return jsonify({
        'ok': True,
        'status': 'ready',
        'frontend_built': frontend_dist_available()
    })


@app.route('/assets/<path:filename>')
def frontend_assets(filename):
    """Serve Vite build assets when Flask hosts the full application."""
    if frontend_dist_available():
        return send_from_directory(FRONTEND_ASSETS, filename)
    return jsonify({'error': 'Frontend build not found. Run npm run build in frontend_jsx.'}), 404


@app.before_request
def serve_single_react_frontend():
    """React is the only browser frontend for normal page requests."""
    if is_react_browser_request():
        record_visitor_once()
        return serve_react_app()
    return None

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            password_confirm = request.form.get('password_confirm')
            
            # Validation
            if not all([username, email, password, password_confirm]):
                return jsonify({'error': 'All fields are required'}), 400
            
            if password != password_confirm:
                return jsonify({'error': 'Passwords do not match'}), 400
            
            # Check if user exists
            if User.query.filter_by(username=username).first():
                return jsonify({'error': 'Username already exists'}), 400
            
            if User.query.filter_by(email=email).first():
                return jsonify({'error': 'Email already exists'}), 400
            
            # Create user
            user = User(username=username, email=email)
            user.set_password(password)
            
            db.session.add(user)
            db.session.flush()
            device, status = create_user_device(user)
            db.session.commit()
            mirror_user(user)
            mirror_device(device)
            mirror_device_status(status)
            
            logger.info(f"New user registered: {username}")
            
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Error in registration: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    return serve_react_app()


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            
            if not username or not password:
                return jsonify({'error': 'Username and password required'}), 400
            
            user = User.query.filter_by(username=username).first()
            
            if not user or not user.check_password(password):
                return jsonify({'error': 'Invalid username or password'}), 401

            if (user.approval_status or 'pending') != 'accepted':
                return jsonify({'error': 'Account is waiting for admin acceptance'}), 403
            
            session['user_id'] = user.id
            session['username'] = user.username
            
            logger.info(f"User logged in: {username}")
            
            # Check if farm setup is complete
            if not user.geolocation_analyzed:
                return redirect(url_for('setup_farm'))
            
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            logger.error(f"Error in login: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    return serve_react_app()


@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    return redirect(url_for('index'))


# ==================== MAIN ROUTES ====================

@app.route('/')
def index():
    """Home page"""
    if frontend_dist_available():
        return serve_react_app()
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return serve_react_app()


@app.route('/setup', methods=['GET', 'POST'])
def setup_farm():
    """Farm setup wizard"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        try:
            farm_name = request.form.get('farm_name')
            farm_size = request.form.get('farm_size', type=float)
            latitude = request.form.get('latitude', type=float)
            longitude = request.form.get('longitude', type=float)
            plant_type = request.form.get('plant_type')
            
            # Update user
            user.farm_name = farm_name
            user.farm_size = farm_size
            user.farm_location_lat = latitude
            user.farm_location_lon = longitude
            user.plant_type = plant_type
            
            analysis_result = analyze_location_for_farming(latitude, longitude, farm_size)
            user.farm_area_suitability = analysis_result['suitability_score']
            user.geolocation_analyzed = True

            Recommendation.query.filter_by(
                user_id=user.id,
                recommendation_type='plant_suggestion',
                is_active=True
            ).update({'is_active': False})

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
                    based_on_factors=json.dumps(analysis_result['climate_factors']),
                    recommended_month=datetime.utcnow().month
                )
                db.session.add(rec)

            create_notification(
                user,
                f"Farm setup complete. Suitability score: {analysis_result['suitability_score']}%.",
                'geolocation_analysis'
            )
            
            db.session.commit()
            mirror_user(user)
            for rec in Recommendation.query.filter_by(
                user_id=user.id,
                recommendation_type='plant_suggestion',
                is_active=True
            ).all():
                mirror_recommendation(rec)
            
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            logger.error(f"Error in setup_farm: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    recommendations = Recommendation.query.filter_by(
        user_id=user.id,
        recommendation_type='plant_suggestion',
        is_active=True
    ).order_by(Recommendation.plant_score.desc()).all()

    return serve_react_app()


@app.route('/dashboard')
def dashboard():
    """Main dashboard"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    # Get latest sensor readings
    latest_readings = SensorReading.query.filter_by(user_id=user.id)\
        .order_by(SensorReading.timestamp.desc()).limit(100).all()
    
    # Get device statuses
    devices = Device.query.filter_by(user_id=user.id).all()
    device_statuses = {d.device_id: DeviceStatus.query.filter_by(device_id=d.device_id).first() for d in devices}
    
    # Get recent notifications
    notifications = Notification.query.filter_by(user_id=user.id)\
        .order_by(Notification.created_at.desc()).limit(10).all()
    
    # Get latest disease detections
    disease_detections = DiseaseDetection.query.filter_by(user_id=user.id)\
        .order_by(DiseaseDetection.timestamp.desc()).limit(5).all()
    
    # Prepare data for charts
    readings_data = {
        'timestamps': [r.timestamp.isoformat() for r in reversed(latest_readings)],
        'temperature': [r.temperature or 0 for r in reversed(latest_readings)],
        'humidity': [r.humidity or 0 for r in reversed(latest_readings)],
        'soil_moisture': [r.soil_moisture or 0 for r in reversed(latest_readings)],
        'light_intensity': [r.light_intensity or 0 for r in reversed(latest_readings)]
    }
    
    return serve_react_app()


@app.route('/control', methods=['GET', 'POST'])
def control_panel():
    """Device control panel"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    devices = Device.query.filter_by(user_id=user.id).all()
    
    if request.method == 'POST':
        try:
            device_id = request.form.get('device_id')
            command = request.form.get('command')
            
            device = Device.query.filter_by(device_id=device_id, user_id=user.id).first()
            if not device:
                return jsonify({'error': 'Device not found'}), 404
            
            status = DeviceStatus.query.filter_by(user_id=user.id, device_id=device_id).first()
            if not status:
                status = DeviceStatus(user_id=user.id, device_id=device_id)
                db.session.add(status)

            if command == 'pump_on':
                status.pump_on = True
                status.last_watering = datetime.utcnow()
            elif command == 'pump_off':
                status.pump_on = False
            elif command == 'light_on':
                status.light_on = True
            elif command == 'light_off':
                status.light_on = False
            elif command == 'auto_on':
                status.auto_watering_enabled = True
            elif command == 'auto_off':
                status.auto_watering_enabled = False
            else:
                return jsonify({'error': 'Unknown command'}), 400

            status.last_command = command
            status.last_command_time = datetime.utcnow()
            db.session.commit()

            create_notification(user, f"Command queued for {device.device_name}: {command}", 'device_control')
            flash('Command sent to ESP32. The device will apply it on the next poll.', 'success')
            
            return redirect(url_for('control_panel'))
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    device_statuses = {d.device_id: DeviceStatus.query.filter_by(device_id=d.device_id).first() for d in devices}
    
    return serve_react_app()


@app.route('/disease-detection', methods=['GET', 'POST'])
def disease_detection():
    """Disease detection page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    detections = DiseaseDetection.query.filter_by(user_id=user.id)\
        .order_by(DiseaseDetection.timestamp.desc()).all()
    
    if request.method == 'POST':
        try:
            if 'image' not in request.files:
                return jsonify({'error': 'No image provided'}), 400
            
            image_file = request.files['image']
            
            if image_file.filename == '':
                return jsonify({'error': 'No image selected'}), 400
            
            if not allowed_file(image_file.filename):
                return jsonify({'error': 'File type not allowed'}), 400
            
            # Save image
            filename = secure_filename(f"{datetime.utcnow().timestamp()}_{image_file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'disease_images', filename)
            image_file.save(filepath)
            
            # Run disease detection
            detection_data = analyze_image_for_disease(filepath)
            original_image_url = f"/static/uploads/disease_images/{filename}"
            diagnosis_image_url = detection_data.get('annotated_image_url') or original_image_url
            
            # Save detection record
            detection = DiseaseDetection(
                user_id=user.id,
                image_path=filepath,
                image_url=diagnosis_image_url,
                is_from_camera=False,
                primary_disease=detection_data.get('primary_disease'),
                disease_confidence=detection_data.get('confidence'),
                detections=json.dumps(detection_data.get('detections', {})),
                recommendations=json.dumps(detection_data.get('recommendations', [])),
                severity_level=detection_data.get('severity')
            )
            
            db.session.add(detection)
            db.session.commit()
            mirror_disease_detection(detection)
            
            return jsonify({
                'status': 'success',
                'detection_id': detection.id,
                'image_url': detection.image_url,
                'annotated_image_url': detection.image_url,
                'original_image_url': original_image_url,
                'primary_disease': detection.primary_disease,
                'confidence': detection.disease_confidence,
                'severity': detection.severity_level,
                'detections': detection_data.get('detections', {}),
                'boxes': detection_data.get('boxes', []),
                'recommendations': detection_data.get('recommendations', [])
            }), 201
            
        except Exception as e:
            logger.error(f"Error in disease_detection upload: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    return serve_react_app()


@app.route('/device/<device_id>', methods=['GET', 'POST'])
def manage_device(device_id):
    """Manage specific device"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    device = Device.query.filter_by(device_id=device_id, user_id=user.id).first()
    
    if not device:
        return jsonify({'error': 'Device not found'}), 404
    
    status = DeviceStatus.query.filter_by(device_id=device_id).first()
    readings = SensorReading.query.filter_by(device_id=device_id)\
        .order_by(SensorReading.timestamp.desc()).limit(1000).all()
    
    if request.method == 'POST':
        # Handle device updates
        pass
    
    return serve_react_app()


@app.route('/api/notifications')
def get_notifications():
    """Get user notifications (AJAX)"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc()).limit(20).all()
    
    return jsonify([n.to_dict() for n in notifications])


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """Farm profile and device registration page."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        device_id = request.form.get('device_id')
        device_name = request.form.get('device_name') or 'ESP32 Farm Controller'

        if not device_id:
            flash('Device ID is required.', 'error')
            return redirect(url_for('profile'))

        existing = Device.query.filter_by(device_id=device_id).first()
        if existing and existing.user_id != user.id:
            flash('That device ID is already registered to another user.', 'error')
            return redirect(url_for('profile'))

        if not existing:
            device = Device(
                device_id=device_id,
                user_id=user.id,
                device_name=device_name,
                device_type='ESP32-WROOM',
                is_active=True
            )
            db.session.add(device)
            db.session.add(DeviceStatus(user_id=user.id, device_id=device_id))
            db.session.commit()
            flash('Device registered successfully.', 'success')
        else:
            existing.device_name = device_name
            db.session.commit()
            flash('Device updated successfully.', 'success')

        return redirect(url_for('profile'))

    devices = Device.query.filter_by(user_id=user.id).all()
    recommendations = Recommendation.query.filter_by(user_id=user.id, is_active=True)\
        .order_by(Recommendation.plant_score.desc()).all()

    return serve_react_app()


@app.route('/recommendations')
def recommendations():
    """Manual AI-style farm recommendations from stored profile and latest sensors."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    latest = SensorReading.query.filter_by(user_id=user.id).order_by(SensorReading.timestamp.desc()).first()
    recs = Recommendation.query.filter_by(user_id=user.id, is_active=True)\
        .order_by(Recommendation.time_of_analysis.desc()).all()

    return serve_react_app()


@app.route('/api/mark-notification/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    """Mark notification as read"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    notification = Notification.query.get(notification_id)
    if not notification or notification.user_id != session['user_id']:
        return jsonify({'error': 'Notification not found'}), 404
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'status': 'success'})


# ==================== UTILITY FUNCTIONS ====================

def allowed_file(filename):
    """Check if file has allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_image_for_disease(image_path):
    """Analyze image for crop diseases using YOLO."""
    try:
        active_model = load_yolo_model()
        if not active_model:
            return {'error': f'Model not loaded: {model_load_error or "unknown error"}', 'primary_disease': None, 'confidence': 0}
        return run_disease_analysis(image_path, model=active_model, logger=logger)
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return {'error': str(e), 'primary_disease': None, 'confidence': 0, 'detections': {}, 'boxes': []}


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    if is_react_browser_request():
        return serve_react_app()
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500


# ==================== INITIALIZATION & MAIN ====================

def create_app():
    """Application factory"""
    with app.app_context():
        db.create_all()
        ensure_runtime_schema()
        ensure_demo_data()
        logger.info("Database initialized!")
    warm_disease_model_async()
    return app


def ensure_runtime_schema():
    """Add new local SQLite columns for existing development databases."""
    if not str(db.engine.url).startswith('sqlite'):
        return

    inspector = inspect(db.engine)
    columns = {
        table: {column['name'] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }

    migrations = {
        'users': {
            'approval_status': "ALTER TABLE users ADD COLUMN approval_status VARCHAR(20) DEFAULT 'accepted'",
            'full_name': 'ALTER TABLE users ADD COLUMN full_name VARCHAR(120)',
            'phone': 'ALTER TABLE users ADD COLUMN phone VARCHAR(40)',
            'profile_notes': 'ALTER TABLE users ADD COLUMN profile_notes TEXT'
        },
        'sensor_readings': {
            'rain_level': 'ALTER TABLE sensor_readings ADD COLUMN rain_level FLOAT',
            'water_level': 'ALTER TABLE sensor_readings ADD COLUMN water_level FLOAT',
            'motion_detected': 'ALTER TABLE sensor_readings ADD COLUMN motion_detected BOOLEAN DEFAULT 0'
        },
        'device_statuses': {
            'pump_b_on': 'ALTER TABLE device_statuses ADD COLUMN pump_b_on BOOLEAN DEFAULT 0',
            'uv_light_level': 'ALTER TABLE device_statuses ADD COLUMN uv_light_level FLOAT DEFAULT 65'
        }
    }

    with db.engine.begin() as connection:
        for table, table_migrations in migrations.items():
            existing = columns.get(table, set())
            for column, statement in table_migrations.items():
                if column not in existing:
                    connection.execute(text(statement))
        connection.execute(text("UPDATE users SET approval_status = 'accepted' WHERE approval_status IS NULL"))


def ensure_demo_data():
    """Create a demo farm and ESP32 device when the database is empty."""
    sample_user = User.query.filter_by(username='demo').first()
    if sample_user:
        if sample_user.approval_status != 'accepted':
            sample_user.approval_status = 'accepted'
            db.session.commit()
        if not Device.query.filter_by(device_id='ESP32_001').first():
            db.session.add(Device(
                device_id='ESP32_001',
                user_id=sample_user.id,
                device_name='Demo ESP32 Controller',
                device_type='ESP32-WROOM',
                is_active=True
            ))
            db.session.add(DeviceStatus(user_id=sample_user.id, device_id='ESP32_001'))
            db.session.commit()
        return

    sample_user = User(
        username='demo',
        email='demo@example.com',
        farm_name='Demo Farm',
        farm_location_lat=40.7128,
        farm_location_lon=-74.0060,
        farm_size=100.0,
        plant_type='Tomato',
        approval_status='accepted',
        geolocation_analyzed=True,
        farm_area_suitability=80
    )
    sample_user.set_password('demo123')
    db.session.add(sample_user)
    db.session.flush()

    sample_device = Device(
        device_id='ESP32_001',
        user_id=sample_user.id,
        device_name='Demo ESP32 Controller',
        device_type='ESP32-WROOM',
        is_active=True
    )
    db.session.add(sample_device)
    db.session.add(DeviceStatus(user_id=sample_user.id, device_id='ESP32_001'))
    db.session.commit()
    logger.info("Demo user and ESP32 device created.")


try:
    create_app()
except Exception as exc:
    logger.error("Database initialization skipped: %s", exc)

if __name__ == '__main__':
    # Run app
    app.run(debug=True, host='0.0.0.0', port=5001)



