"""只读发现影片同目录的横幅图片。"""
from pathlib import Path

from .library_nfo import SidecarIndex, directory_files, read_nfo
from .media import MediaNotFound, MediaUnavailable

EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.tbn')
KINDS = ('fanart', 'landscape', 'banner', 'backdrop')


def backdrop(video: Path, files: dict[str, Path] | None = None) -> Path | None:
    """本地 NFO 引用优先，通用文件只用于单影片目录。"""
    root = video.parent.resolve()
    files = directory_files(root) if files is None else files
    index = SidecarIndex(files)
    names = [f'{video.stem}-{kind}' for kind in KINDS]
    candidates = []
    nfo, _ = index.for_video(video)
    if nfo and nfo.resolve().is_relative_to(root):
        names.extend(f'{nfo.stem}-{kind}' for kind in KINDS)
        try:
            payload, _ = read_nfo(nfo)
            value = payload.get('local_backdrop', '')
            reference = Path(value)
            if value and '://' not in value and not reference.is_absolute() and '..' not in reference.parts:
                candidates.append(root / value)
        except (OSError, ValueError, SyntaxError):
            pass
    if index.single:
        names.extend(KINDS)
    candidates.extend(files[key] for name in names for extension in EXTENSIONS
                      if (key := (name + extension).casefold()) in files)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_relative_to(root) and resolved.suffix.lower() in EXTENSIONS and resolved.is_file():
            return resolved
    return None


def for_asset(engine, asset_id: int) -> Path | None:
    """沿用媒体引擎的挂载、授权根与在线状态检查。"""
    try:
        return backdrop(engine.file_for(asset_id))
    except (OSError, ValueError, MediaNotFound, MediaUnavailable):
        return None


def for_assets(engine, asset_ids) -> dict[int, Path]:
    """一页作品共用目录索引，保持每条媒体的路径授权。"""
    directories = {}
    found = {}
    for asset_id in asset_ids:
        try:
            video = engine.file_for(asset_id)
            root = video.parent.resolve()
            if root not in directories:
                directories[root] = directory_files(root)
            path = backdrop(video, directories[root])
            if path is not None:
                found[asset_id] = path
        except (OSError, ValueError, MediaNotFound, MediaUnavailable):
            continue
    return found
