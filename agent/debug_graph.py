import faulthandler
import time

faulthandler.dump_traceback_later(30, exit=True)   # if still running after 30s, print where it is stuck and quit

from agent.graph import _GRAPH

t0 = time.time()
state = {"line_id": 600, "question": "Why is the order quantity what it is, and why is it short?"}
for update in _GRAPH.stream(state, stream_mode="updates"):
    for node, out in update.items():
        keys = list((out or {}).keys())
        print(f"[{time.time()-t0:5.1f}s] finished node '{node}' -> {keys}")
print("done")