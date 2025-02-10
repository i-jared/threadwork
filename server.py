from aiohttp import web
import json
from aiohttp.web import middleware
from aiohttp.web_request import Request
from aiohttp.web_response import Response

routes = web.RouteTableDef()

@middleware
async def cors_middleware(request: Request, handler):
    response: Response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = 'http://localhost:5173'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@routes.post('/create-project')
async def create_project(request):
    # Parse JSON payload
    data = await request.json()
    # TODO: Implement credit check and S3 upload integration
    return web.json_response({'status': 'Project created', 'project': data}, status=201)

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

app = web.Application(middlewares=[cors_middleware])
app.add_routes(routes)

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8000) 