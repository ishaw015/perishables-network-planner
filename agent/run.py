import json
import sys
from agent.graph import explain

if __name__ == "__main__":
    line_id, question = int(sys.argv[1]), sys.argv[2]
    print(json.dumps(explain(line_id, question), indent=2))