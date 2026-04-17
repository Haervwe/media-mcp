import os
import re
import asyncio
import base64
import uuid
import time
import httpx
import logging
from pathlib import Path
from fastmcp.utilities.types import Image, Audio
from fastmcp.tools.base import ToolResult
from .config import config

logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    """Removes filesystem-unsafe characters from a string."""
    # Replace non-alphanumeric (except underscore, hyphen, and dot) with underscores
    sanitized = re.sub(r'[^\w\-.]', '_', filename)
    # Remove leading/trailing underscores and dots
    return sanitized.strip('._')

def get_unique_path(base_dir: Path, filename: str, extension: str) -> Path:
    """
    Returns a unique file path.
    If the file exists, appends a short UUID.
    """
    base_name = sanitize_filename(filename)
    if not extension.startswith("."):
        extension = f".{extension}"
    
    file_path = base_dir / f"{base_name}{extension}"
    
    if file_path.exists():
        # Append short UUID if duplicate
        short_id = uuid.uuid4().hex[:8]
        file_path = base_dir / f"{base_name}_{short_id}{extension}"
        
    return file_path

def save_base64_to_file(b64_string: str, prefix: str = "input") -> Path:
    """Saves a base64 string to a temporary file in the assets directory."""
    try:
        # Strip potential header (data:image/png;base64,...)
        if "," in b64_string:
            b64_string = b64_string.split(",")[1]
        
        # Add missing padding
        b64_string = b64_string.strip()
        padding = len(b64_string) % 4
        if padding > 0:
            b64_string += "=" * (4 - padding)
            
        data = base64.b64decode(b64_string)
        # Determine extension based on prefix
        if any(x in prefix.lower() for x in ["img", "image", "edit", "pic"]):
            ext = ".png"
        elif any(x in prefix.lower() for x in ["audio", "song", "cover", "music"]):
            ext = ".wav"
        else:
            ext = ".bin"
        filename = f"{prefix}_{uuid.uuid4()}{ext}"
        file_path = config.ASSETS_DIR / filename
        
        with open(file_path, "wb") as f:
            f.write(data)
        
        return file_path
    except Exception as e:
        logger.error(f"Failed to save base64 to file: {e}")
        raise

async def resolve_input_to_base64(input_val: str) -> str:
    """
    Detects if the input is a local file path, a URL, or a base64 string.
    Explicitly uses OS-level checks (pathlib.Path.is_file()) to confirm paths.
    """
    if not input_val:
        raise ValueError("Input is empty")

    # 1. Cleaning and normalization
    original_input = input_val
    # Strip whitespace and common wrappings: quotes and brackets (for stringified lists)
    input_val = input_val.strip().strip("'\"[]")
    
    if input_val != original_input:
        logger.info(f"Cleaned input from '{original_input}' to '{input_val}'")

    # 2. Check if it's a URL
    if input_val.startswith(("http://", "https://")):
        logger.info(f"Detected URL: {input_val}")
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(input_val)
            resp.raise_for_status()
            logger.info(f"Successfully downloaded {len(resp.content)} bytes from URL")
            return base64.b64encode(resp.content).decode("utf-8")

    # 3. Strict Local Path Resolution (OS-level check)
    # Check absolute path or relative to CWD
    p = Path(input_val)
    if p.is_file():
        logger.info(f"Resolved path via OS: {p.absolute()}")
        return file_to_base64(p)
    
    # Check relative to Assets directory
    asset_p = config.ASSETS_DIR / input_val
    if asset_p.is_file():
        logger.info(f"Resolved path in assets: {asset_p.absolute()}")
        return file_to_base64(asset_p)

    # 4. Final heuristic check: if it LOOKS like a path but doesn't exist, we error
    # instead of falling through to base64 which will cause obscure "padding" errors.
    path_heuristics = ["/", "\\", ".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3"]
    if any(h in input_val for h in path_heuristics):
        err_msg = f"Path detected but file does not exist: '{input_val}'"
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)
    
    # 5. Fallback: Assume raw base64 data
    logger.info(f"Input treated as raw binary/base64 data (length: {len(input_val)})")
    return input_val

def file_to_base64(file_path: Path) -> str:
    """Reads a file and returns its base64 representation."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def format_output(file_path: Path, metadata: dict = None, message: str = "", response_format: str = "native") -> ToolResult:
    """
    Formats the output based on requested response_format.
    - native: returns [Image/Audio/File object, success message with absolute path]
    - legacy: returns the old structured dictionary (for frontend compatibility)
    """
    abs_path = str(file_path.absolute())
    filename = file_path.name
    metadata = metadata or {}
    msg = message or f"Successfully generated {filename}"
    full_msg = f"{msg}\nAbsolute Path: {abs_path}"

    if response_format == "legacy":
        legacy_dict = {
            "status": "success",
            "message": msg,
            "filename": filename,
            "metadata": metadata
        }
        if config.RESPONSE_FORMAT == "base64":
            legacy_dict["data"] = file_to_base64(file_path)
            legacy_dict["path"] = None
        else:
            legacy_dict["path"] = abs_path
            legacy_dict["data"] = None
        
        # Return as structured content
        return ToolResult(structured_content=legacy_dict)

    # Default to native format
    # Determine type based on extension
    suffix = file_path.suffix.lower()
    if suffix in [".png", ".jpg", ".jpeg", ".webp"]:
        media_obj = Image(path=abs_path)
    elif suffix in [".wav", ".mp3", ".ogg", ".m4a", ".flac"]:
        media_obj = Audio(path=abs_path)
    else:
        # Fallback to general text/path if unknown
        return ToolResult(content=[full_msg])

    return ToolResult(content=[media_obj, full_msg])


async def poll_ace_step_job(job_id: str, client: httpx.AsyncClient, headers: dict = None) -> dict:
    """Polls ACE Step UI for job completion."""
    start_time = time.time()
    while time.time() - start_time < config.REQUEST_TIMEOUT:
        try:
            response = await client.get(
                f"{config.MUSIC_BASE_URL}/api/generate/status/{job_id}",
                headers=headers
            )
            
            if response.status_code == 429:
                logger.warning(f"Rate limited (429) while polling {job_id}. Waiting 10s...")
                await asyncio.sleep(10)
                continue
                
            response.raise_for_status()
            data = response.json()
            
            status = data.get("status")
            if status == "succeeded":
                result = data.get("result")
                logger.info(f"Music generation job {job_id} succeeded. Result: {result}")
                return result
            elif status == "failed":
                error_msg = data.get("error", "Unknown generation error")
                raise Exception(f"Music generation failed: {error_msg}")
            
            # Still running or queued - wait 5 seconds (async)
            await asyncio.sleep(5)
        except Exception as e:
            if isinstance(e, httpx.HTTPError) and e.response and e.response.status_code == 429:
                logger.warning(f"Caught 429 in exception handler for {job_id}. Waiting 10s...")
                await asyncio.sleep(10)
                continue
            
            if isinstance(e, httpx.HTTPError):
                logger.error(f"HTTP error while polling job {job_id}: {e}")
            else:
                raise
    
    raise TimeoutError(f"Music generation timed out after {config.REQUEST_TIMEOUT}s")

async def unload_models():
    """
    Triggers model unloading for specified endpoints to free VRAM.
    Uses LLAMA_UNLOAD config (comma-separated URLs).
    Polls the /running endpoint to ensure VRAM is cleared.
    """
    if not config.LLAMA_UNLOAD:
        return

    # User provides base URLs (e.g. http://localhost:4134)
    base_urls = [u.strip().rstrip("/") for u in config.LLAMA_UNLOAD.split(",") if u.strip()]
    
    if not base_urls:
        return

    logger.info(f"Triggering model unload for base URLs: {base_urls}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Trigger unloads
        for base_url in base_urls:
            unload_url = f"{base_url}/unload"
            try:
                logger.info(f"Sending unload request to {unload_url}...")
                resp = await client.get(unload_url)
                logger.info(f"Unload request to {unload_url} returned: {resp.status_code} {resp.text[:50]}")
            except Exception as e:
                logger.error(f"Failed to send unload request to {unload_url}: {e}")

        # 2. Polling for empty status (llama-swap /running endpoint)
        polling_urls = [f"{base_url}/running" for base_url in base_urls]

        logger.info(f"Polling status at: {polling_urls}")
        for _ in range(config.MAX_UNLOAD_POLLS):
            all_clear = True
            for p_url in polling_urls:
                try:
                    resp = await client.get(p_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        running = data.get("running", [])
                        if running:
                            all_clear = False
                            logger.info(f"Model(s) still running: {[m.get('model') for m in running]}. Waiting...")
                            break
                    else:
                        logger.warning(f"Status check to {p_url} returned {resp.status_code}")
                except Exception as e:
                    logger.error(f"Error checking status at {p_url}: {e}")
                    all_clear = False # Assume not clear on error
            
            if all_clear:
                logger.info("All models unloaded successfully.")
                return
            
            await asyncio.sleep(config.UNLOAD_WAIT_SECONDS)
        
        logger.warning(f"Unload polling timed out after {config.MAX_UNLOAD_POLLS * config.UNLOAD_WAIT_SECONDS}s.")
