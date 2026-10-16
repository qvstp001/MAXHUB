import json
import logging
import os
import threading

from .server import App, make_server
from . import DEFAULT_ADMIN_PASSWORD


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    roots_value = os.getenv('LIBRARY_ROOTS', '/media')
    # JSON supports Windows paths without overloading drive-letter colons.
    roots = json.loads(roots_value) if roots_value.startswith('[') else roots_value.split(';')
    port = int(os.getenv('PORT', '8096'))
    app = App(os.getenv('DATA_DIR', './data'), roots, os.getenv('ADMIN_PASSWORD') or DEFAULT_ADMIN_PASSWORD,
              os.getenv('PUBLIC_URL') or f'http://localhost:{port}',
              os.getenv('PLAYBACK_PROXY_URL', os.getenv('LITEPAN_PUBLIC_URL', '')))
    stop = threading.Event()
    server = make_server(app, os.getenv('HOST', '0.0.0.0'), port)
    threading.Thread(target=app.schedule, args=(stop,), daemon=True).start()
    logging.info('QMaxHub listening on port %s', server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
