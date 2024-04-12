# from flask import Flask,stream_with_context,Response
from quart import Quart, make_response,request
from EdgeGPT.EdgeGPT import Chatbot,ConversationStyle
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

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
async def completions():
    if request.method == 'OPTIONS':
      return await make_response('', 200, {
        'Access-Control-Allow-Origin': "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
      })
    token = request.headers.get('Authorization').split(' ')[-1]
    if api_key is not None and (not hash_compare(api_key, digest(token))):
      return {'code': 403, 'message': 'Invalid API Key'},403

    data = await request.get_json()
    metadata = extract_metadata(data)
    stream = data.get('stream', False)
    search = metadata['search'] or env.get('search', False)
    # print(metadata)
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
    locale=env.get('locale','en-US')
    print(metadata['prompt'])

    async def gen_title():
      response = await bot.ask(
        prompt=metadata['prompt'],
        conversation_style=metadata['style'],
        webpage_context=metadata['context'],
        no_search=(not search),
        search_result=search,
        locale=locale,
      )
      if 'item' in response and 'result' in response['item']:
        content = response['item']['result']['message']

        yield to_openai_title_data(content)
      else:
        yield {"code": 500, "message": "Failed to fetch response"}

    async def send_events():
      offset = 0

      try:
         async for final,response in bot.ask_stream (
            prompt=metadata['prompt'],
            conversation_style=metadata['style'],
            search_result=True,
            raw=False,
            webpage_context=metadata['context'],
            no_search=(not search),
          ):
            text = None
            if isinstance(response, dict):
              text = response["item"]["messages"][-1].get("text")
            else:
              text = response

            truncated = text[offset:]
            offset = len(text)

            yield to_openai_data(truncated,final)
      except Exception as e:
         print(e)
         yield to_openai_data(str(e),True)
         return

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