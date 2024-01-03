# from flask import Flask,stream_with_context,Response
from quart import Quart,abort, make_response,request
from EdgeGPT.EdgeGPT import Chatbot
from utils import to_openai_data,extract_metadata,is_blank
import json,os,asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve

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

@app.route('/v1/chat/completions', methods=['POST'])
async def completions():
    data = await request.get_json()
    metadata = extract_metadata(data)
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
    search_keyword = ''

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

    def process_message(response,message):
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
        return to_openai_data(truncated)

    async def send_events():
      nonlocal search_result
      nonlocal search_keyword
      nonlocal suggestions
      
      search = metadata['search']

      try:
         async for final,response in bot.ask_stream (
            prompt=metadata['prompt'],
            conversation_style=metadata['style'],
            search_result=search,
            raw=True,
            webpage_context=metadata['context'],
            no_search=(not search),
            mode=metadata['mode'],
          ):

          type = response["type"]
          if type == 1 and "messages" in response["arguments"][0]:
            message = response["arguments"][0]["messages"][0]
            msg_type = message.get("messageType")
            
            if msg_type == "InternalSearchResult":
              search_result = search_result + parse_search_result(message)
            elif msg_type == "InternalSearchQuery":
              search_keyword = message['hiddenText']
            elif msg_type is None:
              yield process_message(response,message)
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

    response = await make_response(
        send_events(),
        {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Transfer-Encoding': 'chunked',
        },
    )
    response.timeout = None
    return response    

@app.route('/v1/modles', methods=['GET'])
async def models():
  return {
    "object": "list",
    "data": [
      {
        "id": "gpt-4",
        "object": "model",
        "created": 1686935002,
        "owned_by": "organization-owner"
      },
      {
        "id": "creative",
        "object": "model",
        "created": 1686935002,
        "owned_by": "organization-owner"
      },
      {
        "id": "precise",
        "object": "model",
        "created": 1686935002,
        "owned_by": "organization-owner"
      },
      {
        "id": "creative_turbo",
        "object": "model",
        "created": 1686935002,
        "owned_by": "organization-owner"
      },
      {
        "id": "precise_turbo",
        "object": "model",
        "created": 1686935002,
        "owned_by": "organization-owner"
      },
      {
        "id": "balanced",
        "object": "model",
        "created": 1686935002,
        "owned_by": "organization-owner"
      }
    ],
    "object": "list"
  }

config = Config()
config.bind = f"{env.get('bind', '127.0.0.1')}:{env.get('port', 5000)}"
asyncio.run(serve(app, config))