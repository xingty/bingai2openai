import time,json,random,string
from EdgeGPT.EdgeGPT import ConversationStyle

def to_openai_data(text,finished=False):
  id = ''.join(random.choices(string.ascii_letters + string.digits, k=28)) 
  obj = {
    "id": id,
    "object": "chat.completion.chunk",
    "created": str(int(time.time())),
    "model": "gpt-4",
    "system_fingerprint": "fp_44709d2fcb",
    "choices": [
      {
        "index": 0,
        "delta": {
          "role": "assistant",
          "content": text
        },
        "finish_reason": "stop" if finished else None
      }
    ]
  }

  content = json.dumps(obj, separators=(',', ':'))
  return f'data: {content}\n\n'

def extract_metadata(payload):
  style = payload['model'].lower()
  style = getattr(ConversationStyle, style) if style in ConversationStyle._member_names_ else ConversationStyle.creative
  messages = payload['messages']

  prompt = messages[-1]
  context = ''
  for msg in messages:
    role = 'assistant'
    type_info = 'additional_instructions'
    if msg['role'].lower() == 'user':
      role = 'user'
      type_info = 'message'

    context += f'[{role}][#{type_info}]\n{msg["content"]}\n'

  prompt_content = prompt['content']

  return {
    'prompt': prompt_content,
    'context': context,
    'style': style,
    'search': '#no_search' not in prompt_content,
  }