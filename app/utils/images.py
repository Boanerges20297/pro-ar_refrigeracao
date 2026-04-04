import os
from PIL import Image
from werkzeug.utils import secure_filename
from flask import current_app

def save_and_resize_image(file, folder, max_size_mb=2, target_width=1024):
    """
    Saves and resizes an image to stay within quality/size limits.
    """
    if not file:
        return None

    filename = secure_filename(file.filename)
    if not filename:
        import uuid
        filename = f"{uuid.uuid4().hex}.jpg"
    
    # Ensure directory exists
    upload_path = os.path.join(current_app.static_folder, folder)
    os.makedirs(upload_path, exist_ok=True)
    
    filepath = os.path.join(upload_path, filename)
    
    # Open image
    img = Image.open(file)
    
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

    return f"/static/{folder}/{filename}"
