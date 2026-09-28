"""Run the current Weis Radar top ten through a local or IBM quantum kernel.

Examples (from repository root):
  python tools/run_weis_quantum_pipeline.py --input scan.json --mode local
  python tools/run_weis_quantum_pipeline.py --api-url https://YOUR-APP --mode local
  python tools/run_weis_quantum_pipeline.py --mode ibm --backend ibm_kingston

With REDIS_URL, the latest scan is read directly from the app and its matching
result is cached for /api/weis-radar/results. --input reads an exported scan.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.weis_quantum_pipeline import execute
from backend.weis_radar_scan import WEIS_RADAR_QUANTUM_KEY, WEIS_RADAR_RESULTS_KEY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Radar scan JSON; otherwise read app Redis")
    parser.add_argument("--api-url", help="App base URL; download scan and optionally publish result")
    parser.add_argument("--admin-token-env", default="SIGMALYTIC_ADMIN_TOKEN",
                        help="Environment variable containing admin bearer token for publishing")
    parser.add_argument("--output", type=Path, default=Path("weis_quantum_results.json"))
    parser.add_argument("--mode", choices=("local", "ibm"), default="local")
    parser.add_argument("--backend", help="IBM physical backend; omitted selects least busy")
    parser.add_argument("--shots", type=int, default=4096)
    args = parser.parse_args()

    client = None
    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    elif args.api_url:
        import urllib.request
        with urllib.request.urlopen(args.api_url.rstrip("/") + "/api/weis-radar/results", timeout=20) as response:
            payload = json.load(response)
    else:
        url = os.environ.get("REDIS_URL")
        if not url:
            parser.error("Set REDIS_URL to the app's Redis, or pass --input scan.json")
        import redis
        client = redis.Redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
        raw = client.get(WEIS_RADAR_RESULTS_KEY)
        if not raw:
            parser.error("No completed Weis Radar scan found in Redis")
        payload = json.loads(raw)

    handoff = (payload.get("trade_finder") or {}).get("handoff") or []
    if not handoff:
        parser.error("Scan has no qualified handoff candidates; run Weis Radar first")
    if len(handoff) > 10:
        parser.error("Expected at most ten selected handoff candidates")
    result = execute(handoff, mode=args.mode, shots=args.shots, backend_name=args.backend)
    result["scan_generated_at"] = payload.get("generated_at")
    result["timeframe"] = (payload.get("config") or {}).get("timeframe")
    result["qualification"] = "Circuit overlap only; trade probability and institutional attribution uncalibrated"
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    if client:
        # A newer scan may have finished while the hardware job was queued.
        current = json.loads(client.get(WEIS_RADAR_RESULTS_KEY) or "{}")
        if current.get("generated_at") == result["scan_generated_at"]:
            client.set(WEIS_RADAR_QUANTUM_KEY, json.dumps(result, allow_nan=False))
    if args.api_url and os.environ.get(args.admin_token_env):
        import urllib.request
        request = urllib.request.Request(
            args.api_url.rstrip("/") + "/api/admin/weis-radar/quantum-result",
            data=json.dumps(result, allow_nan=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + os.environ[args.admin_token_env]},
            method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            acknowledgment = json.load(response)
        if not acknowledgment.get("ok"):
            raise RuntimeError(f"App did not accept quantum result: {acknowledgment.get('error')}")
    print(f"Saved {args.output}; mode={args.mode}, candidates={len(handoff)}, "
          f"job_id={result['job_id'] or 'local'}")


if __name__ == "__main__":
    main()
