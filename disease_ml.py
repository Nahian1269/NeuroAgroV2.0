"""Shared YOLO disease analysis and image annotation utilities."""

import os
from pathlib import Path
from threading import Lock

os.environ.setdefault('YOLO_CONFIG_DIR', os.environ.get('YOLO_CONFIG_DIR', os.path.join(os.getcwd(), 'static', 'yolo_config')))

try:
    import cv2
    CV2_IMPORT_ERROR = None
except Exception as exc:
    cv2 = None
    CV2_IMPORT_ERROR = str(exc)


CLASS_ALIASES = {
    'brown spot': 'Brown spot',
    'brownspot': 'Brown spot',
    'rice blast': 'Rice blast',
    'riceblast': 'Rice blast',
}

CLASS_STYLES = {
    'Blight': {'bgr': (58, 66, 204), 'hex': '#cc423a'},
    'Brown spot': {'bgr': (34, 132, 191), 'hex': '#bf8422'},
    'False Smut': {'bgr': (158, 80, 125), 'hex': '#7d509e'},
    'Healthy': {'bgr': (76, 150, 34), 'hex': '#22964c'},
    'Kernel Smut': {'bgr': (70, 54, 42), 'hex': '#2a3646'},
    'Leaf Smut': {'bgr': (156, 76, 141), 'hex': '#8d4c9c'},
    'Rice blast': {'bgr': (35, 111, 156), 'hex': '#9c6f23'},
    'Stem Rot': {'bgr': (96, 42, 176), 'hex': '#b02a60'},
    'Tungro': {'bgr': (173, 133, 26), 'hex': '#1a85ad'},
    'Background': {'bgr': (140, 140, 140), 'hex': '#8c8c8c'},
}

DEFAULT_STYLE = {'bgr': (80, 80, 80), 'hex': '#505050'}
HEALTHY_CLASSES = {'healthy', 'background'}
MAX_ANALYSIS_EDGE = int(os.environ.get('DISEASE_MAX_ANALYSIS_EDGE', '1280'))
_MODEL_CACHE = None
_MODEL_LOCK = Lock()


def load_model(model_path='best.pt'):
    """Load YOLO lazily for API routes that do not already have a model."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        with _MODEL_LOCK:
            if _MODEL_CACHE is None:
                from ultralytics import YOLO
                _MODEL_CACHE = YOLO(model_path)
    return _MODEL_CACHE


def canonical_class_name(class_name):
    if class_name is None:
        return None
    name = str(class_name).strip()
    return CLASS_ALIASES.get(name.lower(), name)


def class_style(class_name):
    return CLASS_STYLES.get(canonical_class_name(class_name), DEFAULT_STYLE)


def static_url_for_path(path):
    parts = Path(path).parts
    for index, part in enumerate(parts):
        if part == 'static':
            return '/' + '/'.join(parts[index:])
    return None


def annotated_path_for(image_path):
    path = Path(image_path)
    suffix = path.suffix or '.jpg'
    return str(path.with_name(f'{path.stem}_annotated{suffix}'))


def resize_for_analysis(image, max_edge=MAX_ANALYSIS_EDGE):
    """Keep inference responsive by bounding very large uploads."""
    height, width = image.shape[:2]
    longest_edge = max(height, width)
    if not max_edge or longest_edge <= max_edge:
        return image

    scale = max_edge / longest_edge
    next_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return cv2.resize(image, next_size, interpolation=cv2.INTER_AREA)


def severity_for(primary_disease, confidence, disease_box_count):
    if not primary_disease or primary_disease.lower() in HEALTHY_CLASSES:
        return 'Low'
    if confidence >= 85 or disease_box_count >= 5:
        return 'Critical'
    if confidence >= 65 or disease_box_count >= 3:
        return 'High'
    if confidence >= 35:
        return 'Medium'
    return 'Low'


def generate_disease_recommendations(disease, confidence=0):
    disease = canonical_class_name(disease)
    recommendations_db = {
        'Blight': [
            'Remove heavily infected leaves and keep them away from healthy plants.',
            'Apply a recommended fungicide such as Mancozeb or Chlorothalonil.',
            'Improve airflow and avoid overhead watering.',
            'Reduce humidity around the canopy.'
        ],
        'Brown spot': [
            'Improve drainage and avoid long leaf-wetness periods.',
            'Apply copper-based fungicide if symptoms continue.',
            'Remove infected leaves and monitor nearby plants.',
            'Balance nitrogen and potassium fertilization.'
        ],
        'False Smut': [
            'Remove infected panicles where possible.',
            'Avoid excess nitrogen fertilization.',
            'Improve field sanitation and monitor humidity.',
            'Use preventive fungicide during high-risk growth stages.'
        ],
        'Kernel Smut': [
            'Separate infected seed material from healthy stock.',
            'Use clean or treated seed for the next planting cycle.',
            'Improve sanitation around trays and growing media.',
            'Track repeat cases from the same seed source.'
        ],
        'Leaf Smut': [
            'Remove affected leaves from the growing area.',
            'Apply sulfur-based or locally recommended fungicide.',
            'Increase spacing and airflow around plants.',
            'Keep humidity under tighter control.'
        ],
        'Rice blast': [
            'Apply triazole fungicide according to label guidance.',
            'Avoid excessive nitrogen application.',
            'Increase airflow and reduce canopy wetness.',
            'Remove infected plant material where practical.'
        ],
        'Stem Rot': [
            'Remove severely infected plants to reduce spread.',
            'Improve drainage and avoid waterlogged roots.',
            'Disinfect tools and trays after handling infected plants.',
            'Use resistant varieties when available.'
        ],
        'Tungro': [
            'Remove infected plants early to reduce virus spread.',
            'Control leafhopper vectors around the crop area.',
            'Use resistant rice varieties where available.',
            'Avoid staggered planting that keeps hosts available continuously.'
        ],
        'Healthy': [
            'No visible disease detected in this image.',
            'Keep monitoring with regular manual or ESP32 camera scans.',
            'Maintain stable humidity, airflow, and watering cycles.'
        ]
    }
    return recommendations_db.get(disease, [
        'Consult a local agricultural expert for confirmation.',
        'Capture another clear image from a different angle.',
        'Improve growing conditions and monitor symptom spread.',
        'Consider preventive treatment if symptoms increase.'
    ])


def draw_label(image, x1, y1, label, color, thickness):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.5, min(image.shape[:2]) / 1100)
    text_thickness = max(1, thickness - 1)
    (text_width, text_height), baseline = cv2.getTextSize(label, font, scale, text_thickness)
    pad = max(4, thickness + 2)
    label_width = text_width + pad * 2
    label_x1 = min(max(0, x1), max(0, image.shape[1] - label_width - 1))
    label_x2 = min(image.shape[1] - 1, label_x1 + label_width)
    label_y1 = max(0, y1 - text_height - baseline - pad * 2)
    label_y2 = label_y1 + text_height + baseline + pad * 2
    cv2.rectangle(image, (label_x1, label_y1), (label_x2, label_y2), color, -1)
    cv2.putText(
        image,
        label,
        (label_x1 + pad, label_y2 - baseline - pad),
        font,
        scale,
        (255, 255, 255),
        text_thickness,
        cv2.LINE_AA
    )


def draw_inner_label(image, x1, y1, x2, y2, label, color, thickness):
    font = cv2.FONT_HERSHEY_SIMPLEX
    pad = max(5, thickness + 3)
    box_width = max(1, x2 - x1)
    box_height = max(1, y2 - y1)
    scale = max(0.55, min(image.shape[:2]) / 900)
    text_thickness = max(2, thickness)

    while scale > 0.32:
        (text_width, text_height), baseline = cv2.getTextSize(label, font, scale, text_thickness)
        if text_width <= box_width - pad * 2 and text_height + baseline <= box_height - pad * 2:
            break
        scale -= 0.05

    (text_width, text_height), baseline = cv2.getTextSize(label, font, scale, text_thickness)
    label_x1 = min(max(x1 + pad, 0), max(0, image.shape[1] - text_width - pad * 2 - 1))
    label_y1 = min(max(y1 + pad, 0), max(0, image.shape[0] - text_height - baseline - pad * 2 - 1))
    label_x2 = min(image.shape[1] - 1, label_x1 + text_width + pad * 2)
    label_y2 = min(image.shape[0] - 1, label_y1 + text_height + baseline + pad * 2)

    overlay = image.copy()
    cv2.rectangle(overlay, (label_x1, label_y1), (label_x2, label_y2), color, -1)
    cv2.addWeighted(overlay, 0.82, image, 0.18, 0, image)
    cv2.putText(
        image,
        label,
        (label_x1 + pad, label_y2 - baseline - pad),
        font,
        scale,
        (255, 255, 255),
        text_thickness,
        cv2.LINE_AA
    )


def analyze_image_for_disease(image_path, model=None, logger=None):
    """Analyze an image, save a boxed/colored annotated copy, and return diagnosis data."""
    if cv2 is None:
        return {
            'error': f'OpenCV is unavailable in this runtime: {CV2_IMPORT_ERROR}',
            'primary_disease': None,
            'confidence': 0,
            'detections': {},
            'boxes': [],
            'recommendations': []
        }
    try:
        model = model or load_model()
    except Exception as exc:
        return {
            'error': f'YOLO model is unavailable in this runtime: {exc}',
            'primary_disease': None,
            'confidence': 0,
            'detections': {},
            'boxes': [],
            'recommendations': []
        }
    image = cv2.imread(str(image_path))
    if image is None:
        return {
            'error': 'Could not load image',
            'primary_disease': None,
            'confidence': 0,
            'detections': {},
            'boxes': []
        }

    analysis_image = resize_for_analysis(image)
    results = model.predict(analysis_image, imgsz=640, verbose=False)[0]
    annotated_image = analysis_image.copy()
    boxes_payload = []
    disease_counts = {}
    confidence_totals = {}

    boxes = getattr(results, 'boxes', None)
    if boxes is not None and len(boxes) > 0:
        thickness = max(2, min(image.shape[:2]) // 320)
        for xyxy, class_id, conf in zip(boxes.xyxy, boxes.cls, boxes.conf):
            class_id = int(class_id.item() if hasattr(class_id, 'item') else class_id)
            confidence = float(conf.item() if hasattr(conf, 'item') else conf)
            class_name = canonical_class_name(results.names[class_id])
            color = class_style(class_name)['bgr']
            hex_color = class_style(class_name)['hex']
            x1, y1, x2, y2 = [int(round(value)) for value in xyxy.tolist()]
            x1 = max(0, min(x1, image.shape[1] - 1))
            x2 = max(0, min(x2, image.shape[1] - 1))
            y1 = max(0, min(y1, image.shape[0] - 1))
            y2 = max(0, min(y2, image.shape[0] - 1))

            disease_counts[class_name] = disease_counts.get(class_name, 0) + 1
            confidence_totals[class_name] = confidence_totals.get(class_name, 0.0) + confidence

            cv2.rectangle(annotated_image, (x1, y1), (x2, y2), color, thickness)
            draw_label(annotated_image, x1, y1, f'{class_name} {confidence * 100:.1f}%', color, thickness)
            draw_inner_label(annotated_image, x1, y1, x2, y2, class_name, color, thickness)

            boxes_payload.append({
                'class_name': class_name,
                'confidence': round(confidence * 100, 2),
                'box': [x1, y1, x2, y2],
                'color': hex_color
            })

    diagnosis_counts = {
        name: count for name, count in disease_counts.items()
        if name.lower() not in HEALTHY_CLASSES
    }
    candidate_counts = diagnosis_counts or disease_counts
    primary_disease = None
    confidence = 0
    if candidate_counts:
        primary_disease = max(
            candidate_counts,
            key=lambda name: (candidate_counts[name], confidence_totals.get(name, 0))
        )
        confidence = (confidence_totals[primary_disease] / disease_counts[primary_disease]) * 100
    else:
        primary_disease = 'Healthy'

    disease_box_count = sum(diagnosis_counts.values())
    severity = severity_for(primary_disease, confidence, disease_box_count)
    recommendations = generate_disease_recommendations(primary_disease, confidence)

    annotated_path = annotated_path_for(image_path)
    cv2.imwrite(annotated_path, annotated_image)

    if logger:
        logger.info(f'Analyzed disease image: {primary_disease} ({confidence:.1f}%)')

    return {
        'primary_disease': primary_disease,
        'confidence': confidence,
        'detections': disease_counts,
        'boxes': boxes_payload,
        'severity': severity,
        'recommendations': recommendations,
        'original_image_path': str(image_path),
        'original_image_url': static_url_for_path(image_path),
        'annotated_image_path': annotated_path,
        'annotated_image_url': static_url_for_path(annotated_path)
    }

