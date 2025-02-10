from aiohttp import web

# Create an aiohttp application instance without any routes.
app = web.Application()

if __name__ == '__main__':
    # Run the application on host 0.0.0.0 and port 8000.
    # Since no routes are defined, the server will respond with a default 404 for any request.
    web.run_app(app, host='0.0.0.0', port=8000) 