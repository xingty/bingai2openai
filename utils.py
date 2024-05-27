import time, json, random, string
import hashlib, hmac
from EdgeGPT.conversation_style import ConversationStyle

MODELS = {
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


def to_openai_title_data(title: str):
    id = ''.join(random.choices(string.ascii_letters + string.digits, k=28))
    obj = {
        "id": id,
        "object": "chat.completion",
        "created": str(int(time.time())),
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": title
                },
                "logprobs": None,
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        },
        "system_fingerprint": None
    }

    return json.dumps(obj)


def to_openai_data(text: str, finished: bool = False):
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

    segments = payload['model'].lower().split('_')
    style = segments[0]
    # is gpt4-turbo enabled
    enable_turbo = False
    if len(segments) > 1:
        enable_turbo = segments[1] == 'turbo'
    style = getattr(ConversationStyle,
                    style) if style in ConversationStyle._member_names_ else ConversationStyle.precise
    messages = payload['messages']

    prompt = messages[-1]
    prompt_content = prompt['content']

    def remove_instructions(content: str):
        for instruction in instructions:
            content = content.replace(instruction, '')
        return content

    model = None
    if enable_turbo or '#enable_gpt4_turbo' in prompt_content:
        model = 'gpt4-turbo'

    context = ''
    for i in range(len(messages) - 1):
        msg = messages[i]
        role = msg['role'].lower()
        type_info = 'message'
        if role == 'system':
            type_info = 'instructions'

        content = remove_instructions(msg['content'])
        context += f'[{role}][#{type_info}]\n{content}'

    return {
        'prompt': remove_instructions(prompt_content),
        'context': context,
        'style': style,
        'search': '#enable_search' in prompt_content,
        'mode': model
    }


def is_blank(s: str):
    return not bool(s and not s.isspace())


def digest(s: str):
    return hashlib.sha1(s.encode()).digest()


def hash_compare(src: bytes, target: bytes):
    return hmac.compare_digest(src, target)
