from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import os
import subprocess
import sys
import json
import tempfile
import shutil
from typing import Optional

mcp = FastMCP("lastversion")

GITHUB_API_TOKEN = os.environ.get("GITHUB_API_TOKEN", "")


def build_lastversion_env():
    """Build environment variables for lastversion subprocess calls."""
    env = os.environ.copy()
    if GITHUB_API_TOKEN:
        env["GITHUB_API_TOKEN"] = GITHUB_API_TOKEN
    return env


def run_lastversion(args: list, env: dict = None) -> dict:
    """Run lastversion command and return result."""
    if env is None:
        env = build_lastversion_env()
    
    cmd = [sys.executable, "-m", "lastversion"] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=60
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "Command timed out after 60 seconds",
            "returncode": -1
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }


@mcp.tool()
async def get_latest_version(
    repo: str,
    pre: bool = False,
    major: Optional[str] = None,
    having_asset: Optional[str] = None,
    source: Optional[str] = None
) -> dict:
    """Get the latest stable version of a project from GitHub, GitLab, PyPI, npm, or other supported sources.
    Use this when you need to know the current latest release version of any software project."""
    args = [repo]
    
    if pre:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    if having_asset:
        args.extend(["--having-asset", having_asset])
    if source:
        args.extend(["--source", source])
    
    result = run_lastversion(args)
    
    if result["returncode"] == 0 and result["stdout"]:
        return {
            "success": True,
            "repo": repo,
            "latest_version": result["stdout"],
            "pre_releases_included": pre
        }
    else:
        return {
            "success": False,
            "repo": repo,
            "error": result["stderr"] or "Could not determine latest version",
            "returncode": result["returncode"]
        }


@mcp.tool()
async def check_version(
    repo: str,
    version: str,
    pre: bool = False
) -> dict:
    """Check if a given version is the latest for a project. Returns a boolean-style result
    indicating whether the specified version is up to date."""
    # First get the latest version
    args = [repo]
    if pre:
        args.append("--pre")
    
    result = run_lastversion(args)
    
    if result["returncode"] != 0 or not result["stdout"]:
        return {
            "success": False,
            "repo": repo,
            "checked_version": version,
            "error": result["stderr"] or "Could not determine latest version",
            "returncode": result["returncode"]
        }
    
    latest_version = result["stdout"]
    
    # Compare versions using lastversion's version comparison
    # Use lastversion to compare: lastversion <version_a> -gt <version_b>
    cmp_args = [version, "-gt", latest_version]
    cmp_result = run_lastversion(cmp_args)
    
    is_newer = cmp_result["returncode"] == 0
    
    # Check equality
    eq_args = ["test", version, "--eq", latest_version] if False else None
    
    # Parse versions for simple string comparison
    from packaging.version import Version as PkgVersion
    try:
        v_checked = PkgVersion(version)
        v_latest = PkgVersion(latest_version)
        is_latest = v_checked >= v_latest
        is_up_to_date = v_checked == v_latest
        is_outdated = v_checked < v_latest
    except Exception:
        is_latest = version == latest_version
        is_up_to_date = version == latest_version
        is_outdated = version != latest_version
    
    return {
        "success": True,
        "repo": repo,
        "checked_version": version,
        "latest_version": latest_version,
        "is_up_to_date": is_up_to_date,
        "is_outdated": is_outdated,
        "is_newer_than_latest": is_newer
    }


@mcp.tool()
async def download_asset(
    repo: str,
    output_dir: Optional[str] = None,
    having_asset: Optional[str] = None,
    pre: bool = False,
    major: Optional[str] = None
) -> dict:
    """Download the latest release asset or source tarball for a project.
    Use this when you need to actually fetch a release file for installation or inspection."""
    args = [repo, "--download"]
    
    if output_dir:
        args.extend(["--output-dir", output_dir])
    if having_asset:
        args.extend(["--having-asset", having_asset])
    if pre:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    
    result = run_lastversion(args)
    
    if result["returncode"] == 0:
        return {
            "success": True,
            "repo": repo,
            "output": result["stdout"],
            "message": "Download completed successfully",
            "output_dir": output_dir or os.getcwd()
        }
    else:
        return {
            "success": False,
            "repo": repo,
            "error": result["stderr"] or "Download failed",
            "returncode": result["returncode"]
        }


@mcp.tool()
async def install_project(
    repo: str,
    pre: bool = False,
    having_asset: Optional[str] = None,
    major: Optional[str] = None
) -> dict:
    """Download and install the latest version of a project using the system package manager
    or by running the installer."""
    args = [repo, "--install"]
    
    if pre:
        args.append("--pre")
    if having_asset:
        args.extend(["--having-asset", having_asset])
    if major:
        args.extend(["--major", major])
    
    result = run_lastversion(args)
    
    if result["returncode"] == 0:
        return {
            "success": True,
            "repo": repo,
            "output": result["stdout"],
            "message": "Installation completed successfully"
        }
    else:
        return {
            "success": False,
            "repo": repo,
            "error": result["stderr"] or result["stdout"] or "Installation failed",
            "returncode": result["returncode"]
        }


@mcp.tool()
async def get_release_info(
    repo: str,
    format: str = "version",
    pre: bool = False,
    major: Optional[str] = None,
    having_asset: Optional[str] = None
) -> dict:
    """Get detailed metadata about the latest release of a project, including release notes,
    assets list, tag name, and publication date."""
    valid_formats = ["version", "json", "assets", "source", "tag"]
    if format not in valid_formats:
        format = "version"
    
    args = [repo, "--format", format]
    
    if pre:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    if having_asset:
        args.extend(["--having-asset", having_asset])
    
    result = run_lastversion(args)
    
    if result["returncode"] == 0 and result["stdout"]:
        output = result["stdout"]
        
        # If JSON format, try to parse it
        if format == "json":
            try:
                parsed = json.loads(output)
                return {
                    "success": True,
                    "repo": repo,
                    "format": format,
                    "data": parsed
                }
            except json.JSONDecodeError:
                pass
        
        return {
            "success": True,
            "repo": repo,
            "format": format,
            "data": output
        }
    else:
        return {
            "success": False,
            "repo": repo,
            "format": format,
            "error": result["stderr"] or "Could not retrieve release info",
            "returncode": result["returncode"]
        }


@mcp.tool()
async def get_download_url(
    repo: str,
    having_asset: Optional[str] = None,
    source: bool = False,
    pre: bool = False,
    major: Optional[str] = None
) -> dict:
    """Get the direct download URL for the latest release asset or source archive of a project
    without downloading it."""
    if source:
        args = [repo, "--format", "source"]
    elif having_asset:
        args = [repo, "--format", "assets", "--having-asset", having_asset]
    else:
        args = [repo, "--format", "assets"]
    
    if pre:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    
    result = run_lastversion(args)
    
    if result["returncode"] == 0 and result["stdout"]:
        urls = result["stdout"].strip().split("\n")
        return {
            "success": True,
            "repo": repo,
            "urls": urls,
            "primary_url": urls[0] if urls else None,
            "source_requested": source
        }
    else:
        return {
            "success": False,
            "repo": repo,
            "error": result["stderr"] or "Could not retrieve download URL",
            "returncode": result["returncode"]
        }


@mcp.tool()
async def compare_versions(
    repo: str,
    current_version: str,
    pre: bool = False,
    major: Optional[str] = None
) -> dict:
    """Compare two version strings to determine which is newer, or check if a local version
    is outdated compared to the latest release."""
    # Get latest version
    args = [repo]
    if pre:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    
    result = run_lastversion(args)
    
    if result["returncode"] != 0 or not result["stdout"]:
        return {
            "success": False,
            "repo": repo,
            "current_version": current_version,
            "error": result["stderr"] or "Could not determine latest version",
            "returncode": result["returncode"]
        }
    
    latest_version = result["stdout"].strip()
    
    # Compare using packaging library
    try:
        from packaging.version import Version as PkgVersion
        v_current = PkgVersion(current_version)
        v_latest = PkgVersion(latest_version)
        
        if v_current < v_latest:
            comparison = "outdated"
            needs_upgrade = True
            is_current = False
        elif v_current == v_latest:
            comparison = "up_to_date"
            needs_upgrade = False
            is_current = True
        else:
            comparison = "newer_than_latest"
            needs_upgrade = False
            is_current = False
        
        return {
            "success": True,
            "repo": repo,
            "current_version": current_version,
            "latest_version": latest_version,
            "comparison": comparison,
            "needs_upgrade": needs_upgrade,
            "is_current": is_current,
            "version_diff": {
                "current": str(v_current),
                "latest": str(v_latest)
            }
        }
    except Exception as e:
        # Fallback to string comparison
        is_same = current_version == latest_version
        return {
            "success": True,
            "repo": repo,
            "current_version": current_version,
            "latest_version": latest_version,
            "comparison": "up_to_date" if is_same else "different",
            "needs_upgrade": not is_same,
            "is_current": is_same,
            "parse_error": str(e)
        }




_SERVER_SLUG = "lastversion"

def _track(tool_name: str, ua: str = ""):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
        req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

sse_app = mcp.http_app(transport="sse")

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", sse_app),
    ],
    lifespan=sse_app.lifespan,
)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
