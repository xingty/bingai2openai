import time,json,random,string
from EdgeGPT.EdgeGPT import ConversationStyle

def to_openai_data(text: str,finished: bool=False):
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

def extract_metadata(payload: dict):
  instructions = ['#enable_search', '#enable_gpt4_turbo']

  # style = payload['model'].lower()
  segments = payload['model'].lower().split('_')
  style = segments[0]
  # is gpt4-turbo enabled
  enable_turbo = False
  if len(segments) > 1:
    enable_turbo = segments[1] == 'turbo'
  style = getattr(ConversationStyle, style) if style in ConversationStyle._member_names_ else ConversationStyle.creative
  messages = payload['messages']

  prompt = messages[-1]
  prompt_content = prompt['content']

  def remove_instructions(content: str):
    for instruction in instructions:
      content = content.replace(instruction, '')
    return content

  context = ''
  for msg in messages:
    role = 'assistant'
    type_info = 'additional_instructions'
    if msg['role'].lower() == 'user':
      role = 'user'
      type_info = 'message'

    content = remove_instructions(msg['content'])
    context += f'[{role}][#{type_info}]\n{content}\n'

  model = None
  if enable_turbo or '#enable_gpt4_turbo' in prompt_content:
    model = 'gpt4-turbo'

  return {
    'prompt': remove_instructions(prompt_content),
    'context': context,
    'style': style,
    'search': '#enable_search' in prompt_content,
    'mode': model
  }

def is_blank(s: str):
  return not bool(s and not s.isspace())