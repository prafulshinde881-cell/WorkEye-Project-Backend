import os
import base64
from typing import Optional, Dict

try:
    import cloudinary
    import cloudinary.uploader
except Exception:
    cloudinary = None


def _configure():
    if cloudinary is None:
        return False
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET'),
        secure=True,
    )
    return True


def upload_image_bytes(image_bytes: bytes, folder: Optional[str] = None, public_id: Optional[str] = None, tags: Optional[str] = None) -> Dict:
    """Upload image bytes to Cloudinary and return the upload result dict.

    Accepts raw bytes (e.g. WebP binary). The function will convert to a data URL
    so the Cloudinary uploader can accept it without writing a temp file.
    """
    if cloudinary is None:
        raise RuntimeError("cloudinary package not installed")

    _configure()

    data_url = 'data:image/webp;base64,' + base64.b64encode(image_bytes).decode('ascii')

    upload_opts = {
        'resource_type': 'image',
        'use_filename': True,
        'unique_filename': False,
        'overwrite': False,
    }
    if folder:
        upload_opts['folder'] = folder
    if public_id:
        upload_opts['public_id'] = public_id
    if tags:
        upload_opts['tags'] = tags

    result = cloudinary.uploader.upload(data_url, **upload_opts)
    return result
