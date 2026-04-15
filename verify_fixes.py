import asyncio
from mcp import ClientSession
from mcp.client.http import http_client
import os

async def test_fixes():
    # Connect to the running server on port 8080 (SSE/streamable-http)
    # FastMCP starts the streamable-http at /mcp
    async with http_client("http://localhost:8080/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print("--- Testing generate_image (extension fix) ---")
            img_result = await session.call_tool("generate_image", {
                "prompt": "a simple red cube on a white background"
            })
            print(f"Image Tool Result: {img_result}")
            
            print("\n--- Testing generate_song (auth fix) ---")
            song_result = await session.call_tool("generate_song", {
                "prompt": "simple piano melody",
                "lyrics": "Hello world",
                "duration": 5
            })
            print(f"Song Tool Result: {song_result}")

if __name__ == "__main__":
    asyncio.run(test_fixes())
