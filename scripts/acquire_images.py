"""Bounded, robots-aware hospital image discovery with quarantine and explicit review gates."""
from __future__ import annotations

import argparse
import hashlib
import io
import ipaddress
import json
import socket
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.evidence import APPROVED_RIGHTS, DATA, get_research, promotion_errors, read_json, write_json

USER_AGENT = "VelaResearchBot/0.1 (+bounded academic prototype; public metadata only)"
MAX_BYTES = 8 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def allowed_url(url: str, domains: list[str]) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in domains and parsed.port in (None, 443)
            and not parsed.username and not parsed.password)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RestrictedFetcher:
    def __init__(self, domains, *, delay=1.0, timeout=10):
        self.domains = domains
        self.delay = max(1.0, delay)
        self.timeout = timeout
        self.last_request = {}
        self.robots = {}
        self.robots_errors = {}
        self.opener = build_opener(NoRedirect())

    def _fetch(self, url, redirects=0, robots_request=False):
        if not allowed_url(url, self.domains):
            raise ValueError("URL is outside approved HTTPS domains")
        if redirects > 3:
            raise ValueError("Redirect limit")
        host = urlsplit(url).hostname
        # Reject private/link-local/loopback targets, including DNS-resolved addresses.
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise ValueError("Non-public network destination refused")
        remaining = self.delay - (time.monotonic() - self.last_request.get(host, 0))
        if remaining > 0:
            time.sleep(remaining)
        self.last_request[host] = time.monotonic()
        try:
            with self.opener.open(Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,image/*;q=0.8,text/plain;q=0.5"}), timeout=self.timeout) as response:
                if int(response.headers.get("Content-Length", 0)) > MAX_BYTES:
                    raise ValueError("Content exceeds size limit")
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("Content exceeds size limit")
                return data, response.headers.get("Content-Type", ""), url
        except HTTPError as error:
            if error.code in {301, 302, 303, 307, 308}:
                location = error.headers.get("Location")
                if not location:
                    raise ValueError("Redirect without destination")
                target = urljoin(url, location)
                if not allowed_url(target, self.domains):
                    raise ValueError("Redirect outside approved domains")
                if not robots_request and not self.can_fetch(target):
                    raise ValueError("Redirect destination robots denied")
                return self._fetch(target, redirects + 1, robots_request=robots_request)
            raise

    def can_fetch(self, url):
        if not allowed_url(url, self.domains):
            return False
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            # Any missing, forbidden or unreachable robots file fails closed, including 404.
            self.robots[origin] = None
            try:
                data, content_type, final = self._fetch(origin + "/robots.txt", robots_request=True)
                if "html" in content_type.lower() or b"user-agent:" not in data.lower():
                    self.robots_errors[origin] = "No valid robots user-agent directives"
                    return False
                parser = RobotFileParser()
                parser.set_url(final)
                parser.parse(data.decode("utf-8", errors="replace").splitlines())
                crawl_delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 0
                request_rate = parser.request_rate(USER_AGENT) or parser.request_rate("*")
                if request_rate and request_rate.requests:
                    crawl_delay = max(crawl_delay, request_rate.seconds / request_rate.requests)
                if crawl_delay > 60:
                    self.robots_errors[origin] = "Declared crawl delay exceeds this bounded run"
                    return False
                self.delay = max(self.delay, crawl_delay)
                self.robots[origin] = parser
            except (OSError, ValueError) as error:
                self.robots_errors[origin] = str(error)
                return False
        parser = self.robots[origin]
        return parser is not None and parser.can_fetch(USER_AGENT, url)

    def fetch(self, url):
        if not self.can_fetch(url):
            parsed = urlsplit(url)
            reason = self.robots_errors.get(f"{parsed.scheme}://{parsed.netloc}", "URL disallowed or outside approved domains")
            raise ValueError("robots.txt unavailable or disallows URL: " + reason)
        return self._fetch(url)


class PageImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in {"img", "source"}:
            for key in ("src", "data-src", "data-lazy-src"):
                if attrs.get(key):
                    self.images.append((attrs[key], attrs.get("alt", "")))
            srcset = attrs.get("srcset") or attrs.get("data-srcset")
            if srcset:
                # One candidate per responsive set; byte hashing later handles duplicates.
                item = srcset.split(",")[-1].strip().split()[0]
                self.images.append((item, attrs.get("alt", "")))
        if tag == "meta" and attrs.get("property") == "og:image" and attrs.get("content"):
            self.images.append((attrs["content"], "page social image; requires room relevance review"))


def detect_privacy(path: Path):
    """Optional local detectors flag candidates; no detection is not de-identification."""
    annotations = {"people_detection": {"status": "unknown", "reason": "OpenCV detector unavailable"},
                   "text_detection": {"status": "unknown", "reason": "Local Tesseract OCR unavailable"}}
    try:
        import cv2
        image = cv2.imread(str(path))
        if image is None:
            return annotations
        scale = min(1.0, 1400 / max(image.shape[:2]))
        resized = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
        if min(resized.shape[:2]) >= 128:
            detector = cv2.HOGDescriptor()
            detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            boxes, _ = detector.detectMultiScale(resized, winStride=(8, 8), padding=(8, 8), scale=1.1)
            annotations["people_detection"] = {"status": "flagged" if len(boxes) else "clear",
                "method": "opencv_hog", "count": len(boxes), "limitation": "Misses seated, occluded and small people; human review mandatory"}
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    try:
        import pytesseract
        from PIL import Image
        with Image.open(path) as picture:
            text = pytesseract.image_to_string(picture)
        annotations["text_detection"] = {"status": "flagged" if text.strip() else "clear",
            "method": "local_tesseract", "text_detected": bool(text.strip()),
            "limitation": "Text is not stored; OCR can miss identifying information"}
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return annotations


def candidate(hospital, source_url, image_url, alt):
    return {"id": hashlib.sha256((hospital["hospital"] + image_url).encode()).hexdigest()[:20],
            "hospital": hospital["hospital"], "source_url": source_url, "image_url": image_url,
            "source_type": "official_hospital_page", "timestamp": now(), "hash": None,
            "rights_status": "unknown", "rights_evidence": None, "privacy_status": "quarantined",
            "room_type": "unreviewed", "quality": "unreviewed", "usable_for_analysis": False,
            "usable_for_training": False, "local_path": None, "training_permission": False,
            "commercial_reuse_allowed": False, "human_reviewer": None, "reviewed_at": None,
            "annotations": {"alt": alt[:500], "discovery_basis": "page metadata, not confirmed hospital-room content",
                "people_detection": {"status": "unknown", "reason": "content not downloaded"},
                "text_detection": {"status": "unknown", "reason": "content not downloaded"}}}


def download(record, fetcher, output, permission):
    if permission.get("rights_status") not in APPROVED_RIGHTS or not permission.get("rights_evidence"):
        raise ValueError("Byte acquisition requires verified licence/permission evidence")
    if permission.get("image_url") != record["image_url"]:
        raise ValueError("Permission must apply to this exact image URL")
    data, content_type, final = fetcher.fetch(record["image_url"])
    if not content_type.lower().startswith("image/"):
        raise ValueError("Not image content")
    from PIL import Image
    with Image.open(io.BytesIO(data)) as picture:
        width, height = picture.size
        if width * height > 40_000_000 or min(width, height) < 240:
            raise ValueError("Image dimensions outside dataset policy")
        picture.verify()
    digest = hashlib.sha256(data).hexdigest()
    path = output / "quarantine" / f"{digest}.img"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    record.update({"hash": digest, "local_path": str(path.resolve()), "final_image_url": final,
                   "rights_status": permission["rights_status"], "rights_evidence": permission["rights_evidence"],
                   "training_permission": permission.get("training_permission") is True,
                   "commercial_reuse_allowed": permission.get("commercial_reuse_allowed") is True})
    record["annotations"].update({"width": width, "height": height, **detect_privacy(path)})


def crawl(args):
    hospitals = read_json(args.seeds, [])
    if args.hospital:
        hospitals = [h for h in hospitals if h["id"] in args.hospital]
    if not hospitals:
        raise ValueError("No matching hospital seeds")
    records = read_json(args.output / "records.json", [])
    permissions = read_json(args.permissions, []) if args.permissions else []
    seen_images = {(r["hospital"], r["image_url"]) for r in records}
    events = []
    for hospital in hospitals:
        fetcher = RestrictedFetcher(hospital["allowed_domains"], delay=args.delay, timeout=args.timeout)
        queue = list(hospital["seed_urls"])
        visited = set()
        count = sum(r["hospital"] == hospital["hospital"] for r in records)
        while queue and len(visited) < args.max_pages and count < args.per_hospital and len(records) < args.max_candidates:
            url = queue.pop(0)
            if url in visited or not allowed_url(url, hospital["allowed_domains"]):
                continue
            visited.add(url)
            try:
                content, content_type, final = fetcher.fetch(url)
                if "html" not in content_type.lower():
                    continue
                parser = PageImages()
                parser.feed(content.decode("utf-8", errors="replace"))
                for image_url, alt in parser.images:
                    image_url = urldefrag(urljoin(final, image_url))[0]
                    key = hospital["hospital"], image_url
                    if key in seen_images or count >= args.per_hospital or len(records) >= args.max_candidates:
                        continue
                    if not any(token in (image_url + " " + alt + " " + final).lower() for token in ("room", "interior", "ward", "suite", "patient", "tour")):
                        continue
                    if any(token in image_url.lower() for token in ("logo", ".svg", "icon", "pixel")):
                        continue
                    if not fetcher.can_fetch(image_url):
                        continue
                    record = candidate(hospital, final, image_url, alt)
                    record["robots_checked_at"] = now()
                    if args.download:
                        permission = next((p for p in permissions if p.get("image_url") == image_url), {})
                        try:
                            download(record, fetcher, args.output, permission)
                        except (OSError, ValueError) as error:
                            record["download_status"] = str(error)
                    records.append(record)
                    seen_images.add(key)
                    count += 1
                for link in parser.links:
                    target = urldefrag(urljoin(final, link))[0]
                    if any(token in target.lower() for token in ("room", "patient", "tour", "hospital", "gallery", "facility")) and target not in visited:
                        queue.append(target)
                events.append({"hospital": hospital["hospital"], "url": url, "status": "read", "at": now()})
            except (OSError, ValueError) as error:
                events.append({"hospital": hospital["hospital"], "url": url, "status": "blocked_or_unavailable", "reason": str(error), "at": now()})
        write_json(args.output / "records.json", records)
        print(json.dumps({"hospital": hospital["hospital"], "candidate_metadata": count, "pages_attempted": len(visited)}), flush=True)
    log = read_json(args.output / "acquisition_log.json", [])
    write_json(args.output / "acquisition_log.json", log + events)
    print(json.dumps({"candidate_records": len(records), "downloaded_unique_images": len({r["hash"] for r in records if r.get("hash")}), "all_new_records_quarantined": True}))


def review(args):
    records = read_json(args.output / "records.json", [])
    record = next((r for r in records if r["id"] == args.record), None)
    if record is None:
        raise ValueError("Unknown record")
    evidence = read_json(args.review, {})
    # Review cannot rewrite content hashes, detector findings, or silently grant permissions.
    for field in ("human_reviewer", "privacy_status", "room_type", "quality"):
        record[field] = evidence.get(field)
    record["reviewed_at"] = now()
    if not record.get("local_path"):
        raise ValueError("No downloaded content to review")
    path = Path(record["local_path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("hash"):
        raise ValueError("Content hash changed; acquire and review again")
    errors = promotion_errors(record, training=args.training)
    if errors:
        raise ValueError("Promotion refused: " + ", ".join(errors))
    record["usable_for_analysis"] = True
    record["usable_for_training"] = bool(args.training)
    write_json(args.output / "records.json", records)
    log = read_json(args.output / "review_log.json", [])
    log.append({"record": record["id"], "reviewer": record["human_reviewer"], "at": now(), "training": args.training, "hash": record["hash"]})
    write_json(args.output / "review_log.json", log)
    print(json.dumps({"promoted": record["id"], "training": args.training}))


def download_existing(args):
    if not args.permissions:
        raise ValueError("--permissions is required for content acquisition")
    records = read_json(args.output / "records.json", [])
    permissions = read_json(args.permissions, [])
    hospitals = read_json(args.seeds, [])
    fetchers = {}
    acquired = 0
    for record in records:
        if args.record and record["id"] != args.record:
            continue
        if record.get("hash"):
            continue
        hospital = next((h for h in hospitals if h["hospital"] == record["hospital"]), None)
        if not hospital or (args.hospital and hospital["id"] not in args.hospital):
            continue
        permission = next((p for p in permissions if p.get("image_url") == record["image_url"]), None)
        if not permission:
            continue
        fetcher = fetchers.setdefault(hospital["id"], RestrictedFetcher(hospital["allowed_domains"], delay=args.delay, timeout=args.timeout))
        try:
            download(record, fetcher, args.output, permission)
            acquired += 1
            record["download_status"] = "quarantined"
        except (OSError, ValueError) as error:
            record["download_status"] = str(error)
    write_json(args.output / "records.json", records)
    print(json.dumps({"acquired_records": acquired, "downloaded_unique_images": len({r["hash"] for r in records if r.get("hash")}), "all_new_content_quarantined": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "crawl", "download", "status", "review", "scan"])
    parser.add_argument("--seeds", type=Path, default=DATA / "hospital-images" / "hospitals.json")
    parser.add_argument("--output", type=Path, default=DATA / "hospital-images")
    parser.add_argument("--hospital", action="append", help="Seed ID, repeat to select specific hospitals")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--per-hospital", type=int, default=20)
    parser.add_argument("--max-candidates", type=int, default=1000)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--permissions", type=Path)
    parser.add_argument("--record")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--training", action="store_true")
    args = parser.parse_args()
    try:
        if not (1 <= args.max_pages <= 100 and 1 <= args.per_hospital <= 100 and 1 <= args.max_candidates <= 5000):
            raise ValueError("Crawler limits outside allowed bounds")
        if not (1 <= args.delay <= 60 and 1 <= args.timeout <= 30):
            raise ValueError("Delay/timeout outside allowed bounds")
        if args.command == "crawl":
            crawl(args)
        elif args.command == "download":
            download_existing(args)
        elif args.command == "review":
            if not args.record or not args.review:
                raise ValueError("--record and --review required")
            review(args)
        elif args.command == "scan":
            records = read_json(args.output / "records.json", [])
            for record in records:
                if record.get("local_path") and (not args.record or record["id"] == args.record):
                    record["annotations"].update(detect_privacy(Path(record["local_path"])))
                    record["usable_for_analysis"] = False
                    record["usable_for_training"] = False
                    record["privacy_status"] = "quarantined"
            write_json(args.output / "records.json", records)
        elif args.command == "plan":
            hospitals = read_json(args.seeds, [])
            print(json.dumps({"hospital_seeds": len(hospitals), "target_candidates": sum(h["target_candidates"] for h in hospitals), "downloads_permitted_without_rights": False}, indent=2))
        else:
            records = read_json(args.output / "records.json", [])
            print(json.dumps({"candidate_records": len(records), "candidate_hospitals": len({r["hospital"] for r in records}), "downloaded_unique_images": len({r["hash"] for r in records if r.get("hash")}), "analysis_approved": sum(r.get("usable_for_analysis") is True and not promotion_errors(r) for r in records), "training_approved": sum(r.get("usable_for_training") is True and not promotion_errors(r, training=True) for r in records)}, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(2, f"Acquisition/review refused: {error}\n")


if __name__ == "__main__":
    main()
