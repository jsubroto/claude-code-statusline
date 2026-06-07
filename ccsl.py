#!/usr/bin/env python3

import curses
import json
import shutil
import unicodedata
from collections import namedtuple
from pathlib import Path


def _cols(s):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _bar(sample, bf, be):
    try:
        pct = int(sample.split("(")[1].rstrip("%)"))
    except (IndexError, ValueError):
        pct = 0
    return bf * (pct // 10) + be * (10 - pct // 10)


CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
STATUSLINE_SCRIPT = Path.home() / ".claude" / "statusline.py"


_SAMPLE = {
    "cwd": "/current/working/directory",
    "model": {"display_name": "Opus"},
    "cost": {"total_cost_usd": 0.01234, "total_duration_ms": 45000},
    "context_window": {
        "context_window_size": 200000,
        "current_usage": {
            "input_tokens": 80000,
            "output_tokens": 15000,
            "cache_creation_input_tokens": 25000,
            "cache_read_input_tokens": 10000,
        },
    },
    "worktree": {"original_branch": "main"},
}


_used = sum(_SAMPLE["context_window"]["current_usage"].values())
_size = _SAMPLE["context_window"]["context_window_size"]
_pct = round(_used / _size * 100)
_ctx = f"{round(_used / 100) / 10}k/{_size // 1000}k tokens ({_pct}%)"
_dur = str(int(_SAMPLE["cost"]["total_duration_ms"] / 60000))

Field = namedtuple("Field", ["key", "icon", "label", "sample"])
FIELDS = [
    Field("model", "🤖", "Model name", _SAMPLE["model"]["display_name"]),
    Field("dir", "📁", "Directory", Path(_SAMPLE["cwd"]).name),
    Field("context", "📊", "Context", _ctx),
    Field("cost", "💰", "Cost", str(_SAMPLE["cost"]["total_cost_usd"])),
    Field("git", "🌿", "Git branch", _SAMPLE["worktree"]["original_branch"]),
    Field("duration", "⏳", "Session duration", _dur),
    Field("session", "🔖", "Session name", "improve statusline code"),
]

Theme = namedtuple("Theme", ["chars", "ansi", "accent_pair"])
THEMES = {
    "default": Theme(("█", "░"), "\033[96m", 1),
    "minimal": Theme(("▓", "░"), "\033[97m", 2),
    "neon": Theme(("█", "▒"), "\033[95m", 6),
    "pastel": Theme(("●", "○"), "\033[93m", 4),
    "mono": Theme(("#", "-"), "", 2),
}


def render_preview(enabled_keys, theme):
    bf, be = THEMES[theme].chars
    parts = []
    for key, icon, _, sample in FIELDS:
        if key not in enabled_keys:
            continue
        match key:
            case "model":
                parts.append(f"[{sample}]")
            case "context":
                parts.append(f"{_bar(sample, bf, be)} {sample}")
            case "cost":
                parts.append(f"{icon} ${float(sample):.2f}")
            case "duration":
                parts.append(f"{icon} {sample}m")
            case _:
                parts.append(f"{icon} {sample}")
    return "  │  ".join(parts) if parts else "(nothing selected)"


def _enabled_keys(widget_enabled):
    return [f.key for f, on in zip(FIELDS, widget_enabled) if on]


def _safe_addstr(stdscr, *args):
    try:
        stdscr.addstr(*args)
    except curses.error:
        pass


def _draw_section(stdscr, row, title, items, focused_idx, focus_key, focus):
    _safe_addstr(stdscr, row, 2, title, curses.color_pair(4) | curses.A_BOLD)
    for i, (label, selected) in enumerate(items):
        attr = (
            curses.color_pair(3)
            if (focus == focus_key and i == focused_idx)
            else curses.color_pair(2)
        )
        _safe_addstr(
            stdscr, row + 1 + i, 2, f"  {'◉' if selected else '○'} {label}", attr
        )
    return row + 1 + len(items) + 1


def _draw_preview(stdscr, row, widget_enabled, theme_cursor):
    _safe_addstr(stdscr, row, 2, "PREVIEW", curses.color_pair(4) | curses.A_BOLD)
    enabled_keys = _enabled_keys(widget_enabled)
    theme_name = list(THEMES)[theme_cursor]
    bf, be = THEMES[theme_name].chars
    sep_cp = curses.color_pair(THEMES[theme_name].accent_pair)
    mono = theme_name == "mono"
    x, first = 4, True
    for key, icon, _, sample in FIELDS:
        if key not in enabled_keys:
            continue
        if not first:
            _safe_addstr(stdscr, row + 1, x, "  │  ", sep_cp)
            x += _cols("  │  ")
        first = False
        match key:
            case "model":
                seg, cp = (
                    f"[{sample}]",
                    curses.color_pair(2) if mono else curses.color_pair(1),
                )
            case "context":
                seg, cp = (
                    f"{_bar(sample, bf, be)} {sample}",
                    curses.color_pair(2) if mono else curses.color_pair(5),
                )
            case "cost":
                seg, cp = (
                    f"{icon} ${float(sample):.2f}",
                    curses.color_pair(2) if mono else curses.color_pair(4),
                )
            case "duration":
                seg, cp = f"{icon} {sample}m", curses.color_pair(2)
            case _:
                seg, cp = f"{icon} {sample}", curses.color_pair(2)
        _safe_addstr(stdscr, row + 1, x, seg, cp)
        x += _cols(seg)


def draw(stdscr, widget_enabled, widget_cursor, theme_cursor, focus):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    _safe_addstr(
        stdscr, 0, 2, "Claude Code Status Line", curses.color_pair(1) | curses.A_BOLD
    )
    _safe_addstr(stdscr, 1, 2, "─" * (w - 4), curses.color_pair(1))

    row = 3
    _safe_addstr(
        stdscr,
        row,
        12,
        "Space: toggle  ↑↓: navigate  Tab: switch section",
        curses.color_pair(2),
    )
    field_items = [
        (f"{icon}  {label}", widget_enabled[i])
        for i, (_, icon, label, _) in enumerate(FIELDS)
    ]
    row = _draw_section(stdscr, row, "FIELDS", field_items, widget_cursor, "fields", focus)

    theme_items = [(name, i == theme_cursor) for i, name in enumerate(THEMES)]
    row = _draw_section(stdscr, row, "THEME", theme_items, theme_cursor, "themes", focus)

    _draw_preview(stdscr, row, widget_enabled, theme_cursor)
    _safe_addstr(
        stdscr, h - 1, 2, " Enter: Install   q: Quit ", curses.color_pair(3)
    )
    stdscr.refresh()


def run_ui(stdscr):
    curses.start_color()
    curses.use_default_colors()
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_WHITE, -1)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)
    curses.init_pair(5, curses.COLOR_GREEN, -1)
    curses.init_pair(6, curses.COLOR_MAGENTA, -1)

    widget_enabled = [True] * len(FIELDS)
    widget_cursor = theme_cursor = 0
    focus = "fields"

    while True:
        draw(stdscr, widget_enabled, widget_cursor, theme_cursor, focus)
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            return None
        elif key == ord("\t"):
            focus = "themes" if focus == "fields" else "fields"
        elif key in (curses.KEY_UP, curses.KEY_DOWN):
            delta = -1 if key == curses.KEY_UP else 1
            if focus == "fields":
                widget_cursor = max(0, min(len(FIELDS) - 1, widget_cursor + delta))
            else:
                theme_cursor = max(0, min(len(THEMES) - 1, theme_cursor + delta))
        elif key == ord(" ") and focus == "fields":
            widget_enabled[widget_cursor] = not widget_enabled[widget_cursor]
        elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
            if enabled_keys := _enabled_keys(widget_enabled):
                return enabled_keys, list(THEMES)[theme_cursor]


def generate_script(enabled, theme_name):
    bf, be = THEMES[theme_name].chars
    acc = THEMES[theme_name].ansi
    rst = "\033[0m" if acc else ""
    sep = f"{acc}  │  {rst}" if acc else "  │  "

    git_block = ""
    if "git" in enabled:
        git_block = """try:
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True, stderr=subprocess.DEVNULL).strip()
except Exception:
    branch = ""
"""

    session_block = ""
    if "session" in enabled:
        session_block = """session = (data.get("session_name") or "").strip()
if not session:
    try:
        with open(data.get("transcript_path") or "") as fh:
            for line in fh:
                o = json.loads(line)
                if o.get("type") != "user" or o.get("isSidechain") or o.get("isMeta"):
                    continue
                c = (o.get("message") or {}).get("content")
                if isinstance(c, list):
                    c = next((b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"), "")
                if isinstance(c, str) and c.strip():
                    session = " ".join(c.split())
                    break
    except Exception:
        session = ""
if len(session) > 40:
    session = session[:39].rstrip() + "…"
"""

    imports = (
        "import json, os, sys"
        if "git" not in enabled
        else "import json, os, subprocess, sys"
    )

    lines = []
    for key, icon, _, _ in FIELDS:
        if key not in enabled:
            continue
        if key == "model":
            if acc:
                lines.append('parts.append(f"\\033[96m[{model}]\\033[0m")')
            else:
                lines.append('parts.append(f"[{model}]")')
        elif key == "context":
            bar_color = '"\\033[92m" + ' if acc else ""
            bar_reset = ' + "\\033[0m"' if acc else ""
            lines.append(
                f'bar = {bar_color}"{bf}" * (pct // 10) + "{be}" * (10 - pct // 10){bar_reset}'
            )
            lines.append('parts.append(f"{bar} {used_k}k/{size_k}k ({pct}%)")')
        elif key == "dir":
            lines.append(f'parts.append(f"{icon} {{dirname}}" if dirname else None)')
        elif key == "cost":
            if acc:
                lines.append(f'parts.append(f"\\033[93m{icon} ${{cost:.2f}}\\033[0m")')
            else:
                lines.append(f'parts.append(f"{icon} ${{cost:.2f}}")')
        elif key == "session":
            lines.append(f'parts.append(f"{icon} {{session}}" if session else None)')
        elif key == "git":
            lines.append(f'parts.append(f"{icon} {{branch}}" if branch else None)')
        elif key == "duration":
            lines.append(f'parts.append(f"{icon} {{dur_m}}m")')

    return f'''#!/usr/bin/env python3
{imports}

data   = json.load(sys.stdin)
cu     = (data.get("context_window") or {{}}).get("current_usage") or {{}}
used   = sum(cu.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
size   = (data.get("context_window") or {{}}).get("context_window_size", 200000) or 200000
pct    = round(used / size * 100)
used_k = round(used / 100) / 10
size_k = size // 1000
model  = (data.get("model") or {{}}).get("display_name", "?")
cost   = (data.get("cost") or {{}}).get("total_cost_usd", 0) or 0
dur_m  = int(((data.get("cost") or {{}}).get("total_duration_ms", 0) or 0) / 60000)
dirname = os.path.basename(data.get("cwd", "") or "")
{git_block}{session_block}
parts = []
{chr(10).join(lines)}
print("{sep}".join(p for p in parts if p))
'''


def update_settings():
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    try:
        data = json.loads(CLAUDE_SETTINGS.read_text())
        shutil.copy2(CLAUDE_SETTINGS, CLAUDE_SETTINGS.with_suffix(".json.bak"))
    except (OSError, json.JSONDecodeError):
        pass
    data["statusLine"] = {"type": "command", "command": str(STATUSLINE_SCRIPT)}
    CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2))


def main():
    result = curses.wrapper(run_ui)
    if result is None:
        print("\nAborted.\n")
        return

    enabled, theme = result
    STATUSLINE_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    STATUSLINE_SCRIPT.write_text(generate_script(enabled, theme))
    STATUSLINE_SCRIPT.chmod(0o755)
    update_settings()

    print(f"\n  ✔  Script → {STATUSLINE_SCRIPT}")
    print("  ✔  settings.json updated  (backup → settings.json.bak)")
    print(f"\n  Preview:  {render_preview(enabled, theme)}")
    print("\n  Restart Claude Code to see your statusline.\n")


if __name__ == "__main__":
    main()
