# .cfg Python config -- lowest external priority; JSON, CLI, and parent kwargs all win against it.
# Run with:  make gen CFG_CONFIG=config.py
# Every entry names its instance: path.name, the path starting at the top instance (Genesis2 form).

WIDTHS = [3, 7, 11]
configure("top.WALLACES_WIDTHS", WIDTHS)
for n in WIDTHS:
    configure(f"top.wallace_{n}.COND", True)
    configure(f"top.wallace_{n}.ParamHash", {"tag": "cfg-driven", "depth": 7})
