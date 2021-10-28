# zotero2notion
This repository contains a simple script to import [Zotero](https://www.zotero.org/) records into [Notion](https://www.notion.so/). This can be used to easily refer to literature in Notion notes, either by [mentioning](https://www.notion.so/help/comments-mentions-and-reminders#mention-a-page) it or by using [relationships](https://www.notion.so/help/relations-and-rollups).

![example png](https://user-images.githubusercontent.com/1269004/139274982-9603d8e1-2839-4052-a9cd-b0412701f378.jpg)

### Setup
#### In Zotero
1. Install the [Better BibTeX plugin](https://retorque.re/zotero-better-bibtex/installation/).
2. Pin the keys of your existing Zotero records (select all Zotero records, then right click > Better BibTeX > Pin BibTeX key).
3. Set the [`autoPinDelay` parameter](https://retorque.re/zotero-better-bibtex/installation/preferences/hidden-preferences/#autopindelay) to 2.

#### In Notion
1. Clone this Notion [template](https://n3ls.notion.site/bb3c71f287c44b5dad54c2fb3b078521?v=8c41545e0e6e43999eeed9eb210c6ff5).

#### In terminal
1. Clone repository.
2. Install Python 3.
3. [Install](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/#using-requirements-files) required packages from `requirements.txt`.
4. Create `config.ini` by copying `config.ini.sample`.
    * Enter [Zotero API](https://www.zotero.org/settings/keys) credentials (Settings > Feeds/API, allow library access and notes access).
    * Enter [Notion API](https://developers.notion.com/docs/getting-started) credentials.

### Run
Execute `python main.py` to run the script.
