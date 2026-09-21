#!/usr/bin/env python3
"""Read-only live query validation. Prints counts, never metric labels or log lines."""
import argparse
import json
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from build_application_dashboards import dashboards, operations_center, APP_NAMESPACES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="Cluster hosting VictoriaMetrics and Loki")
    parser.add_argument("--loki-url", required=True, help="Local read-only port-forward to Loki, e.g. http://127.0.0.1:19100")
    args = parser.parse_args()

    def check(item):
        title, panel, target = item
        expr = target["expr"]
        replacements = {"$__rate_interval": "5m", "$__range": "1h", "$__auto": "5m", "$cluster": ".*", "$namespace": APP_NAMESPACES, "$monitor": ".*", "$monitor_type": ".*", "$cnpg_cluster": ".*", "$window": "1d", '${search:doublequote}': '""'}
        for key, value in sorted(replacements.items(), key=lambda item: -len(item[0])):
            expr = expr.replace(key, value)
        is_log = target["datasource"]["type"] == "loki"
        namespace, pod, port, path = ("monitoring-logs", "loki-0", 3100, "/loki/api/v1/query_range") if is_log else ("monitoring-metrics", "victoriametrics-0", 8428, "/api/v1/query")
        params = {"query": expr, **({"limit": "1", "since": "1h", "step": "60"} if is_log else {})}
        url = f"http://127.0.0.1:{port}{path}?" + urllib.parse.urlencode(params)
        try:
            if is_log:
                with urllib.request.urlopen(args.loki_url.rstrip('/') + path + '?' + urllib.parse.urlencode(params), timeout=40) as response:
                    data = json.load(response)
                return [title, panel, data["status"], len(data.get("data", {}).get("result", []))]
            proc = subprocess.run(["kubectl", "--context", args.context, "-n", namespace, "exec", pod, "--", "wget", "-qO-", url], capture_output=True, text=True, timeout=40)
            if proc.returncode:
                return [title, panel, "ERROR", "query request failed"]
            data = json.loads(proc.stdout)
            return [title, panel, data["status"], len(data.get("data", {}).get("result", []))]
        except (subprocess.TimeoutExpired, ValueError, KeyError, urllib.error.URLError, TimeoutError):
            return [title, panel, "ERROR", "timeout or invalid response"]

    items = [(d["title"], p["title"], t) for d in [*dashboards().values(), operations_center()] for p in d["panels"] for t in p.get("targets", [])]
    failures = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(check, items):
            print(json.dumps(result), flush=True)
            failures += result[2] != "success"
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
