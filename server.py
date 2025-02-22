from aiohttp import web
import json
from aiohttp.web import middleware
from aiohttp.web_request import Request
from aiohttp.web_response import Response
import asyncio
import sys
from pathlib import Path

routes = web.RouteTableDef()

@middleware
async def cors_middleware(request: Request, handler):
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = web.Response()
        response.headers['Access-Control-Allow-Origin'] = 'http://localhost:5173'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    # Handle actual request
    response: Response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = 'http://localhost:5173'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# add default route
@routes.get('/')
async def default_route(request):
    return web.json_response({
        'message': 'API Server Running',
        'frontend': 'http://localhost:5173'
    }, status=200)

@routes.post('/create-project')
async def create_project(request):
    try:
        data = await request.json()
        description = data.get('description').replace('"', '\\"')  # Escape any existing double quotes
        
        # Run agent.py with named project_description argument, wrapped in double quotes
        process = await asyncio.create_subprocess_exec(
            'python',
            'src/agent.py',
            f'project_description="{description}"',  # Wrap description in double quotes
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return web.json_response({
                'status': 'error',
                'message': stderr.decode()
            }, status=500)
            
        return web.json_response({
            'status': 'success',
            'output': stdout.decode(),
            'description': description
        }, status=201)
        
    except Exception as e:
        return web.json_response({
            'status': 'error',
            'message': str(e)
        }, status=500)

@routes.get('/check-credits')
async def check_credits(request):
    # TODO: Implement logic to check user credits
    return web.json_response({'credits': 100}, status=200)

@routes.post('/stripe-webhook')
async def stripe_webhook(request):
    # TODO: Implement proper signature verification and event handling for Stripe webhook
    payload = await request.read()
    print("Received Stripe webhook payload:", payload)
    return web.Response(text='Webhook received', status=200)

# Add OPTIONS handler for create-project endpoint
@routes.options('/create-project')
async def options_create_project(request):
    return web.Response()

app = web.Application(middlewares=[cors_middleware])
app.add_routes(routes)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8000) 