import requests
import json

payload = {
    "code": "def test():\n    x = 1\n    while True:\n        pass",
    "language": "python"
}

response = requests.post("http://127.0.0.1:5000/api/v1/analyze", json=payload)
print(json.dumps(response.json(), indent=2))
