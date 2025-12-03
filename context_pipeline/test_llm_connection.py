import time
import openai

client = openai.Client(
    base_url="http://10.201.24.88:6655/v1", api_key="EMPTY"
)
MODEL = "qwen3_30b_deployed"


start_time = time.perf_counter()
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are helpful AI assistant"},
        {"role": "user", "content": "Какое у тебя любимое аниме?"},
    ],
    temperature=0,
    max_tokens=256,
    stream=True
)

first_token_time = None
for chunk in response:
    if chunk.choices[0].delta.content is not None:
        if first_token_time is None:  # first token arrived
            first_token_time = time.perf_counter()
            ttft = first_token_time - start_time
            print(f"\n\nTTFT: {ttft:.3f} seconds\n")
        print(chunk.choices[0].delta.content, end="", flush=True)
