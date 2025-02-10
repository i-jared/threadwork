from aiohttp import web

# Async handler for the root URL
async def handle(request):
    # Return a simple HTML response.
    return web.Response(
        text="<html><body><h1>Hello, world!</h1></body></html>",
        content_type="text/html"
    )

# Create an aiohttp application instance
app = web.Application()
# Register the GET route for the root URL
app.router.add_get('/', handle)

if __name__ == '__main__':
    # Run the application on host 0.0.0.0 and port 8000.
    web.run_app(app, host='0.0.0.0', port=8000) 