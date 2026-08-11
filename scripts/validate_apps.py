#!/usr/bin/env python3
"""Validate AppVault's apps.json without third-party dependencies."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

REQUIRED = {
    "id", "name", "name_ar", "category", "category_ar", "description",
    "description_ar", "platform", "rating", "price", "url", "image",
    "added_date", "tags",
}
PLATFORMS = {"android", "ios", "both"}
PRICES = {"free", "freemium", "paid"}
CATEGORIES = {"ai", "productivity", "tools", "music", "weather", "social"}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        apps = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Cannot read valid JSON: {exc}"]
    if not isinstance(apps, list):
        return ["Root value must be an array."]

    seen_ids: set[int] = set()
    seen_urls: set[str] = set()
    for index, app in enumerate(apps):
        label = f"Entry {index + 1}"
        if not isinstance(app, dict):
            errors.append(f"{label}: must be an object.")
            continue
        missing = REQUIRED - app.keys()
        if missing:
            errors.append(f"{label}: missing {', '.join(sorted(missing))}.")
        app_id = app.get("id")
        if not isinstance(app_id, int) or isinstance(app_id, bool) or app_id < 1:
            errors.append(f"{label}: id must be a positive integer.")
        elif app_id in seen_ids:
            errors.append(f"{label}: duplicate id {app_id}.")
        seen_ids.add(app_id)
        for key in ("name", "name_ar", "description", "description_ar", "category_ar"):
            if not isinstance(app.get(key), str) or not app.get(key, "").strip():
                errors.append(f"{label}: {key} must be non-empty text.")
        if app.get("category") not in CATEGORIES:
            errors.append(f"{label}: invalid category {app.get('category')!r}.")
        if app.get("platform") not in PLATFORMS:
            errors.append(f"{label}: invalid platform {app.get('platform')!r}.")
        if app.get("price") not in PRICES:
            errors.append(f"{label}: invalid price {app.get('price')!r}.")
        rating = app.get("rating")
        if not isinstance(rating, (int, float)) or isinstance(rating, bool) or not 0 <= rating <= 5:
            errors.append(f"{label}: rating must be between 0 and 5.")
        url = app.get("url", "")
        parsed = urlparse(url) if isinstance(url, str) else None
        if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{label}: url must be an HTTP(S) URL.")
        elif url in seen_urls:
            errors.append(f"{label}: duplicate url {url}.")
        seen_urls.add(url)
        image = app.get("image")
        if image:
            parsed_image = urlparse(image) if isinstance(image, str) else None
            if not parsed_image or parsed_image.scheme != "https" or not parsed_image.netloc:
                errors.append(f"{label}: image must be empty or an HTTPS URL.")
        try:
            date.fromisoformat(app.get("added_date", ""))
        except (TypeError, ValueError):
            errors.append(f"{label}: added_date must use YYYY-MM-DD.")
        tags = app.get("tags")
        if not isinstance(tags, list) or not tags or not all(isinstance(tag, str) and tag.strip() for tag in tags):
            errors.append(f"{label}: tags must be a non-empty list of text values.")
    return errors


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "apps.json")
    problems = validate(target)
    if problems:
        print("\n".join(f"ERROR: {problem}" for problem in problems), file=sys.stderr)
        raise SystemExit(1)
    print(f"Validated {len(json.loads(target.read_text(encoding='utf-8')))} apps in {target}.")
