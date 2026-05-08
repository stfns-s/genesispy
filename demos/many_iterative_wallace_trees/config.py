# .cfg Python config — lowest external priority; JSON, CLI, and parent kwargs all win against it.
# Run with:  make gen CFG_CONFIG=config.py
# Or layered under JSON:  make gen JSON_CONFIG=config.json CFG_CONFIG=config.py
#                          -> JSON wins where it sets a value, .cfg fills the rest.

configure("WALLACES_WIDTHS", [3, 7, 11])
configure("COND", True)
configure("ParamHash", {"tag": "cfg-driven", "depth": 7})
