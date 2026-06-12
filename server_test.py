"""
Test server — isolated from production. Port 5889, uses test_data/ + classes_test.json
"""
import os, sys
sys.dont_write_bytecode = True

os.environ["ZG_DB"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data.db")
os.environ["ZG_WORK"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")
os.environ["ZG_PORT"] = "5889"
os.environ["ZG_TEST"] = "true"

import server
server.app.run(host="127.0.0.1", port=5889, debug=False)
