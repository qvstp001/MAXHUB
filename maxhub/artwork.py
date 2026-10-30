"""On-demand local thumbnails. The media mount is always read-only."""
import hashlib
import io
import os
import threading
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


class Artwork:
    def __init__(self, directory):
        self.directory = Path(directory) / 'artwork'
        self.directory.mkdir(exist_ok=True)
        self.workers = threading.BoundedSemaphore(2)
        self.locks = [threading.Lock() for _ in range(64)]

    def thumbnail(self, source, key, size):
        name = hashlib.sha256((str(source) + key).encode()).hexdigest() + '.webp'
        cached = self.directory / name
        if cached.is_file():
            return cached.read_bytes()
        # 同一张图片可能同时出现在许多卡片上，合并其缓存生成工作。
        with self.locks[int(name[:2], 16) % len(self.locks)]:
            with self.workers:
                if cached.is_file():
                    return cached.read_bytes()
                try:
                    with Image.open(source) as original:
                        original.draft('RGB', size)
                        image = ImageOps.exif_transpose(original)
                        image.thumbnail(size, Image.Resampling.LANCZOS)
                        image = image.convert('RGB')
                        output = io.BytesIO()
                        image.save(output, 'WEBP', quality=80, method=3)
                        data = output.getvalue()
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                    return None
                temporary = cached.with_suffix('.' + uuid.uuid4().hex + '.tmp')
                try:
                    temporary.write_bytes(data)
                    os.replace(temporary, cached)
                finally:
                    temporary.unlink(missing_ok=True)
                return data
