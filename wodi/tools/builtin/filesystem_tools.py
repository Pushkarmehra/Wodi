"""
Filesystem Tools — MCP tool server for file operations.
[Phase 3 — Stub with permission-gated interface]

All write/delete operations require user-confirm tier.
Read-only operations (read_file, list_dir) are auto-allowed.
"""
from __future__ import annotations

import os
from pathlib import Path

TOOLS = {
    "read_file",
    "list_directory",
    "write_file",
    "delete_file",
    "copy_file",
    "move_file",
    "search_files",
    "get_file_info",
}

# Maximum file size to read (10 MB)
MAX_READ_BYTES = 10 * 1024 * 1024


def read_file(path: str, encoding: str = "utf-8") -> dict:
    """Read a file's text content. [read_only tier]"""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if p.stat().st_size > MAX_READ_BYTES:
            return {"success": False, "error": "File too large to read (>10MB)"}
        return {"success": True, "content": p.read_text(encoding=encoding, errors="replace"),
                "size_bytes": p.stat().st_size}
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_directory(path: str = ".", pattern: str = "*") -> dict:
    """List files in a directory. [read_only tier]"""
    try:
        p = Path(path).expanduser().resolve()
        if not p.is_dir():
            return {"success": False, "error": f"Not a directory: {path}"}
        entries = []
        for item in sorted(p.glob(pattern)):
            entries.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size_bytes": item.stat().st_size if item.is_file() else 0,
            })
        return {"success": True, "path": str(p), "entries": entries[:200]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, encoding: str = "utf-8") -> dict:
    """Write content to a file. [user_confirm tier — staged as dry-run first]"""
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return {"success": True, "path": str(p), "bytes_written": len(content.encode(encoding))}
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_file(path: str) -> dict:
    """Delete a file. [user_confirm tier]"""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        p.unlink()
        return {"success": True, "deleted": str(p)}
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def copy_file(source: str, destination: str) -> dict:
    """Copy a file to a new location. [user_confirm tier]"""
    try:
        import shutil
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return {"success": True, "source": str(src), "destination": str(dst)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_file(source: str, destination: str) -> dict:
    """Move a file to a new location. [user_confirm tier]"""
    try:
        import shutil
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"success": True, "source": str(src), "destination": str(dst)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(directory: str = ".", query: str = "", extension: str = "") -> dict:
    """Search for files matching a pattern. [read_only tier]"""
    try:
        base = Path(directory).expanduser().resolve()
        pattern = f"**/*{query}*" if query else f"**/*{extension}"
        if extension and not extension.startswith("."):
            extension = f".{extension}"
        results = []
        for p in base.glob(pattern if query else f"**/*{extension}"):
            if len(results) >= 50:
                break
            results.append({"path": str(p), "name": p.name, "size_bytes": p.stat().st_size if p.is_file() else 0})
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_file_info(path: str) -> dict:
    """Get metadata about a file. [read_only tier]"""
    try:
        import datetime
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        stat = p.stat()
        return {
            "success": True,
            "path": str(p),
            "name": p.name,
            "size_bytes": stat.st_size,
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "extension": p.suffix,
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
