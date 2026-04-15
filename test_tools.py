import asyncio
from mcp import ClientSession
from mcp.client.http import http_client
import base64
import os

async def test_tools():
    # Connect to the running server
    async with http_client("http://localhost:8080/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            print("--- Initializing Session ---")
            await session.initialize()
            
            print("\n--- Listing Tools ---")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"Tool found: {tool.name}")

            # 1. Test generate_image
            print("\n--- Testing generate_image ---")
            img_result = await session.call_tool("generate_image", {
                "prompt": "a professional 3D render of a futuristic robot, high detail, cyberpunk style"
            })
            print(f"Result: {img_result.content[0].text if img_result.content else 'No content'}")
            
            # 2. Test generate_song
            print("\n--- Testing generate_song ---")
            song_result = await session.call_tool("generate_song", {
                "prompt": "chill lofi hip hop with electric piano",
                "lyrics": "Walking under the neon lights, feeling the rhythm of the night.",
                "duration": 30
            })
            print(f"Result: {song_result.content[0].text if song_result.content else 'No content'}")

            # 3. Test edit_image (if we have an image to test with)
            # For simplicity, we'll just check if we can call it even if mocked or with small dummy data
            # but usually we'd pass a real base64.
            
if __name__ == "__main__":
    asyncio.run(test_tools())
