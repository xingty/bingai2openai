# from flask import Flask,stream_with_context,Response
from quart import Quart, make_response,request
from EdgeGPT.EdgeGPT import Chatbot
from utils import to_openai_data,extract_metadata,to_openai_title_data
from utils import is_blank,MODELS,digest,hash_compare
import json,os,asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from EdgeGPT.utilities import get_location_hint_from_locale

def load_json(filename):
  script_dir = os.path.dirname(os.path.realpath(__file__))
  cookies_file_path = os.path.join(script_dir, filename)

  if not os.path.exists(cookies_file_path):
     return None

  with open(cookies_file_path, encoding="utf-8") as f:
    return json.load(f)

headers = {
  'Content-Type': 'text/event-stream',
  'Cache-Control': 'no-cache',
  'Transfer-Encoding': 'chunked',
  'Access-Control-Allow-Origin': "*",
  "Access-Control-Allow-Methods": "*",
  "Access-Control-Allow-Headers": "*",
}

app = Quart(__name__)
env = load_json("env.json") or {}
api_key = env.get('api_key',None)
if api_key is not None:
  api_key = digest(api_key)

@app.route('/v1/chat/completions', methods=['POST'])
async def completions():
    token = request.headers.get('Authorization').split(' ')[-1]
    if api_key is not None and (not hash_compare(api_key, digest(token))):
      return {'code': 403, 'message': 'Invalid API Key'},403

    data = await request.get_json()
    metadata = extract_metadata(data)
    stream = data.get('stream', False)
    search = metadata['search'] or env.get('search', False)
    print(metadata)
    if is_blank(metadata['prompt']):
      return {'code': 500, 'message': 'messsage cannot be empty'},500

    try:
      cookies = load_json("cookies.json")
      bot = await Chatbot.create(
        cookies=cookies,
        proxy=env.get('proxy')
      )
    except FileNotFoundError:
      return {'code': 500, 'message': 'No cookies file found'},500
    except Exception as e:
      return {'code': 500, 'message': str(e)},500

    offset = 0
    suggestions = []
    search_result = []
    locale=env.get('locale','en-US')

    async def gen_title():
      response = await bot.ask(
        prompt=metadata['prompt'],
        conversation_style=metadata['style'],
        webpage_context=metadata['context'],
        no_search=(not search),
        search_result=search,
        mode=metadata['mode'],
        locale=locale,
      )
      if 'item' in response and 'result' in response['item']:
        content = response['item']['result']['message']

        yield to_openai_title_data(content)
      else:
        yield {"code": 500, "message": "Failed to fetch response"}
          

    def parse_search_result(message):
        if 'Web search returned no relevant result' in message['hiddenText']:
            return [{
                'title': 'No relevant result',
                'url': None,
                'snippet': message['hiddenText']
            }]
        
        data = []
        for group in json.loads(message['text']).values():
            for item in group:
                data.append({
                    'title': item['title'],
                    'url': item['url'],
                })

        return data

    def process_message(response,message,new_line):
        nonlocal offset 
        if "cursor" in response["arguments"][0]:
            offset = 0

        if message.get("contentOrigin") == "Apology":
            print('message has been revoked')
            print(message)
            text = f"{message.get('text')} -end- (message has been revoked)"
            return to_openai_data(text)
        
        text = message["text"]
        truncated = text[offset:]
        offset = len(text)
        return to_openai_data(f'{new_line}{truncated}')

    async def send_events():
      nonlocal search_result
      nonlocal suggestions
      search_keyword = 'Searching the web for:\n'
      new_line = '\n'

      try:
         async for final,response in bot.ask_stream (
            prompt=metadata['prompt'],
            conversation_style=metadata['style'],
            search_result=search,
            raw=True,
            webpage_context=metadata['context'],
            no_search=(not search),
            mode=metadata['mode'],
            locale=locale,
          ):

          type = response["type"]
          if type == 1 and "messages" in response["arguments"][0]:
            message = response["arguments"][0]["messages"][0]
            msg_type = message.get("messageType")
            
            if msg_type == "InternalSearchResult":
              search_result = search_result + parse_search_result(message)
            elif msg_type == "InternalSearchQuery":
              keyword = f"- {message['hiddenText']}\n"
              if not is_blank(search_keyword):
                keyword = search_keyword + keyword
                search_keyword = ''
              yield to_openai_data(keyword)
            elif msg_type is None:
              yield process_message(response,message,new_line)
              new_line = ''
            else:
              print(f'Ignoring message type: {msg_type}')
          elif type == 2 and "item" in response and "messages" in response["item"]:
              message = response["item"]["messages"][-1]
              if "suggestedResponses" in message:
                suggestions = list(map(lambda x: x["text"], message["suggestedResponses"]))
      except Exception as e:
         print(e)
         yield to_openai_data(str(e),True)
         return

      yield to_openai_data('\n\n')
      if len(search_result) > 0:
        index = 1
        for item in search_result:
          yield to_openai_data(f'- [^{index}^] [{item["title"]}]({item["url"]})\n', False)
          index += 1

      yield to_openai_data('',True)
      await bot.close()

    response = None
    if not stream:
      response = await make_response(
        gen_title(),
        {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
        },
      )
    else:
      response = await make_response(
        send_events(),
        headers,
      )
      response.timeout = None

    return response    

@app.route('/v1/modles', methods=['GET'])
async def models():
  return MODELS

@app.route('/v1/models', methods=['GET'])
async def models2():
  return MODELS

config = Config()
config.bind = f"{env.get('bind', '127.0.0.1')}:{env.get('port', 5000)}"
asyncio.run(serve(app, config))