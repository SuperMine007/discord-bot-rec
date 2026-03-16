import http.server
import socketserver
import os

PORT = 8000
DIRECTORY = "web_ui"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

if __name__ == "__main__":
    # Ensure directory exists
    os.makedirs(DIRECTORY, exist_ok=True)
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"✅ Mock UI Server started! Open your browser to http://127.0.0.1:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
