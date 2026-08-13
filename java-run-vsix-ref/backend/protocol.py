import json
import sys
import traceback


def emit(message):
    # JSON is deliberately ASCII-safe so the protocol works even when
    # Python inherits Windows' cp1252 stdout encoding.
    sys.stdout.write(json.dumps(message, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def run_loop(dispatch):
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        request_id = None
        try:
            request = json.loads(raw)
            request_id = request.get("id")
            result = dispatch(request.get("action", ""), request.get("params") or {})
            emit({"type": "response", "id": request_id, "ok": True, "result": result})
        except Exception as exc:
            emit({
                "type": "response",
                "id": request_id,
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })
