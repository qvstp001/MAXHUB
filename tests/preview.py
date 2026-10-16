"""Optional preview with fictional metadata and abstract generated artwork.

Run from repository root: python -m tests.preview (or python tests/preview.py).
Never scans a real library. Only binds to localhost:18096.
"""
import math
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qmaxhub.server import App, make_server


def poster(path, seed):
    width, height = 320, 480
    colors = [(97, 139, 123), (181, 129, 101), (122, 137, 164), (168, 156, 107), (116, 155, 168), (154, 116, 138), (133, 154, 117), (169, 113, 96)]
    base = colors[seed % len(colors)]
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            glow = max(0, 1 - math.hypot((x - 160) / 260, (y - 130) / 420))
            ring = 1 if 58 + seed % 3 * 12 < math.hypot(x - 160, y - 165) < 64 + seed % 3 * 12 else 0
            arch = x > 60 and x < 260 and y > 185 + 60 * math.sin(x / 60 + seed) and y < 380
            fade = .22 + glow * .55 + ring * .5 + (.12 if arch else 0)
            row.extend(min(255, int(c * fade)) for c in base)
        rows.append(bytes(row))
    def chunk(kind, value):
        return struct.pack('!I', len(value)) + kind + value + struct.pack('!I', zlib.crc32(kind + value))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


def main():
    root = Path(__file__).resolve().parent.parent / '.test-data' / 'preview'
    media = root / 'media'
    titles = ['青色时光 · 午后的片刻', '向晚的房间', '海边来信', '留在记忆里的夏天', '无声的对白', '城市另一侧', '光穿过树叶的地方', '雨后的故事']
    for i, title in enumerate(titles):
        folder = media / f'DEMO-{i+1:03}'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'movie.strm').write_text(f'https://example.test/fictional/{i+1}.mp4')
        (folder / 'movie.nfo').write_text(f'<movie><num>DEMO-{i+1:03}</num><title>示例影片：{title}</title><plot>这是用于界面验证的虚构影片资料，海报为程序生成的抽象图形，播放地址仅为占位。真实影片将读取你的 NFO 和本地图片。</plot><studio>示例工作室</studio><premiered>2025-0{i+1}-12</premiered><runtime>120</runtime><rating>{7+i/10:.1f}</rating><set><name>示例收藏系列</name></set><actor><name>示例演员 {i%3+1}</name></actor><tag>示例资料</tag><genre>剧情</genre></movie>', encoding='utf-8')
        poster(folder / 'poster.png', i)
    app = App(root / 'data', [media], 'preview-only-123', 'http://127.0.0.1:18096', 'http://192.168.1.10:42069')
    app.scanner.start()
    server = make_server(app, '127.0.0.1', 18096)
    print('Fictional preview: http://127.0.0.1:18096 | password: preview-only-123', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
