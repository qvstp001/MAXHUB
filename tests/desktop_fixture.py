"""独立的桌面交互测试服务，仅使用虚构媒体，监听本机 18099。"""
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from maxhub.server import App, make_server


def main():
    root = Path(__file__).resolve().parent.parent / '.test-data' / 'desktop-profiles'
    media = root / 'media'
    media.mkdir(parents=True, exist_ok=True)
    (media / 'poster.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
    for name in ('sample-1.png', 'sample-2.png'):
        (media / name).write_bytes((media / 'poster.png').read_bytes())
    for i in range(80):
        studio = '厂商甲' if i % 4 < 2 else '厂商乙'
        folder = media / studio
        if i >= 40:
            folder = folder / '子目录'
        folder.mkdir(parents=True, exist_ok=True)
        code = f'DESK-{i:03}'
        parts = [f'{code}-CD1', f'{code}-CD2'] if i == 0 else [code]
        for part in parts:
            (folder / f'{part}.strm').write_text(f'https://example.test/unused/{part}.mp4', encoding='utf-8')
        image = os.path.relpath(media / 'poster.png', folder).replace('\\', '/')
        sample = os.path.relpath(media / 'sample-1.png', folder).replace('\\', '/')
        sample2 = os.path.relpath(media / 'sample-2.png', folder).replace('\\', '/')
        tags = '<tag>剧情</tag>' if i % 2 == 0 else ''
        tags += '<tag>收藏</tag>' if i % 3 == 0 else ''
        (folder / f'{code}.nfo').write_text(f'<movie><num>{code}</num><title>桌面测试影片 {i:03}</title>'
            f'<originaltitle>Desktop fixture {i:03}</originaltitle><premiered>{2020+i%5}-06-12</premiered>'
            f'<runtime>120</runtime><rating>7.5</rating><director>示例导演</director><plot>本地虚构测试资料。</plot>'
            f'<studio>{studio}</studio><actor><name>{"演员甲" if i%2==0 else "演员乙"}</name>'
            f'<role>出演</role><thumb>{image}</thumb></actor>'
            f'<sample>{sample}</sample><sample>{sample2}</sample>'
            f'<tag>共有</tag>{tags}<thumb aspect="poster">{image}</thumb></movie>', encoding='utf-8')
    app = App(root / 'data', [media], 'http://127.0.0.1:18099')
    app.scanner.lock.acquire()
    app.scanner.run(force=True)
    if app.scanner.status['errors']:
        raise RuntimeError(app.scanner.status['errors'])
    server = make_server(app, '127.0.0.1', 18099)
    print('Desktop fixture ready: http://127.0.0.1:18099', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
