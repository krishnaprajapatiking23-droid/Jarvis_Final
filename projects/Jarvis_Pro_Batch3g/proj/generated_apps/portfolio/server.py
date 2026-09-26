import http.server
import socketserver

PORT = 8000
httpd = socketserver.TCPServer(('', PORT), http.server.SimpleHTTPRequestHandler)
print(f'Serving at port {PORT}')
httpd.serve_forever()