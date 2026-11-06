"""Step 01 - Download original datasets and record catalogue metadata.

* Queries the CKAN API of data.buenosaires.gob.ar for every dataset and saves
  the full metadata (license, modification date, resources) to
  data/raw/catalog_<dataset>.json.
* Downloads the resources used by the project into data/raw/.
* Writes data/raw/download_log.json with the retrieval date, URL and size.

Usage:  python pipeline/01_download.py
"""
import json
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from config import CKAN_API, CKAN_DATASETS, HTTP_HEADERS, RAW, SOURCES


def fetch(url: str, timeout: int = 120):
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    return urllib.request.urlopen(req, timeout=timeout)


def save_catalog() -> None:
    for ds in CKAN_DATASETS:
        for attempt in range(5):  # the portal intermittently answers with an HTML error page
            try:
                with fetch(CKAN_API.format(ds)) as r:
                    meta = json.load(r)["result"]
                break
            except (json.JSONDecodeError, OSError) as e:
                print(f"catalog {ds}: retry after {e!r}")
                time.sleep(3 * (attempt + 1))
        else:
            cached = RAW / f"catalog_{ds}.json"
            print(f"catalog {ds}: API unavailable; {'keeping cached copy' if cached.exists() else 'NO METADATA SAVED'}")
            continue
        (RAW / f"catalog_{ds}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"catalog {ds}: {len(meta['resources'])} resources, license {meta.get('license_id')}")


def remote_size(url: str) -> int | None:
    req = urllib.request.Request(url, method="HEAD", headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        n = r.headers.get("Content-Length")
    return int(n) if n else None


def download(name: str, url: str, max_attempts: int = 20) -> dict:
    """Download with size verification and HTTP Range resume.

    The CDN sometimes closes long transfers early without an error, so the
    file is only accepted once its size equals the server's Content-Length.
    """
    target = RAW / url.rsplit("/", 1)[-1]
    expected = remote_size(url)
    if target.exists() and (expected is None or target.stat().st_size == expected):
        print(f"cached      {name}: {target.name}")
    else:
        tmp = target.with_suffix(target.suffix + ".part")
        if target.exists():  # truncated earlier run: resume from it
            target.replace(tmp)
        for attempt in range(1, max_attempts + 1):
            have = tmp.stat().st_size if tmp.exists() else 0
            if expected is not None and have >= expected:
                break
            print(f"downloading {name} (attempt {attempt}, {have / 1e6:.1f}/{(expected or 0) / 1e6:.1f} MB)")
            headers = dict(HTTP_HEADERS)
            if have:
                headers["Range"] = f"bytes={have}-"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "ab" if have else "wb") as f:
                    if have and r.status != 206:  # server ignored Range: start over
                        f.truncate(0)
                    shutil.copyfileobj(r, f, length=1 << 20)
            except (OSError, urllib.error.URLError) as e:
                print(f"  interrupted: {e!r}")
            if expected is None:
                break
        size = tmp.stat().st_size
        if expected is not None and size != expected:
            raise RuntimeError(f"{name}: got {size} bytes, expected {expected}")
        tmp.replace(target)
    return {
        "name": name,
        "url": url,
        "file": target.name,
        "bytes": target.stat().st_size,
        "retrieved_utc": datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(),
    }


def main() -> None:
    save_catalog()
    log = [download(k, v) for k, v in SOURCES.items()]
    (RAW / "download_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    for e in log:
        print(f"  {e['file']:<45} {e['bytes'] / 1e6:8.1f} MB")


if __name__ == "__main__":
    main()
