"""
    Database Models for NuroAgro
    Using SQLAlchemy ORM with SQLite/PostgreSQL
"""

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

# ==================== USER MODEL ====================

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    # Profile Information
    full_name = db.Column(db.String(120))
    phone = db.Column(db.String(40))
    profile_notes = db.Column(db.Text)
    
    # Farm Information
    farm_name = db.Column(db.String(120))
    farm_location_lat = db.Column(db.Float)
    farm_location_lon = db.Column(db.Float)
    farm_size = db.Column(db.Float)  # in mÂ²
    farm_area_suitability = db.Column(db.Float, default=0)  # 0-100 score
    geolocation_analyzed = db.Column(db.Boolean, default=False)
    
    # Plant Information
    plant_type = db.Column(db.String(120))  # e.g., "Tomato", "Lettuce"
    planting_date = db.Column(db.DateTime)
    
    # Account Management
    approval_status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    devices = db.relationship('Device', backref='user', lazy=True, cascade='all, delete-orphan')
    sensor_readings = db.relationship('SensorReading', backref='user', lazy=True, cascade='all, delete-orphan')
    device_statuses = db.relationship('DeviceStatus', backref='user', lazy=True, cascade='all, delete-orphan')
    disease_detections = db.relationship('DiseaseDetection', backref='user', lazy=True, cascade='all, delete-orphan')
    recommendations = db.relationship('Recommendation', backref='user', lazy=True, cascade='all, delete-orphan')
    projects = db.relationship('Project', backref='user', lazy=True, cascade='all, delete-orphan')
    system_logs = db.relationship('SystemLog', backref='user', lazy=True, cascade='all, delete-orphan')
    weather_records = db.relationship('WeatherRecord', backref='user', lazy=True, cascade='all, delete-orphan')
    weather_training_runs = db.relationship('WeatherTrainingRun', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')
    forum_posts = db.relationship('ForumPost', backref='author', lazy=True, cascade='all, delete-orphan')
    forum_replies = db.relationship('ForumReply', backref='author', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and set user password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'phone': self.phone,
            'profile_notes': self.profile_notes,
            'farm_name': self.farm_name,
            'farm_location': {
                'latitude': self.farm_location_lat,
                'longitude': self.farm_location_lon
            },
            'farm_size': self.farm_size,
            'farm_size_unit': 'sq_ft',
            'farm_area_suitability': self.farm_area_suitability,
            'plant_type': self.plant_type,
            'approval_status': self.approval_status or 'pending',
            'created_at': self.created_at.isoformat()
        }


# ==================== PROJECT MODEL ====================

class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_name = db.Column(db.String(160), nullable=False)
    farming_mode = db.Column(db.String(60))
    water_system = db.Column(db.String(60))
    land_area = db.Column(db.Float)
    vertical_stories = db.Column(db.Integer, default=1)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    weather_snapshot = db.Column(db.Text)
    ai_suitability = db.Column(db.Text)
    recommended_plants = db.Column(db.Text)
    recommended_fish = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        def parse_json(value, fallback):
            try:
                return json.loads(value) if value else fallback
            except Exception:
                return fallback

        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.project_name,
            'project_name': self.project_name,
            'climate': self.farming_mode,
            'farming_mode': self.farming_mode,
            'waterSystem': self.water_system,
            'water_system': self.water_system,
            'area': self.land_area,
            'land_area': self.land_area,
            'area_unit': 'sq_ft',
            'stories': self.vertical_stories,
            'vertical_stories': self.vertical_stories,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'weather_snapshot': parse_json(self.weather_snapshot, {}),
            'ai_suitability': parse_json(self.ai_suitability, {}),
            'recommended_plants': parse_json(self.recommended_plants, []),
            'recommended_fish': parse_json(self.recommended_fish, []),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ==================== DEVICE MODEL ====================

class Device(db.Model):
    __tablename__ = 'devices'
    
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False)  # e.g., ESP32_001
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_name = db.Column(db.String(120))
    device_type = db.Column(db.String(50))  # e.g., "ESP32-WROOM"
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    last_heartbeat = db.Column(db.DateTime)
    firmware_version = db.Column(db.String(20))
    
    # Location of device
    device_location_lat = db.Column(db.Float)
    device_location_lon = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'device_name': self.device_name,
            'device_type': self.device_type,
            'is_active': self.is_active,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None
        }


# ==================== SENSOR READING MODEL ====================

class SensorReading(db.Model):
    __tablename__ = 'sensor_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_id = db.Column(db.String(50), nullable=False)
    
    # Environmental Data
    temperature = db.Column(db.Float)  # Â°C
    humidity = db.Column(db.Float)     # %
    soil_moisture = db.Column(db.Float)  # %
    
    # Gas Sensors
    mq2_reading = db.Column(db.Float)    # LPG/Smoke
    mq5_reading = db.Column(db.Float)    # LPG/Natural Gas
    mq7_reading = db.Column(db.Float)    # Carbon Monoxide
    mq135_reading = db.Column(db.Float)  # Air Quality
    
    # Other Sensors
    sound_level = db.Column(db.Float)      # dB
    light_intensity = db.Column(db.Float)  # Lux
    rain_level = db.Column(db.Float)       # rain sensor level
    water_level = db.Column(db.Float)      # reservoir/tank level %
    motion_detected = db.Column(db.Boolean, default=False)
    
    # Status
    pump_status = db.Column(db.Boolean)
    light_status = db.Column(db.Boolean)
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'temperature': self.temperature,
            'humidity': self.humidity,
            'soil_moisture': self.soil_moisture,
            'mq2': self.mq2_reading,
            'mq5': self.mq5_reading,
            'mq7': self.mq7_reading,
            'mq135': self.mq135_reading,
            'sound_level': self.sound_level,
            'light_intensity': self.light_intensity,
            'rain_level': self.rain_level,
            'water_level': self.water_level,
            'motion_detected': self.motion_detected,
            'pump_status': self.pump_status,
            'light_status': self.light_status,
            'timestamp': self.timestamp.isoformat()
        }


# ==================== DEVICE STATUS MODEL ====================

class DeviceStatus(db.Model):
    __tablename__ = 'device_statuses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_id = db.Column(db.String(50), nullable=False)
    
    # Control States
    pump_on = db.Column(db.Boolean, default=False)
    pump_b_on = db.Column(db.Boolean, default=False)
    light_on = db.Column(db.Boolean, default=False)
    uv_light_level = db.Column(db.Float, default=65)
    
    # Watering Schedule
    last_watering = db.Column(db.DateTime)
    next_scheduled_watering = db.Column(db.DateTime)
    auto_watering_enabled = db.Column(db.Boolean, default=True)
    moisture_threshold = db.Column(db.Float, default=30)  # % - turn on pump below this
    
    # Last Command
    last_command = db.Column(db.String(50))
    last_command_time = db.Column(db.DateTime)
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'device_id': self.device_id,
            'pump_on': self.pump_on,
            'pump_b_on': self.pump_b_on,
            'light_on': self.light_on,
            'uv_light_level': self.uv_light_level,
            'last_watering': self.last_watering.isoformat() if self.last_watering else None,
            'next_scheduled_watering': self.next_scheduled_watering.isoformat() if self.next_scheduled_watering else None,
            'auto_watering_enabled': self.auto_watering_enabled,
            'moisture_threshold': self.moisture_threshold
        }


# ==================== DISEASE DETECTION MODEL ====================

class DiseaseDetection(db.Model):
    __tablename__ = 'disease_detections'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_id = db.Column(db.String(50))  # Optional - from camera feed
    
    # Image Info
    image_path = db.Column(db.String(200))
    image_url = db.Column(db.String(300))
    is_from_camera = db.Column(db.Boolean, default=False)  # True if from IoT camera, False if uploaded
    
    # Detection Results (JSON)
    detections = db.Column(db.Text)  # JSON string with all detected diseases
    primary_disease = db.Column(db.String(120))
    disease_confidence = db.Column(db.Float)  # 0-100%
    
    # Recommendations (JSON)
    recommendations = db.Column(db.Text)  # JSON string with treatment suggestions
    severity_level = db.Column(db.String(20))  # "Low", "Medium", "High", "Critical"
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        try:
            detections_data = json.loads(self.detections) if self.detections else {}
            recommendations_data = json.loads(self.recommendations) if self.recommendations else {}
        except:
            detections_data = {}
            recommendations_data = {}
        
        return {
            'id': self.id,
            'image_url': self.image_url,
            'primary_disease': self.primary_disease,
            'disease_confidence': self.disease_confidence,
            'detections': detections_data,
            'recommendations': recommendations_data,
            'severity_level': self.severity_level,
            'timestamp': self.timestamp.isoformat()
        }


# ==================== RECOMMENDATION MODEL ====================

class Recommendation(db.Model):
    __tablename__ = 'recommendations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Recommendation Type
    recommendation_type = db.Column(db.String(50))  # "plant_suggestion", "watering", "treatment"
    
    # Geolocation-based recommendations
    suitable_plants = db.Column(db.Text)  # JSON array of plant names
    plant_score = db.Column(db.Float)  # Suitability score for each plant
    
    # Cost & Yield
    expected_yield = db.Column(db.Float)  # kg or units
    cost_estimate = db.Column(db.Float)  # in currency
    growing_period = db.Column(db.Integer)  # days
    
    # Reason for recommendation
    reason = db.Column(db.Text)  # Explanation of why this plant is recommended
    based_on_factors = db.Column(db.Text)  # JSON with factors: temperature, humidity, etc.
    
    # Seasonal info
    recommended_month = db.Column(db.Integer)  # 1-12
    time_of_analysis = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    user_accepted = db.Column(db.Boolean, default=None)  # None = not reviewed, True/False = user choice
    
    def to_dict(self):
        try:
            suitable_plants_data = json.loads(self.suitable_plants) if self.suitable_plants else []
            based_on_factors_data = json.loads(self.based_on_factors) if self.based_on_factors else {}
        except:
            suitable_plants_data = []
            based_on_factors_data = {}
        
        return {
            'id': self.id,
            'recommendation_type': self.recommendation_type,
            'suitable_plants': suitable_plants_data,
            'expected_yield': self.expected_yield,
            'cost_estimate': self.cost_estimate,
            'growing_period': self.growing_period,
            'reason': self.reason,
            'based_on_factors': based_on_factors_data,
            'recommended_month': self.recommended_month,
            'time_of_analysis': self.time_of_analysis.isoformat(),
            'user_accepted': self.user_accepted
        }


# ==================== WEATHER MODELS ====================

class WeatherRecord(db.Model):
    __tablename__ = 'weather_records'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_id = db.Column(db.String(50))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))

    source = db.Column(db.String(30), default='predicted')  # realtime, predicted
    horizon_minutes = db.Column(db.Integer, default=30)
    max_temperature = db.Column(db.Float)
    min_temperature = db.Column(db.Float)
    apparent_temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    pressure = db.Column(db.Float)
    rainfall = db.Column(db.Float)
    confidence = db.Column(db.Float)
    model_status = db.Column(db.String(120))
    raw_payload = db.Column(db.Text)
    agent_summary = db.Column(db.Text)
    recommended_plants = db.Column(db.Text)
    forecast_for = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        def parse_json(value, fallback):
            try:
                return json.loads(value) if value else fallback
            except Exception:
                return fallback

        return {
            'id': self.id,
            'user_id': self.user_id,
            'device_id': self.device_id,
            'project_id': self.project_id,
            'source': self.source,
            'horizon_minutes': self.horizon_minutes,
            'max_temperature': self.max_temperature,
            'min_temperature': self.min_temperature,
            'apparent_temperature': self.apparent_temperature,
            'humidity': self.humidity,
            'pressure': self.pressure,
            'rainfall': self.rainfall,
            'confidence': self.confidence,
            'model_status': self.model_status,
            'raw_payload': parse_json(self.raw_payload, {}),
            'agent_summary': self.agent_summary,
            'recommended_plants': parse_json(self.recommended_plants, []),
            'forecast_for': self.forecast_for.isoformat() if self.forecast_for else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class WeatherTrainingRun(db.Model):
    __tablename__ = 'weather_training_runs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    device_id = db.Column(db.String(50))
    samples_count = db.Column(db.Integer, default=0)
    accuracy_score = db.Column(db.Float)
    mean_absolute_error = db.Column(db.Float)
    status = db.Column(db.String(40), default='queued')
    model_version = db.Column(db.String(80))
    details = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        try:
            details_data = json.loads(self.details) if self.details else {}
        except Exception:
            details_data = {}

        return {
            'id': self.id,
            'user_id': self.user_id,
            'device_id': self.device_id,
            'samples_count': self.samples_count,
            'accuracy_score': self.accuracy_score,
            'mean_absolute_error': self.mean_absolute_error,
            'status': self.status,
            'model_version': self.model_version,
            'details': details_data,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }



# ==================== COMMUNICATION MODELS ====================

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sender_role = db.Column(db.String(20), default='user')  # user, admin
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'sender_role': self.sender_role,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ForumPost(db.Model):
    __tablename__ = 'forum_posts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(80), default='general')
    content = db.Column(db.Text, nullable=False)
    plant_type = db.Column(db.String(120))
    is_resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    replies = db.relationship('ForumReply', backref='post', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_replies=True):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.author.username if self.author else None,
            'title': self.title,
            'category': self.category,
            'content': self.content,
            'plant_type': self.plant_type,
            'is_resolved': self.is_resolved,
            'reply_count': len(self.replies or []),
            'replies': [reply.to_dict() for reply in self.replies] if include_replies else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ForumReply(db.Model):
    __tablename__ = 'forum_replies'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('forum_posts.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'user_id': self.user_id,
            'username': self.author.username if self.author else None,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# ==================== NOTIFICATION MODEL ====================

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Notification Details
    notification_type = db.Column(db.String(50))  # "alert", "suggestion", "warning"
    title = db.Column(db.String(200))
    message = db.Column(db.Text)
    
    # Trigger Info
    triggered_by = db.Column(db.String(50))  # "low_moisture", "disease_detected", etc.
    related_id = db.Column(db.Integer)  # ID of related detection/recommendation
    
    # Status
    is_read = db.Column(db.Boolean, default=False)
    is_dismissed = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'notification_type': self.notification_type,
            'title': self.title,
            'message': self.message,
            'triggered_by': self.triggered_by,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat()
        }


# ==================== SYSTEM LOG MODEL ====================

class SystemLog(db.Model):
    __tablename__ = 'system_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Log Details
    action = db.Column(db.String(100))
    log_type = db.Column(db.String(50))  # "info", "warning", "error"
    details = db.Column(db.Text)
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'action': self.action,
            'log_type': self.log_type,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }


# ==================== DATABASE INITIALIZATION ====================

def init_db(app):
    """Initialize database with app context"""
    with app.app_context():
        db.create_all()
        print("Database initialized successfully!")


def create_sample_data():
    """Create sample data for testing (optional)"""
    # Create a test user
    test_user = User(
        username='testuser',
        email='test@example.com',
        farm_name='Test Farm',
        farm_location_lat=40.7128,
        farm_location_lon=-74.0060,
        farm_size=100.0,
        plant_type='Tomato'
    )
    test_user.set_password('password123')
    db.session.add(test_user)
    db.session.commit()
    print("Sample user created!")






