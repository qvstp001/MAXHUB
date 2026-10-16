"""Container probe without shell quoting or proxy environment dependencies."""
import http.client
import os
import sys


def main():
    connection = http.client.HTTPConnection('127.0.0.1', int(os.getenv('PORT', '8096')), timeout=2)
    try:
        connection.request('GET', '/health')
        response = connection.getresponse()
        response.read()
        if response.status != 200:
            print(f'Health endpoint returned HTTP {response.status}', file=sys.stderr)
            return 1
        return 0
    except OSError as error:
        print(f'Health endpoint unavailable: {error}', file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == '__main__':
    sys.exit(main())
