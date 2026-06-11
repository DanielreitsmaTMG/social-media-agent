"""
Helper voor het uploaden van afbeeldingen naar Google Drive t.b.v. de
"📅 Planning"-tab in dashboard.py.

Afbeeldingen worden geplaatst in een submap "Planning" binnen de
Drive-map van de klant (`google_doc_folder_id`, zelfde map als de
wekelijkse Google Docs uit systems/create_weekly_doc.py) en krijgen een
publieke leesrechten-permissie zodat de Meta Graph API de afbeelding kan
ophalen bij het publiceren (image_url / full_picture).

Vereist scope: https://www.googleapis.com/auth/drive
"""

from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/drive"]

PLANNING_SUBFOLDER_NAME = "Planning"


def _drive_service(sa_info: dict):
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def _find_or_create_subfolder(drive_service, parent_folder_id: str, name: str) -> str:
    """Geeft de map-ID van `name` binnen `parent_folder_id` terug, en maakt deze aan indien nodig."""
    query = (
        f"'{parent_folder_id}' in parents and name = '{name}' "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    result = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])
    if files:
        return files[0]["id"]

    folder = drive_service.files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_folder_id],
        },
        fields="id",
    ).execute()
    return folder["id"]


def upload_image(sa_info: dict, parent_folder_id: str, filename: str,
                  content_bytes: bytes, mime_type: str) -> dict:
    """Uploadt een afbeelding naar de Planning-submap van de klant en maakt deze publiek leesbaar.

    Geeft {"id": <drive_file_id>, "url": <publieke directe URL>} terug.
    """
    drive_service = _drive_service(sa_info)
    folder_id = _find_or_create_subfolder(drive_service, parent_folder_id, PLANNING_SUBFOLDER_NAME)

    media = MediaInMemoryUpload(content_bytes, mimetype=mime_type, resumable=False)
    file = drive_service.files().create(
        body={"name": filename, "parents": [folder_id]},
        media_body=media,
        fields="id",
    ).execute()
    file_id = file["id"]

    drive_service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
        fields="id",
    ).execute()

    return {"id": file_id, "url": f"https://drive.google.com/uc?export=view&id={file_id}"}
