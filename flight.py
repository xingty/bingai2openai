# from flask import Flask,stream_with_context,Response
from quart import Quart,abort, make_response,stream_with_context,request
from EdgeGPT.EdgeGPT import Chatbot
from EdgeGPT.EdgeGPT import ConversationStyle
from os import getenv
import json,time,random,string
from utils import to_openai_data,extract_metadata

app = Quart(__name__)

headers = {
  'Content-Type': 'text/event-stream',
  'Cache-Control': 'no-cache',
  'Transfer-Encoding': 'chunked',
  'Access-Control-Allow-Origin': "*",
  "Access-Control-Allow-Methods": "*",
  "Access-Control-Allow-Headers": "*",
}

def get_cookies():
   with open(getenv("EDGE_COOKIES"), encoding="utf-8") as f:
      return json.load(f)

@app.route('/v1/chat/completions', methods=['POST'])
async def completions():
    print(getenv("EDGE_COOKIES"))
    cookies = get_cookies()
    bot = await Chatbot.create(
        proxy='http://127.0.0.1:7890',
        cookies=cookies
    )

    offset = 0
    suggestions = []
    search_result = []
    search_keyword = ''
    data = await request.get_json()

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
      
      metadata = extract_metadata(data)
      print(metadata)

      try:
         async for final,response in bot.ask_stream (
            prompt=metadata['prompt'],
            conversation_style=metadata['style'],
            search_result=metadata['search'],
            raw=True,
            webpage_context=metadata['context']
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
         yield to_openai_data(str(e),True)
         return

      yield '\n\n'
      if len(search_result) > 0:
        index = 1
        for item in search_result:
          yield to_openai_data(f'- [^{index}^] [{item["title"]}]({item["url"]})\n', False)
          index += 1

      yield to_openai_data('',True)

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

@app.route('/v1/chat/completions2', methods=['POST'])
async def test2():
  data = await request.get_json()
  metadata = extract_metadata(data)
  print(metadata)
  # return 'hello world'
  @stream_with_context
  async def streaming():
    test_data = ['hello,','world!','how are you?','i am fine','nice to meet you']
    for item in test_data:
      content = to_openai_data(text=item, finished=(item == 'nice to meet you'))
      time.sleep(0.5)
      yield content

  return streaming(), 200, headers


app.run()