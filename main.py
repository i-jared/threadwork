import sys
# Add the 'src' directory to the Python path so that modules in there (e.g., config.py) can be imported.
sys.path.append("src")

import os
import aiohttp
from aiohttp import web
from config import build_api_request, extract_api_response
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

async def handle_root(request):
    # Simple prompt instructing each AI to produce one concise greeting.
    prompt = "Please respond with a one-sentence greeting."

    # Define configuration for each provider using environment variables.
    anthropic_config = {
        "provider": "anthropic",
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "max_tokens": 50,
        "model": "claude-3-5-sonnet-20241022"
    }
    gemini_config = {
        "provider": "gemini",
        "api_key": os.getenv("GEMINI_API_KEY"),
        "max_tokens": 50,
        "model": "gemini-2.0-flash"
    }
    openai_config = {
        "provider": "openai",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "max_tokens": 50,
        "model": "gpt-3.5-turbo"
    }
    deepseek_config = {
        "provider": "deepseek",
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "max_tokens": 50,
        "model": "deepseek-reasoner"
    }

    # Build a dictionary of provider configurations.
    provider_configs = {
        "Anthropic": anthropic_config,
        "Gemini": gemini_config,
        "OpenAI": openai_config,
        "DeepSeek": deepseek_config
    }

    results = {}

    async with aiohttp.ClientSession() as session:
        # Iterate over each provider and send the request.
        for provider_name, config in provider_configs.items():
            req_config = build_api_request(prompt, config)
            try:
                async with session.post(
                    req_config["api_endpoint"],
                    json=req_config["body"],
                    headers=req_config["headers"]
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Extract the formatted response using the new functions
                        results[provider_name] = extract_api_response(data, config["provider"])
                    else:
                        results[provider_name] = {"error": f"HTTP {response.status}"}
            except Exception as e:
                results[provider_name] = {"error": str(e)}

    html_content = """
    <html>
    <head>
        <title>API Test Results</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .provider { margin-bottom: 20px; }
            .content { margin-left: 20px; }
            .usage { color: #666; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <h1>API Test Results</h1>
    """
    
    for provider, result in results.items():
        html_content += f"""
        <div class="provider">
            <h2>{provider}</h2>
            <div class="content">
        """
        
        if "error" in result:
            html_content += f"<p style='color: red;'>Error: {result['error']}</p>"
        else:
            html_content += f"""
                <p><strong>Response:</strong> {result['content']}</p>
                <p class="usage">
                    Input tokens: {result['usage']['input_tokens']}<br>
                    Output tokens: {result['usage']['output_tokens']}<br>
                    Total tokens: {result['usage']['total_tokens']}
                </p>
            """
        
        html_content += "</div></div>"
    
    html_content += "</body></html>"

    return web.Response(text=html_content, content_type="text/html")

# Create the aiohttp application instance and add the root route.
app = web.Application()
app.add_routes([web.get('/', handle_root)])

if __name__ == '__main__':
    # Run the application on host 0.0.0.0 and port 8000.
    # Since no routes are defined, the server will respond with a default 404 for any request.
    web.run_app(app, host='0.0.0.0', port=8000) 