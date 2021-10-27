import re
import warnings
from dateutil import parser
from configparser import ConfigParser
from notion_client import Client
from pyzotero import zotero
from tqdm import tqdm
import textwrap


def create_post_objects(record):
    """Create objects for Notion POST message, which will create a Notion record based on the given Zotero record.

    Args:
        record: A Zotero record.
    """
    record_data = record["data"]  # Record data from Zotero record.

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
    return properties, children


def get_existing_notion_records(notion_records):
    """Extract the Zotero version numbers of Notion records and return them.

    Args:
        zotero_records: A list of dictionaries containing Zotero records.
        notion_records: A list of dictionaries containing Notion records.
    """
    existing_records = {}
    for record in notion_records:
        existing_records[
            record["properties"]["Zotero: Key"]["rich_text"][0]["plain_text"]
        ] = {
            "page_id": record["id"],
            "version": record["properties"]["Zotero: Version"]["number"],
        }
    return existing_records


def find_removed_records(notion_client, zotero_records, existing_records):
    """Find records that no longer exist in Zotero but do exist in Notion.

    This function checks if records were deleted from Zotero but still exists in Notion. We mark any Notion records that
    should be deleted with an icon and a tag. We do not remove these records automatically, as they may be linked to.
    Therefore, the user should first update any links to the Notion entry before it can be safely deleted.

    Args:
        zotero_records: A list of dictionaries containing Zotero records
        notion_records: A list of dictionaries containing Notion records
    """
    keys_in_zotero = set([record["key"] for record in zotero_records])
    deleted_records = []
    for key, record in tqdm(
        existing_records.items(),
        desc="Checking for deleted Zotero records that exist in Notion",
        unit="record",
    ):
        if key not in keys_in_zotero:
            deleted_records.append(key)
            notion_client.pages.update(
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


def get_notion_records(notion_client, notion_token, notion_db_id):
    """Retrieve Notion records through Notion API.

    Args:
        notion_client: Notion client object.
        notion_token: Notion API token.
        notion_db_id: Notion database ID.
    """
    notion_response = notion_client.databases.query(
        **{"database_id": str(notion_db_id)}
    )
    notion_records = notion_response["results"]
    while notion_response["has_more"]:
        notion_response = notion_client.databases.query(
            **{
                "database_id": notion_db_id,
                "start_cursor": notion_response["next_cursor"],
            }
        )
        notion_records += notion_response["results"]
    print(f"Retrieved {len(notion_records)} Notion records")
    return notion_records


def get_zotero_records(zotero_library_id, zotero_library_type, zotero_api_key):
    """Retrieve Zotero records through Zotero API.

    Args:
        zotero_library_id: Zotero library ID
        zotero_library_type: Zotero library type (typically "user")
        zotero_api_key: Zotero API key
    """
    zot = zotero.Zotero(zotero_library_id, zotero_library_type, zotero_api_key)
    zot.add_parameters(sort="dateAdded", direction="desc")
    zotero_records = zot.everything(zot.top())
    print(f"Retrieved {len(zotero_records)} Zotero records")
    return zotero_records


def process_records(zotero_records, notion_records, notion_client):
    """Process records by submitting new records to Notion, based on the given Zotero records.

    Args:
        zotero_records: A list of dictionaries containing Zotero records.
        notion_records: A list of dictionaries containing Notion records.
        notion_client: Notion client object.
    """
    # Get Zotero keys of records that exist in Notion.
    existing_records = get_existing_notion_records(notion_records)

    for record in tqdm(
        zotero_records,
        desc="Updating Notion records based on Zotero records",
        unit="record",
    ):
        # Check if record already exists in the Notion database. If it does not, we add it. Otherwise, we update it.
        if record["data"]["key"] not in existing_records:
            properties, children = create_post_objects(record)
            notion_client.pages.create(
                parent={"database_id": notion_db_id},
                properties=properties,
                children=children,
            )
        elif (
            record["data"]["version"]
            != existing_records[record["data"]["key"]]["version"]
        ):
            properties, children = create_post_objects(record)
            notion_client.pages.update(
                existing_records[record["data"]["key"]]["page_id"],
                properties=properties,
            )

    find_removed_records(notion_client, zotero_records, existing_records)


if __name__ == "__main__":
    cfg = ConfigParser()
    cfg.read("./config.ini")
    notion_token = cfg.get("Notion", "TOKEN")
    notion_db_id = cfg.get("Notion", "DATABASE_ID")
    notion_client = Client(auth=notion_token)

    zotero_library_id = int(cfg.get("Zotero", "LIBRARY_ID"))
    zotero_library_type = cfg.get("Zotero", "LIBRARY_TYPE")
    zotero_api_key = cfg.get("Zotero", "API_KEY")

    notion_records = get_notion_records(notion_client, notion_token, notion_db_id)
    zotero_records = get_zotero_records(
        zotero_library_id, zotero_library_type, zotero_api_key
    )

    process_records(zotero_records, notion_records, notion_client)
