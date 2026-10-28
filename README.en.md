# QMaxHub Media Library Player

A single-user, self-hosted media library based on [Peach](https://github.com/peach-mitao/peach), focused on local media and STRM playback on NAS Docker.

- Browse videos, people, tags and playlists, with search, natural code sorting, favorites and watch later.
- Adjustable poster and banner views, local artwork and NFO metadata.
- Read-only media scanning and local metadata import; filenames remain usable without metadata.
- Browser playback, Range, progress, local subtitles, SubtitleCat and Xunlei subtitle search.
- STRM proxy or 302 redirects, M3U, PotPlayer and Android mpv links.
- FFmpeg software transcoding and existing hardware detection with software fallback.

Metadata scraping, subscriptions, online title discovery, resource search, cloud downloads, browser history collection and candidate review are unavailable. Existing metadata and personal records remain in the database.

## Docker

Image: `ghcr.io/qvstp001/qmaxhub:latest`. Source changes reach this tag after building, container verification and publication.

Follow the [STRM Docker guide](docs/STRM_DOCKER.md) for a dedicated `/data` volume and read-only `/media`. Preserve the actual ports, user, mounts and network of existing deployments; back up the database and data directory before updating.

The image installs library runtime dependencies without OpenCV, NumPy, face models, crawler transport, cloud download clients or desktop tray dependencies. FFmpeg and the existing VAAPI stack remain. Published image size is recorded by the release workflow.

## Development and license

Dependencies are pinned in `pyproject.toml` and `uv.lock`. Use `uv sync --locked --all-extras` for development and the documented `scripts/test.ps1` or `scripts/test.sh` entry points for verification. See [testing](docs/TESTING.md).

Peach baseline: `de22796c04919aaa057d77930c33c81313765569` (0.46.1), under [AGPL-3.0-or-later](LICENSE). See [ADR-0114](docs/adr/0114-library-player-runtime.md) for the runtime boundary. The original QMaxHub remains in the `qmaxhub-legacy-before-peach` tag and Git history. Historical feature documents describe upstream capabilities.

[中文](README.md)
