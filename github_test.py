import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.environ["GITHUB_TOKEN"]
repo = os.environ["GITHUB_REPO"]

response = requests.post(
    f"https://api.github.com/repos/{repo}/issues",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    },
    json={"title": "Test work order", "body": "Created from the EV pipeline."},
    timeout=10,
)
print(response.status_code)
print(response.json().get("html_url"))