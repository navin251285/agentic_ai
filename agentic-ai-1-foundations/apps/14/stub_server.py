"""Scout's flaky-provider stub: answers like Anthropic or Gemini, but fails on purpose."""
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8714
HITS: dict[str, list[float]] = {}          # scenario -> arrival times
START = time.monotonic()
TEXT = "Perseverance landed on Mars in February 2021."

def ok_body(gemini):
    if gemini:
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": TEXT}]},
                                "finishReason": "STOP"}], "responseId": "stub-ok"}
    return {"id": "msg_stub", "type": "message", "role": "assistant", "model": "stub",
            "content": [{"type": "text", "text": TEXT}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 20, "output_tokens": 12}}

def err_body(gemini, code, kind, msg, details=None):
    if gemini:
        return {"error": {"code": code, "message": msg, "status": kind}}
    err = {"type": kind, "message": msg} | ({"details": details} if details else {})
    return {"type": "error", "error": err, "request_id": "req_stub"}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):            # keep the notebook output clean
        pass

    def send(self, code, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:              # the client timed out and left
            pass

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, {"ok": True})
        if self.path == "/hits":
            return self.send(200, HITS)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        if self.path == "/reset":
            HITS.clear()
            return self.send(200, {"ok": True})
        scenario = self.path.strip("/").split("/")[0]
        n = len(HITS.setdefault(scenario, [])) + 1
        HITS[scenario].append(round(time.monotonic() - START, 3))
        g = "generateContent" in self.path
        if scenario == "flaky" and n <= 2:      # rate limited twice, then fine
            body = err_body(g, 429, "RESOURCE_EXHAUSTED" if g else "rate_limit_error",
                            "Rate limit exceeded: requests per minute.")
            return self.send(429, body, {"retry-after": "1"})
        if scenario == "spendcap":              # monthly cap reached: no retry-after
            body = err_body(g, 429, "rate_limit_error", "You have reached your API usage "
                            "limits. You will regain access on 2026-11-01 at 00:00 UTC.",
                            {"error_code": "enforced_spend_limit_reached"})
            return self.send(429, body)
        if scenario == "badreq":
            return self.send(400, err_body(g, 400, "invalid_request_error",
                                           "max_tokens: must be greater than 0"))
        if scenario == "slow" and n == 1:       # first call hangs for 2 s
            time.sleep(2)
        self.send(200, ok_body(g))

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
