import os
import logging
from typing import Optional
from datetime import datetime
import aiosqlite
import urllib.error
from google.oauth2 import service_account
from googleapiclient.discovery import build
import discord
from pywaclient.api import BoromirApiClient as WaClient
from .config import config_cache
from .utils import extract_document_id

def validate_wa_report(url: str):
    pass # Not implemented in original, so skipped or placeholder.

async def validate_worldanvil_link(guild_id: int, article_id: str) -> Optional[dict]:
    allowed_guilds = [883009758179762208, 280061170231017472]
    if guild_id not in allowed_guilds:
        logging.warning(f"Guild ID {guild_id} is not authorized to create articles.")
        return None
    try:
        api_key = os.getenv('WORLD_ANVIL_API')
        user_id = os.getenv('WORLD_ANVIL_USER')
        if not api_key or not user_id:
            logging.error("World Anvil API credentials are not set.")
            return None

        client = WaClient(
            'pathparser',
            'https://github.com/Solfyrism/pathparser',
            'V1.1',
            api_key,
            user_id
        )

        returned_page = client.article.get(identifier=article_id, granularity=1)

        return returned_page
    except Exception as e:
        logging.exception(f"Error in retrieving article with ID '{article_id}': {e}")
        return None

def drive_word_document(overview: str) -> Optional[str]:
    try:
        if overview.startswith("http"):
            document_id = extract_document_id(overview)
            if document_id is None:
                logging.error(f"Could not extract document ID from URL '{overview}'.")
                return None
        else:
            return overview

        service_account_file = os.getenv('SERVICE_ACCOUNT_FILE')
        if not service_account_file:
            logging.error("Service account file is not set.")
            return None

        scopes = ['https://www.googleapis.com/auth/documents.readonly']
        credentials = service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes)
        service = build('docs', 'v1', credentials=credentials)

        document = service.documents().get(documentId=document_id).execute()

        word_blob = ""
        for element in document.get('body', {}).get('content', []):
            paragraph = element.get('paragraph')
            if paragraph:
                for text_run in paragraph.get('elements', []):
                    text_content = text_run.get('textRun', {}).get('content')
                    if text_content:
                        word_blob += text_content

        return word_blob.strip()
    except urllib.error.HTTPError as e:
        logging.exception(f"HTTP error while retrieving document: {e}")
        return None
    except Exception as e:
        logging.exception(f"Error in retrieving overview: {e}")
        return None

async def put_wa_article(guild_id: int, template: str, category: str, title: str, overview: str, author: str) -> Optional[dict]:
    allowed_guilds = [883009758179762208, 280061170231017472]
    if guild_id not in allowed_guilds:
        logging.warning(f"Guild ID {guild_id} is not authorized to create articles.")
        return None
    try:
        api_key = os.getenv('WORLD_ANVIL_API')
        user_id = os.getenv('WORLD_ANVIL_USER')
        if not api_key or not user_id:
            logging.error("World Anvil API credentials are not set.")
            return None

        client = WaClient(
            'pathparser',
            'https://github.com/Solfyrism/pathparser',
            'V1.1',
            api_key,
            user_id
        )
        world_id = 'f7a60480-ea15-4867-ae03-e9e0c676060a'

        evaluated_overview = drive_word_document(overview)

        template_to_entity_class = {
            'generic': 'Generic',
            'person': 'Person',
            'location': 'Location',
        }
        entity_class = template_to_entity_class.get(template.lower(), template)

        new_page = client.article.put({
            'title': title,
            'content': evaluated_overview,
            'category': {'id': category},
            'templateType': template.lower(),
            'state': 'public',
            'isDraft': False,
            'entityClass': entity_class.title(),
            'tags': author,
            'world': {'id': world_id}
        })
        return new_page
    except Exception as e:
        logging.exception(f"Error in article creation for title '{title}': {e}")
        return None

async def patch_wa_article(guild_id: int, article_id: str, overview: str) -> Optional[dict]:
    allowed_guilds = [883009758179762208, 280061170231017472]
    if guild_id not in allowed_guilds:
        logging.warning(f"Guild ID {guild_id} is not authorized to create articles.")
        return None
    try:
        api_key = os.getenv('WORLD_ANVIL_API')
        user_id = os.getenv('WORLD_ANVIL_USER')
        if not api_key or not user_id:
            logging.error("World Anvil API credentials are not set.")
            return None

        client = WaClient(
            'pathparser',
            'https://github.com/Solfyrism/pathparser',
            'V1.1',
            api_key,
            user_id
        )
        world_id = 'f7a60480-ea15-4867-ae03-e9e0c676060a'

        evaluated_overview = drive_word_document(overview)

        updated_page = client.article.patch(article_id, {
            'content': f'{evaluated_overview}',
            'world': {'id': world_id}
        })
        return updated_page
    except Exception as e:
        logging.exception(f"Error in article patch for article '{article_id}': {e}")
        return None

async def put_wa_report(guild_id: int, session_id: int, overview: str, author: str, plot: str,
                        significance: int) -> Optional[tuple]:
    if guild_id in [883009758179762208, 280061170231017472]:
        evaluated_overview = drive_word_document(overview)
        try:
            client = WaClient(
                'pathparser',
                'https://github.com/Solfyrism/pathparser',
                'V1.1',
                os.getenv('WORLD_ANVIL_API'),
                os.getenv('WORLD_ANVIL_USER')
            )
            world_id = 'f7a60480-ea15-4867-ae03-e9e0c676060a'
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                cursor = await db.cursor()
                async with config_cache.lock:
                    configs = config_cache.cache.get(guild_id)
                    if configs:
                        session_folder = configs.get('WA_Session_Folder')
                        timeline = configs.get('WA_Timeline_Default')

                if not session_folder:
                    raise ValueError("No World Anvil session folder set.")

                if not timeline:
                    raise ValueError("No World Anvil timeline set.")

                await cursor.execute(
                    "SELECT Session_Name, Completed_Time, Alt_Reward_Party, Alt_Reward_All, Overview from Sessions where Session_ID = ?",
                    (session_id,))
                session_info = await cursor.fetchone()
                await cursor.execute(
                    "SELECT SA.Character_Name, PC.Article_Link, Article_ID FROM Sessions_Archive as SA left join Player_Characters AS PC on PC.Character_Name = SA.Character_Name WHERE SA.Session_ID = ? and SA.Player_Name != ? ",
                    (session_id, author))
                characters = await cursor.fetchall()
                character_list = [character_row for character_row in characters]
                if len(character_list) == 0:
                    await cursor.execute(
                        "SELECT SA.Character_Name, PC.Article_Link, Article_ID FROM Sessions_Participants as SA left join Player_Characters AS PC on PC.Character_Name = SA.Character_Name WHERE SA.Session_ID = ? and SA.Player_Name != ? ",
                        (session_id, author))
                    characters = await cursor.fetchall()
                related_persons_block = []
                counter = 0
                completed_str = session_info[1] if session_info[1] is not None else datetime.now().strftime(
                    "%Y-%m-%d %H:%M")
                completed_time = datetime.strptime(completed_str, '%Y-%m-%d %H:%M')
                day = datetime.strftime(completed_time, '%d')
                month = datetime.strftime(completed_time, '%m')
                new_report_page = client.article.put({
                    'title': f'{str(session_id).rjust(3, "0")}: {session_info[0]}',
                    'content': f'{evaluated_overview}',
                    'category': {'id': f'{session_folder}'},
                    'templateType': 'report',  # generic article template
                    'state': 'public',
                    'isDraft': False,
                    'entityClass': 'Report',
                    'tags': f'{author}',
                    'world': {'id': world_id},
                    #                  'reportDate': report_date,  # Convert the date to a string
                    'plots': [{'id': plot}]
                })
                for character in characters:

                    if character[2] is not None:
                        person = {'id': character[2]}
                        related_persons_block.append(person)
                        counter += 1
                if counter == 0:
                    new_timeline_page = client.history.put({
                        'title': f'{session_info[0]}',
                        'content': f'{session_info[4]}',
                        'fullcontent': f'{evaluated_overview}',
                        'timelines': [{'id': f'{timeline}'}],
                        'significance': significance,
                        'parsedContent': session_info[4],
                        'report': {'id': new_report_page['id']},
                        'year': 22083,
                        'month': int(month),
                        'day': int(day),
                        'endingYear': int(22083),
                        'endingMonth': int(month),
                        'endingDay': int(day),
                        'world': {'id': world_id}
                    })
                else:
                    related_persons_block = related_persons_block
                    new_timeline_page = client.history.put({
                        'title': f'{session_info[0]}',
                        'content': f'{session_info[4]}',
                        'fullcontent': f'{evaluated_overview}',
                        'timelines': [{'id': f'{timeline}'}],
                        'significance': significance,
                        'characters': related_persons_block,
                        'parsedContent': session_info[4],
                        'report': {'id': new_report_page['id']},
                        'year': 22083,
                        'month': int(month),
                        'day': int(day),
                        'endingYear': int(22083),
                        'endingMonth': int(month),
                        'endingDay': int(day),
                        'world': {'id': world_id}
                    })
                await cursor.execute(
                    'update Sessions set Article_link = ?, Article_ID = ?, History_ID = ? where Session_ID = ?',
                    (new_report_page['url'], new_report_page['id'], new_timeline_page['id'], session_id))
                await db.commit()
                return new_report_page, new_timeline_page
        except Exception as e:
            logging.exception(f"Error in article creation for session '{session_id}': {e}")
            return None

async def patch_wa_report(guild_id: int, session_id: int, overview: str) -> Optional[dict]:
    if guild_id not in [883009758179762208, 280061170231017472]:
        logging.warning(f"Guild ID {guild_id} is not authorized to create articles.")
        return None

    evaluated_overview = drive_word_document(overview)
    try:
        client = WaClient(
            'pathparser',
            'https://github.com/Solfyrism/pathparser',
            'V1.1',
            os.getenv('WORLD_ANVIL_API'),
            os.getenv('WORLD_ANVIL_USER')
        )
        world_id = 'f7a60480-ea15-4867-ae03-e9e0c676060a'

        # Establish a new database connection
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            # Fetch session information
            await cursor.execute("SELECT Article_ID, History_ID FROM Sessions WHERE Session_ID = ?", (session_id,))
            session_info = await cursor.fetchone()
            if not session_info:
                logging.error(f"No session found with Session_ID {session_id}")
                return None

            article_id = session_info[0]
            history_id = session_info[1]

            # Update the article and history on World Anvil
            new_page = client.article.patch(article_id, {
                'content': evaluated_overview,
                'world': {'id': world_id}
            })
            new_history = client.history.patch(history_id, {
                'content': evaluated_overview,
                'world': {'id': world_id}
            })

            return {'article': new_page, 'history': new_history}

    except Exception as e:
        logging.exception(f"Error in article update for session '{session_id}': {e}")
        return None
