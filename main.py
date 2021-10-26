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
import textwrap

cfg = ConfigParser()
cfg.read("./config.ini")
TOKEN = cfg.get("Notion", "TOKEN")
DATABASE_ID = cfg.get("Notion", "DATABASE_ID")

LIBRARY_ID = int(cfg.get("Zotero", "LIBRARY_ID"))
LIBRARY_TYPE = cfg.get("Zotero", "LIBRARY_TYPE")
API_KEY = cfg.get("Zotero", "API_KEY")


if __name__ == "__main__":
    notion = Client(auth=TOKEN)
    notion_response = notion.databases.query(**{"database_id": str(DATABASE_ID)})
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

    zot = zotero.Zotero(LIBRARY_ID, LIBRARY_TYPE, API_KEY)
    zot.add_parameters(sort="dateAdded", direction="desc")
    zotero_records = zot.everything(zot.top())
    print(f"Retrieved {len(zotero_records)} Zotero records")

    existing_records = {}
    for record in notion_records:
        existing_records[
            record["properties"]["Zotero: Key"]["rich_text"][0]["plain_text"]
        ] = {
            "page_id": record["id"],
            "version": record["properties"]["Zotero: Version"]["number"],
        }

    for record in tqdm(
        zotero_records,
        desc="Updating Notion records based on Zotero records",
        unit="record",
    ):
        record_data = record["data"]  # record data from Zotero record

        properties = {}
        children = []

        citekey_matches = re.search(r"Citation Key: (\S*)", record_data["extra"])
        if citekey_matches:
            properties["Citation Key"] = {
                "title": [{"text": {"content": citekey_matches.group(1)}}]
            }
        else:
            warnings.warn(
                f"Could not retrieve citation key for entry with title {record_data['title']}"
            )

        properties["Title"] = {
            "rich_text": [{"type": "text", "text": {"content": record_data["title"]}}]
        }

        if "date" in record_data and record_data["date"]:
            properties["Publication Date"] = {
                "date": {"start": parser.parse(record_data["date"]).isoformat()}
            }

        authors = []
        for creator in record_data["creators"]:
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
        for tag in record_data["tags"]:
            if (
                "type" not in tag
                and tag["tag"] != "_tablet"
                and tag["tag"] != "_tablet_modified"
            ):  # It seems like manual tags do not have a type. We filter out automatic tags as well as the Zotfile tablet_ tag.
                tags += [{"name": tag["tag"]}]
        properties["Tags"] = {
            "type": "multi_select",
            "multi_select": tags,
        }

        properties["Zotero: Key"] = {
            "rich_text": [{"type": "text", "text": {"content": record_data["key"]}}]
        }
        properties["Zotero: Version"] = {"number": record_data["version"]}
        properties["Zotero: Date Modified"] = {
            "date": {"start": record_data["dateModified"]}
        }
        properties["Zotero: Date Added"] = {"date": {"start": record_data["dateAdded"]}}
        properties["Zotero: Link"] = {"url": record["links"]["alternate"]["href"]}

        if "url" in record_data and record_data["url"]:
            properties["URL"] = {"url": record_data.get("url")}

        if "abstractNote" in record_data:
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
                                "text": {
                                    "content": textwrap.shorten(
                                        record_data["abstractNote"], width=2000
                                    )
                                },
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

        # Check if record already exists in the Notion database. If it does not, we add it. Otherwise, we update it.
        if record_data["key"] not in existing_records:
            notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties=properties,
                children=children,
            )
        elif record_data["version"] != existing_records[record_data["key"]]["version"]:
            notion.pages.update(
                existing_records[record_data["key"]]["page_id"], properties=properties
            )

    # Check if record was deleted from Zotero but still exists in Notion. We mark any Notion records that should be deleted
    # with an icon and a tag. We do not remove these records automatically, as they may be linked to. Therefore, the user should
    # first update any links to the Notion entry before it can be safely deleted.
    keys_in_zotero = set([record["key"] for record in zotero_records])
    deleted_records = []
    for key, record in tqdm(
        existing_records.items(),
        desc="Checking for deleted Zotero records that exist in Notion",
        unit="record",
    ):
        if key not in keys_in_zotero:
            deleted_records.append(key)
            notion.pages.update(
                record["page_id"],
                properties={
                    "Tags": {
                        "type": "multi_select",
                        "multi_select": [{"name": "Deleted from Zotero"}],
                    },
                },
                icon={"type": "emoji", "emoji": "❌"},
            )
    if deleted_records:
        print(
            f"Records to be manually deleted from Notion: {', '.join(deleted_records)} (marked by icon ❌ and tagged \"Deleted from Zotero\")"
        )
