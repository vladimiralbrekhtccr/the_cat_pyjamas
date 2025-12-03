"""
LLM Client Abstraction - Base class and implementations for different LLM providers
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
import openai
from google import genai
from google.genai import types


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """
        Generate text response from LLM
        
        Args:
            system_prompt: System prompt/instructions
            user_prompt: User input/query
            **kwargs: Additional model-specific parameters
            
        Returns:
            Generated text response
        """
        pass
    
    @abstractmethod
    def get_client_info(self) -> Dict[str, str]:
        """Return information about the LLM client configuration"""
        pass


class OpenAICompatibleClient(BaseLLMClient):
    """Client for OpenAI-compatible APIs (including custom endpoints)"""
    
    def __init__(
        self,
        base_url: str,
        api_key: str = "EMPTY",
        model: str = "qwen3_30b_deployed",
        temperature: float = 0.1,
        max_tokens: int = 4000,
        stream: bool = True
    ):
        """
        Initialize OpenAI-compatible client
        
        Args:
            base_url: Base URL for the API endpoint
            api_key: API key (use "EMPTY" for endpoints that don't require auth)
            model: Model name to use
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream responses
        """
        self.client = openai.Client(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.base_url = base_url
    
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Generate text using OpenAI-compatible API"""
        temperature = kwargs.get('temperature', self.temperature)
        max_tokens = kwargs.get('max_tokens', self.max_tokens)
        stream = kwargs.get('stream', self.stream)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )
        
        if stream:
            # Collect streamed response
            full_text = ""
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    full_text += chunk.choices[0].delta.content
            return full_text
        else:
            return response.choices[0].message.content
    
    def get_client_info(self) -> Dict[str, str]:
        """Return client configuration info"""
        return {
            'type': 'OpenAI-Compatible',
            'base_url': self.base_url,
            'model': self.model,
            'temperature': str(self.temperature),
            'max_tokens': str(self.max_tokens)
        }


class GeminiClient(BaseLLMClient):
    """Client for Google Gemini API"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-flash-latest",
        temperature: float = 0.1,
        max_output_tokens: int = 4000
    ):
        """
        Initialize Gemini client
        
        Args:
            api_key: Gemini API key
            model: Model name to use
            temperature: Sampling temperature (0.0 - 1.0)
            max_output_tokens: Maximum tokens to generate
        """
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.api_key_preview = api_key[:8] + "..." if len(api_key) > 8 else "***"
    
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Generate text using Gemini API"""
        temperature = kwargs.get('temperature', self.temperature)
        max_output_tokens = kwargs.get('max_output_tokens', self.max_output_tokens)
        
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=system_prompt),
                    types.Part.from_text(text=user_prompt),
                ],
            )
        ]
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            thinking_config={'thinking_budget': 0}
        )
        
        full_text = ""
        for chunk in self.client.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config
        ):
            full_text += chunk.text
        
        return full_text
    
    def get_client_info(self) -> Dict[str, str]:
        """Return client configuration info"""
        return {
            'type': 'Google Gemini',
            'model': self.model,
            'temperature': str(self.temperature),
            'max_output_tokens': str(self.max_output_tokens)
        }


def create_llm_client(
    provider: str,
    **kwargs
) -> BaseLLMClient:
    """
    Factory function to create LLM clients
    
    Args:
        provider: Provider type ('openai', 'gemini')
        **kwargs: Provider-specific configuration
        
    Returns:
        Configured LLM client
        
    Examples:
        # OpenAI-compatible
        client = create_llm_client(
            provider='openai',
            base_url='http://10.201.24.88:6655/v1',
            api_key='EMPTY',
            model='qwen3_30b_deployed'
        )
        
        # Gemini
        client = create_llm_client(
            provider='gemini',
            api_key='your-api-key',
            model='gemini-flash-latest'
        )
    """
    if provider.lower() in ['openai', 'openai-compatible']:
        return OpenAICompatibleClient(**kwargs)
    elif provider.lower() == 'gemini':
        return GeminiClient(**kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'openai' or 'gemini'")
