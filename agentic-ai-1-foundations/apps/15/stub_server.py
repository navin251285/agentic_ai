"""Scout's chaos stub: an Anthropic-shaped streaming provider with six injectable failures."""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"fault": "none", "left": 0, "hits": 0}     # current fault, failures left, requests seen
TEXT = ["Perseverance ", "landed on Mars ", "in February 2021."]
TOOL_JSON = ['{"query": ', '"Perseverance ', 'landing date"}']

def err(kind, msg, **details):
    e = {"type": kind, "message": msg} | ({"details": details} if details else {})
    return {"type": "error", "error": e, "request_id": "req_stub"}

def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()

def stream_events(fault, max_tokens):
    msg = {"id": "msg_stub", "type": "message", "role": "assistant", "model": "stub", "content": [],
           "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 20, "output_tokens": 0}}
    yield sse("message_start", {"type": "message_start", "message": msg})
    tool = fault == "truncated_tool"
    block = ({"type": "tool_use", "id": "toolu_stub", "name": "search_notes", "input": {}} if tool
             else {"type": "text", "text": ""})
    yield sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": block})
    cut = tool and max_tokens < 100                  # too few tokens: the JSON stops half way
    for i, piece in enumerate((TOOL_JSON if tool else TEXT)[: 2 if cut else 3]):
        delta = {"type": "input_json_delta", "partial_json": piece} if tool else {"type": "text_delta", "text": piece}
        yield sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": delta})
        if i == 1 and fault == "stream_error":       # 200 already sent, then an error event
            yield sse("error", err("overloaded_error", "Overloaded"))
            return
        if i == 1 and fault == "disconnect":         # 200 already sent, then the line goes dead
            return
    yield sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    stop = "max_tokens" if cut else ("tool_use" if tool else "end_turn")
    yield sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                "usage": {"output_tokens": 12}})
    yield sse("message_stop", {"type": "message_stop"})

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args):
        pass

    def send(self, code, data, ctype="application/json", extra=0):
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data) + extra))   # extra > 0: promise more than we send
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.send(200, json.dumps(STATE).encode())

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        if self.path == "/fault":
            STATE.update(fault=req["fault"], left=req.get("times", 10**6), hits=0)
            return self.send(200, json.dumps(STATE).encode())
        STATE["hits"] += 1
        fault = STATE["fault"] if STATE["left"] > 0 else "none"
        STATE["left"] -= 1
        if fault == "ratelimit":                     # a 429 with no retry-after header
            return self.send(429, json.dumps(err("rate_limit_error", "Rate limit exceeded.")).encode())
        if fault == "spendcap":
            body = err("rate_limit_error", "You have reached your API usage limits. You will regain access "
                       "on 2026-11-01 at 00:00 UTC.", error_code="enforced_spend_limit_reached")
            return self.send(429, json.dumps(body).encode())
        if fault == "overloaded":
            return self.send(529, json.dumps(err("overloaded_error", "Overloaded")).encode())
        cut_off = fault == "disconnect"
        self.send(200, b"".join(stream_events(fault, req.get("max_tokens", 0))), "text/event-stream", 500 * cut_off)
        self.close_connection = cut_off

class QuietServer(ThreadingHTTPServer):
    def handle_error(self, *args):                   # a client hanging up is expected here
        pass

if __name__ == "__main__":
    QuietServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
