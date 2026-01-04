"""
Phase 2 LLM Client Adapter - Generic HTTP client for local and remote LLMs
Supports Ollama (local) and remote LLM APIs
"""
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Base exception for LLM client errors"""
    pass


class LLMClient:
    """Generic LLM client supporting local (Ollama) and remote endpoints
    
    Args:
        mode: 'local' for Ollama or 'remote' for remote API
        endpoint: Full URL to LLM endpoint
        model: Model name (e.g., 'llama3:8b' or 'gpt-4')
        timeout: Request timeout in seconds
        api_key: API key for remote authentication (optional for local)
    """
    
    def __init__(
        self,
        mode: str,
        endpoint: str,
        model: str,
        timeout: int = 30,
        api_key: Optional[str] = None
    ):
        self.mode = mode
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.api_key = api_key
        
        if mode not in ('local', 'remote'):
            raise LLMClientError(f"Invalid mode: {mode}. Use 'local' or 'remote'")
        
        if mode == 'remote' and not api_key:
            logger.warning("Remote LLM mode without API key - requests may fail")
    
    def send_prompt(self, prompt: str, context: str = '') -> str:
        """Send prompt to LLM and get response
        
        Args:
            prompt: The prompt template/system message
            context: Additional context or data to include
        
        Returns:
            LLM response as string
        
        Raises:
            LLMClientError: If request fails
        """
        
        if self.mode == 'local':
            return self._send_to_ollama(prompt, context)
        else:
            return self._send_to_remote(prompt, context)
    
    def _send_to_ollama(self, prompt: str, context: str) -> str:
        """Send request to local Ollama instance"""
        
        # Prepare full prompt with context
        full_prompt = f"{prompt}\n\nData to analyze:\n{context}"
        
        # Ollama API: POST /api/generate
        url = f"{self.endpoint}/api/generate"
        
        payload = {
            'model': self.model,
            'prompt': full_prompt,
            'stream': False  # Get complete response at once
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get('response', '')
            
        except requests.exceptions.ConnectionError as e:
            raise LLMClientError(f"Failed to connect to Ollama at {self.endpoint}: {e}")
        except requests.exceptions.Timeout:
            raise LLMClientError(f"Ollama request timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as e:
            raise LLMClientError(f"Ollama returned error {response.status_code}: {response.text}")
        except json.JSONDecodeError as e:
            raise LLMClientError(f"Invalid JSON response from Ollama: {e}")
        except Exception as e:
            raise LLMClientError(f"Unexpected error calling Ollama: {e}")
    
    def _send_to_remote(self, prompt: str, context: str) -> str:
        """Send request to remote LLM API
        
        Assumes OpenAI-compatible API format.
        """
        
        full_prompt = f"{prompt}\n\nData to analyze:\n{context}"
        
        # OpenAI-compatible API: POST /chat/completions
        url = f"{self.endpoint}/chat/completions"
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Add Authorization header if API key is configured
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        payload = {
            'model': self.model,
            'messages': [
                {
                    'role': 'system',
                    'content': prompt
                },
                {
                    'role': 'user',
                    'content': f'Please analyze this data:\n\n{context}'
                }
            ],
            'temperature': 0.2,  # Low temperature for deterministic responses
            'max_tokens': 4096
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            # Extract message from OpenAI-style response
            message = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            return message
            
        except requests.exceptions.ConnectionError as e:
            raise LLMClientError(f"Failed to connect to remote LLM at {self.endpoint}: {e}")
        except requests.exceptions.Timeout:
            raise LLMClientError(f"Remote LLM request timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as e:
            raise LLMClientError(f"Remote LLM returned error {response.status_code}: {response.text}")
        except json.JSONDecodeError as e:
            raise LLMClientError(f"Invalid JSON response from remote LLM: {e}")
        except Exception as e:
            raise LLMClientError(f"Unexpected error calling remote LLM: {e}")
