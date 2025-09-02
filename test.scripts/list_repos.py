#!/usr/bin/env python3
import os
import sys
import csv
import requests

def list_org_repos(org):
    token = os.getenv("GH_TOKEN")
    if not token:
        print("Error: GH_TOKEN environment variable not set")
        sys.exit(1)

    headers = {"Authorization": f"token {token}"}
    url = f"https://api.github.com/orgs/{org}/repos"
    params = {"per_page": 100, "page": 1}

    repos = []
    while True:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print(f"Error: {resp.status_code} {resp.text}")
            sys.exit(1)

        data = resp.json()
        if not data:
            break

        for repo in data:
            repos.append((repo["full_name"], str(repo["archived"]).lower()))

        params["page"] += 1

    return repos


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <org>")
        sys.exit(1)

    org = sys.argv[1]
    repos = list_org_repos(org)

    writer = csv.writer(sys.stdout)
    writer.writerow(["repo_full_name", "archived"])
    for full_name, archived in repos:
        writer.writerow([full_name, archived])
