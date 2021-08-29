import re
import logging
import warnings
from dateutil import parser
from datetime import datetime
from pprint import pprint
from configparser import ConfigParser
from time import perf_counter
from notion_client import Client
from pyzotero import zotero
from tqdm import tqdm

cfg = ConfigParser()
cfg.read("./config.ini")
TOKEN = cfg.get("Notion", "TOKEN")
DATABASE_ID = cfg.get("Notion", "DATABASE_ID")

LIBRARY_ID = int(cfg.get("Zotero", "LIBRARY_ID"))
LIBRARY_TYPE = cfg.get("Zotero", "LIBRARY_TYPE")
API_KEY = cfg.get("Zotero", "API_KEY")


if __name__ == "__main__":
    notion = Client(auth=TOKEN)

    zot = zotero.Zotero(LIBRARY_ID, LIBRARY_TYPE, API_KEY)
    zot.add_parameters(sort="dateAdded", direction="desc")
    items = zot.everything(zot.top())
    print(f"Retrieved {len(items)} Zotero records")

    notion_response = notion.databases.query(**{"database_id": DATABASE_ID})
    notion_records = notion_response["results"]
    while notion_response["has_more"]:
        notion_response = notion.databases.query(
            **{
                "database_id": DATABASE_ID,
                "start_cursor": notion_response["next_cursor"],
            }
        )
        notion_records += notion_response["results"]
    print(f"Retrieved {len(notion_records)} Notion records")

    existing_entries = {}
    for record in notion_records:
        existing_entries[
            record["properties"]["Zotero: Key"]["rich_text"][0]["plain_text"]
        ] = {
            "page_id": record["id"],
            "version": record["properties"]["Zotero: Version"]["number"],
            "citekey": record["properties"]["Citation Key"]["title"][0]["plain_text"],
        }

    for item in tqdm(
        items, desc="Updating Notion records based on Zotero records", unit="record"
    ):
        item_data = item["data"]

        properties = {}
        children = []

        citekey_matches = re.search(r"Citation Key: (\S*)", item_data["extra"])
        if citekey_matches:
            properties["Citation Key"] = {
                "title": [{"text": {"content": citekey_matches.group(1)}}]
            }
        else:
            warnings.warn(
                f"Could not retrieve citation key for entry with title {item_data['title']}"
            )

        properties["Title"] = {
            "rich_text": [{"type": "text", "text": {"content": item_data["title"]}}]
        }

        if "date" in item_data and item_data["date"]:
            properties["Publication Date"] = {
                "date": {"start": parser.parse(item_data["date"]).isoformat()}
            }

        authors = []
        for creator in item_data["creators"]:
            if creator["creatorType"] == "author":
                author_str = ""
                for key in ["name", "firstName", "middleName", "lastName"]:
                    if key in creator:
                        author_str += creator[key]
                        author_str += " " if key != "lastName" else ""
                authors += [{"name": author_str}]
        properties["Authors"] = {
            "type": "multi_select",
            "multi_select": authors,
        }

        tags = []
        for tag in item_data["tags"]:
            if (
                "type" not in tag
            ):  # It seems like manual tags do not have a type (we filter out automatic tags)
                tags += [{"name": tag["tag"]}]
        properties["Tags"] = {
            "type": "multi_select",
            "multi_select": tags,
        }

        properties["Zotero: Key"] = {
            "rich_text": [{"type": "text", "text": {"content": item_data["key"]}}]
        }
        properties["Zotero: Version"] = {"number": item_data["version"]}
        properties["Zotero: Date Modified"] = {
            "date": {"start": item_data["dateModified"]}
        }
        properties["Zotero: Date Added"] = {"date": {"start": item_data["dateAdded"]}}
        properties["Zotero: Link"] = {"url": item["links"]["alternate"]["href"]}

        if "url" in item_data and item_data["url"]:
            properties["URL"] = {"url": item_data.get("url")}

        if "abstractNote" in item_data:
            children.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "text": [
                            {
                                "type": "text",
                                "text": {"content": "Abstract"},
                            }
                        ]
                    },
                }
            )

            children.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "text": [
                            {
                                "type": "text",
                                "text": {"content": item_data["abstractNote"]},
                                "annotations": {
                                    "bold": False,
                                    "italic": False,
                                    "strikethrough": False,
                                    "underline": False,
                                    "code": False,
                                },
                            }
                        ]
                    },
                }
            )

        # Check if entry already exists in the Notion database. If it does not, we add it. Otherwise, we update it.
        if item_data["key"] not in existing_entries:
            notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties=properties,
                children=children,
            )
        elif item_data["version"] != existing_entries[item_data["key"]]["version"]:
            notion.pages.update(
                existing_entries[item_data["key"]]["page_id"], properties=properties
            )
