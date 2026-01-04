"""
Tests for LLM client module
"""
import pytest
from unittest.mock import patch, MagicMock
import requests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase2.llm_client import LLMClient, LLMClientError


class TestLLMClientInit:
    """Tests for LLMClient initialization"""
    
    def test_valid_local_mode(self):
        """Should initialize with local mode"""
        client = LLMClient(
            mode='local',
            endpoint='http://localhost:11434',
            model='llama3:8b'
        )
        assert client.mode == 'local'
        assert client.endpoint == 'http://localhost:11434'
    
    def test_valid_remote_mode(self):
        """Should initialize with remote mode"""
        client = LLMClient(
            mode='remote',
            endpoint='https://api.openai.com',
            model='gpt-4',
            api_key='test-key'
        )
        assert client.mode == 'remote'
        assert client.api_key == 'test-key'
    
    def test_invalid_mode_raises_error(self):
        """Should raise error for invalid mode"""
        with pytest.raises(LLMClientError) as exc_info:
            LLMClient(
                mode='invalid',
                endpoint='http://localhost',
                model='test'
            )
        assert 'Invalid mode' in str(exc_info.value)
    
    def test_remote_without_api_key_warns(self, caplog):
        """Should warn when remote mode without API key"""
        import logging
        with caplog.at_level(logging.WARNING):
            client = LLMClient(
                mode='remote',
                endpoint='https://api.example.com',
                model='test'
            )
        assert 'without API key' in caplog.text


class TestOllamaClient:
    """Tests for Ollama (local) LLM client"""
    
    @patch('phase2.llm_client.requests.post')
    def test_successful_ollama_request(self, mock_post):
        """Should successfully call Ollama API"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'response': 'Test response'}
        mock_post.return_value.raise_for_status = MagicMock()
        
        client = LLMClient(
            mode='local',
            endpoint='http://localhost:11434',
            model='llama3:8b'
        )
        
        response = client.send_prompt('Test prompt', 'Test context')
        
        assert response == 'Test response'
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert '/api/generate' in call_args[0][0]
    
    @patch('phase2.llm_client.requests.post')
    def test_ollama_connection_error(self, mock_post):
        """Should raise LLMClientError on connection failure"""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")
        
        client = LLMClient(
            mode='local',
            endpoint='http://localhost:11434',
            model='llama3:8b'
        )
        
        with pytest.raises(LLMClientError) as exc_info:
            client.send_prompt('Test prompt')
        
        assert 'Failed to connect' in str(exc_info.value)
    
    @patch('phase2.llm_client.requests.post')
    def test_ollama_timeout(self, mock_post):
        """Should raise LLMClientError on timeout"""
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
        
        client = LLMClient(
            mode='local',
            endpoint='http://localhost:11434',
            model='llama3:8b',
            timeout=10
        )
        
        with pytest.raises(LLMClientError) as exc_info:
            client.send_prompt('Test prompt')
        
        assert 'timed out' in str(exc_info.value)


class TestRemoteClient:
    """Tests for remote LLM client"""
    
    @patch('phase2.llm_client.requests.post')
    def test_successful_remote_request(self, mock_post):
        """Should successfully call remote API"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {
            'choices': [{'message': {'content': 'Test response'}}]
        }
        
        client = LLMClient(
            mode='remote',
            endpoint='https://api.example.com',
            model='gpt-4',
            api_key='test-key'
        )
        
        response = client.send_prompt('Test prompt', 'Test context')
        
        assert response == 'Test response'
    
    @patch('phase2.llm_client.requests.post')
    def test_remote_includes_auth_header(self, mock_post):
        """Should include Authorization header with API key"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {
            'choices': [{'message': {'content': 'Test'}}]
        }
        
        client = LLMClient(
            mode='remote',
            endpoint='https://api.example.com',
            model='gpt-4',
            api_key='secret-key-123'
        )
        
        client.send_prompt('Test prompt')
        
        call_args = mock_post.call_args
        headers = call_args[1]['headers']
        assert 'Authorization' in headers
        assert headers['Authorization'] == 'Bearer secret-key-123'
    
    @patch('phase2.llm_client.requests.post')
    def test_remote_without_api_key_no_auth_header(self, mock_post):
        """Should not include Authorization header without API key"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {
            'choices': [{'message': {'content': 'Test'}}]
        }
        
        client = LLMClient(
            mode='remote',
            endpoint='https://api.example.com',
            model='gpt-4',
            api_key=None
        )
        
        client.send_prompt('Test prompt')
        
        call_args = mock_post.call_args
        headers = call_args[1]['headers']
        assert 'Authorization' not in headers


class TestLLMClientError:
    """Tests for LLMClientError exception"""
    
    def test_is_exception(self):
        """LLMClientError should be an Exception"""
        assert issubclass(LLMClientError, Exception)
    
    def test_error_message(self):
        """Should preserve error message"""
        error = LLMClientError("Test error message")
        assert str(error) == "Test error message"
