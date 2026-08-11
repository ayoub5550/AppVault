#!/usr/bin/env python3
"""AppVault full-stack server (stdlib + SQLite, no runtime dependencies)."""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, unquote, urlparse
from wsgiref.simple_server import WSGIServer, make_server

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DB_PATH = Path(os.getenv("APPVAULT_DB", ROOT / "data" / "appvault.db"))
HOST = os.getenv("APPVAULT_HOST", "127.0.0.1")
PORT = int(os.getenv("APPVAULT_PORT", "8080"))
SESSION_TTL = 60 * 60 * 24 * 7
MAX_BODY = 512_000
ALLOWED_CATEGORIES = {"ai", "productivity", "tools", "music", "weather", "social"}
ALLOWED_PLATFORMS = {"android", "ios", "both"}
ALLOWED_PRICES = {"free", "freemium", "paid"}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def password_ok(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, expected = stored.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS apps (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL, name_ar TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
          category TEXT NOT NULL, category_ar TEXT NOT NULL,
          description TEXT NOT NULL, description_ar TEXT NOT NULL,
          platform TEXT NOT NULL, rating REAL NOT NULL DEFAULT 0,
          price TEXT NOT NULL, url TEXT NOT NULL, image TEXT NOT NULL DEFAULT '',
          added_date TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
          featured INTEGER NOT NULL DEFAULT 0, published INTEGER NOT NULL DEFAULT 1,
          views INTEGER NOT NULL DEFAULT 0, clicks INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_apps_published ON apps(published, added_date DESC);
        CREATE INDEX IF NOT EXISTS idx_apps_category ON apps(category, published);
        CREATE TABLE IF NOT EXISTS admins (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, admin_id INTEGER NOT NULL,
          csrf TEXT NOT NULL, expires_at INTEGER NOT NULL,
          FOREIGN KEY(admin_id) REFERENCES admins(id) ON DELETE CASCADE
        );
        """)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or f"app-{secrets.token_hex(3)}"


def row_app(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["tags"] = json.loads(item.get("tags") or "[]")
    item["featured"] = bool(item["featured"])
    item["published"] = bool(item["published"])
    return item


def seed() -> None:
    seed_path = ROOT / "apps.json"
    if not seed_path.exists():
        return
    with db() as conn:
        if conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0]:
            return
        now = datetime.now(timezone.utc).isoformat()
        for item in json.loads(seed_path.read_text(encoding="utf-8")):
            slug = slugify(item["name"])
            base, suffix = slug, 2
            while conn.execute("SELECT 1 FROM apps WHERE slug=?", (slug,)).fetchone():
                slug, suffix = f"{base}-{suffix}", suffix + 1
            conn.execute("""INSERT INTO apps
              (name,name_ar,slug,category,category_ar,description,description_ar,
               platform,rating,price,url,image,added_date,tags,featured,published,created_at,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (item["name"], item["name_ar"], slug, item["category"], item["category_ar"],
               item["description"], item["description_ar"], item["platform"], item["rating"],
               item["price"], item["url"], item.get("image", ""), item["added_date"],
               json.dumps(item.get("tags", []), ensure_ascii=False), 0, 1, now, now))


def ensure_admin() -> None:
    username, password = os.getenv("APPVAULT_ADMIN_USER"), os.getenv("APPVAULT_ADMIN_PASSWORD")
    if not username or not password:
        return
    with db() as conn:
        row = conn.execute("SELECT id FROM admins WHERE username=?", (username,)).fetchone()
        if row:
            conn.execute("UPDATE admins SET password_hash=? WHERE id=?", (password_hash(password), row["id"]))
        else:
            conn.execute("INSERT INTO admins(username,password_hash,created_at) VALUES(?,?,?)",
                         (username, password_hash(password), datetime.now(timezone.utc).isoformat()))


def response(start, body=b"", status=200, content_type="application/json; charset=utf-8", headers=None):
    if not isinstance(body, bytes):
        body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    base = [("Content-Type", content_type), ("Content-Length", str(len(body))),
            ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "strict-origin-when-cross-origin"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()")]
    start(f"{status} {HTTPStatus(status).phrase}", base + (headers or []))
    return [body]


def head_response(start, body=b"", status=200, content_type="application/json; charset=utf-8", headers=None):
    """Return GET-equivalent headers without a response body."""
    if not isinstance(body, bytes):
        body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    base = [("Content-Type", content_type), ("Content-Length", str(len(body))),
            ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "strict-origin-when-cross-origin"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()")]
    start(f"{status} {HTTPStatus(status).phrase}", base + (headers or []))
    return [b""]


def read_json(environ) -> dict:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    if length > MAX_BODY:
        raise ValueError("الطلب كبير جدًا")
    data = json.loads(environ["wsgi.input"].read(length) or b"{}")
    if not isinstance(data, dict):
        raise ValueError("البيانات غير صالحة")
    return data


def session(environ):
    cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    token = cookie.get("appvault_session")
    if not token:
        return None
    digest = hashlib.sha256(token.value.encode()).hexdigest()
    with db() as conn:
        row = conn.execute("""SELECT sessions.*, admins.username FROM sessions
          JOIN admins ON admins.id=sessions.admin_id
          WHERE token_hash=? AND expires_at>?""", (digest, int(time.time()))).fetchone()
    return dict(row) if row else None


def require_admin(environ, csrf=False):
    current = session(environ)
    if not current:
        raise PermissionError("يلزم تسجيل الدخول")
    if csrf and not hmac.compare_digest(environ.get("HTTP_X_CSRF_TOKEN", ""), current["csrf"]):
        raise PermissionError("رمز الحماية غير صالح")
    return current


def validate_app(data: dict) -> dict:
    text_fields = ("name", "name_ar", "category_ar", "description", "description_ar", "url")
    for key in text_fields:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"الحقل {key} مطلوب")
        data[key] = data[key].strip()
    if data.get("category") not in ALLOWED_CATEGORIES:
        raise ValueError("التصنيف غير صالح")
    if data.get("platform") not in ALLOWED_PLATFORMS:
        raise ValueError("المنصة غير صالحة")
    if data.get("price") not in ALLOWED_PRICES:
        raise ValueError("السعر غير صالح")
    parsed = urlparse(data["url"])
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("الرابط غير صالح")
    data["rating"] = float(data.get("rating", 0))
    if not 0 <= data["rating"] <= 5:
        raise ValueError("التقييم يجب أن يكون بين 0 و5")
    try:
        datetime.strptime(data.get("added_date", ""), "%Y-%m-%d")
    except ValueError:
        raise ValueError("التاريخ يجب أن يكون YYYY-MM-DD")
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [tag.strip().lstrip("#") for tag in tags.split(",") if tag.strip()]
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("الوسوم غير صالحة")
    data["tags"] = tags[:12]
    data["image"] = str(data.get("image", "")).strip()
    data["featured"] = int(bool(data.get("featured", False)))
    data["published"] = int(bool(data.get("published", True)))
    data["slug"] = slugify(str(data.get("slug") or data["name"]))
    return data


def api(environ, start, path, method):
    if path == "/api/meta" and method == "GET":
        with db() as conn:
            stats = conn.execute("""SELECT COUNT(*) total, COUNT(DISTINCT category) categories,
                MAX(added_date) latest, SUM(clicks) clicks FROM apps WHERE published=1""").fetchone()
            cats = conn.execute("""SELECT category,category_ar,COUNT(*) count FROM apps
                WHERE published=1 GROUP BY category,category_ar ORDER BY count DESC""").fetchall()
        return response(start, {"stats": dict(stats), "categories": [dict(x) for x in cats]})

    if path == "/api/apps" and method == "GET":
        query = parse_qs(environ.get("QUERY_STRING", ""))
        where, params = ["published=1"], []
        if query.get("category", ["all"])[0] in ALLOWED_CATEGORIES:
            where.append("category=?"); params.append(query["category"][0])
        if query.get("platform", ["all"])[0] in ALLOWED_PLATFORMS:
            where.append("platform=?"); params.append(query["platform"][0])
        q = query.get("q", [""])[0].strip()[:100]
        if q:
            where.append("(name LIKE ? OR name_ar LIKE ? OR description_ar LIKE ? OR tags LIKE ?)")
            params.extend([f"%{q}%"] * 4)
        sort = {"rating": "rating DESC", "name": "name COLLATE NOCASE",
                "popular": "clicks DESC, views DESC"}.get(query.get("sort", ["newest"])[0],
                                                         "featured DESC, added_date DESC, id DESC")
        with db() as conn:
            rows = conn.execute(f"SELECT * FROM apps WHERE {' AND '.join(where)} ORDER BY {sort} LIMIT 250", params).fetchall()
        return response(start, {"apps": [row_app(x) for x in rows], "count": len(rows)})

    match = re.fullmatch(r"/api/apps/([a-z0-9-]+)", path)
    if match and method == "GET":
        with db() as conn:
            row = conn.execute("SELECT * FROM apps WHERE slug=? AND published=1", (match.group(1),)).fetchone()
            if not row:
                return response(start, {"error": "التطبيق غير موجود"}, 404)
            conn.execute("UPDATE apps SET views=views+1 WHERE id=?", (row["id"],))
        return response(start, {"app": row_app(row)})

    match = re.fullmatch(r"/api/apps/(\d+)/click", path)
    if match and method == "POST":
        with db() as conn:
            conn.execute("UPDATE apps SET clicks=clicks+1 WHERE id=? AND published=1", (match.group(1),))
        return response(start, {"ok": True})

    if path == "/api/admin/login" and method == "POST":
        data = read_json(environ)
        with db() as conn:
            admin = conn.execute("SELECT * FROM admins WHERE username=?", (data.get("username", ""),)).fetchone()
            if not admin or not password_ok(str(data.get("password", "")), admin["password_hash"]):
                time.sleep(0.5)
                return response(start, {"error": "بيانات الدخول غير صحيحة"}, 401)
            token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(24)
            conn.execute("DELETE FROM sessions WHERE expires_at<?", (int(time.time()),))
            conn.execute("INSERT INTO sessions VALUES(?,?,?,?)",
                         (hashlib.sha256(token.encode()).hexdigest(), admin["id"], csrf, int(time.time()) + SESSION_TTL))
        cookie = f"appvault_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}"
        if environ.get("wsgi.url_scheme") == "https":
            cookie += "; Secure"
        return response(start, {"ok": True, "csrf": csrf, "username": admin["username"]},
                        headers=[("Set-Cookie", cookie)])

    if path == "/api/admin/session" and method == "GET":
        current = session(environ)
        return response(start, {"authenticated": bool(current), "username": current["username"] if current else None,
                                "csrf": current["csrf"] if current else None})

    if path == "/api/admin/logout" and method == "POST":
        current = require_admin(environ, True)
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (current["token_hash"],))
        return response(start, {"ok": True}, headers=[("Set-Cookie", "appvault_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")])

    if path == "/api/admin/apps" and method == "GET":
        require_admin(environ)
        with db() as conn:
            rows = conn.execute("SELECT * FROM apps ORDER BY updated_at DESC").fetchall()
        return response(start, {"apps": [row_app(x) for x in rows]})

    if path == "/api/admin/apps" and method == "POST":
        require_admin(environ, True); data = validate_app(read_json(environ))
        now = datetime.now(timezone.utc).isoformat()
        try:
            with db() as conn:
                cur = conn.execute("""INSERT INTO apps(name,name_ar,slug,category,category_ar,description,
                  description_ar,platform,rating,price,url,image,added_date,tags,featured,published,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (data["name"],data["name_ar"],data["slug"],data["category"],data["category_ar"],
                   data["description"],data["description_ar"],data["platform"],data["rating"],data["price"],
                   data["url"],data["image"],data["added_date"],json.dumps(data["tags"],ensure_ascii=False),
                   data["featured"],data["published"],now,now))
            return response(start, {"ok": True, "id": cur.lastrowid}, 201)
        except sqlite3.IntegrityError:
            return response(start, {"error": "الرابط المختصر مستخدم"}, 409)

    match = re.fullmatch(r"/api/admin/apps/(\d+)", path)
    if match and method in {"PUT", "DELETE"}:
        require_admin(environ, True); app_id = int(match.group(1))
        with db() as conn:
            if method == "DELETE":
                conn.execute("DELETE FROM apps WHERE id=?", (app_id,))
                return response(start, {"ok": True})
            data = validate_app(read_json(environ)); now = datetime.now(timezone.utc).isoformat()
            try:
                conn.execute("""UPDATE apps SET name=?,name_ar=?,slug=?,category=?,category_ar=?,description=?,
                  description_ar=?,platform=?,rating=?,price=?,url=?,image=?,added_date=?,tags=?,featured=?,
                  published=?,updated_at=? WHERE id=?""",
                  (data["name"],data["name_ar"],data["slug"],data["category"],data["category_ar"],
                   data["description"],data["description_ar"],data["platform"],data["rating"],data["price"],
                   data["url"],data["image"],data["added_date"],json.dumps(data["tags"],ensure_ascii=False),
                   data["featured"],data["published"],now,app_id))
            except sqlite3.IntegrityError:
                return response(start, {"error": "الرابط المختصر مستخدم"}, 409)
        return response(start, {"ok": True})

    return response(start, {"error": "المسار غير موجود"}, 404)


def app(environ, start):
    path, method = unquote(environ.get("PATH_INFO", "/")), environ["REQUEST_METHOD"]
    try:
        if path.startswith("/api/"):
            return api(environ, start, path.rstrip("/") or "/", method)
        if method not in {"GET", "HEAD"}:
            return response(start, {"error": "الطريقة غير مدعومة"}, 405)
        relative = "index.html" if path == "/" else ("admin.html" if path.rstrip("/") == "/admin" else path.lstrip("/"))
        target = (PUBLIC / relative).resolve()
        if PUBLIC not in target.parents or not target.is_file():
            target = PUBLIC / ("admin.html" if path.startswith("/admin") else "index.html")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        cache = "public, max-age=86400" if target.suffix in {".css", ".js", ".png", ".svg"} else "no-cache"
        payload = target.read_bytes()
        if method == "HEAD":
            return head_response(start, payload, 200, content_type, [("Cache-Control", cache)])
        return response(start, payload, 200, content_type, [("Cache-Control", cache)])
    except PermissionError as exc:
        return response(start, {"error": str(exc)}, 401)
    except (ValueError, json.JSONDecodeError) as exc:
        return response(start, {"error": str(exc)}, 400)
    except Exception:
        return response(start, {"error": "حدث خطأ داخلي"}, 500)


class ThreadingServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


if __name__ == "__main__":
    init_db(); seed(); ensure_admin()
    print(f"AppVault listening on http://{HOST}:{PORT}")
    with make_server(HOST, PORT, app, server_class=ThreadingServer) as server:
        server.serve_forever()
