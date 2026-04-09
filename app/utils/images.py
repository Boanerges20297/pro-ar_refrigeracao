import os
import uuid
from PIL import Image
from PIL import UnidentifiedImageError
from werkzeug.utils import secure_filename
from flask import current_app, url_for


ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

def save_and_resize_image(file, folder, max_size_mb=2, target_width=1024):
    """
    Saves and resizes an image to stay within quality/size limits.
    """
    if not file:
        return None

    filename = secure_filename(file.filename)
    if not filename:
        filename = f"{uuid.uuid4().hex}.jpg"

    extension = os.path.splitext(filename)[1].lower().lstrip('.')
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Formato de imagem não permitido. Use JPG, PNG ou WEBP.')
    
    # Ensure directory exists
    upload_root = None
    app_config = getattr(current_app, 'config', None)
    if app_config:
        upload_root = app_config.get('UPLOAD_ROOT')

    if not upload_root:
        upload_root = getattr(current_app, 'static_folder')

    upload_path = os.path.join(upload_root, folder)
    os.makedirs(upload_path, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(upload_path, stored_filename)
    
    try:
        file.stream.seek(0)
        img = Image.open(file.stream)
    except UnidentifiedImageError as exc:
        raise ValueError('Arquivo enviado não é uma imagem válida.') from exc
    
    # Convert RGBA to RGB if necessary (for JPEG)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    # Resize if width is larger than target_width
    if img.width > target_width:
        ratio = target_width / float(img.width)
        target_height = int(float(img.height) * ratio)
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    
    # Save with optimization
    # We try to keep it under max_size_mb by adjusting quality if needed, 
    # but usually optimization + resizing handles it.
    img.save(filepath, "JPEG", optimize=True, quality=85)
    
    # Check final size and log a warning if it's still large (unlikely after resizing)
    final_size = os.path.getsize(filepath)
    if final_size > max_size_mb * 1024 * 1024:
        # If still too large, save again with lower quality
        img.save(filepath, "JPEG", optimize=True, quality=50)

    return f"{folder}/{stored_filename}".replace('\\', '/')


def get_workorder_photo_url(photo_path):
    if not photo_path:
        return None

    if photo_path.startswith('/static/') or photo_path.startswith('http://') or photo_path.startswith('https://'):
        return photo_path

    return url_for('services.workorder_photo', filename=photo_path)
