import os
import time
import openai
from google import genai
from google.genai import types

class BaseLLMProvider:
    """Interface for all LLM providers"""
    def ask(self, system_prompt, user_content, temperature=0.1):
        raise NotImplementedError

class GeminiProvider(BaseLLMProvider):
    """Provider for Google Gemini API"""
    def __init__(self, api_key, model_name="gemini-flash-latest"):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        print(f"🧠 LLM Initialized: Google Gemini ({model_name})")

    def ask(self, system_prompt, user_content, temperature=0.1):
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=system_prompt), types.Part.from_text(text=user_content)],
            )
        ]
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=4000,
            thinking_config={'thinking_budget': 0} 
        )
        
        try:
            full_text = ""
            for chunk in self.client.models.generate_content_stream(
                model=self.model_name, contents=contents, config=config
            ):
                full_text += chunk.text
            return self._clean_response(full_text)
        except Exception as e:
            print(f"   ❌ Gemini Error: {e}")
            return "{}"

    def _clean_response(self, text):
        # 1. Handle Chain of Thought / Thinking models
        if "</think>" in text:
            text = text.split("</think>")[-1]

        # 2. Basic markdown cleaning
        text = text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return text.strip()

class OpenAIProvider(BaseLLMProvider):
    """Provider for OpenAI or Local vLLM/Qwen/DeepSeek"""
    def __init__(self, api_key, base_url, model_name):
        self.client = openai.Client(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        print(f"🧠 LLM Initialized: OpenAI Compatible ({model_name} @ {base_url})")

    def ask(self, system_prompt, user_content, temperature=0.1):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=temperature,
                max_tokens=16000,
                extra_body={
                    "top_p": 0.8,
                    "top_k": 20,
                    "min_p": 0.0
                },
                stream=False
            )
            return self._clean_response(response.choices[0].message.content)
        except Exception as e:
            print(f"   ❌ OpenAI/Local Error: {e}")
            return "{}"

    def _clean_response(self, text):
        # 1. REMOVE THINKING PROCESS
        # If the model outputs <think>...</think>, we only want what comes AFTER.
        if "</think>" in text:
            # Split by the closing tag and take the last part
            text = text.split("</think>")[-1]

        # 2. Basic markdown cleaning
        text = text.strip()
        if text.startswith("```json"): text = text[7:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return text.strip()