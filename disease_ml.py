"""Shared YOLO disease analysis and image annotation utilities."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from threading import Lock

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')
os.environ.setdefault('NUMEXPR_NUM_THREADS', '1')
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
MAX_ANALYSIS_EDGE = int(os.environ.get('DISEASE_MAX_ANALYSIS_EDGE', '640'))
YOLO_IMAGE_SIZE = int(os.environ.get('DISEASE_YOLO_IMGSZ', '320'))
YOLO_MAX_DETECTIONS = int(os.environ.get('DISEASE_YOLO_MAX_DETECTIONS', '20'))
YOLO_DEVICE = os.environ.get('DISEASE_YOLO_DEVICE', 'cpu')
CONFIDENCE_THRESHOLD = float(os.environ.get('DISEASE_CONFIDENCE_THRESHOLD', '0.20'))
POSSIBLE_CONFIDENCE_THRESHOLD = float(os.environ.get('DISEASE_POSSIBLE_CONFIDENCE_THRESHOLD', '0.12'))
HEALTHY_CONFIDENCE = float(os.environ.get('DISEASE_HEALTHY_CONFIDENCE', '0.0'))
INFERENCE_TIMEOUT_SECONDS = float(os.environ.get('DISEASE_INFERENCE_TIMEOUT_SECONDS', '60'))
_MODEL_CACHE = None
_MODEL_LOCK = Lock()

try:
    from PIL import Image, ImageStat
    PIL_IMPORT_ERROR = None
except Exception as exc:
    Image = None
    ImageStat = None
    PIL_IMPORT_ERROR = str(exc)


def load_model(model_path='best.pt'):
    """Load YOLO lazily for API routes that do not already have a model."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        with _MODEL_LOCK:
            if _MODEL_CACHE is None:
                from ultralytics import YOLO
                _MODEL_CACHE = YOLO(model_path, task='detect')
                try:
                    import torch
                    torch.set_num_threads(max(1, int(os.environ.get('DISEASE_TORCH_THREADS', '1'))))
                except Exception:
                    pass
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


def is_disease_class(class_name):
    return bool(class_name) and canonical_class_name(class_name).lower() not in HEALTHY_CLASSES


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


def analyze_image_with_visual_fallback(image_path, logger=None, reason=None):
    """Return a fast, conservative image-health estimate when YOLO is unavailable."""
    if Image is None:
        return {
            'error': f'Fallback image analyzer is unavailable: {PIL_IMPORT_ERROR}',
            'primary_disease': None,
            'confidence': 0,
            'detections': {},
            'boxes': [],
            'recommendations': []
        }

    try:
        with Image.open(image_path) as source:
            image = source.convert('RGB')
            image.thumbnail((360, 360))
            stat = ImageStat.Stat(image)
            mean_r, mean_g, mean_b = stat.mean
            pixels = list(image.getdata())
    except Exception as exc:
        return {
            'error': f'Could not inspect image: {exc}',
            'primary_disease': None,
            'confidence': 0,
            'detections': {},
            'boxes': [],
            'recommendations': []
        }

    total = max(1, len(pixels))
    yellow_brown = 0
    dark_spots = 0
    pale = 0
    green = 0
    for red, green_value, blue in pixels:
        if green_value > red * 0.86 and green_value > blue * 1.08 and green_value > 45:
            green += 1
        if red > 92 and green_value > 70 and blue < 90 and red >= green_value * 0.78:
            yellow_brown += 1
        if red < 85 and green_value < 85 and blue < 85:
            dark_spots += 1
        if red > 150 and green_value > 140 and blue > 105:
            pale += 1

    ratios = {
        'yellow_brown': yellow_brown / total,
        'dark_spots': dark_spots / total,
        'pale': pale / total,
        'green': green / total,
    }
    likely_issue_score = min(0.92, ratios['yellow_brown'] * 1.4 + ratios['dark_spots'] * 1.1 + ratios['pale'] * 0.45)
    image_is_leaf_like = ratios['green'] > 0.08 or mean_g >= max(mean_r, mean_b)

    if image_is_leaf_like and likely_issue_score >= 0.18:
        disease = 'Brown spot' if ratios['yellow_brown'] >= ratios['dark_spots'] else 'Leaf Smut'
        confidence = max(22, min(58, likely_issue_score * 100))
        severity = severity_for(disease, confidence, 1)
        detections = {disease: 1}
    else:
        disease = 'Healthy'
        confidence = HEALTHY_CONFIDENCE
        severity = 'Low'
        detections = {}

    recommendations = generate_disease_recommendations(disease, confidence)
    if reason:
        recommendations = [
            f'YOLO analysis was not available, so this is a fast visual fallback result. Reason: {reason}',
            'Use this as a temporary estimate and retry YOLO service analysis for a confirmed diagnosis.',
            *recommendations
        ]

    if logger:
        logger.warning('Disease fallback used for %s: %s', image_path, reason or 'YOLO unavailable')

    return {
        'primary_disease': disease,
        'confidence': round(confidence, 2),
        'detections': detections,
        'possible_detections': {},
        'boxes': [],
        'discarded_low_confidence': 0,
        'confidence_threshold': CONFIDENCE_THRESHOLD * 100,
        'possible_confidence_threshold': POSSIBLE_CONFIDENCE_THRESHOLD * 100,
        'severity': severity,
        'recommendations': recommendations,
        'original_image_path': str(image_path),
        'original_image_url': static_url_for_path(image_path),
        'annotated_image_path': str(image_path),
        'annotated_image_url': static_url_for_path(image_path),
        'fallback': True,
        'fallback_metrics': ratios,
    }


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
    results = model.predict(
        analysis_image,
        imgsz=YOLO_IMAGE_SIZE,
        conf=POSSIBLE_CONFIDENCE_THRESHOLD,
        device=YOLO_DEVICE,
        max_det=YOLO_MAX_DETECTIONS,
        verbose=False
    )[0]
    annotated_image = analysis_image.copy()
    frame_height, frame_width = annotated_image.shape[:2]
    boxes_payload = []
    disease_counts = {}
    confidence_totals = {}
    possible_disease_counts = {}
    possible_confidence_totals = {}
    discarded_low_confidence = 0

    boxes = getattr(results, 'boxes', None)
    if boxes is not None and len(boxes) > 0:
        thickness = max(2, min(frame_height, frame_width) // 320)
        for xyxy, class_id, conf in zip(boxes.xyxy, boxes.cls, boxes.conf):
            class_id = int(class_id.item() if hasattr(class_id, 'item') else class_id)
            confidence = float(conf.item() if hasattr(conf, 'item') else conf)
            class_name = canonical_class_name(results.names[class_id])
            is_disease = is_disease_class(class_name)
            if is_disease and confidence < POSSIBLE_CONFIDENCE_THRESHOLD:
                discarded_low_confidence += 1
                continue
            color = class_style(class_name)['bgr']
            hex_color = class_style(class_name)['hex']
            x1, y1, x2, y2 = [int(round(value)) for value in xyxy.tolist()]
            x1 = max(0, min(x1, frame_width - 1))
            x2 = max(0, min(x2, frame_width - 1))
            y1 = max(0, min(y1, frame_height - 1))
            y2 = max(0, min(y2, frame_height - 1))

            if is_disease and confidence < CONFIDENCE_THRESHOLD:
                possible_disease_counts[class_name] = possible_disease_counts.get(class_name, 0) + 1
                possible_confidence_totals[class_name] = possible_confidence_totals.get(class_name, 0.0) + confidence
            else:
                disease_counts[class_name] = disease_counts.get(class_name, 0) + 1
                confidence_totals[class_name] = confidence_totals.get(class_name, 0.0) + confidence

            cv2.rectangle(annotated_image, (x1, y1), (x2, y2), color, thickness)
            label_prefix = 'Possible ' if is_disease and confidence < CONFIDENCE_THRESHOLD else ''
            draw_label(annotated_image, x1, y1, f'{label_prefix}{class_name} {confidence * 100:.1f}%', color, thickness)
            draw_inner_label(annotated_image, x1, y1, x2, y2, class_name, color, thickness)

            boxes_payload.append({
                'class_name': class_name,
                'confidence': round(confidence * 100, 2),
                'box': [x1, y1, x2, y2],
                'color': hex_color,
                'possible': bool(is_disease and confidence < CONFIDENCE_THRESHOLD)
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
    elif possible_disease_counts:
        primary_disease = max(
            possible_disease_counts,
            key=lambda name: (possible_disease_counts[name], possible_confidence_totals.get(name, 0))
        )
        confidence = (possible_confidence_totals[primary_disease] / possible_disease_counts[primary_disease]) * 100
    else:
        primary_disease = 'Healthy'
        confidence = HEALTHY_CONFIDENCE

    disease_box_count = sum(diagnosis_counts.values())
    possible_box_count = sum(possible_disease_counts.values())
    severity = severity_for(primary_disease, confidence, disease_box_count)
    recommendations = generate_disease_recommendations(primary_disease, confidence)
    if possible_box_count and not disease_box_count:
        recommendations = [
            f'Possible {primary_disease} was found below the strong-confidence threshold.',
            'Retake the image in bright light with the leaf filling most of the frame.',
            'Use this result as a warning and confirm with another scan before treatment.',
            *recommendations
        ]
    elif discarded_low_confidence and primary_disease == 'Healthy':
        recommendations = [
            'Only very weak disease marks were found, so this scan is treated as healthy/uncertain.',
            'Retake the image in bright light with the leaf filling most of the frame.',
            *recommendations
        ]

    annotated_path = annotated_path_for(image_path)
    cv2.imwrite(annotated_path, annotated_image)

    if logger:
        logger.info(f'Analyzed disease image: {primary_disease} ({confidence:.1f}%)')

    return {
        'primary_disease': primary_disease,
        'confidence': confidence,
        'detections': disease_counts,
        'possible_detections': possible_disease_counts,
        'boxes': boxes_payload,
        'discarded_low_confidence': discarded_low_confidence,
        'confidence_threshold': CONFIDENCE_THRESHOLD * 100,
        'possible_confidence_threshold': POSSIBLE_CONFIDENCE_THRESHOLD * 100,
        'severity': severity,
        'recommendations': recommendations,
        'original_image_path': str(image_path),
        'original_image_url': static_url_for_path(image_path),
        'annotated_image_path': annotated_path,
        'annotated_image_url': static_url_for_path(annotated_path)
    }


def analyze_image_for_disease_guarded(image_path, logger=None):
    """Run YOLO in an isolated worker so inference cannot crash the Flask server."""
    if os.environ.get('DISEASE_INFERENCE_SUBPROCESS', 'false').lower() in {'0', 'false', 'no', 'off'}:
        return analyze_image_for_disease(image_path, logger=logger)

    env = os.environ.copy()
    env['DISEASE_INFERENCE_SUBPROCESS'] = 'false'
    process = None
    try:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        process = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), '--analyze-json', str(image_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            creationflags=creationflags,
            start_new_session=os.name != 'nt',
        )
        stdout, stderr = process.communicate(timeout=INFERENCE_TIMEOUT_SECONDS)
        returncode = process.returncode
        output = (stdout or '').strip().splitlines()
        if returncode != 0:
            message = (stderr or stdout or 'Disease worker failed').strip()
            return {
                'error': f'Disease worker failed: {message[:320]}',
                'primary_disease': None,
                'confidence': 0,
                'detections': {},
                'boxes': [],
                'recommendations': []
            }
        if not output:
            return {
                'error': 'Disease worker returned no result.',
                'primary_disease': None,
                'confidence': 0,
                'detections': {},
                'boxes': [],
                'recommendations': []
            }
        return json.loads(output[-1])
    except subprocess.TimeoutExpired:
        if process is not None:
            try:
                if os.name == 'nt':
                    subprocess.run(
                        ['taskkill', '/PID', str(process.pid), '/T', '/F'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    cleanup_script = (
                        "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | "
                        "Where-Object { $_.CommandLine -like '*disease_ml.py*--analyze-json*' } | "
                        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
                    )
                    subprocess.run(
                        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cleanup_script],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                pass
        return {
            'error': f'Disease analysis exceeded {INFERENCE_TIMEOUT_SECONDS:.0f}s. Try a smaller, clearer image.',
            'primary_disease': None,
            'confidence': 0,
            'detections': {},
            'boxes': [],
            'recommendations': []
        }
    except Exception as exc:
        if logger:
            logger.error(f'Disease worker error: {exc}')
        return {
            'error': f'Disease worker error: {exc}',
            'primary_disease': None,
            'confidence': 0,
            'detections': {},
            'boxes': [],
            'recommendations': []
        }


def _cli_analyze_json():
    image_path = sys.argv[sys.argv.index('--analyze-json') + 1]
    model_path = os.environ.get('DISEASE_MODEL_PATH', 'best.pt')
    result = analyze_image_for_disease(image_path, model=load_model(model_path))
    print(json.dumps(result))


if __name__ == '__main__' and '--analyze-json' in sys.argv:
    _cli_analyze_json()

