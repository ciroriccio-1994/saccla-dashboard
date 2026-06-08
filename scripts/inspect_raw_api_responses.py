from __future__ import annotations

from pathlib import Path


RAW_DIR = Path("outputs/raw_api_responses")
ERROR_WORDS = ["login", "password", "session", "expired", "unauthorized", "forbidden", "errore", "error"]


def main() -> None:
    if not RAW_DIR.exists():
        raise SystemExit(f"Missing directory: {RAW_DIR}")

    files = sorted(path for path in RAW_DIR.iterdir() if path.is_file())
    if not files:
        print(f"No raw API responses found in {RAW_DIR}")
        return

    for path in files:
        text = read_text(path)
        preview = text[:500].replace("\r", " ").replace("\n", " ")
        lowered = text.lower()
        stripped = text.lstrip()
        matches = [word for word in ERROR_WORDS if word in lowered]

        print("=" * 100)
        print(f"filename: {path.name}")
        print(f"file_size: {path.stat().st_size} bytes")
        print(f"looks_like_xml: {looks_like_xml(stripped)}")
        print(f"looks_like_json: {looks_like_json(stripped)}")
        print(f"looks_like_html: {looks_like_html(stripped)}")
        print(f"contains_login_or_error_words: {bool(matches)}")
        print(f"matched_words: {', '.join(matches) if matches else ''}")
        print(f"first_500_chars: {preview}")


def read_text(path: Path) -> str:
    for encoding in ["utf-8", "latin-1"]:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def looks_like_xml(text: str) -> bool:
    return text.startswith("<?xml") or (text.startswith("<") and not looks_like_html(text))


def looks_like_json(text: str) -> bool:
    return text.startswith("{") or text.startswith("[")


def looks_like_html(text: str) -> bool:
    lowered = text[:1000].lower()
    return "<html" in lowered or "<!doctype html" in lowered


if __name__ == "__main__":
    main()
