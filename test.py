"""Quick smoke test for Craw's hands."""
from craw.hands import REGISTRY

print(f"{len(REGISTRY.names())} tools registered:\n")
for t in REGISTRY.all():
    print(f"  [{t.tier:7}] {t.name}")

print("\n--- live calls ---")
print("tell_time       →", REGISTRY.get("tell_time").call())
print("tell_date       →", REGISTRY.get("tell_date").call())
print("system_stats    →", REGISTRY.get("system_stats").call())
print("active_window   →", REGISTRY.get("active_window").call())
print("list_dir (~)    →", REGISTRY.get("list_dir").call().splitlines()[0])
print("search_files    →", REGISTRY.get("search_files").call(query=".py", folder=".").splitlines()[:3])
print("read_file       →", REGISTRY.get("read_file").call(path="pyproject.toml", max_bytes=80))

print("\n--- confirm-tier safety check ---")
print("open_app(spoof) →", REGISTRY.get("open_app").call(name="spoof"))
print("open_app(chrome)→", REGISTRY.get("open_app").call(name="chrome"))