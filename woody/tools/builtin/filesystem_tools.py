"""
Filesystem Tools — MCP tool server for file operations.

All write/delete operations require the user-confirm tier.
Read-only operations (read_file, list_directory, search_files, get_file_info)
are auto-allowed.
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path

# Ordered list for deterministic schema registration
TOOLS = [
    "read_file",
    "list_directory",
    "write_file",
    "delete_file",
    "copy_file",
    "move_file",
    "search_files",
    "get_file_info",
]

# Maximum file size to read (10 MB)
MAX_READ_BYTES = 10 * 1024 * 1024


def read_file(path: str, encoding: str = "utf-8") -> dict:
    """Read the text content of a file.

    Args:
        path: Absolute or relative path to the file.
        encoding: Text encoding to use when reading (default utf-8).
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not p.is_file():
            return {"success": False, "error": f"Path is a directory, not a file: {path}"}
        if p.stat().st_size > MAX_READ_BYTES:
            return {"success": False, "error": "File too large to read (> 10 MB)."}
        content = p.read_text(encoding=encoding, errors="replace")
        return {"success": True, "content": content, "size_bytes": p.stat().st_size}
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_directory(path: str = ".", pattern: str = "*") -> dict:
    """List files and folders inside a directory.

    Args:
        path: Path to the directory to list (default current directory).
        pattern: Glob pattern to filter entries (default '*' — all files).
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.is_dir():
            return {"success": False, "error": f"Not a directory: {path}"}
        entries = []
        for item in sorted(p.glob(pattern)):
            try:
                entries.append(
                    {
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size_bytes": item.stat().st_size if item.is_file() else 0,
                    }
                )
            except (PermissionError, OSError):
                pass  # Skip inaccessible entries
        return {"success": True, "path": str(p), "entries": entries[:200]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, encoding: str = "utf-8") -> dict:
    """Write text content to a file, creating parent directories as needed.

    Args:
        path: Path of the file to write.
        content: Text content to write to the file.
        encoding: Text encoding to use (default utf-8).
    """
    try:
        p = Path(path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return {
            "success": True,
            "path": str(p),
            "bytes_written": len(content.encode(encoding)),
        }
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_file(path: str) -> dict:
    """Permanently delete a file.

    Args:
        path: Path of the file to delete.
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if p.is_dir():
            return {"success": False, "error": "Path is a directory. Use a directory removal tool instead."}
        p.unlink()
        return {"success": True, "deleted": str(p)}
    except PermissionError:
        return {"success": False, "error": f"Permission denied: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def copy_file(source: str, destination: str) -> dict:
    """Copy a file to a new location, preserving metadata.

    Args:
        source: Path of the source file.
        destination: Destination path (file or directory).
    """
    try:
        import shutil

        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()
        if not src.exists():
            return {"success": False, "error": f"Source file not found: {source}"}
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return {"success": True, "source": str(src), "destination": str(dst)}
    except PermissionError as e:
        return {"success": False, "error": f"Permission denied: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_file(source: str, destination: str) -> dict:
    """Move or rename a file.

    Args:
        source: Path of the file to move.
        destination: New path or directory to move the file to.
    """
    try:
        import shutil

        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()
        if not src.exists():
            return {"success": False, "error": f"Source file not found: {source}"}
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"success": True, "source": str(src), "destination": str(dst)}
    except PermissionError as e:
        return {"success": False, "error": f"Permission denied: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(
    directory: str = ".",
    query: str = "",
    extension: str = "",
    max_results: int = 50,
) -> dict:
    """Search for files by name fragment and/or file extension.

    Combines query and extension filters: a file must match both when both are provided.

    Args:
        directory: Root directory to search in (default current directory).
        query: Substring to look for in the file name (case-insensitive).
        extension: File extension to filter by, e.g. 'py' or '.py'.
        max_results: Maximum number of results to return (default 50).
    """
    try:
        base = Path(directory).expanduser().resolve()
        if not base.is_dir():
            return {"success": False, "error": f"Not a directory: {directory}"}

        # Normalize extension
        if extension and not extension.startswith("."):
            extension = f".{extension}"
        ext_lower = extension.lower()
        query_lower = query.lower()

        results: list[dict] = []

        for p in base.rglob("*"):
            if len(results) >= max_results:
                break
            if not p.is_file():
                continue
            # Apply extension filter
            if ext_lower and p.suffix.lower() != ext_lower:
                continue
            # Apply name query filter
            if query_lower and query_lower not in p.name.lower():
                continue
            try:
                results.append(
                    {
                        "path": str(p),
                        "name": p.name,
                        "size_bytes": p.stat().st_size,
                    }
                )
            except (PermissionError, OSError):
                pass

        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_file_info(path: str) -> dict:
    """Get metadata about a file or directory.

    Args:
        path: Path to the file or directory to inspect.
    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Path not found: {path}"}
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
