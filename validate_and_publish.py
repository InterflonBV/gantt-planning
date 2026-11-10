#!/usr/bin/env python3
"""Create public gantt-data.json from GitHub repository_dispatch payload.

REV05: optionally include validated folder paths for projects.
NEVER publish raw SharePoint records or private metadata.
Compatible with existing payloads that do not include folderPaths.
"""
import datetime
import json
import os
import re
from pathlib import Path


def fail(message):
    raise ValueError(message)


def is_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        return datetime.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def build(payload):
    if not isinstance(payload, dict):
        fail("Geen object als client_payload")

    projects = payload.get("projects")
    sharepoint = payload.get("sharepointProjects")
    milestones = payload.get("milestones")
    folder_paths = payload.get("folderPaths", [])

    if not isinstance(projects, list) or not projects:
        fail("Geen projecten ontvangen")
    if not isinstance(sharepoint, list) or not isinstance(milestones, list):
        fail("SharePoint-projecten of mijlpalen ontbreken")
    if not isinstance(folder_paths, list):
        fail("folderPaths moet een lijst zijn")
    if len(projects) > 1500 or len(milestones) > 3000 or len(folder_paths) > 1500:
        fail("Onverwacht grote planning; verwerking gestopt")

    by_id = {}
    for project in projects:
        if not isinstance(project, dict):
            fail("Project is geen object")
        pid = str(project.get("wrikeId", "")).strip()
        if not re.fullmatch(r"\d+", pid):
            fail("Ongeldige Wrike-ID")
        if pid in by_id:
            fail("Dubbele Wrike-ID: " + pid)
        if not project.get("name") or not project.get("status"):
            fail("Projectnaam/status ontbreekt")
        if not is_date(project.get("startDate")) or not is_date(project.get("endDate")) or project["endDate"] < project["startDate"]:
            fail("Ongeldige projectdatums: " + pid)
        by_id[pid] = project

    for pid, project in by_id.items():
        parent = str(project.get("parentWrikeId") or "")
        if parent and parent not in by_id:
            fail("Onbekende parentWrikeId voor " + pid)
        if parent == pid:
            fail("Zelfverwijzende projectrelatie: " + pid)
        visited = {pid}
        while parent:
            if parent in visited:
                fail("Cirkel in hiërarchie: " + pid)
            visited.add(parent)
            parent = str(by_id[parent].get("parentWrikeId") or "")

    sp_map = {}
    for project in sharepoint:
        sid = str(project.get("id", "")).strip()
        wid = str(project.get("wrikeId", "")).strip()
        if not sid.isdigit() or not wid.isdigit():
            fail("Ongeldig actief SharePoint-project")
        if sid in sp_map:
            fail("Dubbel SharePoint item ID: " + sid)
        sp_map[sid] = wid
    if len(set(sp_map.values())) != len(sp_map):
        fail("Meerdere SharePoint-items voor dezelfde Wrike-ID")
    if set(sp_map.values()) != set(by_id):
        fail("Actieve SharePoint-projecten wijken af van Wrike-export. Publicatie geblokkeerd.")

    checked_milestones = []
    seen = set()
    for milestone in milestones:
        mid = str(milestone.get("id", "")).strip()
        sid = str(milestone.get("projectId", "")).strip()
        if not mid.isdigit() or mid in seen:
            fail("Dubbele/ongeldige mijlpaal-ID")
        seen.add(mid)
        if not milestone.get("title") or not is_date(milestone.get("date")):
            fail("Ongeldige mijlpaal: " + mid)
        if sid not in sp_map:
            fail("Mijlpaal " + mid + " heeft geen actief gekoppeld project")
        checked_milestones.append({
            "id": int(mid), "title": str(milestone["title"]),
            "date": milestone["date"],
            "status": str(milestone.get("status") or "Planned"),
            "wrikeId": sp_map[sid]
        })

    checked_folders = []
    seen_projects = set()
    folder_names = {}
    for path in folder_paths:
        if not isinstance(path, dict):
            fail("Ongeldig folderpad-object")
        pid = str(path.get("projectWrikeId", "")).strip()
        if pid not in by_id:
            fail("Folderpad verwijst naar onbekend gepubliceerd project: " + pid)
        if pid in seen_projects:
            fail("Dubbel folderpad voor project: " + pid)
        seen_projects.add(pid)
        chain = path.get("folders")
        if not isinstance(chain, list) or len(chain) > 40:
            fail("Ongeldig folderpad voor project: " + pid)
        checked_chain = []
        seen_folder_ids = set()
        for folder in chain:
            if not isinstance(folder, dict):
                fail("Folder in pad is geen object: " + pid)
            fid = str(folder.get("wrikeId", "")).strip()
            name = str(folder.get("name", "")).strip()
            if not re.fullmatch(r"\d+", fid) or not name:
                fail("Ongeldige foldergegevens voor project: " + pid)
            if fid in by_id:
                fail("Folder-ID is ook geselecteerd project-ID: " + fid)
            if fid in seen_folder_ids:
                fail("Dubbele folder in ouderketen van project: " + pid)
            seen_folder_ids.add(fid)
            if fid in folder_names and folder_names[fid] != name:
                fail("Eén folder-ID heeft verschillende namen: " + fid)
            folder_names[fid] = name
            checked_chain.append({"wrikeId": fid, "name": name})
        checked_folders.append({"projectWrikeId": pid, "folders": checked_chain})

    cleaned_projects = []
    for pid, project in by_id.items():
        cleaned_projects.append({
            "wrikeId": pid, "name": str(project["name"]),
            "status": str(project["status"]),
            "startDate": project["startDate"],
            "endDate": project["endDate"],
            "parentWrikeId": str(project.get("parentWrikeId") or ""),
            "parentName": str(project.get("parentName") or ""),
            "level": int(project.get("level") or 1)
        })

    return {
        "schema": "interflon-stakeholder-gantt-v1",
        "publishedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "projects": cleaned_projects,
        "milestones": checked_milestones,
        "folderPaths": checked_folders
    }


if __name__ == "__main__":
    raw = os.environ.get("GANTT_DISPATCH_PAYLOAD")
    if not raw:
        fail("GANTT_DISPATCH_PAYLOAD ontbreekt")
    output = build(json.loads(raw))
    Path("gantt-data.json").write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("Gevalideerd:", len(output["projects"]), "projecten;", len(output["milestones"]), "mijlpalen;", len(output["folderPaths"]), "folderpaden")
