#!/usr/local/bin/python3
"""Pin today's not-yet-familiar MaiMemo words in the bottom-right corner.

Uses the Open API for the studied list and MaiMemo's public vocabulary
endpoint for the official gloss. Scheduled at 10:05 by launchd, and exposed
in Raycast as「墨墨今日未记住」.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from AppKit import (
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSBitmapImageRep,
    NSMakeRect,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
    NSPasteboard,
    NSScreen,
    NSString,
)
from Foundation import NSMakeSize
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    CGWindowListCopyWindowInfo,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGHIDEventTap,
    kCGNullWindowID,
    kCGWindowListOptionOnScreenOnly,
)

OPEN_API = "https://open.maimemo.com/open/api/v1"
VOCAB_API = "https://api.maimemo.com/api/v1/vocabulary"
if not os.environ.get("SSL_CERT_FILE") and Path("/etc/ssl/cert.pem").is_file():
    os.environ["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"

ROOT = Path(__file__).resolve().parent
TOKEN_PATH = ROOT / ".token"
DB_CANDIDATES = (
    ROOT / "data" / "maimemo.v3.db",
    ROOT / "unpacked" / "assets" / "maimemo.v3.db",
)
IMAGE_PATH = ROOT / "review-pin.png"
CACHE_PATH = ROOT / "gloss-cache.json"
WORDS_PATH = ROOT / "today-words.json"
SCALE = 0.75

SKIP_RESPONSES = {"FAMILIAR"}


def notify(message: str) -> None:
    safe = message.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e", f'display notification "{safe}" with title "墨墨"'],
        check=False,
    )


def load_token() -> str:
    env = os.environ.get("MAIMEMO_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_PATH.is_file():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    return ""


def request_json(url: str, token: str | None, body: dict | None, retries: int = 4) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "momo-today-pin/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last_error: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                wait = int(exc.headers.get("Retry-After") or 2 * (attempt + 1))
                time.sleep(max(1, min(wait, 30)))
                last_error = exc
                continue
            raise SystemExit(f"HTTP {exc.code} {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise SystemExit(f"网络错误 {url}: {exc}") from exc
    raise SystemExit(f"请求失败: {last_error}")


def unwrap(payload: dict) -> dict:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def today_rows(token: str) -> list[dict]:
    items_resp = unwrap(
        request_json(
            OPEN_API + "/study/get_today_items",
            token,
            {"is_finished": True, "limit": 1000},
        )
    )
    items = [row for row in (items_resp.get("today_items") or []) if row.get("is_finished")]
    items.sort(key=lambda row: row.get("order", 0))
    kept = [row for row in items if row.get("first_response") not in SKIP_RESPONSES]
    WORDS_PATH.write_text(
        json.dumps({"count": len(items), "kept": len(kept), "today_items": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return kept


def vocabulary_db() -> Path:
    for path in DB_CANDIDATES:
        if path.is_file():
            return path
    raise SystemExit("找不到词库 data/maimemo.v3.db，请按 README 放好墨墨词库。")


def lookup_voc_id(spelling: str) -> str | None:
    import sqlite3

    con = sqlite3.connect(f"file:{vocabulary_db()}?mode=ro", uri=True)
    try:
        exact = con.execute("SELECT id FROM VOC_TB WHERE spelling = ?", (spelling,)).fetchone()
        if exact:
            return exact[0]
        rows = con.execute(
            "SELECT id FROM VOC_TB WHERE spelling = ? COLLATE NOCASE",
            (spelling,),
        ).fetchall()
        if rows:
            return rows[0][0]
        return None
    finally:
        con.close()


def official_gloss(voc_id: str) -> str:
    payload = request_json(f"{VOCAB_API}/{voc_id}", None, None)
    voc = unwrap(payload).get("voc") or {}
    interps = voc.get("interpretations") or []
    official = [item for item in interps if item.get("is_official") or "官方" in (item.get("tags") or [])]
    core = [item for item in official if "核心释义" in (item.get("tags") or [])]
    chosen = core or official or interps[:1]
    texts: list[str] = []
    for item in chosen:
        text = " ".join((item.get("interpretation") or "").split())
        if text and text not in texts:
            texts.append(text)
    return " ".join(texts)


def load_cache() -> dict[str, str]:
    if not CACHE_PATH.is_file():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def glosses_for(rows: list[dict]) -> list[dict]:
    vocabulary_db()
    cache = load_cache()
    changed = False
    result = []
    for row in rows:
        spelling = str(row.get("voc_spelling") or "").strip()
        if not spelling:
            continue
        voc_id = lookup_voc_id(spelling)
        gloss = cache.get(voc_id or "") if voc_id else ""
        if voc_id and not gloss:
            gloss = official_gloss(voc_id)
            if gloss:
                cache[voc_id] = gloss
                changed = True
            time.sleep(0.05)
        result.append({"spelling": spelling, "gloss": gloss or "（未取到释义）"})
    if changed:
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def measure(text: str, font, width: float | None = None):
    style = NSMutableParagraphStyle.alloc().init()
    style.setLineBreakMode_(0)
    attrs = {NSFontAttributeName: font, NSParagraphStyleAttributeName: style}
    value = NSString.stringWithString_(text)
    if width is None:
        return value.sizeWithAttributes_(attrs)
    return value.boundingRectWithSize_options_attributes_(NSMakeSize(width, 10000), 1, attrs).size


def render(rows: list[dict], scale: float) -> tuple[int, int]:
    word_font = NSFont.fontWithName_size_("Menlo", 15 * scale) or NSFont.monospacedSystemFontOfSize_weight_(15 * scale, 0)
    gloss_font = NSFont.fontWithName_size_("PingFangSC-Regular", 15 * scale) or NSFont.systemFontOfSize_(15 * scale)
    word_w = int(max(measure(row["spelling"], word_font).width for row in rows) + 6)
    gloss_w = int(340 * scale)
    pad_x, pad_y, gap = int(round(18 * scale)), int(round(16 * scale)), int(round(18 * scale))
    row_h_min, row_gap = int(round(28 * scale)), max(3, int(round(6 * scale)))
    heights = []
    for row in rows:
        height = measure(row["gloss"], gloss_font, gloss_w).height
        heights.append(max(row_h_min, int(height + 6)))
    width = pad_x + word_w + gap + gloss_w + pad_x
    height = pad_y + sum(heights) + row_gap * (len(rows) - 1) + pad_y
    image = NSImage.alloc().initWithSize_(NSMakeSize(width, height))
    image.lockFocus()
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.09, 0.09, 0.10, 0.96).set()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(0, 0, width, height), 10, 10).fill()
    word_color = NSColor.colorWithCalibratedWhite_alpha_(0.96, 1)
    gloss_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.78, 0.80, 0.76, 1)
    y_top = height - pad_y
    for row, row_h in zip(rows, heights):
        y_top -= row_h
        style = NSMutableParagraphStyle.alloc().init()
        NSString.stringWithString_(row["spelling"]).drawInRect_withAttributes_(
            NSMakeRect(pad_x, y_top, word_w, row_h),
            {NSFontAttributeName: word_font, NSForegroundColorAttributeName: word_color, NSParagraphStyleAttributeName: style},
        )
        NSString.stringWithString_(row["gloss"]).drawInRect_withAttributes_(
            NSMakeRect(pad_x + word_w + gap, y_top, gloss_w, row_h),
            {NSFontAttributeName: gloss_font, NSForegroundColorAttributeName: gloss_color, NSParagraphStyleAttributeName: style},
        )
        y_top -= row_gap
    image.unlockFocus()
    rep = NSBitmapImageRep.alloc().initWithData_(image.TIFFRepresentation())
    png = rep.representationUsingType_properties_(4, None)
    png.writeToFile_atomically_(str(IMAGE_PATH), True)
    return int(width), int(height)


def screen_corner() -> tuple[float, float]:
    screen = NSScreen.mainScreen()
    visible = screen.visibleFrame()
    primary_h = NSScreen.screens()[0].frame().size.height
    right = visible.origin.x + visible.size.width
    bottom = primary_h - visible.origin.y
    return right, bottom


def pixpin_windows() -> list[dict]:
    found = []
    for item in CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID):
        if (item.get("kCGWindowOwnerName") or "") != "PixPin":
            continue
        bounds = item.get("kCGWindowBounds") or {}
        width, height = int(bounds.get("Width", 0)), int(bounds.get("Height", 0))
        # Ignore PixPin's tiny helper windows. The card is hundreds of points tall.
        if width < 250 or height < 250:
            continue
        found.append(
            {
                "id": item.get("kCGWindowNumber"),
                "pid": item.get("kCGWindowOwnerPID"),
                "x": int(bounds.get("X", 0)),
                "y": int(bounds.get("Y", 0)),
                "w": width,
                "h": height,
            }
        )
    return found


def is_corner_pin(window: dict) -> bool:
    right, bottom = screen_corner()
    return abs(window["x"] + window["w"] - right) <= 80 and abs(window["y"] + window["h"] - bottom) <= 80


def pixpin_pids() -> list[int]:
    result = subprocess.run(["pgrep", "-x", "PixPin"], capture_output=True, text=True)
    return [int(pid) for pid in result.stdout.split() if pid.strip().isdigit()]


def quit_pixpin() -> None:
    """Quit every PixPin. A second copy never shows its pin while one is already running."""
    pids = pixpin_pids()
    if not pids:
        return
    for pid in pids:
        os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not pixpin_pids():
            return
        time.sleep(0.15)
    for pid in pixpin_pids():
        os.kill(pid, signal.SIGKILL)


def ensure_pixpin() -> None:
    pids = pixpin_pids()
    if len(pids) > 1:
        # A second copy cannot receive the paste hotkey.
        quit_pixpin()
        pids = []
    if not pids:
        subprocess.run(["open", "-a", "PixPin"], check=False)
        for _ in range(40):
            if pixpin_pids():
                time.sleep(1.2)
                return
            time.sleep(0.25)
        raise SystemExit("PixPin 没有启动")


def post_key(keycode: int, flags: int, pid: int | None = None) -> None:
    from Quartz import CGEventPostToPid

    for down in (True, False):
        event = CGEventCreateKeyboardEvent(None, keycode, down)
        CGEventSetFlags(event, flags)
        if pid is None:
            CGEventPost(kCGHIDEventTap, event)
        else:
            CGEventPostToPid(pid, event)
        time.sleep(0.06)


def post_pin_hotkey() -> None:
    post_key(19, kCGEventFlagMaskControl)


def move_to_corner(window: dict) -> None:
    right, bottom = screen_corner()
    origin_x = int(round(right - window["w"] + 8))
    origin_y = int(round(bottom - window["h"] + 7))
    subprocess.run(
        [
            "osascript",
            "-e",
            f'tell application "System Events" to tell process "PixPin" to set position of window 1 to {{{origin_x}, {origin_y}}}',
        ],
        check=False,
    )


def pin_image() -> None:
    image = NSImage.alloc().initWithContentsOfFile_(str(IMAGE_PATH))
    if image is None:
        raise SystemExit("贴图没有生成")
    ensure_pixpin()
    for window in pixpin_windows():
        post_key(13, kCGEventFlagMaskCommand, int(window["pid"]))
        time.sleep(0.2)
    board = NSPasteboard.generalPasteboard()
    board.clearContents()
    if not board.writeObjects_([image]):
        raise SystemExit("无法把贴图放进剪贴板")
    before = {window["id"] for window in pixpin_windows()}
    post_pin_hotkey()
    created = None
    for _ in range(20):
        time.sleep(0.25)
        fresh = [window for window in pixpin_windows() if window["id"] not in before]
        if fresh:
            created = fresh[-1]
            break
    if created is None:
        raise SystemExit("快捷键没有贴出来，PixPin 没收到")
    time.sleep(0.4)
    created = next((window for window in pixpin_windows() if window["id"] == created["id"]), None)
    if created is None:
        raise SystemExit("贴图闪了一下就关掉了")
    move_to_corner(created)


def main() -> None:
    token = load_token()
    if not token:
        raise SystemExit("缺少 token，请写入 .token 或设置 MAIMEMO_TOKEN")
    rows = today_rows(token)
    if not rows:
        windows = pixpin_windows()
        if windows and all(is_corner_pin(window) for window in windows):
            quit_pixpin()
        print("今天没有未记住的词")
        return
    cards = glosses_for(rows)
    width, height = render(cards, SCALE)
    _right, bottom = screen_corner()
    if height > bottom * 0.92:
        render(cards, SCALE * (bottom * 0.92) / height)
    pin_image()
    print(f"已贴上 {len(cards)} 个词")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        message = str(exc)
        if message:
            print(message, file=sys.stderr)
            notify(message)
        raise SystemExit(1) from exc
