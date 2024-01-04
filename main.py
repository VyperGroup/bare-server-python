import http.server
import os
import socketserver
import json
import requests

PORT = os.environ["PORT"] or 3000

class BareHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            with open(os.path.join(os.path.dirname(__file__), 'bare_server_info.json'), 'r') as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data.encode())
        else:
          if "x-bare-url" in self.headers:
              url = self.headers["x-bare-url"]
              if "x-bare-headers" in self.headers:
                  headers = json.loads(self.headers["x-bare-headers"])
              else:
                  headers = {}
              if "x-bare-forward-headers" in self.headers:
                  forward_headers = json.loads(self.headers["x-bare-forward-headers"])
                  for header in forward_headers:
                      if header in self.headers:
                          headers[header] = self.headers[header]
              response = requests.get(url, headers=headers)
              if "x-bare-pass-status" in self.headers:
                  pass_status = json.loads(self.headers["x-bare-pass-status"])
                  if response.status_code in pass_status:
                      self.send_response(response.status_code)
                  else:
                      self.send_response(200)
              else:
                  self.send_response(200)
              if "x-bare-pass-headers" in self.headers:
                  pass_headers = json.loads(self.headers["x-bare-pass-headers"])
                  for header in pass_headers:
                      if header in response.headers:
                          self.send_header(header, response.headers[header])
              self.send_header("Cache-Control", "no-cache")
              self.send_header("ETag", response.headers.get("ETag", ""))
              self.send_header("Content-Encoding", response.headers.get("Content-Encoding", ""))
              self.send_header("Content-Length", response.headers.get("Content-Length", ""))
              self.send_header("X-Bare-Status", response.status_code)
              self.send_header("X-Bare-Status-Text", response.reason)
              self.send_header("X-Bare-Headers", json.dumps(response.headers))
              self.end_headers()
              self.wfile.write(response.content)
          else:
              self.send_error(400, "Missing x-bare-url header")

with socketserver.TCPServer(("", PORT), BareHandler) as httpd:
    print("serving at port", PORT)
    httpd.serve_forever()
