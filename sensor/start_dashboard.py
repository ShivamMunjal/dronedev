#!/usr/bin/env python3
"""Dashboard server with no CSP restrictions"""
import http.server, socketserver, os, threading

PORT = 8080
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Remove CSP restrictions
        self.send_header("Content-Security-Policy", "default-src * 'unsafe-inline' 'unsafe-eval'; script-src * 'unsafe-inline' 'unsafe-eval'; connect-src * ws: wss:; style-src * 'unsafe-inline'; img-src * data: blob:;")
        super().end_headers()

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"HTTP server: http://localhost:{PORT}")
    httpd.serve_forever()
