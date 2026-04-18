import logging
from typing import Optional, Annotated, Literal, Union
from pydantic import BaseModel, Field
from fastmcp import FastMCP, Context
from fastmcp.utilities.types import Image, Audio
from fastmcp.tools.base import ToolResult
from .clients import MediaClient, MusicClient, ImageFormat, VocalLanguage, MusicKey, TimeSignature
from .utils import format_output
from .config import config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("media-mcp")

# Initialize FastMCP
mcp = FastMCP("MediaMCP")

# Core clients
media_client = MediaClient()
music_client = MusicClient()

def get_response_format(ctx: Context) -> str:
    """Extracts response format from x-response-format header."""
    if ctx.request_context and ctx.request_context.request:
        return ctx.request_context.request.headers.get("x-response-format", "native")
    return "native"

# Removed MediaResponse class and ResponseFormat literal

@mcp.tool()
async def generate_image(
    ctx: Context,
    prompt: str,
    format: ImageFormat = "square"
) -> ToolResult:
    """
    Creates visually stunning images with text prompts using the local Flux text-to-image model.
    If the user prompt is too general or lacking, embellish it to generate a better illustration.

    Args:
        prompt: Detailed description of the image to generate
        format: Image format (square, portrait, landscape)
    """
    logger.info(f"Generating image: {prompt} (format: {format})")
    try:
        path = await media_client.generate_image(prompt, format=format)
        return format_output(
            path, 
            {"prompt": prompt, "model": config.IMAGE_MODEL, "format": format},
            message=f"Successfully generated image: {prompt[:50]}...",
            response_format=get_response_format(ctx)
        )
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def edit_image(
    ctx: Context,
    images: Union[str, list[str]],
    prompt: str,
    format: ImageFormat = "square"
) -> ToolResult:
    """
    Edits an existing image (image-to-image) using a text prompt and up to 3 reference images.
    Use this tool when you need to perform an image-to-image transformation, modify a subject, 
    apply a style, or alter an existing picture based on a text prompt.

    Args:
        images: A list containing up to 3 images (paths or base64 strings). 
            - The FIRST image (index 0) is treated as the MAIN SUBJECT or base image to be edited.
            - Additional images will be used as supplementary context (style references, compositional guides).
        prompt: A detailed description of what the final image should look like or what edits should be made.
        format: Image format (square, portrait, landscape)
    """
    logger.info(f"Editing image with prompt: {prompt} (format: {format})")
    try:
        path = await media_client.edit_image(images, prompt, format=format)
        num_imgs = len(images) if isinstance(images, list) else 1
        return format_output(
            path, 
            {"prompt": prompt, "action": "edit", "format": format, "input_count": num_imgs},
            message=f"Successfully edited image using {num_imgs} input image(s).",
            response_format=get_response_format(ctx)
        )
    except Exception as e:
        logger.error(f"Image editing failed: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def generate_song(
    ctx: Context,
    prompt: str,
    lyrics: str = "",
    tags: str = "",
    language: VocalLanguage = "en",
    key: MusicKey = "",
    time_signature: TimeSignature = "",
    title: Optional[str] = None
) -> ToolResult:
    """
    Generate a complete song (music + vocals) using the ACE Step 1.5 model.

    **Prompting Guide for Agents:**
    - **Tags (Style/Genre)**: Be descriptive! Include genre, instruments, mood, tempo, and vocal style.
      Examples: "rock, hard rock, powerful voice, electric guitar, 120 bpm", "lo-fi, chill, study beats, jazz piano".
    - **Lyrics**: Use structure tags `[verse]`, `[chorus]`, `[bridge]` to guide the song arrangement.
      For instrumental, use `[inst]` or describe instruments as tags.
    - **Languages**: Supports 50+ languages including EN, ZH, JA. For Japanese, use Katakana.

    Args:
        prompt: Style, mood, and genre description of the song
        lyrics: Optional lyrics to sing
        tags: Optional music tags (instruments, mood, tempo)
        language: Vocal language
        key: Musical key and scale
        time_signature: Rhythmic time signature (2, 3, 4, 5, 6)
        title: Optional title for the song (used as filename)
    """
    logger.info(f"Generating song. Prompt: {prompt}, Language: {language}, Key: {key}, TS: {time_signature}, Title: {title}")
    try:
        path = await music_client.generate_song(prompt, lyrics, language=language, tags=tags, key=key, time_signature=time_signature, title=title)
        return format_output(
            path, 
            {"prompt": prompt, "lyrics": lyrics, "tags": tags, "language": language, "key": key, "time_signature": time_signature, "title": title},
            message=f"Successfully generated song: {title if title else prompt[:50]}...",
            response_format=get_response_format(ctx)
        )
    except Exception as e:
        logger.error(f"Song generation failed: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def generate_cover(
    ctx: Context,
    audio: str,
    style_prompt: str = "",
    strength: float = 0.7,
    tags: str = "",
    lyrics: str = "",
    language: VocalLanguage = "en",
    key: MusicKey = "",
    time_signature: TimeSignature = "",
    title: Optional[str] = None
) -> ToolResult:
    """
    Generate a cover version of an existing audio file (voice conversion/style swap) using ACE Step 1.5.

    **Prompting Guide for Agents:**
    - **Style Prompt**: Describe how the cover should differ from the original (e.g., "Change the singer to a deep male voice", "Transform into a jazz version").
    - **Strength**: Controls how much of the original audio's structure (melody/rhythm) is preserved. 0.7 is a good default.
    - **Tags**: Specify instruments and genre for the new version.
    - **Lyrics**: Optionally provide lyrics if you want to refine the vocal delivery.

    Args:
        audio: Local file path or base64-encoded source audio file (song)
        style_prompt: Description of the target style or instructions
        strength: Strength of the source audio influence (0.0 to 1.0)
        tags: Optional music tags for the cover style
        lyrics: Optional lyrics to sing
        language: Vocal language
        key: Musical key and scale
        time_signature: Rhythmic time signature (2, 3, 4, 5, 6)
        title: Optional title for the cover (used as filename)
    """
    logger.info(f"Generating cover version. Style: {style_prompt}, Language: {language}, Key: {key}, Title: {title}")
    try:
        path = await music_client.generate_cover(
            audio, style_prompt, strength=strength, tags=tags, lyrics=lyrics, 
            language=language, key=key, time_signature=time_signature, title=title
        )
        return format_output(
            path, 
            {
                "style": style_prompt, "action": "cover", "strength": strength, 
                "tags": tags, "lyrics": lyrics, "language": language, "key": key, "time_signature": time_signature, "title": title
            },
            message=f"Successfully generated cover: {title if title else style_prompt[:50]}...",
            response_format=get_response_format(ctx)
        )
    except Exception as e:
        logger.error(f"Cover generation failed: {e}")
        return {"status": "error", "message": str(e)}

def main():
    logger.info(f"Starting MediaMCP server on {config.MCP_HOST}:{config.MCP_PORT} (streamable-http)")
    mcp.run(transport="streamable-http", host=config.MCP_HOST, port=config.MCP_PORT)

if __name__ == "__main__":
    main()
